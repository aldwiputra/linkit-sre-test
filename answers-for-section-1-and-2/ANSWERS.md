# PT LINKIT — SRE Technical Test
**Candidate:** Aldiansyah Dwi Putra  
**Position:** Fullstack Sys Admin / Site Reliability Engineer  
**Date:** May 2026

---

## Section 1 · Observability & Troubleshooting

### Log Analysis

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

### 1.1 Root Causes (minimum 3)

**Root Cause 1 — Database Connection Saturation / Crash**
The `db-primary` at `10.10.2.14:5432` is timing out on connection. Combined with the earlier slow query (2400ms), this suggests the connection pool is exhausted or the Postgres process itself is unhealthy. A runaway query or lock contention likely consumed all available connections.

**Root Cause 2 — Redis Cache Unavailability**
`redis-cache` at `10.10.2.20:6379` is actively refusing connections (not a timeout — a refused connection means Redis is down, not slow). Without cache, every request hits the database directly, amplifying the load on an already-stressed primary.

**Root Cause 3 — Database Deadlock (TRX991)**
A deadlock was detected on the second retry. This indicates multiple concurrent transactions competing for the same row locks, which can cascade: deadlocks trigger rollbacks, rollbacks increase retry traffic, retries worsen connection pool exhaustion.

**Root Cause 4 — Missing Circuit Breaker**
The service retried a known-failing database twice (retry=1, retry=2), each time adding 2–3 seconds. A circuit breaker pattern would have short-circuited the second attempt and returned an early 503, reducing `response_time` from 8199ms to under 1000ms.

**Root Cause 5 — No Read Replica Fallback**
When the primary DB is unavailable, the service has nowhere to fall back for read operations. A read replica (or at minimum a cached response) would have served the orders list while the primary recovered.

---

### 1.2 Troubleshooting Steps

**Step 1 — Confirm the blast radius**
```bash
# How many endpoints are failing right now?
grep "status=5" /var/log/api-gateway/access.log | awk '{print $NF}' | sort | uniq -c | sort -rn

# Error rate per minute
grep "ERROR" /var/log/orders-service/*.log | awk -F'T' '{print $1"T"substr($2,1,5)}' | uniq -c
```

**Step 2 — Check database primary health**
```bash
# From the app server:
pg_isready -h 10.10.2.14 -p 5432 -U appuser

# If reachable, check connections:
psql -h 10.10.2.14 -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# Check for long-running queries:
psql -h 10.10.2.14 -c "SELECT pid, now()-query_start AS duration, query, state 
FROM pg_stat_activity WHERE now()-query_start > interval '5 seconds' ORDER BY duration DESC;"

# Check for locks:
psql -h 10.10.2.14 -c "SELECT * FROM pg_locks WHERE NOT granted;"
```

**Step 3 — Check Redis**
```bash
redis-cli -h 10.10.2.20 -p 6379 ping
redis-cli -h 10.10.2.20 -p 6379 info server | grep -E "uptime|version|used_memory"
systemctl status redis  # on the Redis host
```

**Step 4 — Check the slow query**
```bash
# Enable slow query log in postgres (if not enabled):
psql -c "ALTER SYSTEM SET log_min_duration_statement = 1000;"  # log queries > 1s
psql -c "SELECT pg_reload_conf();"

# Check existing slow query log:
grep "duration:" /var/log/postgresql/postgresql-*.log | sort -t ':' -k2 -rn | head -20

# Check for missing indexes on orders table:
psql -c "EXPLAIN ANALYZE SELECT * FROM orders WHERE user_id = 182 ORDER BY created_at DESC LIMIT 20;"
```

**Step 5 — Check application metrics**
```bash
# If Prometheus is scraping:
curl -s http://orders-service:8080/metrics | grep -E "db_pool|http_request_duration|errors_total"

# Pod logs in Kubernetes:
kubectl logs orders-service-77fd --previous -n production | tail -100
kubectl describe pod orders-service-77fd -n production
```

