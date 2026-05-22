# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# App source
COPY src/ ./src/

# Create log directory
RUN mkdir -p /app/src/logs

# Non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8383

ENV PYTHONUNBUFFERED=1 \
    JWT_SECRET_KEY=change-me-in-production-at-least-32-chars \
    FLASK_ENV=production

CMD ["python", "src/server.py"]
