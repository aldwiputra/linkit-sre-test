"""Movies routes - CRUD + sync from SampleAPIs"""
from flask import Blueprint, request, current_app
from flask_jwt_extended import jwt_required
import requests as http
from app import db
from models.movie import Movie
from utils.response import success, error

movies_bp = Blueprint("movies", __name__)

SAMPLE_API_URL = "https://api.sampleapis.com/movies/drama"


# ── GET /api/movies ──────────────────────────────────────────────────────────
@movies_bp.route("/", methods=["GET"])
@jwt_required()
def list_movies():
    page     = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search   = request.args.get("search", "").strip()

    query = Movie.query
    if search:
        query = query.filter(Movie.title.ilike(f"%{search}%"))

    pagination = query.order_by(Movie.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return success(
        [m.to_dict() for m in pagination.items],
        total=pagination.total,
        page=pagination.page,
        pages=pagination.pages,
        per_page=per_page,
    )


# ── GET /api/movies/:id ───────────────────────────────────────────────────────
@movies_bp.route("/<int:movie_id>", methods=["GET"])
@jwt_required()
def get_movie(movie_id):
    movie = Movie.query.get(movie_id)
    if not movie:
        return error("Movie not found", 404)
    return success(movie.to_dict())


# ── POST /api/movies ──────────────────────────────────────────────────────────
@movies_bp.route("/", methods=["POST"])
@jwt_required()
def create_movie():
    data  = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return error("title is required", 400)

    movie = Movie(
        title      = title,
        year       = data.get("year"),
        rated      = data.get("rated"),
        runtime    = data.get("runtime"),
        genre      = data.get("genre"),
        director   = data.get("director"),
        actors     = data.get("actors"),
        plot       = data.get("plot"),
        imdb_rating= data.get("imdb_rating"),
        poster_url = data.get("poster_url"),
        source     = "manual",
    )
    db.session.add(movie)
    db.session.commit()
    current_app.logger.info(f"Movie created: {title}")
    return success(movie.to_dict(), "Movie created", 201)


# ── PUT /api/movies/:id ───────────────────────────────────────────────────────
@movies_bp.route("/<int:movie_id>", methods=["PUT"])
@jwt_required()
def update_movie(movie_id):
    movie = Movie.query.get(movie_id)
    if not movie:
        return error("Movie not found", 404)

    data = request.get_json() or {}
    fields = ["title", "year", "rated", "runtime", "genre", "director",
              "actors", "plot", "imdb_rating", "poster_url"]
    for f in fields:
        if f in data:
            setattr(movie, f, data[f])

    db.session.commit()
    current_app.logger.info(f"Movie updated: id={movie_id}")
    return success(movie.to_dict(), "Movie updated")


# ── DELETE /api/movies/:id ────────────────────────────────────────────────────
@movies_bp.route("/<int:movie_id>", methods=["DELETE"])
@jwt_required()
def delete_movie(movie_id):
    movie = Movie.query.get(movie_id)
    if not movie:
        return error("Movie not found", 404)
    db.session.delete(movie)
    db.session.commit()
    current_app.logger.info(f"Movie deleted: id={movie_id}")
    return success(None, "Movie deleted")


# ── POST /api/movies/sync ─────────────────────────────────────────────────────
@movies_bp.route("/sync", methods=["POST"])
@jwt_required()
def sync_from_api():
    """Fetch from SampleAPIs and upsert into local DB."""
    try:
        resp = http.get(SAMPLE_API_URL, timeout=10)
        resp.raise_for_status()
        items = resp.json()
    except Exception as exc:
        current_app.error_logger.error(f"SampleAPI fetch failed: {exc}")
        return error(f"Failed to fetch from SampleAPI: {str(exc)}", 502)

    created = updated = 0
    for item in items[:50]:          # cap at 50
        ext_id = item.get("id")
        existing = Movie.query.filter_by(external_id=ext_id).first() if ext_id else None

        poster = ""
        if isinstance(item.get("posterURL"), str):
            poster = item["posterURL"]

        fields = dict(
            title       = item.get("title", "Unknown"),
            year        = str(item.get("Year", "")),
            rated       = item.get("Rated", ""),
            runtime     = item.get("Runtime", ""),
            genre       = item.get("Genre", ""),
            director    = item.get("Director", ""),
            actors      = item.get("Actors", ""),
            plot        = item.get("Plot", ""),
            imdb_rating = str(item.get("imdbRating", "")),
            poster_url  = poster,
            source      = "sampleapis",
        )
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
            updated += 1
        else:
            movie = Movie(external_id=ext_id, **fields)
            db.session.add(movie)
            created += 1

    db.session.commit()
    msg = f"Sync complete: {created} created, {updated} updated"
    current_app.logger.info(msg)
    return success({"created": created, "updated": updated}, msg)