---

### 1.3 Investigating Slow Response & DB Timeout

**Slow Response Investigation**

The 8199ms total response time breaks down as:
- ~56ms: JWT + auth validation (normal)
- ~2400ms: Initial slow DB query
- ~2300ms: DB connection timeout (wait)
- ~2000ms: Retry attempt 1
- ~1400ms: Deadlock + retry 2
- Total: ~8199ms

Action plan:
```bash
# 1. Run EXPLAIN ANALYZE on the offending query
psql -h 10.10.2.14 -d orders_db -c \
  "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) 
   SELECT * FROM orders WHERE user_id = 182 ORDER BY created_at DESC;"

# 2. Check if index exists
psql -h 10.10.2.14 -d orders_db -c \
  "\d orders" 
# Look for index on user_id + created_at

# 3. If missing, add composite index:
psql -h 10.10.2.14 -d orders_db -c \
  "CREATE INDEX CONCURRENTLY idx_orders_user_created ON orders(user_id, created_at DESC);"

# 4. Check table bloat (vacuuming)
psql -c "SELECT schemaname, tablename, n_dead_tup, last_vacuum, last_autovacuum 
         FROM pg_stat_user_tables WHERE tablename = 'orders';"
```

**DB Timeout Investigation**
```bash
# Check max_connections vs current usage
psql -c "SHOW max_connections;"
psql -c "SELECT count(*) FROM pg_stat_activity;"

# Check connection pool settings in app config
grep -r "pool" /etc/orders-service/config.yaml

# Monitor pg_stat_activity in real time
watch -n 2 "psql -c \"SELECT state, count(*) FROM pg_stat_activity GROUP BY state;\""
```

---

### 1.4 Alert Rules (Prometheus / AlertManager format)

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

      # Absolute error count > 3 in 60s (matches the test scenario)
      - alert: ErrorRateAbsolute
        expr: increase(http_requests_total{status=~"5..",endpoint="/api/orders"}[60s]) > 3
        for: 0m
        labels:
          severity: warning
        annotations:
          summary: "More than 3 errors on /api/orders in last 60s"

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
          summary: "Slow p95 response on /api/orders ({{ $value }}s)"

      # Database connection failure
      - alert: DatabaseConnectionFailure
        expr: pg_up{instance="10.10.2.14:9187"} == 0
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "PostgreSQL primary is unreachable"
          description: "DB at 10.10.2.14:5432 has been down for > 30s"

      # Database connection pool saturation
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

### 1.5 Improvement Suggestions

#### Reliability
- **Circuit Breaker** (Resilience4j / Hystrix pattern): After 3 consecutive failures to the DB, open the circuit and return a cached/degraded response immediately instead of queuing retries.
- **Read Replica**: Route `SELECT` queries to a read replica. Primary only handles writes.
- **Connection Pooling**: Deploy PgBouncer in front of PostgreSQL. Set `pool_mode = transaction` to allow thousands of app connections over a small pool of actual DB connections.
- **Redis High Availability**: Deploy Redis Sentinel or Redis Cluster. Single-node Redis is a SPOF.
- **Retry with Exponential Backoff + Jitter**: Current retry is immediate (retry=1 at +0ms, retry=2 at +1s). Add backoff: 100ms, 400ms, 1600ms with ±20% jitter.
- **Graceful Degradation**: For the orders endpoint, serve stale cached data if available rather than a hard 500.

#### Observability
- **Distributed Tracing** (Jaeger / OpenTelemetry): Instrument every service with trace IDs. The `RequestID=8fd12a1` is a good start — propagate it through all downstream calls.
- **Structured Logging**: Use JSON logs (already partially implemented). Every log line should have `trace_id`, `span_id`, `user_id`, `service`, `level`, `message`.
- **Custom Metrics**: Expose `db_query_duration_seconds`, `cache_hit_ratio`, `retry_count_total` as Prometheus metrics.
- **Error Budget Tracking**: Define SLOs (e.g., 99.9% availability, p99 < 500ms). Track error budget burn rate.

