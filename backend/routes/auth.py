"""Authentication API routes."""

import os

from flask import Blueprint, request, session
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash


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
                """SELECT id, username, email, password, role,
                          must_change_password
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
        session["must_change_password"] = bool(user["must_change_password"])
        return {
            "message": "Login successful",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
                "must_change_password": bool(user["must_change_password"])
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
        cur = None
        try:
            cur = mysql.connection.cursor()
            cur.execute(
                """SELECT id, username, role, must_change_password
                   FROM users WHERE id = %s""",
                (session["user_id"],)
            )
            user = cur.fetchone()
        except Exception as error:
            print("Current user lookup error:", error)
            return {"error": "Unable to verify authentication"}, 500
        finally:
            if cur is not None:
                cur.close()
        if not user:
            session.clear()
            return {"error": "Authentication required"}, 401
        session["username"] = user["username"]
        session["role"] = user["role"]
        session["must_change_password"] = bool(user["must_change_password"])
        return {
            "user": {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "must_change_password": bool(user["must_change_password"])
            }
        }, 200

    @auth.post("/api/auth/change-password")
    @login_required
    def change_password():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {"error": "Password data is required"}, 400
        current_password = str(data.get("current_password") or "")
        new_password = str(data.get("new_password") or "")
        confirm_password = str(data.get("confirm_password") or "")
        if not current_password or not new_password or not confirm_password:
            return {
                "error": (
                    "Current password, new password, and confirmation are required"
                )
            }, 400
        if len(new_password) < 8:
            return {
                "error": "Password must contain at least 8 characters"
            }, 400
        if not new_password.strip():
            return {"error": "Password cannot contain only whitespace"}, 400
        if new_password != confirm_password:
            return {"error": "New passwords do not match"}, 400
        if new_password == current_password:
            return {"error": "New password must differ from current password"}, 400

        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "SELECT id, username, role, password FROM users WHERE id = %s",
                (session["user_id"],)
            )
            user = cur.fetchone()
            if not user or not check_password_hash(
                user["password"], current_password
            ):
                return {"error": "Current password is incorrect"}, 401
            cur.execute(
                """UPDATE users
                   SET password = %s, must_change_password = FALSE
                   WHERE id = %s""",
                (generate_password_hash(new_password), user["id"])
            )
            mysql.connection.commit()
            session["must_change_password"] = False
            return {
                "message": "Password changed successfully",
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "role": user["role"],
                    "must_change_password": False
                }
            }, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Password change error:", error)
            return {"error": "Unable to change password"}, 500
        finally:
            cur.close()

    return auth
