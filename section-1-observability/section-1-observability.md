# Section 1 · Observability & Troubleshooting

**Candidate:** Aldiansyah Dwi Putra

---

## Log Analysis

```
[10:01:11] GET /api/orders → JWT OK → Fetching orders user_id=182
[10:01:11] WARN  Slow query detected            execution_time=2400ms
[10:01:13] ERROR DB primary connection timeout  host=10.10.2.14:5432
[10:01:14] ERROR Redis connection refused       host=10.10.2.20:6379
[10:01:14] WARN  Falling back to database query
[10:01:16] ERROR Deadlock detected              transaction_id=TRX991
[10:01:17] INFO  Retry attempt=2
[10:01:19] ERROR Failed fetching orders         reason="Database unavailable"
[10:01:19] INFO  Response status=500            response_time=8199ms
[10:01:20] ALERT High error rate                endpoint=/api/orders threshold=3
[10:01:21] INFO  Kubernetes Pod restart         pod=orders-service-77fd
```

---

## 1. Root Causes

**Root Cause 1 — Database Connection Saturation / Crash**
The `db-primary` at `10.10.2.14:5432` is timing out on connection. Combined with the earlier slow query (2400ms), this suggests the connection pool is exhausted or the Postgres process itself is unhealthy. A runaway query or lock contention likely consumed all available connections.

**Root Cause 2 — Redis Cache Unavailability**
`redis-cache` at `10.10.2.20:6379` is actively refusing connections — not a timeout, but a refused connection, meaning Redis is fully down. Without the cache layer, every request hits the database directly, amplifying load on an already-stressed primary.

**Root Cause 3 — Database Deadlock (TRX991)**
A deadlock was detected on the second retry. Multiple concurrent transactions are competing for the same row locks. This cascades: deadlocks trigger rollbacks → rollbacks increase retry traffic → retries worsen connection pool exhaustion.

**Root Cause 4 — Missing Circuit Breaker**
The service retried a known-failing database twice (retry=1, retry=2), each adding 2–3 seconds of delay. A circuit breaker pattern would have short-circuited after the first failure and returned an early 503, reducing total `response_time` from 8199ms to under 1000ms.

**Root Cause 5 — No Read Replica Fallback**
When the primary DB is unavailable, the service has no fallback for read operations. A read replica or stale cache response would have served the orders list while the primary recovered, instead of returning a hard 500.

---

## 2. Troubleshooting Steps

**Step 1 — Confirm the blast radius**
```bash
# How many endpoints are affected right now?
grep "status=5" /var/log/api-gateway/access.log | awk '{print $NF}' | sort | uniq -c | sort -rn

# Error rate per minute
grep "ERROR" /var/log/orders-service/*.log \
  | awk -F'T' '{print $1"T"substr($2,1,5)}' | uniq -c
```

**Step 2 — Check database primary health**
```bash
pg_isready -h 10.10.2.14 -p 5432 -U appuser

# Check active connections
psql -h 10.10.2.14 -c \
  "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# Check long-running queries
psql -h 10.10.2.14 -c \
  "SELECT pid, now()-query_start AS duration, query, state
   FROM pg_stat_activity
   WHERE now()-query_start > interval '5 seconds'
   ORDER BY duration DESC;"

# Check for active locks
psql -h 10.10.2.14 -c "SELECT * FROM pg_locks WHERE NOT granted;"
```

**Step 3 — Check Redis**
```bash
redis-cli -h 10.10.2.20 -p 6379 ping
redis-cli -h 10.10.2.20 -p 6379 info server | grep -E "uptime|version|used_memory"
systemctl status redis
```

**Step 4 — Check the slow query**
```bash
# Enable slow query logging (queries > 1s)
psql -c "ALTER SYSTEM SET log_min_duration_statement = 1000;"
psql -c "SELECT pg_reload_conf();"

# Inspect existing slow query log
grep "duration:" /var/log/postgresql/postgresql-*.log \
  | sort -t ':' -k2 -rn | head -20

# Check for missing index on the orders query
psql -c "EXPLAIN ANALYZE
  SELECT * FROM orders WHERE user_id = 182 ORDER BY created_at DESC LIMIT 20;"
```

