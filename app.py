from flask import Flask, request, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import os
import json
import secrets
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

def env_flag(name, default=False):
    """Read a boolean environment variable without accepting ambiguous values."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


app = Flask(__name__)
app_environment = os.getenv("APP_ENV", "development").strip().lower()
is_production = app_environment == "production"

default_cors_origins = "http://localhost:5173,http://localhost:5174"
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", default_cors_origins).split(",")
    if origin.strip()
]

CORS(
    app,
    origins=cors_origins,
    supports_credentials=True
)

# A production deployment must provide a stable, private signing key. Local
# development receives an ephemeral key instead of an unsafe shared default.
secret_key = os.getenv("SECRET_KEY", "").strip()
if not secret_key:
    if is_production:
        raise RuntimeError("SECRET_KEY is required when APP_ENV=production")
    secret_key = secrets.token_hex(32)
app.config["SECRET_KEY"] = secret_key

# Session cookie settings (important for React + credentials)
app.config["SESSION_COOKIE_SAMESITE"] = os.getenv(
    "SESSION_COOKIE_SAMESITE", "Lax"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = env_flag(
    "SESSION_COOKIE_SECURE", default=is_production
)

# MySQL Configuration (prefer environment variables)
app.config["MYSQL_HOST"] = os.getenv("MYSQL_HOST", "localhost")
app.config["MYSQL_USER"] = os.getenv("MYSQL_USER", "siksha_user")
app.config["MYSQL_PASSWORD"] = os.getenv("MYSQL_PASSWORD", "")
app.config["MYSQL_DB"] = os.getenv("MYSQL_DB", "siksha_sarathi")
app.config["MYSQL_CURSORCLASS"] = "DictCursor"

mysql = MySQL(app)


def login_rate_limit_key():
    """Limit repeated attempts against one account without blocking a whole lab."""
    data = request.get_json(silent=True)
    email = "unknown"
    if isinstance(data, dict) and isinstance(data.get("email"), str):
        email = data["email"].strip().lower() or "unknown"
    return f"{get_remote_address()}:{email}"


limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://")
)


# ============================================================
# ROLES
# ============================================================

STUDENT = "student"
TEACHER = "teacher"
ADMIN = "admin"


# ============================================================
# AUTHENTICATION DECORATORS
# ============================================================

def login_required(f):

    @wraps(f)
    def decorated(*args, **kwargs):

        if "user_id" not in session:
            return {
                "error": "Authentication required"
            }, 401

        return f(*args, **kwargs)

    return decorated


def role_required(role):

    def decorator(f):

        @wraps(f)
        def decorated(*args, **kwargs):

            if "user_id" not in session:
                return {
                    "error": "Authentication required"
                }, 401

            if session.get("role") != role:
                return {
                    "error": "Access denied"
                }, 403

            return f(*args, **kwargs)

        return decorated

    return decorator


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/", methods=["GET"])
def health_check():

    return {
        "message": "Siksha Sarathi API is running",
        "status": "success"
    }, 200


# ============================================================
# AUTHENTICATION
# ============================================================

@app.route("/api/login", methods=["POST"])
@limiter.limit(
    lambda: os.getenv("LOGIN_RATE_LIMIT", "10 per minute"),
    key_func=login_rate_limit_key
)
def api_login():

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {
            "error": "Login data is required"
        }, 400

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return {
            "error": "Email and password are required"
        }, 400

    cur = mysql.connection.cursor()

    try:

        cur.execute(
            """
            SELECT
                id,
                username,
                email,
                password,
                role
            FROM users
            WHERE email = %s
            """,
            (email,)
        )

        user = cur.fetchone()

    finally:
        cur.close()

    if not user:
        return {
            "error": "Invalid email or password"
        }, 401

    if not check_password_hash(
        user["password"],
        password
    ):
        return {
            "error": "Invalid email or password"
        }, 401

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


@app.errorhandler(429)
def login_rate_limit_exceeded(_error):
    return {
        "error": "Too many login attempts. Please wait before trying again."
    }, 429


@app.route("/api/public/classes", methods=["GET"])
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


@app.route("/api/register", methods=["POST"])
def api_register():

    data = request.get_json(silent=True)

    if not data:
        return {
            "error": "Registration data is required"
        }, 400

    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    full_name = data.get("full_name")
    role = data.get("role")

    if not username or not email or not password or not role:
        return {
            "error": "Username, email, password, and role are required"
        }, 400

    if role != STUDENT:
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
            "SELECT id, grade FROM classes WHERE id = %s",
            (class_id,)
        )
        selected_class = cur.fetchone()
        if not selected_class:
            return {"error": "Selected class was not found"}, 404

        # Check duplicate email
        cur.execute(
            """
            SELECT id
            FROM users
            WHERE email = %s
            """,
            (email,)
        )

        existing_user = cur.fetchone()

        if existing_user:
            return {
                "error": "Email already registered"
            }, 409

        # Hash password
        hashed_password = generate_password_hash(password)

        # Create user
        cur.execute(
            """
            INSERT INTO users
            (
                username,
                email,
                password,
                role
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                username,
                email,
                hashed_password,
                role
            )
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

    except Exception as e:

        mysql.connection.rollback()

        print("Registration error:", e)

        return {
            "error": "Registration failed"
        }, 500

    finally:

        cur.close()


@app.route("/api/logout", methods=["POST"])
@login_required
def api_logout():

    session.clear()

    return {
        "message": "Logout successful"
    }, 200


@app.route("/api/auth/me", methods=["GET"])
@login_required
def current_user():

    return {
        "user": {
            "id": session.get("user_id"),
            "username": session.get("username"),
            "role": session.get("role")
        }
    }, 200


# ============================================================
# STUDENT DASHBOARD
# ============================================================

@app.route("/api/student/dashboard", methods=["GET"])
@login_required
@role_required(STUDENT)
def student_dashboard_api():

    cur = mysql.connection.cursor()

    try:

        # ----------------------------------------------------
        # Student profile
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                s.id AS student_id,
                s.full_name,
                s.grade
            FROM students s
            WHERE s.user_id = %s
            """,
            (session["user_id"],)
        )

        student = cur.fetchone()

        if not student:
            return {
                "error": "Student profile not found"
            }, 404

        student_id = student["student_id"]

        # ----------------------------------------------------
        # Available notes
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT COUNT(*) AS total_notes
            FROM notes
            """
        )

        notes_data = cur.fetchone()

        total_notes = notes_data["total_notes"]

        # ----------------------------------------------------
        # Quiz statistics
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                COUNT(*) AS completed_quizzes,
                COALESCE(AVG(100.0 * score / NULLIF(total_questions, 0)), 0) AS average_score
            FROM quiz_results
            WHERE student_id = %s
            """,
            (student_id,)
        )

        quiz_stats = cur.fetchone()

        completed_quizzes = quiz_stats["completed_quizzes"]

        average_score = round(
            float(quiz_stats["average_score"]),
            2
        )

        return {
            "student": student,
            "stats": {
                "total_notes": total_notes,
                "completed_quizzes": completed_quizzes,
                "average_quiz_score": average_score
            }
        }, 200

    finally:

        cur.close()


# ============================================================
# STUDENT NOTES
# ============================================================

@app.route("/api/student/practice-plan", methods=["GET"])
@login_required
@role_required(STUDENT)
def student_practice_plan_api():
    """Suggest practice from the student's recent, tagged quiz answers."""
    cur = mysql.connection.cursor()
    try:
        cur.execute(
            "SELECT id, full_name FROM students WHERE user_id = %s",
            (session["user_id"],)
        )
        student = cur.fetchone()
        if not student:
            return {"error": "Student profile not found"}, 404

        cur.execute(
            """
            SELECT q.subject, qar.topic,
                   COUNT(*) AS total_questions,
                   COUNT(DISTINCT qar.question_text) AS distinct_questions,
                   COALESCE(SUM(qar.is_correct), 0) AS correct_answers,
                   COALESCE(SUM(qar.is_skipped), 0) AS skipped_answers
            FROM (
                SELECT id FROM quiz_results
                WHERE student_id = %s ORDER BY id DESC LIMIT 10
            ) recent
            INNER JOIN quiz_answer_results qar
                ON qar.quiz_result_id = recent.id
            INNER JOIN quiz_results qr ON qr.id = recent.id
            INNER JOIN quizzes q ON q.id = qr.quiz_id
            GROUP BY q.subject, qar.topic
            """,
            (student["id"],)
        )
        rows = cur.fetchall()
        priorities = []
        for row in rows:
            subject = str(row["subject"] or "").strip()
            topic = str(row["topic"] or "").strip()
            if not topic or topic.casefold() in {"unspecified", subject.casefold()}:
                continue
            total = int(row["total_questions"] or 0)
            correct = int(row["correct_answers"] or 0)
            if total < 3 or int(row["distinct_questions"] or 0) < 2:
                continue
            accuracy = round(100 * correct / total, 2)
            if accuracy >= 60:
                continue
            priorities.append({
                "subject": subject, "topic": topic,
                "total_questions": total, "correct_answers": correct,
                "skipped_answers": int(row["skipped_answers"] or 0),
                "accuracy_percent": accuracy,
                "steps": [
                    f"Review your notes about {topic}.",
                    "Try a short practice quiz and check your answers.",
                    "Ask your teacher about questions you still find difficult."
                ],
                "notes": [], "quizzes": []
            })
        priorities.sort(key=lambda item: (
            item["accuracy_percent"], -item["total_questions"],
            item["subject"], item["topic"]
        ))
        priorities = priorities[:3]

        if priorities:
            cur.execute(
                "SELECT id, title, subject, chapter FROM notes ORDER BY id DESC"
            )
            notes = cur.fetchall()
            cur.execute(
                """
                SELECT id, title, subject, questions FROM quizzes
                WHERE is_published = TRUE
                ORDER BY id DESC
                """
            )
            quizzes = [
                quiz for quiz in cur.fetchall()
                if not quiz_has_open_lab_session(cur, quiz["id"])
            ]
            for priority in priorities:
                subject = priority["subject"].casefold()
                topic = priority["topic"].casefold()
                priority["notes"] = [
                    {"id": note["id"], "title": note["title"],
                     "chapter": note["chapter"]}
                    for note in notes
                    if str(note["subject"] or "").casefold() == subject
                    and topic in str(note["chapter"] or "").casefold()
                ][:2]
                for quiz in quizzes:
                    if str(quiz["subject"] or "").casefold() != subject:
                        continue
                    try:
                        questions = parse_quiz_questions(
                            quiz["questions"], quiz["subject"] or "General"
                        )
                    except (TypeError, ValueError):
                        continue
                    if any(str(question["topic"]).casefold() == topic
                           for question in questions):
                        priority["quizzes"].append({
                            "id": quiz["id"], "title": quiz["title"]
                        })
                    if len(priority["quizzes"]) >= 2:
                        break

        if priorities:
            message = "Start with one topic, then check your progress with new questions."
        elif rows:
            message = (
                "No clear topic to practise yet. Keep learning and try more "
                "questions across different topics."
            )
        else:
            message = (
                "Take a practice quiz to start building a plan for your learning."
            )
        return {"message": message, "topics": priorities}, 200
    finally:
        cur.close()


@app.route("/api/student/notes", methods=["GET"])
@login_required
@role_required(STUDENT)
def student_notes_api():

    cur = mysql.connection.cursor()

    try:

        cur.execute(
            """
            SELECT
                id,
                title,
                subject,
                chapter,
                content,
                created_at
            FROM notes
            ORDER BY created_at DESC
            """
        )

        notes = cur.fetchall()

        return {
            "notes": notes
        }, 200

    finally:

        cur.close()


# ============================================================
# TEACHER DASHBOARD
# ============================================================

@app.route("/api/teacher/dashboard", methods=["GET"])
@login_required
@role_required(TEACHER)
def teacher_dashboard_api():

    cur = mysql.connection.cursor()

    try:

        # ----------------------------------------------------
        # Teacher notes
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT COUNT(*) AS total_notes
            FROM notes
            WHERE uploaded_by = %s
            """,
            (session["user_id"],)
        )

        total_notes = cur.fetchone()["total_notes"]

        # ----------------------------------------------------
        # Recent teacher notes
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                id,
                title,
                subject,
                chapter,
                created_at
            FROM notes
            WHERE uploaded_by = %s
            ORDER BY created_at DESC
            LIMIT 5
            """,
            (session["user_id"],)
        )

        recent_notes = cur.fetchall()

        # ----------------------------------------------------
        # Total students
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT COUNT(DISTINCT sce.student_id) AS total_students
            FROM teacher_class_subjects tcs
            INNER JOIN student_class_enrollments sce ON sce.class_id = tcs.class_id
            WHERE tcs.teacher_user_id = %s
            """,
            (session["user_id"],)
        )

        total_students = cur.fetchone()["total_students"]

        # ----------------------------------------------------
        # Quiz statistics
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                COUNT(*) AS total_quiz_attempts,
                COALESCE(AVG(100.0 * score / NULLIF(total_questions, 0)), 0) AS average_quiz_score
            FROM quiz_results qr
            INNER JOIN quizzes q ON q.id = qr.quiz_id
            WHERE EXISTS (
                SELECT 1 FROM teacher_class_subjects tcs
                INNER JOIN student_class_enrollments sce ON sce.class_id = tcs.class_id
                WHERE tcs.teacher_user_id = %s
                  AND sce.student_id = qr.student_id
                  AND LOWER(tcs.subject) = LOWER(q.subject)
            )
            """,
            (session["user_id"],)
        )

        quiz_stats = cur.fetchone()

        total_quiz_attempts = (
            quiz_stats["total_quiz_attempts"]
        )

        average_quiz_score = round(
            float(quiz_stats["average_quiz_score"]),
            2
        )

        # ----------------------------------------------------
        # Quiz support is based on recorded answers for assigned subjects.
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT qr.student_id,
                   COUNT(qar.id) AS total_questions,
                   COALESCE(SUM(qar.is_correct), 0) AS correct_answers,
                   COALESCE(SUM(qar.is_skipped), 0) AS skipped_answers
            FROM quiz_results qr
            INNER JOIN quizzes q ON q.id = qr.quiz_id
            LEFT JOIN quiz_answer_results qar ON qar.quiz_result_id = qr.id
            WHERE EXISTS (
                SELECT 1 FROM teacher_class_subjects tcs
                INNER JOIN student_class_enrollments sce ON sce.class_id = tcs.class_id
                WHERE tcs.teacher_user_id = %s
                  AND sce.student_id = qr.student_id
                  AND LOWER(tcs.subject) = LOWER(q.subject)
            )
            GROUP BY qr.student_id, LOWER(q.subject)
            """,
            (session["user_id"],)
        )
        students_needing_quiz_support = len({
            row["student_id"] for row in cur.fetchall()
            if build_learning_metrics({"attempts": 0, **row})["status"] == "Needs attention"
        })

        # ----------------------------------------------------
        # Individual student performance
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                s.id AS student_id,
                s.full_name,
                s.grade,

                COUNT(qr.id)
                AS quiz_attempts,

                COALESCE(
                    AVG(100.0 * qr.score / NULLIF(qr.total_questions, 0)),
                    0
                ) AS average_quiz_score

            FROM students s
            LEFT JOIN quiz_results qr ON s.id = qr.student_id
                AND EXISTS (
                    SELECT 1 FROM quizzes q
                    INNER JOIN teacher_class_subjects tcs
                        ON LOWER(q.subject) = LOWER(tcs.subject)
                    INNER JOIN student_class_enrollments sce
                        ON sce.class_id = tcs.class_id
                    WHERE q.id = qr.quiz_id
                      AND sce.student_id = s.id
                      AND tcs.teacher_user_id = %s
                )
            WHERE EXISTS (
                SELECT 1 FROM teacher_class_subjects tcs
                INNER JOIN student_class_enrollments sce ON sce.class_id = tcs.class_id
                WHERE sce.student_id = s.id AND tcs.teacher_user_id = %s
            )

            GROUP BY
                s.id,
                s.full_name,
                s.grade

            ORDER BY s.full_name
            """,
            (session["user_id"], session["user_id"])
        )

        student_performance = cur.fetchall()

        # ----------------------------------------------------
        # Convert Decimal values if necessary
        # ----------------------------------------------------

        for student in student_performance:

            if student["average_quiz_score"] is not None:

                student["average_quiz_score"] = round(
                    float(student["average_quiz_score"]),
                    2
                )

        return {
            "teacher": {
                "name": session.get("username")
            },

            "statistics": {
                "total_notes": total_notes,
                "total_students": total_students,
                "total_quiz_attempts": total_quiz_attempts,
                "average_quiz_score": average_quiz_score,
                "students_needing_quiz_support":
                    students_needing_quiz_support
            },

            "recent_notes": recent_notes,

            "student_performance":
                student_performance
        }, 200

    finally:

        cur.close()


