"""
SRE Technical Test - PT LINKIT
Backend API: Movies from SampleAPIs
Author: Aldiansyah Dwi Putra
"""

import os
import time
import logging
from flask import Flask, jsonify, g
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from datetime import timedelta

from utils.logger import setup_logger, get_transaction_logger, get_error_logger
from utils.alert_simulator import AlertSimulator

# ── App Init ──────────────────────────────────────────────────────────────────
db = SQLAlchemy()
jwt = JWTManager()

def create_app():
    app = Flask(__name__)

    # Config
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///linkit_movies.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "linkit-super-secret-sre-technical-test-2026")
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=2)
    app.config["SECRET_KEY"] = "linkit-flask-secret"

    # Extensions
    db.init_app(app)
    jwt.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

    # Loggers
    app.logger = setup_logger("app")
    app.transaction_logger = get_transaction_logger()
    app.error_logger = get_error_logger()
    app.alert_sim = AlertSimulator()

    # Request logging middleware
    @app.before_request
    def before_request():
        g.start_time = time.time()

    @app.after_request
    def after_request(response):
        from flask import request
        duration_ms = round((time.time() - g.start_time) * 1000, 2)
        status = response.status_code
        log_entry = {
            "method": request.method,
            "endpoint": request.path,
            "status": status,
            "response_time_ms": duration_ms,
            "ip": request.remote_addr,
        }
        app.transaction_logger.info("REQUEST", extra=log_entry)
        if status >= 500:
            app.error_logger.error("SERVER_ERROR", extra=log_entry)
            app.alert_sim.record_error(request.path)
        if duration_ms > 2000:
            app.alert_sim.record_slow_response(request.path, duration_ms)
        return response

    # Register blueprints
    from routes.auth import auth_bp
    from routes.movies import movies_bp
    from routes.watchlist import watchlist_bp
    from routes.health import health_bp

    app.register_blueprint(auth_bp,      url_prefix="/api/auth")
    app.register_blueprint(movies_bp,    url_prefix="/api/movies")
    app.register_blueprint(watchlist_bp, url_prefix="/api/watchlist")
    app.register_blueprint(health_bp,    url_prefix="/api")

    # Create tables & seed
    with app.app_context():
        db.create_all()
        _seed_default_user(app)

    return app


def _seed_default_user(app):
    from models.user import User
    with app.app_context():
        if not User.query.filter_by(username="admin").first():
            admin = User(username="admin", email="admin@linkit.co.id")
            admin.set_password("admin123")
            db.session.add(admin)
            demo = User(username="demo", email="demo@linkit.co.id")
            demo.set_password("demo123")
            db.session.add(demo)
            db.session.commit()
            app.logger.info("Default users seeded: admin / demo")
