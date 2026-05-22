"""
Master table  : movies   – data fetched from SampleAPIs
Transactional : watchlist – user's saved movies with notes/status
"""
from app import db
from datetime import datetime, timezone


class Movie(db.Model):
    __tablename__ = "movies"

    id             = db.Column(db.Integer, primary_key=True)
    external_id    = db.Column(db.Integer, unique=True, nullable=True)
    title          = db.Column(db.String(255), nullable=False)
    year           = db.Column(db.String(10))
    rated          = db.Column(db.String(20))
    released       = db.Column(db.String(50))
    runtime        = db.Column(db.String(30))
    genre          = db.Column(db.String(100))
    director       = db.Column(db.String(150))
    actors         = db.Column(db.Text)
    plot           = db.Column(db.Text)
    imdb_rating    = db.Column(db.String(10))
    poster_url     = db.Column(db.Text)
    source         = db.Column(db.String(30), default="sampleapis")
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))

    watchlists = db.relationship("Watchlist", backref="movie", lazy=True)

    def to_dict(self):
        return {
            "id":          self.id,
            "external_id": self.external_id,
            "title":       self.title,
            "year":        self.year,
            "rated":       self.rated,
            "runtime":     self.runtime,
            "genre":       self.genre,
            "director":    self.director,
            "actors":      self.actors,
            "plot":        self.plot,
            "imdb_rating": self.imdb_rating,
            "poster_url":  self.poster_url,
            "source":      self.source,
            "created_at":  self.created_at.isoformat(),
        }


class Watchlist(db.Model):
    __tablename__ = "watchlist"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"),  nullable=False)
    movie_id   = db.Column(db.Integer, db.ForeignKey("movies.id"), nullable=False)
    status     = db.Column(db.String(20), default="want_to_watch")  # watching / watched / dropped
    rating     = db.Column(db.Integer)          # 1-10, user's personal rating
    notes      = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id":         self.id,
            "user_id":    self.user_id,
            "movie_id":   self.movie_id,
            "movie":      self.movie.to_dict() if self.movie else None,
            "status":     self.status,
            "rating":     self.rating,
            "notes":      self.notes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