# ============================================================
# TEACHER NOTES
# ============================================================

@app.route("/api/teacher/notes", methods=["GET"])
@login_required
@role_required(TEACHER)
def teacher_notes_api():

    cur = mysql.connection.cursor()

    try:

        cur.execute(
            """
            SELECT
                id,
                title,
                subject,
                chapter,
                content,
                created_at
            FROM notes
            WHERE uploaded_by = %s
            ORDER BY created_at DESC
            """,
            (session["user_id"],)
        )

        notes = cur.fetchall()

        return {
            "notes": notes
        }, 200

    finally:

        cur.close()


@app.route("/api/teacher/notes", methods=["POST"])
@login_required
@role_required(TEACHER)
def teacher_upload_note_api():

    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data:
        return {
            "error": "Note data is required"
        }, 400

    title = str(data.get("title") or "").strip()
    subject = str(data.get("subject") or "").strip()
    chapter = str(data.get("chapter") or "").strip()
    content = str(data.get("content") or "").strip()

    if not all([
        title,
        subject,
        chapter,
        content
    ]):

        return {
            "error": "All note fields are required"
        }, 400

    cur = mysql.connection.cursor()

    try:

        cur.execute(
            """
            INSERT INTO notes
            (
                title,
                subject,
                chapter,
                content,
                uploaded_by
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                title,
                subject,
                chapter,
                content,
                session["user_id"]
            )
        )

        mysql.connection.commit()

        return {
            "message": "Note uploaded successfully"
        }, 201

    except Exception as e:

        mysql.connection.rollback()

        print("Teacher note upload error:", e)

        return {
            "error": "Failed to upload note"
        }, 500

    finally:

        cur.close()


@app.route("/api/teacher/notes/<int:note_id>", methods=["GET"])
@login_required
@role_required(TEACHER)
def teacher_note_detail_api(note_id):

    cur = mysql.connection.cursor()

    try:

        cur.execute(
            """
            SELECT
                id,
                title,
                subject,
                chapter,
                content,
                created_at
            FROM notes
            WHERE id = %s
              AND uploaded_by = %s
            """,
            (note_id, session["user_id"])
        )

        note = cur.fetchone()

        if not note:
            return {
                "error": "Note not found"
            }, 404

        return {
            "note": note
        }, 200

    finally:

        cur.close()


@app.route("/api/teacher/notes/<int:note_id>", methods=["PUT"])
@login_required
@role_required(TEACHER)
def teacher_update_note_api(note_id):

    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data:
        return {
            "error": "Note data is required"
        }, 400

    title = str(data.get("title") or "").strip()
    subject = str(data.get("subject") or "").strip()
    chapter = str(data.get("chapter") or "").strip()
    content = str(data.get("content") or "").strip()

    if not all([title, subject, chapter, content]):
        return {
            "error": "All note fields are required"
        }, 400

    cur = mysql.connection.cursor()

    try:

        cur.execute(
            """
            SELECT id
            FROM notes
            WHERE id = %s
              AND uploaded_by = %s
            """,
            (note_id, session["user_id"])
        )

        if not cur.fetchone():
            return {
                "error": "Note not found"
            }, 404

        cur.execute(
            """
            UPDATE notes
            SET
                title = %s,
                subject = %s,
                chapter = %s,
                content = %s
            WHERE id = %s
              AND uploaded_by = %s
            """,
            (
                title,
                subject,
                chapter,
                content,
                note_id,
                session["user_id"]
            )
        )

        mysql.connection.commit()

        return {
            "message": "Note updated successfully"
        }, 200

    except Exception as e:

        mysql.connection.rollback()

        print("Teacher note update error:", e)

        return {
            "error": "Failed to update note"
        }, 500

    finally:

        cur.close()


@app.route("/api/teacher/notes/<int:note_id>", methods=["DELETE"])
@login_required
@role_required(TEACHER)
def teacher_delete_note_api(note_id):

    cur = mysql.connection.cursor()

    try:

        cur.execute(
            """
            SELECT id
            FROM notes
            WHERE id = %s
              AND uploaded_by = %s
            """,
            (note_id, session["user_id"])
        )

        if not cur.fetchone():
            return {
                "error": "Note not found"
            }, 404

        cur.execute(
            """
            DELETE FROM notes
            WHERE id = %s
              AND uploaded_by = %s
            """,
            (note_id, session["user_id"])
        )

        mysql.connection.commit()

        return {
            "message": "Note deleted successfully"
        }, 200

    except Exception as e:

        mysql.connection.rollback()

        print("Teacher note deletion error:", e)

        return {
            "error": "Failed to delete note"
        }, 500

    finally:

        cur.close()


# ============================================================
# TEACHER LEARNING ANALYTICS
# ============================================================

def build_learning_metrics(row):
    total_questions = int(row["total_questions"] or 0)
    correct_answers = int(row["correct_answers"] or 0)
    skipped_answers = int(row["skipped_answers"] or 0)
    accuracy = round(100 * correct_answers / total_questions, 2) if total_questions else 0
    skip_rate = round(100 * skipped_answers / total_questions, 2) if total_questions else 0

    if total_questions == 0:
        status = "No activity"
    elif accuracy < 50 or skip_rate >= 25:
        status = "Needs attention"
    elif accuracy < 75:
        status = "Developing"
    else:
        status = "On track"

    return {
        "attempts": int(row["attempts"] or 0),
        "total_questions": total_questions,
        "correct_answers": correct_answers,
        "skipped_answers": skipped_answers,
        "accuracy_percent": accuracy,
        "skip_percent": skip_rate,
        "status": status
    }


def fetch_student_subject_metrics(cur, student_id, subject):
    cur.execute(
        """
        SELECT
            COUNT(DISTINCT qr.id) AS attempts,
            COUNT(qar.id) AS total_questions,
            COALESCE(SUM(qar.is_correct), 0) AS correct_answers,
            COALESCE(SUM(qar.is_skipped), 0) AS skipped_answers
        FROM quiz_results qr
        INNER JOIN quizzes q ON q.id = qr.quiz_id
        LEFT JOIN quiz_answer_results qar ON qar.quiz_result_id = qr.id
        WHERE qr.student_id = %s
          AND LOWER(q.subject) = LOWER(%s)
        """,
        (student_id, subject)
    )
    return build_learning_metrics(cur.fetchone())


def fetch_student_paper_metrics(
    cur, teacher_id, student_id, class_id, subject
):
    cur.execute(
        """
        SELECT
            COUNT(CASE WHEN pas.id IS NOT NULL THEN 1 END) AS recorded_assessments,
            COUNT(CASE
                WHEN pas.is_absent = FALSE AND pas.marks_obtained IS NOT NULL
                THEN 1 END) AS graded_assessments,
            COALESCE(SUM(CASE WHEN pas.is_absent = TRUE THEN 1 ELSE 0 END), 0)
                AS absent_assessments,
            COALESCE(SUM(CASE
                WHEN pas.is_absent = FALSE AND pas.marks_obtained IS NOT NULL
                THEN pas.marks_obtained ELSE 0 END), 0) AS marks_obtained,
            COALESCE(SUM(CASE
                WHEN pas.is_absent = FALSE AND pas.marks_obtained IS NOT NULL
                THEN pa.max_marks ELSE 0 END), 0) AS maximum_marks
        FROM paper_assessments pa
        LEFT JOIN paper_assessment_scores pas
            ON pas.assessment_id = pa.id AND pas.student_id = %s
        WHERE pa.teacher_user_id = %s
          AND pa.class_id = %s
          AND LOWER(pa.subject) = LOWER(%s)
          AND pa.is_published = TRUE
        """,
        (student_id, teacher_id, class_id, subject)
    )
    row = cur.fetchone()
    recorded = int(row["recorded_assessments"] or 0)
    absent = int(row["absent_assessments"] or 0)
    marks = float(row["marks_obtained"] or 0)
    maximum = float(row["maximum_marks"] or 0)
    return {
        "recorded_assessments": recorded,
        "graded_assessments": int(row["graded_assessments"] or 0),
        "absent_assessments": absent,
        "marks_obtained": round(marks, 2),
        "maximum_marks": round(maximum, 2),
        "average_percent": round(100 * marks / maximum, 2) if maximum else 0
    }


def fetch_student_attendance_metrics(cur, student_id, class_id):
    cur.execute(
        """
        SELECT
            COALESCE(SUM(mas.total_school_days), 0) AS recorded_days,
            COALESCE(SUM(mar.present_days), 0) AS present_days,
            COALESCE(SUM(mas.total_school_days - mar.present_days), 0)
                AS absent_days,
            COUNT(mar.id) AS recorded_months
        FROM monthly_attendance_summaries mas
        INNER JOIN monthly_attendance_records mar ON mar.summary_id = mas.id
        WHERE mas.class_id = %s AND mar.student_id = %s
        """,
        (class_id, student_id)
    )
    row = cur.fetchone()
    recorded = int(row["recorded_days"] or 0)
    present = int(row["present_days"] or 0)
    if not recorded:
        # Keep analytics compatible with historical daily records until a
        # school runs the monthly-summary migration.
        cur.execute(
            """
            SELECT
                COUNT(ar.id) AS recorded_days,
                COALESCE(SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END), 0)
                    AS present_days,
                COALESCE(SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END), 0)
                    AS absent_days,
                COALESCE(SUM(CASE WHEN ar.status = 'late' THEN 1 ELSE 0 END), 0)
                    AS late_days,
                COALESCE(SUM(CASE WHEN ar.status = 'excused' THEN 1 ELSE 0 END), 0)
                    AS excused_days
            FROM attendance_sessions ats
            INNER JOIN attendance_records ar ON ar.attendance_session_id = ats.id
            WHERE ats.class_id = %s AND ar.student_id = %s
            """,
            (class_id, student_id)
        )
        legacy = cur.fetchone()
        recorded = int(legacy["recorded_days"] or 0)
        present = int(legacy["present_days"] or 0)
        late = int(legacy["late_days"] or 0)
        return {
            "recorded_months": 0,
            "recorded_days": recorded,
            "present_days": present,
            "absent_days": int(legacy["absent_days"] or 0),
            "late_days": late,
            "excused_days": int(legacy["excused_days"] or 0),
            "attendance_percent": (
                round(100 * (present + late) / recorded, 2) if recorded else 0
            )
        }
    return {
        "recorded_months": int(row["recorded_months"] or 0),
        "recorded_days": recorded,
        "present_days": present,
        "absent_days": int(row["absent_days"] or 0),
        "late_days": 0,
        "excused_days": 0,
        "attendance_percent": (
            round(100 * present / recorded, 2) if recorded else 0
        )
    }


def build_teacher_actions(topics, metrics, paper, attendance, subject):
    """Suggest review steps from observed evidence, without predicting causes."""
    actions = []
    specific_topics = [
        topic for topic in topics
        if str(topic["topic"]).strip().casefold() not in
        {"unspecified", str(subject).strip().casefold()}
        and topic["total_questions"] >= 3
        and topic["distinct_questions"] >= 2
        and topic["accuracy_percent"] < 60
    ]
    for topic in specific_topics[:2]:
        actions.append({
            "kind": "topic",
            "title": f'Review {topic["topic"]}',
            "evidence": (
                f'{topic["correct_answers"]}/{topic["total_questions"]} '
                f'correct; {topic["skipped_answers"]} skipped'
            ),
            "suggestion": (
                "Revisit the concept with a worked example, then give a "
                "short practice quiz and check whether accuracy improves."
            )
        })

    if metrics["total_questions"] >= 4 and metrics["skip_percent"] >= 25:
        actions.append({
            "kind": "quiz",
            "title": "Check unanswered quiz questions",
            "evidence": (
                f'{metrics["skipped_answers"]}/{metrics["total_questions"]} '
                "questions skipped"
            ),
            "suggestion": (
                "Ask which questions were unclear and offer guided practice. "
                "A skipped answer does not identify the reason."
            )
        })

    if paper["graded_assessments"] >= 2 and paper["average_percent"] < 60:
        actions.append({
            "kind": "paper",
            "title": "Review paper assessment work",
            "evidence": (
                f'{paper["average_percent"]}% across '
                f'{paper["graded_assessments"]} graded assessments'
            ),
            "suggestion": (
                "Compare marked answers with the lesson objectives and "
                "discuss where the student needs support."
            )
        })

    if attendance["recorded_days"] >= 5 and attendance["absent_days"] >= 2:
        actions.append({
            "kind": "attendance",
            "title": "Follow up on missed school days",
            "evidence": (
                f'{attendance["absent_days"]} absences in '
                f'{attendance["recorded_days"]} recorded days'
            ),
            "suggestion": (
                "Check in privately and offer a way to catch up on missed lessons. "
                "Attendance alone does not explain learning performance."
            )
        })

    return actions


def fetch_teacher_topic_priorities(cur, teacher_id):
    cur.execute(
        """
        SELECT tcs.class_id, tcs.subject, qar.topic, s.id AS student_id,
               s.full_name, COUNT(*) AS total_questions,
               COUNT(DISTINCT qar.question_text) AS distinct_questions,
               COALESCE(SUM(qar.is_correct), 0) AS correct_answers,
               COALESCE(SUM(qar.is_skipped), 0) AS skipped_answers
        FROM teacher_class_subjects tcs
        INNER JOIN student_class_enrollments sce
            ON sce.class_id = tcs.class_id
        INNER JOIN students s ON s.id = sce.student_id
        INNER JOIN quiz_results qr ON qr.student_id = s.id
        INNER JOIN quizzes q ON q.id = qr.quiz_id
            AND LOWER(q.subject) = LOWER(tcs.subject)
        INNER JOIN quiz_answer_results qar ON qar.quiz_result_id = qr.id
        WHERE tcs.teacher_user_id = %s
        GROUP BY tcs.class_id, tcs.subject, qar.topic, s.id, s.full_name
        """,
        (teacher_id,)
    )
    groups = {}
    for row in cur.fetchall():
        topic = str(row["topic"] or "").strip()
        if topic.casefold() in {"", "unspecified", row["subject"].casefold()}:
            continue
        key = (row["class_id"], row["subject"], topic)
        group = groups.setdefault(key, {
            "class_id": row["class_id"], "subject": row["subject"],
            "topic": topic, "total_questions": 0, "correct_answers": 0,
            "skipped_answers": 0, "students_to_support": []
        })
        total = int(row["total_questions"] or 0)
        correct = int(row["correct_answers"] or 0)
        group["total_questions"] += total
        group["correct_answers"] += correct
        group["skipped_answers"] += int(row["skipped_answers"] or 0)
        if total >= 3 and int(row["distinct_questions"] or 0) >= 2 \
                and correct / total < 0.6:
            group["students_to_support"].append({
                "student_id": row["student_id"],
                "full_name": row["full_name"]
            })
    priorities = []
    for group in groups.values():
        if group["total_questions"] < 3 or not group["students_to_support"]:
            continue
        group["accuracy_percent"] = round(
            100 * group["correct_answers"] / group["total_questions"], 2
        )
        priorities.append(group)
    priorities.sort(key=lambda item: (
        -len(item["students_to_support"]), item["accuracy_percent"],
        item["class_id"], item["subject"], item["topic"]
    ))
    return priorities[:10]


@app.route("/api/teacher/learning-analytics", methods=["GET"])
@login_required
@role_required(TEACHER)
def teacher_learning_analytics_api():
    cur = mysql.connection.cursor()

    try:
        cur.execute(
            """
            SELECT
                c.id AS class_id,
                c.name AS class_name,
                c.grade,
                c.section,
                tcs.subject
            FROM teacher_class_subjects tcs
            INNER JOIN classes c ON c.id = tcs.class_id
            WHERE tcs.teacher_user_id = %s
            ORDER BY c.grade, c.section, tcs.subject
            """,
            (session["user_id"],)
        )
        assignments = cur.fetchall()

        cur.execute(
            """
            SELECT DISTINCT
                s.id AS student_id,
                s.full_name,
                s.grade,
                c.id AS class_id,
                c.name AS class_name,
                c.section,
                tcs.subject
            FROM teacher_class_subjects tcs
            INNER JOIN classes c ON c.id = tcs.class_id
            INNER JOIN student_class_enrollments sce ON sce.class_id = c.id
            INNER JOIN students s ON s.id = sce.student_id
            WHERE tcs.teacher_user_id = %s
            ORDER BY s.full_name, tcs.subject
            """,
            (session["user_id"],)
        )
        student_rows = cur.fetchall()

        topic_priorities = fetch_teacher_topic_priorities(
            cur, session["user_id"]
        )

        profiles = []
        for student in student_rows:
            metrics = fetch_student_subject_metrics(
                cur, student["student_id"], student["subject"]
            )
            paper_metrics = fetch_student_paper_metrics(
                cur, session["user_id"], student["student_id"],
                student["class_id"], student["subject"]
            )
            attendance_metrics = fetch_student_attendance_metrics(
                cur, student["student_id"], student["class_id"]
            )
            profiles.append({
                **student,
                **metrics,
                "paper_assessments": paper_metrics,
                "attendance": attendance_metrics
            })

        assigned_student_ids = {profile["student_id"] for profile in profiles}
        active_student_ids = {
            profile["student_id"]
            for profile in profiles
            if profile["total_questions"] > 0
        }

        return {
            "assignments": assignments,
            "topic_priorities": topic_priorities,
            "statistics": {
                "assigned_students": len(assigned_student_ids),
                "student_subject_profiles": len(profiles),
                "students_with_activity": len(active_student_ids),
                "profiles_needing_attention": sum(
                    profile["status"] == "Needs attention"
                    for profile in profiles
                )
            },
            "students": profiles
        }, 200

    finally:
        cur.close()


@app.route("/api/teacher/students/<int:student_id>/learning-profile", methods=["GET"])
@login_required
@role_required(TEACHER)
def teacher_student_learning_profile_api(student_id):
    subject = str(request.args.get("subject") or "").strip()
    if not subject:
        return {"error": "Subject is required"}, 400

    cur = mysql.connection.cursor()

    try:
        cur.execute(
            """
            SELECT DISTINCT
                s.id AS student_id,
                s.full_name,
                s.grade,
                c.id AS class_id,
                c.name AS class_name,
                c.section,
                tcs.subject
            FROM teacher_class_subjects tcs
            INNER JOIN classes c ON c.id = tcs.class_id
            INNER JOIN student_class_enrollments sce ON sce.class_id = c.id
            INNER JOIN students s ON s.id = sce.student_id
            WHERE tcs.teacher_user_id = %s
              AND s.id = %s
              AND LOWER(tcs.subject) = LOWER(%s)
            LIMIT 1
            """,
            (session["user_id"], student_id, subject)
        )
        student = cur.fetchone()
        if not student:
            return {"error": "Student learning profile not found"}, 404

        metrics = fetch_student_subject_metrics(cur, student_id, subject)
        paper_metrics = fetch_student_paper_metrics(
            cur, session["user_id"], student_id,
            student["class_id"], student["subject"]
        )
        attendance_metrics = fetch_student_attendance_metrics(
            cur, student_id, student["class_id"]
        )

        cur.execute(
            """
            SELECT pa.id AS assessment_id, pa.title, pa.assessment_type,
                   pa.assessment_date, pa.max_marks, pas.marks_obtained,
                   pas.is_absent, pas.remarks
            FROM paper_assessments pa
            INNER JOIN paper_assessment_scores pas
                ON pas.assessment_id = pa.id
            WHERE pa.teacher_user_id = %s
              AND pa.class_id = %s
              AND pas.student_id = %s
              AND LOWER(pa.subject) = LOWER(%s)
              AND pa.is_published = TRUE
            ORDER BY pa.assessment_date DESC, pa.id DESC
            LIMIT 10
            """,
            (session["user_id"], student["class_id"], student_id, subject)
        )
        recent_paper_assessments = cur.fetchall()
        for assessment in recent_paper_assessments:
            assessment["assessment_date"] = serialize_api_date(
                assessment["assessment_date"]
            )
            maximum = float(assessment["max_marks"] or 0)
            marks = assessment["marks_obtained"]
            assessment["max_marks"] = maximum
            assessment["marks_obtained"] = (
                float(marks) if marks is not None else None
            )
            assessment["percentage"] = (
                round(100 * float(marks) / maximum, 2)
                if marks is not None and maximum else None
            )
            assessment["is_absent"] = bool(assessment["is_absent"])

        cur.execute(
            """
            SELECT mas.id AS attendance_summary_id, mas.attendance_month,
                   mas.total_school_days, mar.present_days,
                   (mas.total_school_days - mar.present_days) AS absent_days,
                   mar.note
            FROM monthly_attendance_summaries mas
            INNER JOIN monthly_attendance_records mar ON mar.summary_id = mas.id
            WHERE mas.class_id = %s AND mar.student_id = %s
            ORDER BY mas.attendance_month DESC, mas.id DESC
            LIMIT 12
            """,
            (student["class_id"], student_id)
        )
        recent_attendance = cur.fetchall()
        if recent_attendance:
            for record in recent_attendance:
                record["attendance_month"] = serialize_api_date(
                    record["attendance_month"]
                )
                record["total_school_days"] = int(record["total_school_days"])
                record["present_days"] = int(record["present_days"])
                record["absent_days"] = int(record["absent_days"])
        else:
            cur.execute(
                """
                SELECT ats.id AS attendance_session_id, ats.attendance_date,
                       ar.status, ar.note
                FROM attendance_sessions ats
                INNER JOIN attendance_records ar
                    ON ar.attendance_session_id = ats.id
                WHERE ats.class_id = %s AND ar.student_id = %s
                ORDER BY ats.attendance_date DESC, ats.id DESC
                LIMIT 30
                """,
                (student["class_id"], student_id)
            )
            recent_attendance = cur.fetchall()
            for record in recent_attendance:
                record["attendance_date"] = serialize_api_date(
                    record["attendance_date"]
                )

        cur.execute(
            """
            SELECT
                qar.topic,
                COUNT(*) AS total_questions,
                COUNT(DISTINCT qar.question_text) AS distinct_questions,
                COALESCE(SUM(qar.is_correct), 0) AS correct_answers,
                COALESCE(SUM(qar.is_skipped), 0) AS skipped_answers
            FROM quiz_answer_results qar
            INNER JOIN quiz_results qr ON qr.id = qar.quiz_result_id
            INNER JOIN quizzes q ON q.id = qr.quiz_id
            WHERE qr.student_id = %s
              AND LOWER(q.subject) = LOWER(%s)
            GROUP BY qar.topic
            """,
            (student_id, subject)
        )
        topics = []
        for row in cur.fetchall():
            topic_metrics = build_learning_metrics({
                **row,
                "attempts": 0
            })
            topics.append({
                "topic": row["topic"],
                "distinct_questions": int(row["distinct_questions"] or 0),
                **topic_metrics
            })
        topics.sort(key=lambda item: (item["accuracy_percent"], -item["total_questions"]))

        teacher_actions = build_teacher_actions(
            topics, metrics, paper_metrics, attendance_metrics, subject
        )

        cur.execute(
            """
            SELECT
                qar.difficulty,
                COUNT(*) AS total_questions,
                COALESCE(SUM(qar.is_correct), 0) AS correct_answers,
                COALESCE(SUM(qar.is_skipped), 0) AS skipped_answers
            FROM quiz_answer_results qar
            INNER JOIN quiz_results qr ON qr.id = qar.quiz_result_id
            INNER JOIN quizzes q ON q.id = qr.quiz_id
            WHERE qr.student_id = %s
              AND LOWER(q.subject) = LOWER(%s)
            GROUP BY qar.difficulty
            """,
            (student_id, subject)
        )
        difficulties = []
        for row in cur.fetchall():
            difficulty_metrics = build_learning_metrics({
                **row,
                "attempts": 0
            })
            difficulties.append({
                "difficulty": row["difficulty"],
                **difficulty_metrics
            })

        cur.execute(
            """
            SELECT
                qr.id AS attempt_id,
                q.title AS quiz_title,
                qr.score,
                qr.total_questions,
                COALESCE(SUM(qar.is_skipped), 0) AS skipped_answers
            FROM quiz_results qr
            INNER JOIN quizzes q ON q.id = qr.quiz_id
            LEFT JOIN quiz_answer_results qar ON qar.quiz_result_id = qr.id
            WHERE qr.student_id = %s
              AND LOWER(q.subject) = LOWER(%s)
            GROUP BY qr.id, q.title, qr.score, qr.total_questions
            ORDER BY qr.id DESC
            LIMIT 10
            """,
            (student_id, subject)
        )
        recent_attempts = []
        for attempt in cur.fetchall():
            total = int(attempt["total_questions"] or 0)
            score = int(attempt["score"] or 0)
            recent_attempts.append({
                **attempt,
                "score": score,
                "total_questions": total,
                "skipped_answers": int(attempt["skipped_answers"] or 0),
                "percentage": round(100 * score / total, 2) if total else 0
            })

        cur.execute(
            """
            SELECT
                qar.question_text,
                qar.topic,
                qar.difficulty,
                MAX(qar.correct_answer) AS correct_answer,
                COUNT(*) AS mistake_count
            FROM quiz_answer_results qar
            INNER JOIN quiz_results qr ON qr.id = qar.quiz_result_id
            INNER JOIN quizzes q ON q.id = qr.quiz_id
            WHERE qr.student_id = %s
              AND LOWER(q.subject) = LOWER(%s)
              AND qar.is_correct = FALSE
              AND qar.is_skipped = FALSE
            GROUP BY qar.question_text, qar.topic, qar.difficulty
            ORDER BY mistake_count DESC, qar.topic
            LIMIT 10
            """,
            (student_id, subject)
        )
        common_mistakes = cur.fetchall()
        for mistake in common_mistakes:
            mistake["mistake_count"] = int(mistake["mistake_count"] or 0)

        return {
            "student": student,
            "summary": metrics,
            "paper_assessments": paper_metrics,
            "attendance": attendance_metrics,
            "recent_paper_assessments": recent_paper_assessments,
            "recent_attendance": recent_attendance,
            "topics": topics,
            "teacher_actions": teacher_actions,
            "difficulties": difficulties,
            "recent_attempts": recent_attempts,
            "common_mistakes": common_mistakes
        }, 200

    finally:
        cur.close()


# ============================================================
# TEACHER SUPPORT INTERVENTIONS
# ============================================================

INTERVENTION_SOURCES = {"topic", "paper", "attendance", "manual"}
INTERVENTION_STATUSES = {"planned", "in_progress", "completed", "cancelled"}


def fetch_teacher_support_class_id(cur, teacher_id, student_id, subject):
    cur.execute(
        """
        SELECT tcs.class_id
        FROM teacher_class_subjects tcs
        INNER JOIN student_class_enrollments sce ON sce.class_id = tcs.class_id
        INNER JOIN students s ON s.id = sce.student_id
        WHERE tcs.teacher_user_id = %s
          AND s.id = %s
          AND LOWER(tcs.subject) = LOWER(%s)
        LIMIT 1
        """,
        (teacher_id, student_id, subject)
    )
    row = cur.fetchone()
    return int(row["class_id"]) if row else None


def teacher_can_support_student(cur, teacher_id, student_id, subject):
    return fetch_teacher_support_class_id(
        cur, teacher_id, student_id, subject
    ) is not None


def capture_intervention_snapshot(
    cur, teacher_id, student_id, class_id, subject
):
    quiz = fetch_student_subject_metrics(cur, student_id, subject)
    paper = fetch_student_paper_metrics(
        cur, teacher_id, student_id, class_id, subject
    )
    attendance = fetch_student_attendance_metrics(cur, student_id, class_id)
    return {
        "quiz_accuracy": (
            float(quiz["accuracy_percent"])
            if int(quiz["total_questions"] or 0) else None
        ),
        "quiz_questions": int(quiz["total_questions"] or 0),
        "paper_average": (
            float(paper["average_percent"])
            if int(paper["graded_assessments"] or 0) else None
        ),
        "paper_assessments": int(paper["graded_assessments"] or 0),
        "attendance_percent": (
            float(attendance["attendance_percent"])
            if int(attendance["recorded_days"] or 0) else None
        ),
        "attendance_days": int(attendance["recorded_days"] or 0)
    }


def intervention_effectiveness(cur, row):
    class_id = fetch_teacher_support_class_id(
        cur, row["teacher_user_id"], row["student_id"], row["subject"]
    )
    if class_id is None:
        return {"available": False, "reason": "Student assignment changed"}
    current = capture_intervention_snapshot(
        cur, row["teacher_user_id"], row["student_id"], class_id,
        row["subject"]
    )
    baseline = {
        "quiz_accuracy": (
            float(row["baseline_quiz_accuracy"])
            if row.get("baseline_quiz_accuracy") is not None else None
        ),
        "quiz_questions": int(row.get("baseline_quiz_questions") or 0),
        "paper_average": (
            float(row["baseline_paper_average"])
            if row.get("baseline_paper_average") is not None else None
        ),
        "paper_assessments": int(row.get("baseline_paper_assessments") or 0),
        "attendance_percent": (
            float(row["baseline_attendance_percent"])
            if row.get("baseline_attendance_percent") is not None else None
        ),
        "attendance_days": int(row.get("baseline_attendance_days") or 0)
    }
    deltas = {}
    for name in ("quiz_accuracy", "paper_average", "attendance_percent"):
        before = baseline[name]
        after = current[name]
        deltas[name] = (
            round(after - before, 2)
            if before is not None and after is not None else None
        )
    available = row.get("baseline_captured_at") is not None
    return {
        "available": available,
        "baseline": baseline,
        "current": current,
        "delta": deltas,
        "note": (
            "Observed change after the plan was created; this does not prove causation."
            if available else "No baseline is available for this older plan."
        )
    }


def normalize_intervention_payload(data, existing=None):
    if not isinstance(data, dict):
        raise ValueError("Support plan data is required")
    current = existing or {}
    subject = str(data.get("subject", current.get("subject", "")) or "").strip()
    source_kind = str(
        data.get("source_kind", current.get("source_kind", "manual")) or "manual"
    ).strip().lower()
    focus_area = str(
        data.get("focus_area", current.get("focus_area", "")) or ""
    ).strip()
    evidence = str(data.get("evidence", current.get("evidence", "")) or "").strip()
    action_plan = str(
        data.get("action_plan", current.get("action_plan", "")) or ""
    ).strip()
    success_criteria = str(
        data.get("success_criteria", current.get("success_criteria", "")) or ""
    ).strip()
    status = str(
        data.get("status", current.get("status", "planned")) or "planned"
    ).strip().lower()
    outcome_note = str(
        data.get("outcome_note", current.get("outcome_note", "")) or ""
    ).strip()
    review_value = data.get("review_date", current.get("review_date"))
    review_date = None
    if review_value:
        try:
            review_date = datetime.strptime(
                str(review_value)[:10], "%Y-%m-%d"
            ).date().isoformat()
        except ValueError as error:
            raise ValueError("Review date must use YYYY-MM-DD") from error
    if not subject or len(subject) > 100:
        raise ValueError("Subject is required and must be at most 100 characters")
    if source_kind not in INTERVENTION_SOURCES:
        raise ValueError("Support plan source is invalid")
    if not focus_area or len(focus_area) > 150:
        raise ValueError("Focus area is required and must be at most 150 characters")
    if len(evidence) > 500:
        raise ValueError("Evidence must be at most 500 characters")
    if not 10 <= len(action_plan) <= 2000:
        raise ValueError("Action plan must contain 10 to 2000 characters")
    if len(success_criteria) > 500:
        raise ValueError("Success criteria must be at most 500 characters")
    if status not in INTERVENTION_STATUSES:
        raise ValueError("Support plan status is invalid")
    if len(outcome_note) > 1000:
        raise ValueError("Outcome note must be at most 1000 characters")
    if status == "completed" and not outcome_note:
        raise ValueError("An outcome note is required before completing a plan")
    return {
        "subject": subject,
        "source_kind": source_kind,
        "focus_area": focus_area,
        "evidence": evidence,
        "action_plan": action_plan,
        "success_criteria": success_criteria,
        "status": status,
        "review_date": review_date,
        "outcome_note": outcome_note
    }


def serialize_intervention(row, cur=None):
    if not row:
        return row
    for field in (
        "review_date", "completed_at", "created_at", "updated_at",
        "baseline_captured_at"
    ):
        if field in row:
            row[field] = serialize_api_date(row[field])
    if cur is not None:
        row["effectiveness"] = intervention_effectiveness(cur, row)
    return row


def fetch_teacher_intervention(cur, intervention_id, teacher_id):
    cur.execute(
        """
        SELECT i.*, s.full_name
        FROM teacher_interventions i
        INNER JOIN students s ON s.id = i.student_id
        WHERE i.id = %s AND i.teacher_user_id = %s
        """,
        (intervention_id, teacher_id)
    )
    return serialize_intervention(cur.fetchone())


@app.route("/api/teacher/students/<int:student_id>/interventions",
           methods=["GET", "POST"])
@login_required
@role_required(TEACHER)
def teacher_student_interventions_api(student_id):
    data = request.get_json(silent=True) if request.method == "POST" else None
    subject = str(
        (data or {}).get("subject") or request.args.get("subject") or ""
    ).strip()
    if not subject:
        return {"error": "Subject is required"}, 400
    cur = mysql.connection.cursor()
    try:
        class_id = fetch_teacher_support_class_id(
            cur, session["user_id"], student_id, subject
        )
        if class_id is None:
            return {"error": "Student support profile not found"}, 404
        if request.method == "GET":
            cur.execute(
                """
                SELECT i.*, s.full_name
                FROM teacher_interventions i
                INNER JOIN students s ON s.id = i.student_id
                WHERE i.teacher_user_id = %s
                  AND i.student_id = %s
                  AND LOWER(i.subject) = LOWER(%s)
                ORDER BY
                  CASE i.status
                    WHEN 'in_progress' THEN 1 WHEN 'planned' THEN 2
                    WHEN 'completed' THEN 3 ELSE 4
                  END,
                  i.review_date, i.id DESC
                """,
                (session["user_id"], student_id, subject)
            )
            rows = cur.fetchall()
            return {
                "interventions": [
                    serialize_intervention(row, cur) for row in rows
                ]
            }, 200
        try:
            plan = normalize_intervention_payload(data)
        except ValueError as error:
            return {"error": str(error)}, 400
        baseline = capture_intervention_snapshot(
            cur, session["user_id"], student_id, class_id, plan["subject"]
        )
        cur.execute(
            """
            INSERT INTO teacher_interventions
                (teacher_user_id, student_id, subject, source_kind,
                 focus_area, evidence, action_plan, success_criteria,
                 status, review_date, outcome_note,
                 baseline_quiz_accuracy, baseline_quiz_questions,
                 baseline_paper_average, baseline_paper_assessments,
                 baseline_attendance_percent, baseline_attendance_days,
                 baseline_captured_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """,
            (session["user_id"], student_id, plan["subject"],
             plan["source_kind"], plan["focus_area"], plan["evidence"],
             plan["action_plan"], plan["success_criteria"], plan["status"],
             plan["review_date"], plan["outcome_note"],
             baseline["quiz_accuracy"], baseline["quiz_questions"],
             baseline["paper_average"], baseline["paper_assessments"],
             baseline["attendance_percent"], baseline["attendance_days"])
        )
        intervention_id = cur.lastrowid
        mysql.connection.commit()
        return {
            "message": "Student support plan created",
            "intervention_id": intervention_id
        }, 201
    except Exception as error:
        mysql.connection.rollback()
        print("Teacher intervention error:", error)
        return {"error": "Failed to manage student support plan"}, 500
    finally:
        cur.close()


@app.route("/api/teacher/interventions/<int:intervention_id>",
           methods=["PUT", "DELETE"])
@login_required
@role_required(TEACHER)
def teacher_intervention_api(intervention_id):
    cur = mysql.connection.cursor()
    try:
        existing = fetch_teacher_intervention(
            cur, intervention_id, session["user_id"]
        )
        if not existing:
            return {"error": "Student support plan not found"}, 404
        if request.method == "DELETE":
            cur.execute(
                "DELETE FROM teacher_interventions "
                "WHERE id = %s AND teacher_user_id = %s",
                (intervention_id, session["user_id"])
            )
            mysql.connection.commit()
            return {"message": "Student support plan deleted"}, 200
        try:
            plan = normalize_intervention_payload(
                request.get_json(silent=True), existing
            )
        except ValueError as error:
            return {"error": str(error)}, 400
        if not teacher_can_support_student(
            cur, session["user_id"], existing["student_id"], plan["subject"]
        ):
            return {"error": "Student support profile not found"}, 404
        cur.execute(
            """
            UPDATE teacher_interventions
            SET subject = %s, source_kind = %s, focus_area = %s,
                evidence = %s, action_plan = %s, success_criteria = %s,
                status = %s, review_date = %s, outcome_note = %s,
                completed_at = CASE WHEN %s = 'completed'
                    THEN COALESCE(completed_at, CURRENT_TIMESTAMP) ELSE NULL END
            WHERE id = %s AND teacher_user_id = %s
            """,
            (plan["subject"], plan["source_kind"], plan["focus_area"],
             plan["evidence"], plan["action_plan"], plan["success_criteria"],
             plan["status"], plan["review_date"], plan["outcome_note"],
             plan["status"], intervention_id, session["user_id"])
        )
        mysql.connection.commit()
        return {"message": "Student support plan updated"}, 200
    except Exception as error:
        mysql.connection.rollback()
        print("Teacher intervention update error:", error)
        return {"error": "Failed to update student support plan"}, 500
    finally:
        cur.close()


@app.route("/api/student/interventions", methods=["GET"])
@login_required
@role_required(STUDENT)
def student_interventions_api():
    cur = mysql.connection.cursor()
    try:
        cur.execute(
            """
            SELECT i.id, i.subject, i.source_kind, i.focus_area, i.evidence,
                   i.action_plan, i.success_criteria, i.status, i.review_date,
                   i.outcome_note, i.completed_at, i.created_at, i.updated_at,
                   i.teacher_user_id, i.student_id,
                   i.baseline_quiz_accuracy, i.baseline_quiz_questions,
                   i.baseline_paper_average, i.baseline_paper_assessments,
                   i.baseline_attendance_percent, i.baseline_attendance_days,
                   i.baseline_captured_at,
                   u.username AS teacher_name
            FROM students s
            INNER JOIN teacher_interventions i ON i.student_id = s.id
            INNER JOIN users u ON u.id = i.teacher_user_id
            WHERE s.user_id = %s AND i.status <> 'cancelled'
            ORDER BY
              CASE i.status
                WHEN 'in_progress' THEN 1 WHEN 'planned' THEN 2 ELSE 3
              END,
              i.review_date, i.id DESC
            """,
            (session["user_id"],)
        )
        rows = cur.fetchall()
        return {
            "interventions": [
                serialize_intervention(row, cur) for row in rows
            ]
        }, 200
    finally:
        cur.close()


# ============================================================
# TEACHER QUIZ MANAGEMENT
# ============================================================

def validate_teacher_quiz_payload(data):
    """Return normalized teacher quiz data or raise ValueError."""
    if not isinstance(data, dict) or not data:
        raise ValueError("Quiz data is required")

    title = str(data.get("title") or "").strip()
    subject = str(data.get("subject") or "").strip()
    questions = data.get("questions")
    is_published = data.get("is_published", False)

    if not title or len(title) > 200:
        raise ValueError("Quiz title is required and must be at most 200 characters")
    if not subject or len(subject) > 100:
        raise ValueError("Subject is required and must be at most 100 characters")
    if not isinstance(is_published, bool):
        raise ValueError("Published status must be true or false")
    if not isinstance(questions, list) or not 1 <= len(questions) <= 100:
        raise ValueError("A quiz must contain between 1 and 100 questions")

    normalized_questions = []
    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise ValueError(f"Question {index} is invalid")

        prompt = str(question.get("question") or "").strip()
        topic = str(question.get("topic") or "").strip()
        difficulty = str(question.get("difficulty") or "").strip().lower()
        curriculum_code = str(question.get("curriculum_code") or "unspecified").strip()
        cognitive_level = str(
            question.get("cognitive_level") or "unspecified"
        ).strip().lower()
        raw_options = question.get("options")
        answer = str(question.get("answer") or "").strip()
        explanation = str(question.get("explanation") or "").strip()

        if not prompt:
            raise ValueError(f"Question {index} text is required")
        if not topic or len(topic) > 100:
            raise ValueError(f"Question {index} topic is required")
        if difficulty not in {"easy", "medium", "hard"}:
            raise ValueError(
                f"Question {index} difficulty must be easy, medium, or hard"
            )
        if not curriculum_code or len(curriculum_code) > 50:
            raise ValueError(
                f"Question {index} curriculum code must be at most 50 characters"
            )
        if cognitive_level not in {
            "recall", "understanding", "application", "higher_order", "unspecified"
        }:
            raise ValueError(
                f"Question {index} cognitive level is invalid"
            )
        if not isinstance(raw_options, list) or not 2 <= len(raw_options) <= 6:
            raise ValueError(f"Question {index} must have between 2 and 6 options")

        options = [
            str(option).strip() if option is not None else ""
            for option in raw_options
        ]
        if any(not option for option in options) or len(set(options)) != len(options):
            raise ValueError(f"Question {index} options must be non-empty and unique")
        if answer not in options:
            raise ValueError(f"Question {index} must have a valid correct answer")

        normalized_question = {
            "question": prompt,
            "options": options,
            "answer": answer,
            "topic": topic,
            "difficulty": difficulty,
            "curriculum_code": curriculum_code,
            "cognitive_level": cognitive_level
        }
        if explanation:
            normalized_question["explanation"] = explanation
        normalized_questions.append(normalized_question)

    return {
        "title": title,
        "subject": subject,
        "questions": normalized_questions,
        "is_published": is_published
    }


@app.route("/api/teacher/quizzes", methods=["GET"])
@login_required
@role_required(TEACHER)
def teacher_quizzes_api():
    cur = mysql.connection.cursor()

    try:
        cur.execute(
            """
            SELECT
                q.id,
                q.title,
                q.subject,
                q.questions,
                q.is_published,
                q.created_at,
                (
                    SELECT COUNT(*)
                    FROM quiz_results qr
                    WHERE qr.quiz_id = q.id
                ) AS attempt_count
            FROM quizzes q
            WHERE q.created_by = %s
            ORDER BY q.id DESC
            """,
            (session["user_id"],)
        )

        quizzes = cur.fetchall()
        response_quizzes = []
        for quiz in quizzes:
            try:
                question_count = len(json.loads(quiz["questions"]))
            except (TypeError, ValueError):
                question_count = 0
            response_quizzes.append({
                "id": quiz["id"],
                "title": quiz["title"],
                "subject": quiz["subject"],
                "question_count": question_count,
                "attempt_count": int(quiz["attempt_count"] or 0),
                "is_published": bool(quiz["is_published"]),
                "created_at": quiz["created_at"]
            })

        return {"quizzes": response_quizzes}, 200

    finally:
        cur.close()


@app.route("/api/teacher/quizzes", methods=["POST"])
@login_required
@role_required(TEACHER)
def teacher_create_quiz_api():
    try:
        quiz = validate_teacher_quiz_payload(request.get_json(silent=True))
    except ValueError as error:
        return {"error": str(error)}, 400

    cur = mysql.connection.cursor()

    try:
        cur.execute(
            """
            INSERT INTO quizzes
                (title, subject, questions, created_by, is_published)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                quiz["title"],
                quiz["subject"],
                json.dumps(quiz["questions"]),
                session["user_id"],
                quiz["is_published"]
            )
        )
        mysql.connection.commit()
        return {
            "message": "Quiz created successfully",
            "quiz_id": cur.lastrowid
        }, 201

    except Exception as error:
        mysql.connection.rollback()
        print("Teacher quiz creation error:", error)
        return {"error": "Failed to create quiz"}, 500

    finally:
        cur.close()