#### Scalability
- **Horizontal Pod Autoscaling (HPA)**: Scale `orders-service` based on CPU or custom metrics (requests/sec).
- **Database Sharding / Partitioning**: Partition the `orders` table by `user_id` range or `created_at` month to reduce per-query scan time.
- **Async Processing**: For non-critical operations (notifications, audit logs), use a message queue (RabbitMQ / Kafka) instead of synchronous DB writes.
- **CDN / Edge Caching**: Cache order list responses at the API gateway level for a short TTL (e.g., 5s) to handle traffic bursts.

#### Security
- **mTLS between services**: Encrypt and authenticate all internal service-to-service communication.
- **DB credentials via Vault**: Never hardcode DB credentials. Use HashiCorp Vault or Kubernetes Secrets with rotation.
- **Rate Limiting**: Apply per-`user_id` rate limiting at the API gateway to prevent one user from exhausting the DB.
- **JWT Expiry**: Ensure JWT tokens have short expiry (15–60 min) and implement refresh token rotation.
- **Principle of Least Privilege**: The `orders-service` DB user should only have `SELECT, INSERT, UPDATE` on the `orders` table, not `DROP` or `TRUNCATE`.

---

### 1.6 Monitoring Tools in Production

| Layer | Tool | Purpose |
|-------|------|---------|
| **Metrics** | Prometheus + Grafana | Time-series metrics, dashboards, alert rules |
| **Tracing** | Jaeger / Tempo | Distributed request tracing across services |
| **Logging** | Loki + Grafana (or ELK stack) | Log aggregation, search, and correlation |
| **APM** | Datadog / New Relic | End-to-end application performance, real-user monitoring |
| **Uptime** | Blackbox Exporter / Pingdom | External synthetic monitoring, SLA enforcement |
| **DB** | pg_stat_statements + PMM | PostgreSQL query analysis, slow query identification |
| **Alerting** | AlertManager / PagerDuty | Alert routing, escalation, on-call integration |
| **K8s** | Lens / K9s / Pixie | Cluster visibility, live debugging |

The ideal stack for this scenario: **Prometheus → AlertManager → Grafana** for metrics/alerting, **OpenTelemetry → Jaeger** for tracing, **Promtail → Loki → Grafana** for logs — all in one Grafana dashboard.

---

## Section 2 · System & Infrastructure

### Website is down (timeout), server is running

#### Step 1 — Check if the service process is running
```bash
# Check systemd service status
systemctl status nginx          # or apache2, or your app service
systemctl status your-app.service

# Check if the process is actually running
ps aux | grep -E "nginx|node|python|java" | grep -v grep

# Check process uptime
ps -o pid,etime,cmd -p $(pgrep nginx)
```
**Why:** A process can crash while the server stays up (kernel still runs). `systemctl status` shows recent logs and exit codes.

---

#### Step 2 — Check if the port is listening
```bash
# Check what's listening on expected ports
ss -tlnp | grep -E ":80|:443|:3000|:8080"
# or: netstat -tlnp | grep -E ":80|:443"

# Try connecting locally (bypass firewall/network entirely)
curl -v http://localhost:80
curl -v --resolve yourdomain.com:80:127.0.0.1 http://yourdomain.com/

# Check if port 80 is bound at all
lsof -i :80
```
**Why:** If `ss` shows nothing on port 80, the service isn't listening. Local `curl` confirms the app works before blaming the network.

---

#### Step 3 — Check system resources
```bash
# CPU and memory overview
top -bn1 | head -20
free -h
vmstat 1 5

# Disk space (full disk = service failures)
df -h
df -i   # inode exhaustion is a common gotcha

# Check for OOM kills
dmesg | grep -i "killed process"
journalctl -k | grep -i oom

# Load average (high load = slow responses that look like timeouts)
uptime
cat /proc/loadavg
```
**Why:** A full disk stops log writes (and sometimes crashes services). OOM kills silently kill processes. High load causes timeouts even if the service is "running."

