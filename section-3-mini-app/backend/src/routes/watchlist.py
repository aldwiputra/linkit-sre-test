"""Watchlist routes - transactional table"""
from flask import Blueprint, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from models.movie import Movie, Watchlist
from utils.response import success, error

watchlist_bp = Blueprint("watchlist", __name__)

VALID_STATUSES = {"want_to_watch", "watching", "watched", "dropped"}


@watchlist_bp.route("/", methods=["GET"])
@jwt_required()
def list_watchlist():
    user_id = int(get_jwt_identity())
    status  = request.args.get("status")
    query   = Watchlist.query.filter_by(user_id=user_id)
    if status:
        query = query.filter_by(status=status)
    items = query.order_by(Watchlist.created_at.desc()).all()
    return success([i.to_dict() for i in items])


@watchlist_bp.route("/", methods=["POST"])
@jwt_required()
def add_to_watchlist():
    user_id = int(get_jwt_identity())
    data    = request.get_json() or {}
    movie_id = data.get("movie_id")
    if not movie_id:
        return error("movie_id is required", 400)

    movie = Movie.query.get(movie_id)
    if not movie:
        return error("Movie not found", 404)

    status = data.get("status", "want_to_watch")
    if status not in VALID_STATUSES:
        return error(f"status must be one of {list(VALID_STATUSES)}", 400)

    rating = data.get("rating")
    if rating is not None:
        try:
            rating = int(rating)
            if not (1 <= rating <= 10):
                raise ValueError
        except (ValueError, TypeError):
            return error("rating must be an integer 1-10", 400)

    existing = Watchlist.query.filter_by(user_id=user_id, movie_id=movie_id).first()
    if existing:
        return error("Movie already in watchlist", 409)

    entry = Watchlist(
        user_id  = user_id,
        movie_id = movie_id,
        status   = status,
        rating   = rating,
        notes    = data.get("notes", ""),
    )
    db.session.add(entry)
    db.session.commit()
    current_app.transaction_logger.info(
        "WATCHLIST_ADD",
        extra={"method": "POST", "endpoint": "/api/watchlist",
               "status": 201, "response_time_ms": 0, "ip": "internal"}
    )
    return success(entry.to_dict(), "Added to watchlist", 201)


@watchlist_bp.route("/<int:entry_id>", methods=["PUT"])
@jwt_required()
def update_watchlist(entry_id):
    user_id = int(get_jwt_identity())
    entry   = Watchlist.query.filter_by(id=entry_id, user_id=user_id).first()
    if not entry:
        return error("Watchlist entry not found", 404)

    data   = request.get_json() or {}
    status = data.get("status")
    if status:
        if status not in VALID_STATUSES:
            return error(f"status must be one of {list(VALID_STATUSES)}", 400)
        entry.status = status

    if "rating" in data:
        r = data["rating"]
        if r is not None:
            try:
                r = int(r)
                if not (1 <= r <= 10):
                    raise ValueError
            except (ValueError, TypeError):
                return error("rating must be an integer 1-10", 400)
        entry.rating = r

    if "notes" in data:
        entry.notes = data["notes"]

    db.session.commit()
    return success(entry.to_dict(), "Watchlist updated")


@watchlist_bp.route("/<int:entry_id>", methods=["DELETE"])
@jwt_required()
def delete_watchlist(entry_id):
    user_id = int(get_jwt_identity())
    entry   = Watchlist.query.filter_by(id=entry_id, user_id=user_id).first()
    if not entry:
        return error("Watchlist entry not found", 404)
    db.session.delete(entry)
    db.session.commit()
    return success(None, "Removed from watchlist")
