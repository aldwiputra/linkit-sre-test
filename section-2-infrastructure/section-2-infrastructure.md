# Section 2 · System & Infrastructure Troubleshooting

**Candidate:** Aldiansyah Dwi Putra

---

## Scenario
> Website is down (timeout), but the server is still running.

The key constraint — **server is up, website is not** — tells us the problem is above the OS level. The kernel is alive, SSH works, but something in the stack between the network and the application is broken. The steps below isolate each layer systematically.

---

## Step 1 — Check if the Service Process is Running

```bash
# Check systemd service status (shows state + recent logs)
systemctl status nginx
systemctl status your-app.service

# Verify the process actually exists
ps aux | grep -E "nginx|node|python|java|gunicorn" | grep -v grep

# Check process uptime (did it recently restart/crash?)
ps -o pid,etime,cmd -p $(pgrep -f your-app)
```

**Why:** A process can crash and restart (or stay dead) while the server itself stays up. `systemctl status` shows the last exit code, which reveals whether it crashed, was killed (OOM), or stopped intentionally. If the process is missing entirely, this is the root cause — fix it here before continuing.

---

## Step 2 — Check if the Port is Listening

```bash
# List all listening TCP ports
ss -tlnp | grep -E ":80|:443|:3000|:8080"
# or: netstat -tlnp | grep -E ":80|:443"

# Verify the correct process owns the port
lsof -i :80
lsof -i :443

# Test connectivity locally — bypasses all external network/firewall issues
curl -v http://localhost:80
curl -v http://localhost:8080

# Simulate an external request locally using the real domain
curl -v --resolve yourdomain.com:80:127.0.0.1 http://yourdomain.com/
```

**Why:** `ss` tells you if anything is bound to the expected port. If `ss` shows nothing on port 80, the web server/app isn't listening — no amount of firewall tweaking will help. The local `curl` confirms the application layer works independently of DNS and external routing.

---

## Step 3 — Check System Resources

```bash
# CPU and memory overview
top -bn1 | head -25
free -h

# Disk space — a full disk causes silent failures in many services
df -h
df -i   # inode exhaustion: disk shows space but files can't be created

# Check for OOM kills (kernel silently kills processes when RAM is full)
dmesg | grep -i "killed process"
dmesg | grep -i "oom"
journalctl -k | grep -i oom

# Load average — high load causes timeouts even if the process is "running"
uptime
cat /proc/loadavg
```

**Why:** These are silent killers. A full disk stops log writes, pid file creation, and socket binding — all without a clear error message. OOM kills terminate processes instantly with no application-level log. High load averages (e.g., 20+ on a 4-core machine) mean the kernel is scheduling-starved and requests time out before being handled.

---

## Step 4 — Check Logs

```bash
# Web server / reverse proxy logs
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log
journalctl -u nginx --since "15 minutes ago"

# Application logs
tail -f /var/log/your-app/app.log
journalctl -u your-app.service -n 100 --no-pager

# System-level errors
journalctl -p err --since "1 hour ago"
dmesg -T | tail -30
```

**Why:** Logs contain the actual failure reason. Common findings here include: "permission denied" opening a socket, "address already in use" (port conflict), missing config file after a deployment, or SSL certificate expiry errors. Always check logs *before* making changes — they tell you exactly what to fix.

---

## Step 5 — Check Reverse Proxy / Load Balancer

```bash
# Validate nginx config syntax before anything else
nginx -t

# Check if nginx is forwarding to the right upstream
cat /etc/nginx/sites-enabled/your-site.conf
# Look for: proxy_pass http://127.0.0.1:3000;

# Test the upstream directly — bypasses nginx entirely
curl -v http://127.0.0.1:3000/
curl -v http://127.0.0.1:3000/health

# If using HAProxy, check backend state
echo "show stat" | socat stdio /var/run/haproxy/admin.sock \
  | cut -d ',' -f 1,2,18 | grep -v "^#"

# Reload nginx after any config fix (graceful — no downtime)
systemctl reload nginx
```

**Why:** The proxy can be running and healthy while routing to a dead upstream, or a recent config change introduced a syntax error that caused nginx to silently keep the old config. Testing the upstream directly isolates "is this a proxy problem or an app problem?" — two very different fixes.

---

## Step 6 — Check Firewall / Network

```bash
# Check iptables rules — look for DROP rules on port 80/443
iptables -L INPUT -n -v | grep -E "80|443|DROP|REJECT"
iptables -L -n -v --line-numbers

# If using ufw (Ubuntu)
ufw status verbose

# Ensure port 80/443 is allowed
ufw allow 80/tcp
ufw allow 443/tcp

# Test connectivity from a remote machine or another server
curl -v --max-time 10 http://YOUR_SERVER_IP/
telnet YOUR_SERVER_IP 80   # if it hangs/refuses, the port is blocked

# Trace the network path
traceroute YOUR_SERVER_IP
mtr YOUR_SERVER_IP   # real-time traceroute

# DNS — is the domain resolving to the right IP?
nslookup yourdomain.com
dig yourdomain.com A
dig yourdomain.com @8.8.8.8   # check against Google DNS
```

**Why:** A cloud security group change, a new iptables rule from a cron job, or a DNS propagation issue can make the server completely unreachable from the outside while locally everything looks fine. Check this *after* confirming the app works locally — it rules out all the layers above before blaming the network.

---

## Step 7 — Check Database Connectivity

```bash
# Test DB reachability from the app server
pg_isready -h DB_HOST -p 5432 -U appuser
# For MySQL:
mysqladmin -h DB_HOST -u appuser -p ping

# Try an actual query
psql -h DB_HOST -U appuser -d appdb -c "SELECT 1;"

# Check if the port is reachable at all
nc -zv DB_HOST 5432
telnet DB_HOST 5432

# Check connection count vs limit
psql -h DB_HOST -c \
  "SELECT count(*) AS active,
          (SELECT setting::int FROM pg_settings WHERE name='max_connections') AS max
   FROM pg_stat_activity;"

# Check app-side DB config
grep -rE "DATABASE_URL|DB_HOST|db_host|max_connections" /etc/your-app/ ~/.env
```

**Why:** Many "website down" incidents are actually DB connection failures — the app process starts and listens, but every request fails because it can't connect to the database. This step is last because it requires the process to be running (Step 1) and listening (Step 2) first. If the DB is unreachable, check: firewall rules between app and DB servers, DB `max_connections` exhaustion, and whether the DB process itself is running.

---

## Summary Flowchart

```
Website timeout
      │
      ▼
Is the service process running?  ──NO──▶ Start/restart service → check logs
      │ YES
      ▼
Is it listening on the port?  ──NO──▶ Check config, port conflicts
      │ YES
      ▼
Does local curl succeed?  ──NO──▶ App-level error → check app logs
      │ YES
      ▼
Does curl via proxy succeed?  ──NO──▶ Nginx/HAProxy config issue
      │ YES
      ▼
Is the port reachable from outside?  ──NO──▶ Firewall / security group
      │ YES
      ▼
Does DNS resolve correctly?  ──NO──▶ DNS misconfiguration / propagation
      │ YES
      ▼
Can the app connect to the DB?  ──NO──▶ DB down / pool exhausted / firewall
      │ YES
      ▼
Check resources (disk, RAM, CPU load)
```