**Step 5 — Check application metrics**
```bash
# If Prometheus is scraping
curl -s http://orders-service:8080/metrics \
  | grep -E "db_pool|http_request_duration|errors_total"

# Pod logs in Kubernetes
kubectl logs orders-service-77fd --previous -n production | tail -100
kubectl describe pod orders-service-77fd -n production
```

---

## 3. Investigating Slow Response & Database Timeout

### Slow Response (8199ms) Breakdown

| Phase | Duration | Source |
|-------|----------|--------|
| JWT + auth validation | ~56ms | Normal |
| Initial slow DB query | ~2400ms | Missing index / table bloat |
| DB connection timeout wait | ~2300ms | Pool exhausted |
| Retry attempt 1 | ~2000ms | No circuit breaker |
| Deadlock + retry 2 | ~1400ms | Lock contention |
| **Total** | **~8199ms** | |

**Investigation:**
```bash
# 1. Run EXPLAIN ANALYZE on the offending query
psql -h 10.10.2.14 -d orders_db -c \
  "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
   SELECT * FROM orders WHERE user_id = 182 ORDER BY created_at DESC;"

# 2. Check if index exists on (user_id, created_at)
psql -h 10.10.2.14 -d orders_db -c "\d orders"

# 3. If missing, create it without locking the table
psql -h 10.10.2.14 -d orders_db -c \
  "CREATE INDEX CONCURRENTLY idx_orders_user_created
   ON orders(user_id, created_at DESC);"

# 4. Check table bloat / autovacuum health
psql -c "SELECT schemaname, tablename, n_dead_tup, last_vacuum, last_autovacuum
         FROM pg_stat_user_tables WHERE tablename = 'orders';"
```

**DB Timeout Investigation:**
```bash
# Check max connections vs current usage
psql -c "SHOW max_connections;"
psql -c "SELECT count(*) FROM pg_stat_activity;"

# Monitor in real time
watch -n 2 "psql -c \"SELECT state, count(*) FROM pg_stat_activity GROUP BY state;\""

# Check connection pool config in app
grep -r "pool_size\|max_overflow\|pool_timeout" /etc/orders-service/config.yaml
```

---

## 4. Alert Rules (Prometheus / AlertManager)

```yaml
groups:
  - name: orders-service-alerts
    rules:

      # High error rate: >5% 5xx over 2 minutes
      - alert: HighErrorRate
        expr: |
          (
            sum(rate(http_requests_total{status=~"5..",endpoint="/api/orders"}[2m]))
            /
            sum(rate(http_requests_total{endpoint="/api/orders"}[2m]))
          ) > 0.05
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "High 5xx error rate on /api/orders"
          description: "Error rate is {{ $value | humanizePercentage }} over the last 2m"

      # Absolute error count >3 in 60s (matches the test scenario)
      - alert: ErrorRateAbsolute
        expr: increase(http_requests_total{status=~"5..",endpoint="/api/orders"}[60s]) > 3
        for: 0m
        labels:
          severity: warning
        annotations:
          summary: "More than 3 errors on /api/orders in the last 60s"

      # Slow response: p95 latency > 2s
      - alert: SlowResponse
        expr: |
          histogram_quantile(0.95,
            sum(rate(http_request_duration_seconds_bucket{endpoint="/api/orders"}[5m])) by (le)
          ) > 2
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Slow p95 response on /api/orders"
          description: "p95 latency is {{ $value }}s"

      # Database unreachable
      - alert: DatabaseConnectionFailure
        expr: pg_up{instance="10.10.2.14:9187"} == 0
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "PostgreSQL primary is unreachable"
          description: "DB at 10.10.2.14:5432 has been down for > 30s"

      # Connection pool saturation
      - alert: DBConnectionPoolSaturation
        expr: |
          (pg_stat_activity_count / pg_settings_max_connections) > 0.8
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "DB connection pool > 80% utilized"
```

---

## 5. Suggested Improvements

