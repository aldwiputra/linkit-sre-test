"""Structured logging: app / transaction / error"""
import logging
import os
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)


class StructuredFormatter(logging.Formatter):
    def format(self, record):
        ts = datetime.utcnow().isoformat() + "Z"
        level = record.levelname
        msg   = record.getMessage()
        extra_parts = []
        for k, v in record.__dict__.items():
            if k in ("method", "endpoint", "status", "response_time_ms", "ip"):
                extra_parts.append(f"{k}={v}")
        extra = " ".join(extra_parts)
        return f"[{ts}] [{level}] [{record.name}] {msg} {extra}".strip()


def _make_logger(name: str, filename: str, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        # File handler
        fh = logging.FileHandler(os.path.join(LOG_DIR, filename))
        fh.setFormatter(StructuredFormatter())
        logger.addHandler(fh)
        # Console handler
        ch = logging.StreamHandler()
        ch.setFormatter(StructuredFormatter())
        logger.addHandler(ch)
    return logger


def setup_logger(name: str) -> logging.Logger:
    return _make_logger(name, "app.log")

def get_transaction_logger() -> logging.Logger:
    return _make_logger("transaction", "transactions.log")

def get_error_logger() -> logging.Logger:
    return _make_logger("error", "errors.log", logging.ERROR)