@app.route("/api/teacher/quizzes/<int:quiz_id>", methods=["GET"])
@login_required
@role_required(TEACHER)
def teacher_quiz_detail_api(quiz_id):
    cur = mysql.connection.cursor()

    try:
        cur.execute(
            """
            SELECT id, title, subject, questions, is_published, created_at
            FROM quizzes
            WHERE id = %s AND created_by = %s
            """,
            (quiz_id, session["user_id"])
        )
        quiz = cur.fetchone()
        if not quiz:
            return {"error": "Quiz not found"}, 404

        try:
            questions = json.loads(quiz["questions"])
        except (TypeError, ValueError):
            return {"error": "Stored quiz questions are invalid"}, 500

        return {
            "quiz": {
                "id": quiz["id"],
                "title": quiz["title"],
                "subject": quiz["subject"],
                "questions": questions,
                "is_published": bool(quiz["is_published"]),
                "created_at": quiz["created_at"]
            }
        }, 200

    finally:
        cur.close()


@app.route("/api/teacher/quizzes/<int:quiz_id>", methods=["PUT"])
@login_required
@role_required(TEACHER)
def teacher_update_quiz_api(quiz_id):
    try:
        quiz = validate_teacher_quiz_payload(request.get_json(silent=True))
    except ValueError as error:
        return {"error": str(error)}, 400

    cur = mysql.connection.cursor()

    try:
        cur.execute(
            "SELECT id FROM quizzes WHERE id = %s AND created_by = %s",
            (quiz_id, session["user_id"])
        )
        if not cur.fetchone():
            return {"error": "Quiz not found"}, 404

        cur.execute(
            """
            UPDATE quizzes
            SET title = %s, subject = %s, questions = %s, is_published = %s
            WHERE id = %s AND created_by = %s
            """,
            (
                quiz["title"],
                quiz["subject"],
                json.dumps(quiz["questions"]),
                quiz["is_published"],
                quiz_id,
                session["user_id"]
            )
        )
        mysql.connection.commit()
        return {"message": "Quiz updated successfully"}, 200

    except Exception as error:
        mysql.connection.rollback()
        print("Teacher quiz update error:", error)
        return {"error": "Failed to update quiz"}, 500

    finally:
        cur.close()