### Reliability
- **Circuit Breaker** — After 3 consecutive DB failures, open the circuit and return a cached/degraded response immediately instead of queuing retries. Libraries: Resilience4j (Java), `opossum` (Node.js), `pybreaker` (Python).
- **Read Replica** — Route all `SELECT` queries to a read replica. Primary only handles writes. This also isolates read traffic from write-lock contention.
- **Connection Pooling (PgBouncer)** — Deploy PgBouncer in front of PostgreSQL (`pool_mode = transaction`). Allows thousands of app connections over a small pool of actual DB connections.
- **Redis High Availability** — Deploy Redis Sentinel or Redis Cluster. A single-node Redis is a SPOF as demonstrated in this incident.
- **Retry with Exponential Backoff + Jitter** — Current retry is near-immediate. Apply backoff: 100ms → 400ms → 1600ms with ±20% jitter to avoid thundering herd on recovery.
- **Graceful Degradation** — Serve stale cached data if available rather than a hard 500. Users see slightly old orders rather than an error page.

### Observability
- **Distributed Tracing (OpenTelemetry + Jaeger)** — Propagate the `RequestID` as a trace ID through every downstream call. Currently it's only logged at the gateway.
- **Structured JSON Logs** — Every log line should include: `trace_id`, `span_id`, `user_id`, `service`, `level`, `message`. Makes log querying in Loki/Elasticsearch far more efficient.
- **Custom Metrics** — Expose `db_query_duration_seconds`, `cache_hit_ratio`, `retry_count_total`, `deadlock_total` as Prometheus counters/histograms.
- **Error Budget Tracking** — Define SLOs (e.g. 99.9% availability, p99 < 500ms) and track burn rate in Grafana.

### Scalability
- **Horizontal Pod Autoscaling (HPA)** — Scale `orders-service` pods based on CPU usage or custom metrics (requests/sec).
- **Table Partitioning** — Partition the `orders` table by `user_id` range or `created_at` month. Dramatically reduces per-query scan size as the table grows.
- **Async Processing** — Move non-critical DB writes (audit logs, notifications, analytics events) to a message queue (Kafka / RabbitMQ) instead of synchronous writes that block the request.
- **API Gateway Caching** — Cache order list responses at the gateway level with a short TTL (e.g. 5s) to absorb traffic bursts without hitting the DB at all.

### Security
- **mTLS Between Services** — Encrypt and mutually authenticate all internal service-to-service traffic. Prevents lateral movement if one service is compromised.
- **Secrets via Vault** — Never hardcode DB credentials or JWT secrets. Use HashiCorp Vault or Kubernetes Secrets with automatic rotation.
- **Per-User Rate Limiting** — Apply rate limits keyed by `user_id` at the API gateway to prevent one user from exhausting the DB connection pool.
- **Short-lived JWT + Refresh Tokens** — Access tokens should expire in 15–60 minutes. Implement refresh token rotation with revocation support.
- **Principle of Least Privilege** — The `orders-service` DB user should only have `SELECT, INSERT, UPDATE` on the `orders` table — no `DROP`, `TRUNCATE`, or cross-schema access.

---

## 6. Monitoring Tools in Production

| Layer | Tool | Purpose |
|-------|------|---------|
| **Metrics** | Prometheus + Grafana | Time-series metrics, dashboards, alert rules |
| **Tracing** | OpenTelemetry + Jaeger | Distributed request tracing across services |
| **Logging** | Promtail + Loki + Grafana | Log aggregation, search, correlation with metrics |
| **APM** | Datadog / New Relic | End-to-end performance, real-user monitoring |
| **Uptime** | Blackbox Exporter / Pingdom | External synthetic probes, SLA tracking |
| **Database** | pg_stat_statements + PMM | PostgreSQL slow query analysis |
| **Alerting** | AlertManager + PagerDuty | Alert routing, deduplication, on-call escalation |
| **Kubernetes** | Lens / K9s | Cluster visibility, live pod debugging |

**Recommended stack for this incident:**
Prometheus → AlertManager → Grafana for metrics/alerting, OpenTelemetry → Jaeger for tracing, Promtail → Loki → Grafana for logs — unified in a single Grafana instance with correlated dashboards.
