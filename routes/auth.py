"""Authentication and public registration API routes."""

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


def create_auth_blueprint(mysql, limiter, login_required, student_role):
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

    @auth.get("/api/public/classes")
    def public_classes_api():
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT id, name, grade, section FROM classes
                   ORDER BY grade, section, name"""
            )
            return {"classes": cur.fetchall()}, 200
        finally:
            cur.close()

    @auth.post("/api/register")
    def api_register():
        data = request.get_json(silent=True)
        if not data:
            return {"error": "Registration data is required"}, 400

        username = data.get("username")
        email = data.get("email")
        password = data.get("password")
        full_name = data.get("full_name")
        role = data.get("role")
        if not username or not email or not password or not role:
            return {
                "error": "Username, email, password, and role are required"
            }, 400
        if role != student_role:
            return {
                "error": "Public registration is available only for students; teachers are created by an administrator"
            }, 403
        if not full_name:
            return {"error": "Full name is required for students"}, 400
        if len(str(password)) < 8:
            return {"error": "Password must contain at least 8 characters"}, 400

        try:
            class_id = int(data.get("class_id"))
        except (TypeError, ValueError):
            return {"error": "Select a class"}, 400

        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "SELECT id, grade FROM classes WHERE id = %s", (class_id,)
            )
            selected_class = cur.fetchone()
            if not selected_class:
                return {"error": "Selected class was not found"}, 404

            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                return {"error": "Email already registered"}, 409

            cur.execute(
                """INSERT INTO users (username, email, password, role)
                   VALUES (%s, %s, %s, %s)""",
                (username, email, generate_password_hash(password), role)
            )
            user_id = cur.lastrowid
            cur.execute(
                """INSERT INTO students (user_id, full_name, grade)
                   VALUES (%s, %s, %s)""",
                (user_id, str(full_name).strip(), selected_class["grade"])
            )
            student_id = cur.lastrowid
            cur.execute(
                """INSERT INTO student_class_enrollments (student_id, class_id)
                   VALUES (%s, %s)""",
                (student_id, class_id)
            )
            mysql.connection.commit()
            return {
                "message": "Registration successful",
                "user": {
                    "id": user_id,
                    "username": username,
                    "email": email,
                    "role": role
                }
            }, 201
        except Exception as error:
            mysql.connection.rollback()
            print("Registration error:", error)
            return {"error": "Registration failed"}, 500
        finally:
            cur.close()

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