@app.route("/api/teacher/quizzes/<int:quiz_id>", methods=["DELETE"])
@login_required
@role_required(TEACHER)
def teacher_delete_quiz_api(quiz_id):
    cur = mysql.connection.cursor()

    try:
        cur.execute(
            "SELECT id FROM quizzes WHERE id = %s AND created_by = %s",
            (quiz_id, session["user_id"])
        )
        if not cur.fetchone():
            return {"error": "Quiz not found"}, 404

        cur.execute(
            "SELECT COUNT(*) AS attempt_count FROM quiz_results WHERE quiz_id = %s",
            (quiz_id,)
        )
        if int(cur.fetchone()["attempt_count"] or 0) > 0:
            return {
                "error": "Quiz has student attempts and cannot be deleted; unpublish it instead"
            }, 409

        cur.execute(
            "DELETE FROM quizzes WHERE id = %s AND created_by = %s",
            (quiz_id, session["user_id"])
        )
        mysql.connection.commit()
        return {"message": "Quiz deleted successfully"}, 200

    except Exception as error:
        mysql.connection.rollback()
        print("Teacher quiz deletion error:", error)
        return {"error": "Failed to delete quiz"}, 500

    finally:
        cur.close()


def parse_session_datetime(value, field_name):
    """Normalize an ISO-8601 value to a naive UTC datetime for MySQL."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid ISO date and time") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def lab_session_state(lab_session, now=None):
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    starts_at = lab_session["starts_at"]
    ends_at = lab_session["ends_at"]
    if isinstance(starts_at, str):
        starts_at = datetime.fromisoformat(starts_at)
    if isinstance(ends_at, str):
        ends_at = datetime.fromisoformat(ends_at)
    if bool(lab_session["is_closed"]):
        return "closed"
    if now < starts_at:
        return "scheduled"
    if now > ends_at:
        return "ended"
    return "active"


def public_quiz_payload(quiz_data, questions):
    return {
        "id": quiz_data["id"],
        "title": quiz_data["title"],
        "subject": quiz_data["subject"],
        "questions": [{
            "question": question["question"],
            "options": question["options"],
            "topic": question["topic"],
            "difficulty": question["difficulty"],
            "curriculum_code": question["curriculum_code"],
            "cognitive_level": question["cognitive_level"]
        } for question in questions]
    }


def quiz_has_open_lab_session(cur, quiz_id, now=None):
    """Return whether a scheduled or active lab session still protects a quiz."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    cur.execute(
        """
        SELECT COUNT(*) AS session_count
        FROM quiz_sessions
        WHERE quiz_id = %s AND is_closed = FALSE AND ends_at > %s
        """,
        (quiz_id, now)
    )
    return int(cur.fetchone()["session_count"] or 0) > 0