---

#### Step 4 — Check logs
```bash
# Application logs
journalctl -u nginx --since "10 minutes ago" | tail -50
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log

# App-specific logs
tail -f /var/log/your-app/app.log
journalctl -u your-app.service -n 100 --no-pager

# System logs
journalctl -p err --since "1 hour ago"
dmesg -T | tail -30
```
**Why:** Logs reveal the actual failure reason — misconfiguration, permission errors, missing files, crashed dependencies.

---

#### Step 5 — Check reverse proxy / load balancer
```bash
# Test nginx config validity
nginx -t

# Check nginx upstream status
curl -s http://localhost/nginx_status   # if stub_status enabled

# Reload nginx if config changed
systemctl reload nginx

# Check HAProxy (if used)
echo "show info" | socat stdio /var/run/haproxy/admin.sock
echo "show stat" | socat stdio /var/run/haproxy/admin.sock | cut -d ',' -f 1,2,18

# Test upstream directly (bypass proxy)
curl -v http://127.0.0.1:3000/health
```
**Why:** The proxy might be running but routing to a dead upstream, or the config may have been reloaded with syntax errors. Test upstream directly to isolate proxy vs application.

---

#### Step 6 — Check firewall / network
```bash
# Check iptables rules
iptables -L -n -v | grep -E "80|443"
ufw status verbose   # if using ufw

# Check from outside (if you have another server)
curl -v --max-time 10 http://YOUR_SERVER_IP/
telnet YOUR_SERVER_IP 80

# Check if the cloud security group is blocking traffic
# (AWS: check EC2 security groups; GCP: check VPC firewall rules)

# Check routing
ip route show
traceroute YOUR_SERVER_IP

# Check DNS resolution
nslookup yourdomain.com
dig yourdomain.com A
```
**Why:** A recently-changed firewall rule, security group, or DNS misconfiguration can make the server "invisible" from the outside while everything locally looks fine.

---

#### Step 7 — Check database connectivity
```bash
# Test DB connection from app server
pg_isready -h DB_HOST -p 5432 -U appuser
# or for MySQL:
mysqladmin -h DB_HOST -u appuser -p ping

# Check if the app can connect
psql -h DB_HOST -U appuser -d appdb -c "SELECT 1;"

# Check DB port from app server
telnet DB_HOST 5432
nc -zv DB_HOST 5432

# Check connection limits
psql -c "SELECT count(*), max_conn FROM pg_stat_activity, 
         (SELECT setting::int AS max_conn FROM pg_settings WHERE name='max_connections') s 
         GROUP BY max_conn;"

# App-side: check connection pool config
grep -r "DATABASE_URL\|db_host\|max_connections" /etc/your-app/
```
**Why:** Many "website down" cases are actually DB connection failures — the app starts, but every request fails because it can't reach the database.

---

## Section 3 · Mini App Development

See the `/backend` and `/frontend` directories. Summary:

### Architecture
```
┌─────────────────────┐         ┌──────────────────────┐
│   Frontend (HTML)   │ ──────▶ │   Flask REST API      │
│   CineVault Dashboard│         │   Port 5000           │
└─────────────────────┘         └──────────┬───────────┘
                                           │
                              ┌────────────▼───────────┐
                              │    SQLite Database      │
                              │  ┌─────────────────┐   │
                              │  │ movies (master) │   │
                              │  ├─────────────────┤   │
                              │  │ watchlist (txn) │   │
                              │  ├─────────────────┤   │
                              │  │ users (master)  │   │
                              │  └─────────────────┘   │
                              └────────────────────────┘
                                           │
                              ┌────────────▼───────────┐
                              │  SampleAPIs (external)  │
                              │  /movies/drama          │
                              └────────────────────────┘
```

