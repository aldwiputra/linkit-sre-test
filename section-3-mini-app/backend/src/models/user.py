"""Master table: users"""
from app import db
import bcrypt
from datetime import datetime, timezone


class User(db.Model):
    __tablename__ = "users"

    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(80), unique=True, nullable=False)
    email      = db.Column(db.String(120), unique=True, nullable=False)
    password   = db.Column(db.String(200), nullable=False)
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    watchlists = db.relationship("Watchlist", backref="user", lazy=True)

    def set_password(self, plain: str):
        self.password = bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

    def check_password(self, plain: str) -> bool:
        return bcrypt.checkpw(plain.encode(), self.password.encode())

    def to_dict(self):
        return {
            "id":         self.id,
            "username":   self.username,
            "email":      self.email,
            "is_active":  self.is_active,
            "created_at": self.created_at.isoformat(),
        }