@app.route("/api/teacher/quiz-sessions", methods=["GET", "POST"])
@login_required
@role_required(TEACHER)
def teacher_quiz_sessions_api():
    cur = mysql.connection.cursor()
    try:
        if request.method == "GET":
            cur.execute(
                """
                SELECT
                    qs.id, qs.quiz_id, qs.class_id, qs.starts_at, qs.ends_at,
                    qs.is_closed, qs.created_at, q.title, q.subject,
                    c.name AS class_name,
                    (SELECT COUNT(*) FROM quiz_results qr
                     WHERE qr.quiz_session_id = qs.id) AS submission_count
                FROM quiz_sessions qs
                INNER JOIN quizzes q ON q.id = qs.quiz_id
                INNER JOIN classes c ON c.id = qs.class_id
                WHERE qs.created_by = %s
                ORDER BY qs.starts_at DESC, qs.id DESC
                """,
                (session["user_id"],)
            )
            lab_sessions = cur.fetchall()
            for item in lab_sessions:
                item["state"] = lab_session_state(item)
                item["is_closed"] = bool(item["is_closed"])
                item["submission_count"] = int(item["submission_count"] or 0)
            return {"sessions": lab_sessions}, 200

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {"error": "Lab session data is required"}, 400
        try:
            quiz_id = int(data.get("quiz_id"))
            class_id = int(data.get("class_id"))
        except (TypeError, ValueError):
            return {"error": "Quiz and class are required"}, 400
        access_code = str(data.get("access_code") or "").strip()
        if not 4 <= len(access_code) <= 20:
            return {"error": "Access code must contain 4 to 20 characters"}, 400
        try:
            starts_at = parse_session_datetime(data.get("starts_at"), "Start time")
            ends_at = parse_session_datetime(data.get("ends_at"), "End time")
        except ValueError as error:
            return {"error": str(error)}, 400
        if ends_at <= starts_at:
            return {"error": "End time must be after start time"}, 400
        if (ends_at - starts_at).total_seconds() > 8 * 60 * 60:
            return {"error": "A lab session cannot be longer than 8 hours"}, 400

        cur.execute(
            """
            SELECT q.id
            FROM quizzes q
            INNER JOIN teacher_class_subjects tcs
                ON tcs.teacher_user_id = %s
               AND tcs.class_id = %s
               AND LOWER(tcs.subject) = LOWER(q.subject)
            WHERE q.id = %s AND q.created_by = %s AND q.is_published = TRUE
            """,
            (session["user_id"], class_id, quiz_id, session["user_id"])
        )
        if not cur.fetchone():
            return {"error": "Published quiz or class-subject assignment not found"}, 404

        cur.execute(
            """
            INSERT INTO quiz_sessions
                (quiz_id, class_id, created_by, access_code_hash, starts_at, ends_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (quiz_id, class_id, session["user_id"],
             generate_password_hash(access_code), starts_at, ends_at)
        )
        lab_session_id = cur.lastrowid
        cur.execute("UPDATE quizzes SET requires_session = TRUE WHERE id = %s", (quiz_id,))
        mysql.connection.commit()
        return {
            "message": "Lab quiz session created successfully",
            "session_id": lab_session_id,
            "access_code": access_code
        }, 201
    except Exception as error:
        mysql.connection.rollback()
        print("Lab quiz session error:", error)
        return {"error": "Failed to manage lab quiz session"}, 500
    finally:
        cur.close()


@app.route("/api/teacher/quiz-sessions/<int:lab_session_id>/close", methods=["POST"])
@login_required
@role_required(TEACHER)
def teacher_close_quiz_session_api(lab_session_id):
    cur = mysql.connection.cursor()
    try:
        cur.execute(
            "SELECT id, quiz_id FROM quiz_sessions WHERE id = %s AND created_by = %s",
            (lab_session_id, session["user_id"])
        )
        lab_session = cur.fetchone()
        if not lab_session:
            return {"error": "Lab quiz session not found"}, 404
        cur.execute(
            "UPDATE quiz_sessions SET is_closed = TRUE WHERE id = %s AND created_by = %s",
            (lab_session_id, session["user_id"])
        )
        still_protected = quiz_has_open_lab_session(cur, lab_session["quiz_id"])
        cur.execute(
            "UPDATE quizzes SET requires_session = %s WHERE id = %s",
            (still_protected, lab_session["quiz_id"])
        )
        mysql.connection.commit()
        return {"message": "Lab quiz session closed"}, 200
    except Exception as error:
        mysql.connection.rollback()
        print("Lab quiz session close error:", error)
        return {"error": "Failed to close lab quiz session"}, 500
    finally:
        cur.close()


@app.route("/api/student/quiz-sessions", methods=["GET"])
@login_required
@role_required(STUDENT)
def student_quiz_sessions_api():
    cur = mysql.connection.cursor()
    try:
        cur.execute(
            """
            SELECT s.id AS student_id
            FROM students s WHERE s.user_id = %s
            """,
            (session["user_id"],)
        )
        student = cur.fetchone()
        if not student:
            return {"error": "Student profile not found"}, 404
        cur.execute(
            """
            SELECT qs.id, qs.quiz_id, qs.class_id, qs.starts_at, qs.ends_at,
                   qs.is_closed, q.title, q.subject, c.name AS class_name,
                   (SELECT COUNT(*) FROM quiz_results qr
                    WHERE qr.quiz_session_id = qs.id
                      AND qr.student_id = %s) AS submitted
            FROM quiz_sessions qs
            INNER JOIN student_class_enrollments sce
                ON sce.class_id = qs.class_id AND sce.student_id = %s
            INNER JOIN quizzes q ON q.id = qs.quiz_id AND q.is_published = TRUE
            INNER JOIN classes c ON c.id = qs.class_id
            ORDER BY qs.starts_at DESC, qs.id DESC
            """,
            (student["student_id"], student["student_id"])
        )
        lab_sessions = cur.fetchall()
        for item in lab_sessions:
            item["state"] = "submitted" if int(item["submitted"] or 0) else lab_session_state(item)
            item["submitted"] = bool(item["submitted"])
            item["is_closed"] = bool(item["is_closed"])
        return {"sessions": lab_sessions}, 200
    finally:
        cur.close()


@app.route("/api/student/quiz-sessions/<int:lab_session_id>/start", methods=["POST"])
@login_required
@role_required(STUDENT)
def student_start_quiz_session_api(lab_session_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Access code is required"}, 400
    access_code = str(data.get("access_code") or "").strip()
    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT id FROM students WHERE user_id = %s", (session["user_id"],))
        student = cur.fetchone()
        if not student:
            return {"error": "Student profile not found"}, 404
        cur.execute(
            """
            SELECT qs.id AS session_id, qs.quiz_id, qs.starts_at, qs.ends_at,
                   qs.is_closed, qs.access_code_hash,
                   q.id, q.title, q.subject, q.questions
            FROM quiz_sessions qs
            INNER JOIN quizzes q ON q.id = qs.quiz_id AND q.is_published = TRUE
            INNER JOIN student_class_enrollments sce
                ON sce.class_id = qs.class_id AND sce.student_id = %s
            WHERE qs.id = %s
            """,
            (student["id"], lab_session_id)
        )
        lab_session = cur.fetchone()
        if not lab_session:
            return {"error": "Lab quiz session not found"}, 404
        if lab_session_state(lab_session) != "active":
            return {"error": "Lab quiz session is not active"}, 409
        if not check_password_hash(lab_session["access_code_hash"], access_code):
            return {"error": "Invalid access code"}, 403
        cur.execute(
            "SELECT COUNT(*) AS attempts FROM quiz_results WHERE quiz_session_id = %s AND student_id = %s",
            (lab_session_id, student["id"])
        )
        if int(cur.fetchone()["attempts"] or 0) > 0:
            return {"error": "This lab quiz has already been submitted"}, 409
        try:
            questions = parse_quiz_questions(lab_session["questions"], lab_session["subject"])
        except (TypeError, ValueError):
            return {"error": "Quiz questions are invalid"}, 500
        access = dict(session.get("lab_quiz_access") or {})
        access[str(lab_session_id)] = True
        session["lab_quiz_access"] = access
        return {
            "session_id": lab_session_id,
            "quiz": public_quiz_payload(lab_session, questions)
        }, 200
    finally:
        cur.close()


# ============================================================
# TEACHER PAPER-BASED ASSESSMENTS
# ============================================================

PAPER_ASSESSMENT_TYPES = {
    "class_test", "unit_test", "terminal_exam", "assignment", "practical"
}


def validate_paper_assessment_payload(data):
    if not isinstance(data, dict):
        raise ValueError("Assessment data is required")
    title = str(data.get("title") or "").strip()
    subject = str(data.get("subject") or "").strip()
    assessment_type = str(data.get("assessment_type") or "").strip().lower()
    academic_year = str(data.get("academic_year") or "").strip()
    term = str(data.get("term") or "").strip()
    try:
        class_id = int(data.get("class_id"))
    except (TypeError, ValueError) as error:
        raise ValueError("Class is required") from error
    try:
        assessment_date = datetime.strptime(
            str(data.get("assessment_date") or ""), "%Y-%m-%d"
        ).date()
    except ValueError as error:
        raise ValueError("Assessment date must use YYYY-MM-DD") from error
    try:
        max_marks = round(float(data.get("max_marks")), 2)
    except (TypeError, ValueError) as error:
        raise ValueError("Maximum marks must be a number") from error

    if not 2 <= len(title) <= 150:
        raise ValueError("Title must contain 2 to 150 characters")
    if not subject or len(subject) > 100:
        raise ValueError("Subject is required and must be at most 100 characters")
    if assessment_type not in PAPER_ASSESSMENT_TYPES:
        raise ValueError("Assessment type is invalid")
    if not 0 < max_marks <= 1000:
        raise ValueError("Maximum marks must be greater than 0 and at most 1000")
    if len(academic_year) > 20:
        raise ValueError("Academic year must be at most 20 characters")
    if len(term) > 50:
        raise ValueError("Term must be at most 50 characters")

    return {
        "class_id": class_id,
        "subject": subject,
        "title": title,
        "assessment_type": assessment_type,
        "assessment_date": assessment_date.isoformat(),
        "max_marks": max_marks,
        "academic_year": academic_year,
        "term": term,
        "is_published": bool(data.get("is_published", False))
    }


def teacher_has_class_subject(cur, teacher_id, class_id, subject):
    cur.execute(
        """
        SELECT id FROM teacher_class_subjects
        WHERE teacher_user_id = %s AND class_id = %s
          AND LOWER(subject) = LOWER(%s)
        """,
        (teacher_id, class_id, subject)
    )
    return bool(cur.fetchone())


def fetch_teacher_paper_assessment(cur, assessment_id, teacher_id):
    cur.execute(
        """
        SELECT pa.id, pa.teacher_user_id, pa.class_id, pa.subject, pa.title,
               pa.assessment_type, pa.assessment_date, pa.max_marks,
               pa.academic_year, pa.term, pa.is_published, pa.created_at,
               c.name AS class_name, c.grade, c.section
        FROM paper_assessments pa
        INNER JOIN classes c ON c.id = pa.class_id
        WHERE pa.id = %s AND pa.teacher_user_id = %s
        """,
        (assessment_id, teacher_id)
    )
    assessment = cur.fetchone()
    if assessment:
        assessment["max_marks"] = float(assessment["max_marks"])
        assessment["is_published"] = bool(assessment["is_published"])
    return assessment


@app.route("/api/teacher/paper-assessments", methods=["GET", "POST"])
@login_required
@role_required(TEACHER)
def teacher_paper_assessments_api():
    cur = mysql.connection.cursor()
    try:
        if request.method == "GET":
            cur.execute(
                """
                SELECT pa.id, pa.class_id, pa.subject, pa.title,
                       pa.assessment_type, pa.assessment_date, pa.max_marks,
                       pa.academic_year, pa.term, pa.is_published,
                       c.name AS class_name,
                       (SELECT COUNT(*) FROM paper_assessment_scores pas
                        WHERE pas.assessment_id = pa.id) AS recorded_students
                FROM paper_assessments pa
                INNER JOIN classes c ON c.id = pa.class_id
                WHERE pa.teacher_user_id = %s
                ORDER BY pa.assessment_date DESC, pa.id DESC
                """,
                (session["user_id"],)
            )
            assessments = cur.fetchall()
            for item in assessments:
                item["max_marks"] = float(item["max_marks"])
                item["is_published"] = bool(item["is_published"])
                item["recorded_students"] = int(item["recorded_students"] or 0)
            return {"assessments": assessments}, 200

        try:
            assessment = validate_paper_assessment_payload(
                request.get_json(silent=True)
            )
        except ValueError as error:
            return {"error": str(error)}, 400
        if not teacher_has_class_subject(
            cur, session["user_id"], assessment["class_id"], assessment["subject"]
        ):
            return {"error": "Class-subject assignment not found"}, 404
        cur.execute(
            """
            INSERT INTO paper_assessments
                (teacher_user_id, class_id, subject, title, assessment_type,
                 assessment_date, max_marks, academic_year, term, is_published)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (session["user_id"], assessment["class_id"], assessment["subject"],
             assessment["title"], assessment["assessment_type"],
             assessment["assessment_date"], assessment["max_marks"],
             assessment["academic_year"], assessment["term"],
             assessment["is_published"])
        )
        assessment_id = cur.lastrowid
        mysql.connection.commit()
        return {
            "message": "Paper assessment created successfully",
            "assessment_id": assessment_id
        }, 201
    except Exception as error:
        mysql.connection.rollback()
        print("Paper assessment error:", error)
        return {"error": "Failed to manage paper assessment"}, 500
    finally:
        cur.close()


@app.route("/api/teacher/paper-assessments/<int:assessment_id>",
           methods=["GET", "PUT", "DELETE"])