### Database Schema
```sql
-- Master table 1: users
CREATE TABLE users (
    id         INTEGER PRIMARY KEY,
    username   VARCHAR(80) UNIQUE NOT NULL,
    email      VARCHAR(120) UNIQUE NOT NULL,
    password   VARCHAR(200) NOT NULL,   -- bcrypt hash
    is_active  BOOLEAN DEFAULT TRUE,
    created_at DATETIME
);

-- Master table 2: movies (from SampleAPIs)
CREATE TABLE movies (
    id          INTEGER PRIMARY KEY,
    external_id INTEGER UNIQUE,   -- SampleAPIs ID
    title       VARCHAR(255) NOT NULL,
    year        VARCHAR(10),
    genre       VARCHAR(100),
    director    VARCHAR(150),
    actors      TEXT,
    plot        TEXT,
    imdb_rating VARCHAR(10),
    poster_url  TEXT,
    source      VARCHAR(30),      -- 'sampleapis' | 'manual'
    created_at  DATETIME,
    updated_at  DATETIME
);

-- Transactional table: watchlist
CREATE TABLE watchlist (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id),
    movie_id   INTEGER REFERENCES movies(id),
    status     VARCHAR(20),   -- want_to_watch | watching | watched | dropped
    rating     INTEGER,       -- 1-10 user personal rating
    notes      TEXT,
    created_at DATETIME,
    updated_at DATETIME
);
```

### API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/auth/register` | ✗ | Register user |
| POST | `/api/auth/login` | ✗ | Login, get JWT |
| GET | `/api/auth/me` | ✓ | Current user info |
| GET | `/api/movies/` | ✓ | List movies (paginated, searchable) |
| GET | `/api/movies/:id` | ✓ | Get single movie |
| POST | `/api/movies/` | ✓ | Create movie |
| PUT | `/api/movies/:id` | ✓ | Update movie |
| DELETE | `/api/movies/:id` | ✓ | Delete movie |
| POST | `/api/movies/sync` | ✓ | Sync from SampleAPIs |
| GET | `/api/watchlist/` | ✓ | List my watchlist |
| POST | `/api/watchlist/` | ✓ | Add to watchlist |
| PUT | `/api/watchlist/:id` | ✓ | Update entry |
| DELETE | `/api/watchlist/:id` | ✓ | Remove entry |
| GET | `/api/health` | ✗ | Health check |
| GET | `/api/metrics` | ✗ | Prometheus metrics |
| GET | `/api/alerts` | ✗ | Recent alert simulation |

### Logging
Three separate log files under `src/logs/`:
- `app.log` — application events (startups, user actions)
- `transactions.log` — every HTTP request: method, endpoint, status, response_time_ms
- `errors.log` — 5xx errors
- `alerts.log` — fired alerts (high error rate, slow response)

### Monitoring & Reliability
- `/api/health` — DB connectivity check, uptime, version
- `/api/metrics` — Prometheus-format text metrics
- `/api/alerts` — Alert simulation endpoint
- `AlertSimulator` — in-memory sliding window: fires alert when endpoint has >3 errors in 60s, or response_time > 2000ms

---

## Setup Instructions

### Option A: Docker (recommended)
```bash
# Clone / unzip project
cd linkit-sre-test

# Build and start
docker-compose up --build

# Access:
#   Frontend: http://localhost:3000
#   Backend:  http://localhost:5000/api/health
```

### Option B: Local Development
```bash
# Backend
cd backend
pip install -r requirements.txt
cd src
python server.py

# Frontend (in a second terminal)
cd frontend
python -m http.server 3000
# or: npx serve .

# Default credentials:
#   admin / admin123
#   demo  / demo123
```

### Quick API test
```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

# Sync movies from SampleAPIs
curl -X POST http://localhost:5000/api/movies/sync \
  -H "Authorization: Bearer $TOKEN"

# List movies
curl http://localhost:5000/api/movies/ \
  -H "Authorization: Bearer $TOKEN"

# Health check
curl http://localhost:5000/api/health
```

---

*Submitted by: Aldiansyah Dwi Putra*
