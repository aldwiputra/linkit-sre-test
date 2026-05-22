"""
Simulates monitoring alerts:
  - error rate > 3 in rolling window
  - slow response > 2000ms
"""
import time
import logging
from collections import defaultdict, deque

alert_logger = logging.getLogger("alerts")
if not alert_logger.handlers:
    import os
    LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
    os.makedirs(LOG_DIR, exist_ok=True)
    fh = logging.FileHandler(os.path.join(LOG_DIR, "alerts.log"))
    fh.setFormatter(logging.Formatter("[%(asctime)s] [ALERT] %(message)s"))
    alert_logger.addHandler(fh)
    ch = logging.StreamHandler()
    alert_logger.addHandler(ch)
    alert_logger.setLevel(logging.WARNING)


class AlertSimulator:
    WINDOW_SECONDS = 60
    ERROR_THRESHOLD = 3
    SLOW_THRESHOLD_MS = 2000

    def __init__(self):
        self._errors: dict[str, deque] = defaultdict(deque)
        self._alerts: list[dict] = []

    def record_error(self, endpoint: str):
        now = time.time()
        q = self._errors[endpoint]
        q.append(now)
        # purge old
        while q and now - q[0] > self.WINDOW_SECONDS:
            q.popleft()
        count = len(q)
        if count >= self.ERROR_THRESHOLD:
            msg = (f"HIGH ERROR RATE endpoint={endpoint} "
                   f"errors={count} window={self.WINDOW_SECONDS}s threshold={self.ERROR_THRESHOLD}")
            alert_logger.warning(msg)
            self._alerts.append({"type": "high_error_rate", "endpoint": endpoint,
                                  "count": count, "ts": now})

    def record_slow_response(self, endpoint: str, ms: float):
        msg = (f"SLOW RESPONSE endpoint={endpoint} "
               f"response_time_ms={ms} threshold={self.SLOW_THRESHOLD_MS}ms")
        alert_logger.warning(msg)
        self._alerts.append({"type": "slow_response", "endpoint": endpoint,
                              "response_time_ms": ms, "ts": time.time()})

    def get_recent_alerts(self, limit=20):
        return self._alerts[-limit:]