@login_required
@role_required(TEACHER)
def teacher_paper_assessment_api(assessment_id):
    cur = mysql.connection.cursor()
    try:
        existing = fetch_teacher_paper_assessment(
            cur, assessment_id, session["user_id"]
        )
        if not existing:
            return {"error": "Paper assessment not found"}, 404

        if request.method == "DELETE":
            cur.execute(
                "DELETE FROM paper_assessments WHERE id = %s AND teacher_user_id = %s",
                (assessment_id, session["user_id"])
            )
            mysql.connection.commit()
            return {"message": "Paper assessment deleted"}, 200

        if request.method == "PUT":
            try:
                assessment = validate_paper_assessment_payload(
                    request.get_json(silent=True)
                )
            except ValueError as error:
                return {"error": str(error)}, 400
            if not teacher_has_class_subject(
                cur, session["user_id"], assessment["class_id"],
                assessment["subject"]
            ):
                return {"error": "Class-subject assignment not found"}, 404
            cur.execute(
                """
                SELECT COUNT(*) AS score_count,
                       MAX(marks_obtained) AS highest_marks
                FROM paper_assessment_scores
                WHERE assessment_id = %s
                """,
                (assessment_id,)
            )
            score_summary = cur.fetchone()
            if int(score_summary["score_count"] or 0) > 0:
                if int(assessment["class_id"]) != int(existing["class_id"]):
                    return {
                        "error": "Class cannot be changed after marks are recorded"
                    }, 409
                highest_marks = score_summary["highest_marks"]
                if (
                    highest_marks is not None
                    and float(highest_marks) > assessment["max_marks"]
                ):
                    return {
                        "error": "Maximum marks cannot be lower than a recorded score"
                    }, 409
            cur.execute(
                """
                UPDATE paper_assessments
                SET class_id = %s, subject = %s, title = %s,
                    assessment_type = %s, assessment_date = %s,
                    max_marks = %s, academic_year = %s, term = %s,
                    is_published = %s
                WHERE id = %s AND teacher_user_id = %s
                """,
                (assessment["class_id"], assessment["subject"], assessment["title"],
                 assessment["assessment_type"], assessment["assessment_date"],
                 assessment["max_marks"], assessment["academic_year"],
                 assessment["term"], assessment["is_published"], assessment_id,
                 session["user_id"])
            )
            mysql.connection.commit()
            return {"message": "Paper assessment updated"}, 200

        cur.execute(
            """
            SELECT s.id AS student_id, s.full_name, s.grade,
                   pas.marks_obtained, pas.is_absent, pas.remarks
            FROM student_class_enrollments sce
            INNER JOIN students s ON s.id = sce.student_id
            LEFT JOIN paper_assessment_scores pas
                ON pas.student_id = s.id AND pas.assessment_id = %s
            WHERE sce.class_id = %s
            ORDER BY s.full_name, s.id
            """,
            (assessment_id, existing["class_id"])
        )
        students = cur.fetchall()
        for student in students:
            student["is_absent"] = bool(student["is_absent"] or False)
            if student["marks_obtained"] is not None:
                student["marks_obtained"] = float(student["marks_obtained"])
                student["percentage"] = round(
                    100 * student["marks_obtained"] / existing["max_marks"], 2
                )
            else:
                student["percentage"] = None
        return {"assessment": existing, "students": students}, 200
    except Exception as error:
        mysql.connection.rollback()
        print("Paper assessment detail error:", error)
        return {"error": "Failed to manage paper assessment"}, 500
    finally:
        cur.close()


@app.route("/api/teacher/paper-assessments/<int:assessment_id>/scores",
           methods=["PUT"])
@login_required
@role_required(TEACHER)
def teacher_paper_assessment_scores_api(assessment_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("scores"), list):
        return {"error": "Scores must be provided as a list"}, 400
    publish = data.get("is_published")
    if publish is not None and not isinstance(publish, bool):
        return {"error": "Publish status must be true or false"}, 400

    cur = mysql.connection.cursor()
    try:
        assessment = fetch_teacher_paper_assessment(
            cur, assessment_id, session["user_id"]
        )
        if not assessment:
            return {"error": "Paper assessment not found"}, 404
        cur.execute(
            """
            SELECT s.id FROM student_class_enrollments sce
            INNER JOIN students s ON s.id = sce.student_id
            WHERE sce.class_id = %s
            """,
            (assessment["class_id"],)
        )
        enrolled_ids = {int(row["id"]) for row in cur.fetchall()}
        normalized = []
        seen_ids = set()
        for index, score in enumerate(data["scores"], start=1):
            if not isinstance(score, dict):
                return {"error": f"Score {index} is invalid"}, 400
            try:
                student_id = int(score.get("student_id"))
            except (TypeError, ValueError):
                return {"error": f"Score {index} requires a student"}, 400
            if student_id not in enrolled_ids:
                return {"error": "Score contains a student outside this class"}, 400
            if student_id in seen_ids:
                return {"error": "Each student can appear only once"}, 400
            seen_ids.add(student_id)
            raw_is_absent = score.get("is_absent", False)
            if not isinstance(raw_is_absent, (bool, int)) or raw_is_absent not in {
                False, True, 0, 1
            }:
                return {"error": "Absent status must be true or false"}, 400
            is_absent = bool(raw_is_absent)
            marks = score.get("marks_obtained")
            if is_absent:
                marks = None
            else:
                try:
                    marks = round(float(marks), 2)
                except (TypeError, ValueError):
                    return {"error": "Marks are required for present students"}, 400
                if not 0 <= marks <= assessment["max_marks"]:
                    return {
                        "error": f"Marks must be between 0 and {assessment['max_marks']}"
                    }, 400
            remarks = str(score.get("remarks") or "").strip()
            if len(remarks) > 500:
                return {"error": "Remarks must be at most 500 characters"}, 400
            normalized.append((student_id, marks, is_absent, remarks))

        if publish is True and (not enrolled_ids or seen_ids != enrolled_ids):
            return {"error": "Record marks or absence for every enrolled student before publishing"}, 400

        cur.execute(
            "DELETE FROM paper_assessment_scores WHERE assessment_id = %s",
            (assessment_id,)
        )
        for student_id, marks, is_absent, remarks in normalized:
            cur.execute(
                """
                INSERT INTO paper_assessment_scores
                    (assessment_id, student_id, marks_obtained, is_absent, remarks)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (assessment_id, student_id, marks, is_absent, remarks)
            )
        if publish is not None:
            cur.execute(
                """UPDATE paper_assessments SET is_published = %s
                   WHERE id = %s AND teacher_user_id = %s""",
                (publish, assessment_id, session["user_id"])
            )
        mysql.connection.commit()
        return {
            "message": "Paper assessment scores saved",
            "recorded_students": len(normalized)
        }, 200
    except Exception as error:
        mysql.connection.rollback()
        print("Paper assessment scores error:", error)
        return {"error": "Failed to save paper assessment scores"}, 500
    finally:
        cur.close()


# ============================================================
# TEACHER MONTHLY CLASS ATTENDANCE
# ============================================================


def serialize_api_date(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def teacher_has_class_assignment(cur, teacher_id, class_id):
    cur.execute(
        """
        SELECT id FROM class_teacher_assignments
        WHERE teacher_user_id = %s AND class_id = %s
        """,
        (teacher_id, class_id)
    )
    return cur.fetchone() is not None


def validate_attendance_summary_payload(data):
    if not isinstance(data, dict):
        raise ValueError("Monthly attendance data is required")
    try:
        class_id = int(data.get("class_id"))
    except (TypeError, ValueError) as error:
        raise ValueError("Class is required") from error
    try:
        attendance_month = datetime.strptime(
            str(data.get("attendance_month") or ""), "%Y-%m"
        ).date().replace(day=1)
    except ValueError as error:
        raise ValueError("Attendance month must use YYYY-MM") from error
    try:
        total_school_days = int(data.get("total_school_days"))
    except (TypeError, ValueError) as error:
        raise ValueError("Total school days must be a whole number") from error
    if not 1 <= total_school_days <= 31:
        raise ValueError("Total school days must be between 1 and 31")
    return {
        "class_id": class_id,
        "attendance_month": attendance_month.isoformat(),
        "total_school_days": total_school_days
    }


def fetch_teacher_attendance_summary(cur, summary_id, teacher_id):
    cur.execute(
        """
        SELECT mas.id, mas.teacher_user_id, mas.class_id,
               mas.attendance_month, mas.total_school_days, mas.created_at,
               c.name AS class_name, c.grade, c.section
        FROM monthly_attendance_summaries mas
        INNER JOIN classes c ON c.id = mas.class_id
        WHERE mas.id = %s AND mas.teacher_user_id = %s
        """,
        (summary_id, teacher_id)
    )
    attendance = cur.fetchone()
    if attendance:
        attendance["attendance_month"] = serialize_api_date(
            attendance["attendance_month"]
        )
        attendance["total_school_days"] = int(attendance["total_school_days"])
    return attendance


@app.route("/api/teacher/monthly-attendance", methods=["GET", "POST"])
@login_required
@role_required(TEACHER)
def teacher_monthly_attendance_api():
    cur = mysql.connection.cursor()
    try:
        if request.method == "GET":
            cur.execute(
                """
                SELECT c.id AS class_id, c.name AS class_name,
                       c.grade, c.section
                FROM class_teacher_assignments cta
                INNER JOIN classes c ON c.id = cta.class_id
                WHERE cta.teacher_user_id = %s
                ORDER BY c.grade, c.section, c.name
                """,
                (session["user_id"],)
            )
            assigned_classes = cur.fetchall()
            cur.execute(
                """
                SELECT mas.id, mas.class_id, mas.attendance_month,
                       mas.total_school_days, c.name AS class_name,
                       COUNT(mar.id) AS recorded_students,
                       COALESCE(SUM(mar.present_days), 0) AS present_days,
                       COALESCE(SUM(mas.total_school_days - mar.present_days), 0)
                           AS absent_days
                FROM monthly_attendance_summaries mas
                INNER JOIN classes c ON c.id = mas.class_id
                LEFT JOIN monthly_attendance_records mar ON mar.summary_id = mas.id
                WHERE mas.teacher_user_id = %s
                GROUP BY mas.id, mas.class_id, mas.attendance_month,
                         mas.total_school_days, c.name
                ORDER BY mas.attendance_month DESC, mas.id DESC
                """,
                (session["user_id"],)
            )
            summaries = cur.fetchall()
            for item in summaries:
                item["attendance_month"] = serialize_api_date(
                    item["attendance_month"]
                )
                for field in (
                    "total_school_days", "recorded_students", "present_days",
                    "absent_days"
                ):
                    item[field] = int(item[field] or 0)
            return {
                "assigned_classes": assigned_classes,
                "summaries": summaries
            }, 200

        try:
            attendance = validate_attendance_summary_payload(
                request.get_json(silent=True)
            )
        except ValueError as error:
            return {"error": str(error)}, 400
        if not teacher_has_class_assignment(
            cur, session["user_id"], attendance["class_id"]
        ):
            return {"error": "Class teacher assignment not found"}, 404
        cur.execute(
            """
            SELECT id FROM monthly_attendance_summaries
            WHERE class_id = %s AND attendance_month = %s
            """,
            (attendance["class_id"], attendance["attendance_month"])
        )
        if cur.fetchone():
            return {
                "error": "Attendance already exists for this class and month"
            }, 409
        cur.execute(
            """
            INSERT INTO monthly_attendance_summaries
                (teacher_user_id, class_id, attendance_month, total_school_days)
            VALUES (%s, %s, %s, %s)
            """,
            (session["user_id"], attendance["class_id"],
             attendance["attendance_month"], attendance["total_school_days"])
        )
        summary_id = cur.lastrowid
        mysql.connection.commit()
        return {
            "message": "Monthly attendance summary created",
            "attendance_summary_id": summary_id
        }, 201
    except Exception as error:
        mysql.connection.rollback()
        print("Attendance session error:", error)
        return {"error": "Failed to manage attendance session"}, 500
    finally:
        cur.close()


@app.route("/api/teacher/monthly-attendance/<int:summary_id>",
           methods=["GET", "PUT", "DELETE"])
@login_required
@role_required(TEACHER)
def teacher_monthly_attendance_detail_api(summary_id):
    cur = mysql.connection.cursor()
    try:
        attendance = fetch_teacher_attendance_summary(
            cur, summary_id, session["user_id"]
        )
        if not attendance:
            return {"error": "Monthly attendance summary not found"}, 404
        if request.method == "DELETE":
            cur.execute(
                "DELETE FROM monthly_attendance_summaries WHERE id = %s AND teacher_user_id = %s",
                (summary_id, session["user_id"])
            )
            mysql.connection.commit()
            return {"message": "Monthly attendance summary deleted"}, 200
        if request.method == "PUT":
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return {"error": "Monthly attendance data is required"}, 400
            try:
                total_school_days = int(data.get("total_school_days"))
            except (TypeError, ValueError):
                return {"error": "Total school days must be a whole number"}, 400
            if not 1 <= total_school_days <= 31:
                return {"error": "Total school days must be between 1 and 31"}, 400
            cur.execute(
                "SELECT COALESCE(MAX(present_days), 0) AS maximum_present_days "
                "FROM monthly_attendance_records WHERE summary_id = %s",
                (summary_id,)
            )
            maximum_present_days = int(
                cur.fetchone()["maximum_present_days"] or 0
            )
            if maximum_present_days > total_school_days:
                return {
                    "error": (
                        "Total school days cannot be lower than an existing "
                        f"present-days value ({maximum_present_days})"
                    )
                }, 400
            cur.execute(
                "UPDATE monthly_attendance_summaries "
                "SET total_school_days = %s WHERE id = %s",
                (total_school_days, summary_id)
            )
            mysql.connection.commit()
            return {
                "message": "Total school days updated",
                "total_school_days": total_school_days
            }, 200

        cur.execute(
            """
            SELECT s.id AS student_id, s.full_name, s.grade,
                   mar.present_days, mar.note
            FROM student_class_enrollments sce
            INNER JOIN students s ON s.id = sce.student_id
            LEFT JOIN monthly_attendance_records mar
                ON mar.student_id = s.id AND mar.summary_id = %s
            WHERE sce.class_id = %s
            ORDER BY s.full_name, s.id
            """,
            (summary_id, attendance["class_id"])
        )
        return {"summary": attendance, "students": cur.fetchall()}, 200
    except Exception as error:
        mysql.connection.rollback()
        print("Attendance detail error:", error)
        return {"error": "Failed to manage attendance session"}, 500
    finally:
        cur.close()


@app.route(
    "/api/teacher/monthly-attendance/<int:summary_id>/records",
    methods=["PUT"]
)
@login_required
@role_required(TEACHER)
def teacher_monthly_attendance_records_api(summary_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        return {"error": "Attendance records must be provided as a list"}, 400
    cur = mysql.connection.cursor()
    try:
        attendance = fetch_teacher_attendance_summary(
            cur, summary_id, session["user_id"]
        )
        if not attendance:
            return {"error": "Monthly attendance summary not found"}, 404
        cur.execute(
            "SELECT student_id FROM student_class_enrollments WHERE class_id = %s",
            (attendance["class_id"],)
        )
        enrolled_ids = {int(row["student_id"]) for row in cur.fetchall()}
        normalized = []
        seen_ids = set()
        for index, record in enumerate(data["records"], start=1):
            if not isinstance(record, dict):
                return {"error": f"Attendance record {index} is invalid"}, 400
            try:
                student_id = int(record.get("student_id"))
            except (TypeError, ValueError):
                return {"error": f"Attendance record {index} requires a student"}, 400
            if student_id not in enrolled_ids:
                return {"error": "Attendance contains a student outside this class"}, 400
            if student_id in seen_ids:
                return {"error": "Each student can appear only once"}, 400
            seen_ids.add(student_id)
            try:
                present_days = int(record.get("present_days"))
            except (TypeError, ValueError):
                return {"error": "Present days must be a whole number"}, 400
            if not 0 <= present_days <= attendance["total_school_days"]:
                return {
                    "error": (
                        "Present days must be between 0 and "
                        f'{attendance["total_school_days"]}'
                    )
                }, 400
            note = str(record.get("note") or "").strip()
            if len(note) > 255:
                return {"error": "Attendance note must be at most 255 characters"}, 400
            normalized.append((student_id, present_days, note))
        if seen_ids != enrolled_ids:
            return {"error": "Attendance must include every enrolled student"}, 400

        cur.execute(
            "DELETE FROM monthly_attendance_records WHERE summary_id = %s",
            (summary_id,)
        )
        for student_id, present_days, note in normalized:
            cur.execute(
                """
                INSERT INTO monthly_attendance_records
                    (summary_id, student_id, present_days, note)
                VALUES (%s, %s, %s, %s)
                """,
                (summary_id, student_id, present_days, note)
            )
        mysql.connection.commit()
        return {
            "message": "Monthly attendance saved",
            "recorded_students": len(normalized)
        }, 200
    except Exception as error:
        mysql.connection.rollback()
        print("Attendance records error:", error)
        return {"error": "Failed to save attendance"}, 500
    finally:
        cur.close()


# Legacy daily-attendance APIs remain available for historical records and
# older clients. The React teacher workflow uses the monthly APIs above.
ATTENDANCE_STATUSES = {"present", "absent", "late", "excused"}


def validate_attendance_session_payload(data):
    if not isinstance(data, dict):
        raise ValueError("Attendance session data is required")
    try:
        class_id = int(data.get("class_id"))
    except (TypeError, ValueError) as error:
        raise ValueError("Class is required") from error
    try:
        attendance_date = datetime.strptime(
            str(data.get("attendance_date") or ""), "%Y-%m-%d"
        ).date()
    except ValueError as error:
        raise ValueError("Attendance date must use YYYY-MM-DD") from error
    return {"class_id": class_id, "attendance_date": attendance_date.isoformat()}


def fetch_teacher_attendance_session(cur, attendance_session_id, teacher_id):
    cur.execute(
        """
        SELECT ats.id, ats.teacher_user_id, ats.class_id,
               ats.attendance_date, ats.created_at,
               c.name AS class_name, c.grade, c.section
        FROM attendance_sessions ats
        INNER JOIN classes c ON c.id = ats.class_id
        WHERE ats.id = %s AND ats.teacher_user_id = %s
        """,
        (attendance_session_id, teacher_id)
    )
    attendance = cur.fetchone()
    if attendance:
        attendance["attendance_date"] = serialize_api_date(
            attendance["attendance_date"]
        )
    return attendance


@app.route("/api/teacher/attendance-sessions", methods=["GET", "POST"])
@login_required
@role_required(TEACHER)
def teacher_attendance_sessions_api():
    cur = mysql.connection.cursor()
    try:
        if request.method == "GET":
            cur.execute(
                """
                SELECT c.id AS class_id, c.name AS class_name,
                       c.grade, c.section
                FROM class_teacher_assignments cta
                INNER JOIN classes c ON c.id = cta.class_id
                WHERE cta.teacher_user_id = %s
                ORDER BY c.grade, c.section, c.name
                """,
                (session["user_id"],)
            )
            assigned_classes = cur.fetchall()
            cur.execute(
                """
                SELECT ats.id, ats.class_id, ats.attendance_date,
                       c.name AS class_name,
                       COUNT(ar.id) AS recorded_students,
                       COALESCE(SUM(ar.status = 'present'), 0) AS present_count,
                       COALESCE(SUM(ar.status = 'absent'), 0) AS absent_count,
                       COALESCE(SUM(ar.status = 'late'), 0) AS late_count,
                       COALESCE(SUM(ar.status = 'excused'), 0) AS excused_count
                FROM attendance_sessions ats
                INNER JOIN classes c ON c.id = ats.class_id
                LEFT JOIN attendance_records ar ON ar.attendance_session_id = ats.id
                WHERE ats.teacher_user_id = %s
                GROUP BY ats.id, ats.class_id, ats.attendance_date, c.name
                ORDER BY ats.attendance_date DESC, ats.id DESC
                """,
                (session["user_id"],)
            )
            sessions = cur.fetchall()
            for item in sessions:
                item["attendance_date"] = serialize_api_date(item["attendance_date"])
                for field in (
                    "recorded_students", "present_count", "absent_count",
                    "late_count", "excused_count"
                ):
                    item[field] = int(item[field] or 0)
            return {"assigned_classes": assigned_classes, "sessions": sessions}, 200

        try:
            attendance = validate_attendance_session_payload(
                request.get_json(silent=True)
            )
        except ValueError as error:
            return {"error": str(error)}, 400
        if not teacher_has_class_assignment(
            cur, session["user_id"], attendance["class_id"]
        ):
            return {"error": "Class teacher assignment not found"}, 404
        cur.execute(
            "SELECT id FROM attendance_sessions WHERE class_id = %s AND attendance_date = %s",
            (attendance["class_id"], attendance["attendance_date"])
        )
        if cur.fetchone():
            return {"error": "Attendance already exists for this class and date"}, 409
        cur.execute(
            """
            INSERT INTO attendance_sessions
                (teacher_user_id, class_id, attendance_date)
            VALUES (%s, %s, %s)
            """,
            (session["user_id"], attendance["class_id"], attendance["attendance_date"])
        )
        attendance_session_id = cur.lastrowid
        mysql.connection.commit()
        return {
            "message": "Attendance session created",
            "attendance_session_id": attendance_session_id
        }, 201
    except Exception as error:
        mysql.connection.rollback()
        print("Attendance session error:", error)
        return {"error": "Failed to manage attendance session"}, 500
    finally:
        cur.close()


@app.route("/api/teacher/attendance-sessions/<int:attendance_session_id>",
           methods=["GET", "DELETE"])
@login_required
@role_required(TEACHER)
def teacher_attendance_session_api(attendance_session_id):
    cur = mysql.connection.cursor()
    try:
        attendance = fetch_teacher_attendance_session(
            cur, attendance_session_id, session["user_id"]
        )
        if not attendance:
            return {"error": "Attendance session not found"}, 404
        if request.method == "DELETE":
            cur.execute(
                "DELETE FROM attendance_sessions WHERE id = %s AND teacher_user_id = %s",
                (attendance_session_id, session["user_id"])
            )
            mysql.connection.commit()
            return {"message": "Attendance session deleted"}, 200
        cur.execute(
            """
            SELECT s.id AS student_id, s.full_name, s.grade,
                   ar.status, ar.note
            FROM student_class_enrollments sce
            INNER JOIN students s ON s.id = sce.student_id
            LEFT JOIN attendance_records ar
                ON ar.student_id = s.id AND ar.attendance_session_id = %s
            WHERE sce.class_id = %s
            ORDER BY s.full_name, s.id
            """,
            (attendance_session_id, attendance["class_id"])
        )
        return {"session": attendance, "students": cur.fetchall()}, 200
    except Exception as error:
        mysql.connection.rollback()
        print("Attendance detail error:", error)
        return {"error": "Failed to manage attendance session"}, 500
    finally:
        cur.close()


@app.route(
    "/api/teacher/attendance-sessions/<int:attendance_session_id>/records",
    methods=["PUT"]
)
@login_required
@role_required(TEACHER)
def teacher_attendance_records_api(attendance_session_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        return {"error": "Attendance records must be provided as a list"}, 400
    cur = mysql.connection.cursor()
    try:
        attendance = fetch_teacher_attendance_session(
            cur, attendance_session_id, session["user_id"]
        )
        if not attendance:
            return {"error": "Attendance session not found"}, 404
        cur.execute(
            "SELECT student_id FROM student_class_enrollments WHERE class_id = %s",
            (attendance["class_id"],)
        )
        enrolled_ids = {int(row["student_id"]) for row in cur.fetchall()}
        normalized = []
        seen_ids = set()
        for index, record in enumerate(data["records"], start=1):
            if not isinstance(record, dict):
                return {"error": f"Attendance record {index} is invalid"}, 400
            try:
                student_id = int(record.get("student_id"))
            except (TypeError, ValueError):
                return {"error": f"Attendance record {index} requires a student"}, 400
            if student_id not in enrolled_ids:
                return {"error": "Attendance contains a student outside this class"}, 400
            if student_id in seen_ids:
                return {"error": "Each student can appear only once"}, 400
            seen_ids.add(student_id)
            status = str(record.get("status") or "").strip().lower()
            if status not in ATTENDANCE_STATUSES:
                return {"error": "Attendance status is invalid"}, 400
            note = str(record.get("note") or "").strip()
            if len(note) > 255:
                return {"error": "Attendance note must be at most 255 characters"}, 400
            normalized.append((student_id, status, note))
        if seen_ids != enrolled_ids:
            return {"error": "Attendance must include every enrolled student"}, 400
        cur.execute(
            "DELETE FROM attendance_records WHERE attendance_session_id = %s",
            (attendance_session_id,)
        )
        for student_id, status, note in normalized:
            cur.execute(
                """
                INSERT INTO attendance_records
                    (attendance_session_id, student_id, status, note)
                VALUES (%s, %s, %s, %s)
                """,
                (attendance_session_id, student_id, status, note)
            )
        mysql.connection.commit()
        return {"message": "Attendance saved", "recorded_students": len(normalized)}, 200
    except Exception as error:
        mysql.connection.rollback()
        print("Attendance records error:", error)
        return {"error": "Failed to save attendance"}, 500
    finally:
        cur.close()


# ============================================================
# STUDENT AI ASSISTANT
# ============================================================

@app.route("/api/student/ai", methods=["POST"])
@login_required
@role_required(STUDENT)
def student_ai_api():

    data = request.get_json(silent=True)

    if not data:
        return {
            "error": "Question is required"
        }, 400

    question = data.get("question")

    if not isinstance(question, str) or not question.strip():

        return {
            "error": "Question is required"
        }, 400

    question = question.strip()

    if len(question) > 1000:
        return {
            "error": "Question must be at most 1000 characters"
        }, 400

    try:

        from assistant import generate_answer

        subject, answer, mode = generate_answer(question)

        cur = mysql.connection.cursor()

        try:

            cur.execute(
                """
                INSERT INTO chat_history
                (
                    user_id,
                    question,
                    answer
                )
                VALUES
                (
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    session["user_id"],
                    question,
                    answer
                )
            )

            mysql.connection.commit()

        finally:

            cur.close()

        return {
            "subject": subject,
            "question": question,
            "answer": answer,
            "mode": mode
        }, 200

    except Exception as e:

        mysql.connection.rollback()

        print("AI assistant error:", e)

        return {
            "error": "AI assistant failed to generate a response"
        }, 500


