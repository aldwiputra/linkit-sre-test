"""Auth routes: register, login, me"""
from flask import Blueprint, request, current_app
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from app import db
from models.user import User
from utils.response import success, error

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    email    = (data.get("email") or "").strip()
    password = data.get("password", "")

    if not username or not email or not password:
        return error("username, email, and password are required", 400)
    if len(password) < 6:
        return error("Password must be at least 6 characters", 400)
    if User.query.filter_by(username=username).first():
        return error("Username already taken", 409)
    if User.query.filter_by(email=email).first():
        return error("Email already registered", 409)

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    current_app.logger.info(f"New user registered: {username}")
    return success(user.to_dict(), "User registered", 201)


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password", "")

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return error("Invalid username or password", 401)
    if not user.is_active:
        return error("Account is deactivated", 403)

    token = create_access_token(identity=str(user.id))
    current_app.logger.info(f"User logged in: {username}")
    return success({
        "access_token": token,
        "token_type":   "Bearer",
        "user":         user.to_dict(),
    }, "Login successful")


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return error("User not found", 404)
    return success(user.to_dict())
