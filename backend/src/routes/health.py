"""Health & monitoring endpoints"""
import time
from flask import Blueprint, current_app, jsonify
from app import db

health_bp = Blueprint("health", __name__)

START_TIME = time.time()


@health_bp.route("/health", methods=["GET"])
def health():
    """Kubernetes/load balancer health probe."""
    db_ok = True
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception:
        db_ok = False

    status  = "healthy" if db_ok else "degraded"
    code    = 200 if db_ok else 503
    uptime  = round(time.time() - START_TIME, 2)

    return jsonify({
        "status":    status,
        "uptime_s":  uptime,
        "checks": {
            "database": "ok" if db_ok else "error",
        },
        "version": "1.0.0",
    }), code


@health_bp.route("/metrics", methods=["GET"])
def metrics():
    """Lightweight metrics endpoint (Prometheus-style text)."""
    from models.movie import Movie, Watchlist
    from models.user import User

    movie_count     = Movie.query.count()
    watchlist_count = Watchlist.query.count()
    user_count      = User.query.count()
    uptime          = round(time.time() - START_TIME, 2)
    alerts          = current_app.alert_sim.get_recent_alerts()

    lines = [
        f"# HELP app_uptime_seconds Time since process start",
        f"app_uptime_seconds {uptime}",
        f"# HELP movies_total Total movies in DB",
        f"movies_total {movie_count}",
        f"# HELP users_total Total registered users",
        f"users_total {user_count}",
        f"# HELP watchlist_total Total watchlist entries",
        f"watchlist_total {watchlist_count}",
        f"# HELP recent_alerts_total Recent alert count",
        f"recent_alerts_total {len(alerts)}",
    ]
    return "\n".join(lines), 200, {"Content-Type": "text/plain; charset=utf-8"}


@health_bp.route("/alerts", methods=["GET"])
def recent_alerts():
    alerts = current_app.alert_sim.get_recent_alerts()
    return jsonify({"alerts": alerts, "count": len(alerts)})
