"""Authentication API routes."""

import os

from flask import Blueprint, request, session
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash


def _login_rate_limit_key():
    """Limit one account without blocking other students in a school lab."""
    data = request.get_json(silent=True)
    email = "unknown"
    if isinstance(data, dict) and isinstance(data.get("email"), str):
        email = data["email"].strip().lower() or "unknown"
    return f"{get_remote_address()}:{email}"


def create_auth_blueprint(mysql, limiter, login_required):
    auth = Blueprint("auth", __name__)

    @auth.post("/api/login")
    @limiter.limit(
        lambda: os.getenv("LOGIN_RATE_LIMIT", "10 per minute"),
        key_func=_login_rate_limit_key
    )
    def api_login():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {"error": "Login data is required"}, 400

        email = data.get("email")
        password = data.get("password")
        if not email or not password:
            return {"error": "Email and password are required"}, 400

        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT id, username, email, password, role
                   FROM users WHERE email = %s""",
                (email,)
            )
            user = cur.fetchone()
        finally:
            cur.close()

        if not user or not check_password_hash(user["password"], password):
            return {"error": "Invalid email or password"}, 401

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        return {
            "message": "Login successful",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"]
            }
        }, 200

    @auth.post("/api/logout")
    @login_required
    def api_logout():
        session.clear()
        return {"message": "Logout successful"}, 200

    @auth.get("/api/auth/me")
    @login_required
    def current_user():
        return {
            "user": {
                "id": session.get("user_id"),
                "username": session.get("username"),
                "role": session.get("role")
            }
        }, 200

    return auth