# ============================================================
# STUDENT QUIZ
# ============================================================


def parse_quiz_questions(raw_questions, fallback_topic="General"):
    """Validate stored questions before presenting or grading a quiz."""
    questions = json.loads(raw_questions)
    if not isinstance(questions, list) or not questions:
        raise ValueError("Quiz must contain at least one question")

    normalized_questions = []

    for question in questions:
        if not isinstance(question, dict):
            raise ValueError("Invalid question")
        prompt = question.get("question")
        options = question.get("options")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Question text is required")
        if (
            not isinstance(options, list)
            or len(options) < 2
            or any(not isinstance(option, str) or not option.strip() for option in options)
            or len(set(options)) != len(options)
            or question.get("answer") not in options
        ):
            raise ValueError("Question must have unique options and a valid answer")

        topic = question.get("topic")
        difficulty = question.get("difficulty")
        curriculum_code = question.get("curriculum_code")
        cognitive_level = question.get("cognitive_level")
        if topic is not None and (not isinstance(topic, str) or not topic.strip()):
            raise ValueError("Question topic must be text")
        if difficulty is not None and (
            not isinstance(difficulty, str)
            or difficulty.strip().lower() not in {"easy", "medium", "hard"}
        ):
            raise ValueError("Question difficulty must be easy, medium, or hard")
        if curriculum_code is not None and (
            not isinstance(curriculum_code, str)
            or not curriculum_code.strip()
            or len(curriculum_code.strip()) > 50
        ):
            raise ValueError("Question curriculum code is invalid")
        if cognitive_level is not None and (
            not isinstance(cognitive_level, str)
            or cognitive_level.strip().lower() not in {
                "recall", "understanding", "application", "higher_order",
                "unspecified"
            }
        ):
            raise ValueError("Question cognitive level is invalid")

        normalized_question = dict(question)
        normalized_question["topic"] = (
            topic.strip() if isinstance(topic, str) else fallback_topic
        )
        normalized_question["difficulty"] = (
            difficulty.strip().lower() if isinstance(difficulty, str) else "unspecified"
        )
        normalized_question["curriculum_code"] = (
            curriculum_code.strip()
            if isinstance(curriculum_code, str) else "unspecified"
        )
        normalized_question["cognitive_level"] = (
            cognitive_level.strip().lower()
            if isinstance(cognitive_level, str) else "unspecified"
        )
        normalized_questions.append(normalized_question)

    return normalized_questions

@app.route("/api/student/quizzes", methods=["GET"])
@login_required
@role_required(STUDENT)
def student_quizzes_api():
    cur = mysql.connection.cursor()

    try:
        cur.execute(
            """
            SELECT id, title, subject, questions
            FROM quizzes
            WHERE is_published = TRUE
            ORDER BY id
            """
        )
        quizzes = []
        for quiz in cur.fetchall():
            if quiz_has_open_lab_session(cur, quiz["id"]):
                continue
            try:
                question_count = len(parse_quiz_questions(
                    quiz["questions"], quiz["subject"] or "General"
                ))
            except (TypeError, ValueError):
                continue
            quizzes.append({
                "id": quiz["id"],
                "title": quiz["title"],
                "subject": quiz["subject"],
                "question_count": question_count
            })

        return {"quizzes": quizzes}, 200

    finally:
        cur.close()


@app.route("/api/student/quiz", methods=["GET"])
@login_required
@role_required(STUDENT)
def student_quiz_api():

    raw_quiz_id = request.args.get("quiz_id")
    quiz_id = request.args.get("quiz_id", type=int)
    if raw_quiz_id is not None and quiz_id is None:
        return {"error": "Quiz ID must be a number"}, 400

    cur = mysql.connection.cursor()

    try:

        if quiz_id is None:
            cur.execute(
                """
                SELECT id, title, subject, questions
                FROM quizzes
                WHERE is_published = TRUE
                ORDER BY id
                """
            )
            quiz_data = None
            for candidate in cur.fetchall():
                if not quiz_has_open_lab_session(cur, candidate["id"]):
                    quiz_data = candidate
                    break
        else:
            cur.execute(
                """
                SELECT id, title, subject, questions
                FROM quizzes
                WHERE id = %s AND is_published = TRUE
                """,
                (quiz_id,)
            )
            quiz_data = cur.fetchone()
            if quiz_data and quiz_has_open_lab_session(cur, quiz_data["id"]):
                quiz_data = None

        if not quiz_data:

            return {
                "error": "No quiz available"
            }, 404

        try:

            questions = parse_quiz_questions(
                quiz_data["questions"],
                quiz_data["subject"] or "General"
            )

        except (TypeError, ValueError):

            return {
                "error": "Quiz questions are invalid"
            }, 500

        return {
            "quiz": {
                "id": quiz_data["id"],
                "title": quiz_data["title"],
                "subject": quiz_data["subject"],
                "questions": [
                    {
                        "question": question["question"],
                        "options": question["options"],
                        "topic": question["topic"],
                        "difficulty": question["difficulty"],
                        "curriculum_code": question["curriculum_code"],
                        "cognitive_level": question["cognitive_level"]
                    }
                    for question in questions
                ]
            }
        }, 200

    finally:

        cur.close()


@app.route("/api/student/quiz/submit", methods=["POST"])
@login_required
@role_required(STUDENT)
def submit_student_quiz():

    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data:

        return {
            "error": "No quiz data provided"
        }, 400

    quiz_id = data.get("quiz_id")
    answers = data.get("answers", {})
    raw_lab_session_id = data.get("quiz_session_id")

    if not quiz_id:

        return {
            "error": "Quiz ID is required"
        }, 400

    if not isinstance(answers, dict):

        return {
            "error": "Answers must be an object"
        }, 400

    cur = mysql.connection.cursor()

    try:

        # ----------------------------------------------------
        # Get quiz
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                id,
                subject,
                questions
            FROM quizzes
            WHERE id = %s AND is_published = TRUE
            """,
            (quiz_id,)
        )

        quiz_data = cur.fetchone()

        if not quiz_data:

            return {
                "error": "Quiz not found"
            }, 404

        try:

            questions = parse_quiz_questions(
                quiz_data["questions"],
                quiz_data["subject"] or "General"
            )

        except (TypeError, ValueError):

            return {
                "error": "Quiz questions are invalid"
            }, 500

        # ----------------------------------------------------
        # Calculate score
        # ----------------------------------------------------

        expected_keys = {str(index) for index in range(len(questions))}
        if not set(answers).issubset(expected_keys):
            return {"error": "Answers contain an unknown question"}, 400

        for key, selected_answer in answers.items():
            if selected_answer not in questions[int(key)]["options"]:
                return {"error": "Each answer must be a valid option"}, 400

        score = sum(
            answers.get(str(index)) == question["answer"]
            for index, question in enumerate(questions)
        )

        answer_details = []
        for index, question in enumerate(questions):
            selected_answer = answers.get(str(index))
            answer_details.append({
                "question_index": index,
                "question_text": question["question"],
                "topic": question["topic"],
                "difficulty": question["difficulty"],
                "curriculum_code": question["curriculum_code"],
                "cognitive_level": question["cognitive_level"],
                "selected_answer": selected_answer,
                "correct_answer": question["answer"],
                "is_correct": int(selected_answer == question["answer"]),
                "is_skipped": int(selected_answer is None)
            })

        # ----------------------------------------------------
        # Get student
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT id
            FROM students
            WHERE user_id = %s
            """,
            (session["user_id"],)
        )

        student = cur.fetchone()

        if not student:

            return {
                "error": "Student profile not found"
            }, 404

        student_id = student["id"]

        lab_session_id = None
        requires_session = quiz_has_open_lab_session(cur, quiz_id)
        if requires_session:
            try:
                lab_session_id = int(raw_lab_session_id)
            except (TypeError, ValueError):
                return {"error": "An active lab quiz session is required"}, 403
            if not (session.get("lab_quiz_access") or {}).get(str(lab_session_id)):
                return {"error": "Start the lab quiz with its access code first"}, 403
            cur.execute(
                """
                SELECT qs.id, qs.starts_at, qs.ends_at, qs.is_closed
                FROM quiz_sessions qs
                INNER JOIN student_class_enrollments sce
                    ON sce.class_id = qs.class_id AND sce.student_id = %s
                WHERE qs.id = %s AND qs.quiz_id = %s
                """,
                (student_id, lab_session_id, quiz_id)
            )
            lab_session = cur.fetchone()
            if not lab_session or lab_session_state(lab_session) != "active":
                return {"error": "Lab quiz session is not active"}, 409
            cur.execute(
                "SELECT COUNT(*) AS attempts FROM quiz_results WHERE quiz_session_id = %s AND student_id = %s",
                (lab_session_id, student_id)
            )
            if int(cur.fetchone()["attempts"] or 0) > 0:
                return {"error": "This lab quiz has already been submitted"}, 409
        elif raw_lab_session_id is not None:
            return {"error": "This quiz does not use a lab session"}, 400

        # ----------------------------------------------------
        # Save result
        # ----------------------------------------------------

        cur.execute(
            """
            INSERT INTO quiz_results
            (
                student_id,
                quiz_id,
                score,
                total_questions,
                quiz_session_id
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                student_id,
                quiz_id,
                score,
                len(questions),
                lab_session_id
            )
        )

        quiz_result_id = cur.lastrowid

        for answer_detail in answer_details:
            cur.execute(
                """
                INSERT INTO quiz_answer_results
                (
                    quiz_result_id,
                    question_index,
                    question_text,
                    topic,
                    difficulty,
                    curriculum_code,
                    cognitive_level,
                    selected_answer,
                    correct_answer,
                    is_correct,
                    is_skipped
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    quiz_result_id,
                    answer_detail["question_index"],
                    answer_detail["question_text"],
                    answer_detail["topic"],
                    answer_detail["difficulty"],
                    answer_detail["curriculum_code"],
                    answer_detail["cognitive_level"],
                    answer_detail["selected_answer"],
                    answer_detail["correct_answer"],
                    answer_detail["is_correct"],
                    answer_detail["is_skipped"]
                )
            )

        mysql.connection.commit()

        return {
            "message": "Quiz submitted successfully",
            "quiz_id": quiz_id,
            "score": score,
            "total": len(questions),
            "skipped": sum(detail["is_skipped"] for detail in answer_details)
        }, 200

    except Exception as e:

        mysql.connection.rollback()

        print("Quiz submission error:", e)

        return {
            "error": "Quiz submission failed"
        }, 500

    finally:

        cur.close()


# ============================================================
# ADMIN SCHOOL SETUP
# ============================================================

@app.route("/api/admin/school-setup", methods=["GET"])
@login_required
@role_required(ADMIN)
def admin_school_setup_api():
    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT id, name, grade, section FROM classes ORDER BY grade, section")
        classes = cur.fetchall()
        cur.execute(
            """SELECT id, username, email FROM users
               WHERE role = 'teacher' ORDER BY username"""
        )
        teachers = cur.fetchall()
        cur.execute(
            """SELECT s.id AS student_id, s.full_name, s.grade, u.email,
                      c.id AS class_id, c.name AS class_name
               FROM students s
               INNER JOIN users u ON u.id = s.user_id
               LEFT JOIN student_class_enrollments sce ON sce.student_id = s.id
               LEFT JOIN classes c ON c.id = sce.class_id
               ORDER BY s.full_name, c.name"""
        )
        students = cur.fetchall()
        cur.execute(
            """SELECT tcs.id, tcs.teacher_user_id, u.username AS teacher_name,
                      tcs.class_id, c.name AS class_name, tcs.subject,
                      CASE WHEN cta.teacher_user_id IS NULL THEN 0 ELSE 1 END
                          AS is_class_teacher
               FROM teacher_class_subjects tcs
               INNER JOIN users u ON u.id = tcs.teacher_user_id
               INNER JOIN classes c ON c.id = tcs.class_id
               LEFT JOIN class_teacher_assignments cta
                 ON cta.class_id = tcs.class_id
                AND cta.teacher_user_id = tcs.teacher_user_id
               ORDER BY c.name, tcs.subject, u.username"""
        )
        assignments = cur.fetchall()
        for assignment in assignments:
            assignment["is_class_teacher"] = bool(assignment["is_class_teacher"])
        return {
            "classes": classes, "teachers": teachers,
            "students": students, "assignments": assignments
        }, 200
    finally:
        cur.close()


@app.route("/api/admin/classes", methods=["POST"])
@login_required
@role_required(ADMIN)
def admin_create_class_api():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Class data is required"}, 400
    name = str(data.get("name") or "").strip()
    grade = str(data.get("grade") or "").strip()
    section = str(data.get("section") or "Default").strip()
    if not name or not grade or not section:
        return {"error": "Class name, grade and section are required"}, 400
    if len(name) > 100 or len(grade) > 20 or len(section) > 50:
        return {"error": "Class information is too long"}, 400
    cur = mysql.connection.cursor()
    try:
        cur.execute(
            "SELECT id FROM classes WHERE grade = %s AND section = %s",
            (grade, section)
        )
        if cur.fetchone():
            return {"error": "This grade and section already exist"}, 409
        cur.execute(
            "INSERT INTO classes (name, grade, section) VALUES (%s, %s, %s)",
            (name, grade, section)
        )
        class_id = cur.lastrowid
        mysql.connection.commit()
        return {"message": "Class created", "class_id": class_id}, 201
    except Exception as error:
        mysql.connection.rollback()
        print("Admin class creation error:", error)
        return {"error": "Unable to create class"}, 500
    finally:
        cur.close()


@app.route("/api/admin/teachers", methods=["POST"])
@login_required
@role_required(ADMIN)
def admin_create_teacher_api():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Teacher data is required"}, 400
    username = str(data.get("username") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    if not username or not email or "@" not in email:
        return {"error": "Teacher name and a valid email are required"}, 400
    if len(password) < 8:
        return {"error": "Password must contain at least 8 characters"}, 400
    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            return {"error": "Email already registered"}, 409
        cur.execute(
            """INSERT INTO users (username, email, password, role)
               VALUES (%s, %s, %s, 'teacher')""",
            (username, email, generate_password_hash(password))
        )
        teacher_id = cur.lastrowid
        mysql.connection.commit()
        return {"message": "Teacher account created", "teacher_id": teacher_id}, 201
    except Exception as error:
        mysql.connection.rollback()
        print("Admin teacher creation error:", error)
        return {"error": "Unable to create teacher"}, 500
    finally:
        cur.close()


@app.route("/api/admin/students/<int:student_id>/class", methods=["PUT"])
@login_required
@role_required(ADMIN)
def admin_enroll_student_api(student_id):
    data = request.get_json(silent=True)
    try:
        class_id = int(data.get("class_id")) if isinstance(data, dict) else 0
    except (TypeError, ValueError):
        class_id = 0
    if not class_id:
        return {"error": "Class is required"}, 400
    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT id FROM students WHERE id = %s", (student_id,))
        if not cur.fetchone():
            return {"error": "Student not found"}, 404
        cur.execute("SELECT id, grade FROM classes WHERE id = %s", (class_id,))
        selected_class = cur.fetchone()
        if not selected_class:
            return {"error": "Class not found"}, 404
        cur.execute("DELETE FROM student_class_enrollments WHERE student_id = %s", (student_id,))
        cur.execute(
            "INSERT INTO student_class_enrollments (student_id, class_id) VALUES (%s, %s)",
            (student_id, class_id)
        )
        cur.execute("UPDATE students SET grade = %s WHERE id = %s",
                    (selected_class["grade"], student_id))
        mysql.connection.commit()
        return {"message": "Student enrolled in class"}, 200
    except Exception as error:
        mysql.connection.rollback()
        print("Admin enrollment error:", error)
        return {"error": "Unable to enroll student"}, 500
    finally:
        cur.close()


@app.route("/api/admin/teacher-assignments", methods=["POST"])
@login_required
@role_required(ADMIN)
def admin_create_teacher_assignment_api():
    data = request.get_json(silent=True)
    try:
        teacher_id = int(data.get("teacher_user_id"))
        class_id = int(data.get("class_id"))
    except (AttributeError, TypeError, ValueError):
        return {"error": "Teacher and class are required"}, 400
    subject = str(data.get("subject") or "").strip()
    is_class_teacher = data.get("is_class_teacher", False)
    if not subject or len(subject) > 100:
        return {"error": "Subject is required and must be at most 100 characters"}, 400
    if not isinstance(is_class_teacher, bool):
        return {"error": "Class teacher status must be true or false"}, 400
    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE id = %s AND role = 'teacher'", (teacher_id,))
        if not cur.fetchone():
            return {"error": "Teacher not found"}, 404
        cur.execute("SELECT id FROM classes WHERE id = %s", (class_id,))
        if not cur.fetchone():
            return {"error": "Class not found"}, 404
        cur.execute(
            """SELECT id FROM teacher_class_subjects
               WHERE teacher_user_id = %s AND class_id = %s
                 AND LOWER(subject) = LOWER(%s)""",
            (teacher_id, class_id, subject)
        )
        if cur.fetchone():
            return {"error": "Teacher already has this class-subject assignment"}, 409
        cur.execute(
            """INSERT INTO teacher_class_subjects
               (teacher_user_id, class_id, subject) VALUES (%s, %s, %s)""",
            (teacher_id, class_id, subject)
        )
        assignment_id = cur.lastrowid
        if is_class_teacher:
            cur.execute("DELETE FROM class_teacher_assignments WHERE class_id = %s", (class_id,))
            cur.execute(
                """INSERT INTO class_teacher_assignments (teacher_user_id, class_id)
                   VALUES (%s, %s)""", (teacher_id, class_id)
            )
        mysql.connection.commit()
        return {"message": "Teacher assignment created", "assignment_id": assignment_id}, 201
    except Exception as error:
        mysql.connection.rollback()
        print("Admin assignment error:", error)
        return {"error": "Unable to assign teacher"}, 500
    finally:
        cur.close()


@app.route("/api/admin/teacher-assignments/<int:assignment_id>", methods=["DELETE"])
@login_required
@role_required(ADMIN)
def admin_delete_teacher_assignment_api(assignment_id):
    cur = mysql.connection.cursor()
    try:
        cur.execute(
            "SELECT teacher_user_id, class_id FROM teacher_class_subjects WHERE id = %s",
            (assignment_id,)
        )
        assignment = cur.fetchone()
        if not assignment:
            return {"error": "Teacher assignment not found"}, 404
        cur.execute("DELETE FROM teacher_class_subjects WHERE id = %s", (assignment_id,))
        cur.execute(
            """SELECT id FROM teacher_class_subjects
               WHERE teacher_user_id = %s AND class_id = %s LIMIT 1""",
            (assignment["teacher_user_id"], assignment["class_id"])
        )
        if not cur.fetchone():
            cur.execute(
                """DELETE FROM class_teacher_assignments
                   WHERE teacher_user_id = %s AND class_id = %s""",
                (assignment["teacher_user_id"], assignment["class_id"])
            )
        mysql.connection.commit()
        return {"message": "Teacher assignment removed"}, 200
    finally:
        cur.close()


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/api/admin/dashboard", methods=["GET"])
@login_required
@role_required(ADMIN)
def admin_dashboard_api():

    cur = mysql.connection.cursor()

    try:
        # ----------------------------------------------------
        # User statistics
        # ----------------------------------------------------
        cur.execute("""
            SELECT
                COUNT(*) AS total_users,
                SUM(role = 'student') AS total_students,
                SUM(role = 'teacher') AS total_teachers,
                SUM(role = 'admin') AS total_admins
            FROM users
        """)

        user_stats = cur.fetchone()

        # ----------------------------------------------------
        # Notes
        # ----------------------------------------------------
        cur.execute("""
            SELECT COUNT(*) AS total_notes
            FROM notes
        """)

        total_notes = cur.fetchone()["total_notes"]

        # ----------------------------------------------------
        # Quizzes
        # ----------------------------------------------------
        cur.execute("""
            SELECT COUNT(*) AS total_quizzes
            FROM quizzes
        """)

        total_quizzes = cur.fetchone()["total_quizzes"]

        # ----------------------------------------------------
        # Quiz attempts
        # ----------------------------------------------------
        cur.execute("""
            SELECT COUNT(*) AS total_quiz_attempts
            FROM quiz_results
        """)

        total_quiz_attempts = cur.fetchone()["total_quiz_attempts"]

        # ----------------------------------------------------
        # Recent users
        # ----------------------------------------------------
        cur.execute("""
            SELECT
                id,
                username,
                email,
                role,
                created_at
            FROM users
            ORDER BY created_at DESC
            LIMIT 10
        """)

        recent_users = cur.fetchall()

        return {
            "statistics": {
                "total_users": int(user_stats["total_users"] or 0),
                "total_students": int(user_stats["total_students"] or 0),
                "total_teachers": int(user_stats["total_teachers"] or 0),
                "total_admins": int(user_stats["total_admins"] or 0),
                "total_notes": int(total_notes or 0),
                "total_quizzes": int(total_quizzes or 0),
                "total_quiz_attempts": int(total_quiz_attempts or 0)
            },
            "recent_users": recent_users
        }, 200

    finally:
        cur.close()
        
# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=env_flag("FLASK_DEBUG", default=False)
    )
