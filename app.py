from flask import Flask, request, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask_cors import CORS

import os
import json
import joblib
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

app = Flask(__name__)

CORS(
    app,
    origins=[
        "http://localhost:5173",
        "http://localhost:5174"
    ],
    supports_credentials=True
)

# Secret key (prefer environment variable)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-in-production-2026")
app.secret_key = app.config["SECRET_KEY"]   # keep this for compatibility

# Session cookie settings (important for React + credentials)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
# app.config["SESSION_COOKIE_SECURE"] = True   # enable later when using HTTPS

# MySQL Configuration (prefer environment variables)
app.config["MYSQL_HOST"] = os.getenv("MYSQL_HOST", "localhost")
app.config["MYSQL_USER"] = os.getenv("MYSQL_USER", "siksha_user")
app.config["MYSQL_PASSWORD"] = os.getenv("MYSQL_PASSWORD", "Siksha123!")
app.config["MYSQL_DB"] = os.getenv("MYSQL_DB", "siksha_sarathi")
app.config["MYSQL_CURSORCLASS"] = "DictCursor"

mysql = MySQL(app)


# ============================================================
# MACHINE LEARNING MODEL
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = os.path.join(
    BASE_DIR,
    "ml",
    "performance_model.pkl"
)

LABEL_ENCODER_PATH = os.path.join(
    BASE_DIR,
    "ml",
    "label_encoder.pkl"
)

model = joblib.load(MODEL_PATH)
label_encoder = joblib.load(LABEL_ENCODER_PATH)


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
def api_login():

    data = request.get_json(silent=True)

    if not data:
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
    grade = data.get("grade")
    role = data.get("role")

    if not username or not email or not password or not role:
        return {
            "error": "Username, email, password, and role are required"
        }, 400

    if role not in [STUDENT, TEACHER]:
        return {
            "error": "Invalid role"
        }, 400

    if role == STUDENT:

        if not full_name or not grade:
            return {
                "error": "Full name and grade are required for students"
            }, 400

    cur = mysql.connection.cursor()

    try:

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

        # Create student profile
        if role == STUDENT:

            cur.execute(
                """
                INSERT INTO students
                (
                    user_id,
                    full_name,
                    grade
                )
                VALUES
                (
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    user_id,
                    full_name,
                    grade
                )
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

        # ----------------------------------------------------
        # Latest ML prediction
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                prediction,
                attendance,
                assignment_score,
                quiz_score,
                study_hours
            FROM predictions
            WHERE student_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (student_id,)
        )

        prediction = cur.fetchone()

        return {
            "student": student,
            "stats": {
                "total_notes": total_notes,
                "completed_quizzes": completed_quizzes,
                "average_quiz_score": average_score
            },
            "prediction": prediction
        }, 200

    finally:

        cur.close()


# ============================================================
# STUDENT PERFORMANCE / ML PREDICTION
# ============================================================

@app.route("/api/student/prediction", methods=["GET"])
@login_required
@role_required(STUDENT)
def get_student_prediction():

    cur = mysql.connection.cursor()

    try:

        cur.execute(
            """
            SELECT
                p.id,
                p.attendance,
                p.assignment_score,
                p.quiz_score,
                p.study_hours,
                p.prediction
            FROM predictions p
            INNER JOIN students s
                ON p.student_id = s.id
            WHERE s.user_id = %s
            ORDER BY p.id DESC
            LIMIT 1
            """,
            (session["user_id"],)
        )

        prediction = cur.fetchone()

        return {
            "prediction": prediction
        }, 200

    finally:

        cur.close()


@app.route("/api/student/prediction", methods=["POST"])
@login_required
@role_required(STUDENT)
def create_student_prediction():

    data = request.get_json(silent=True)

    if not data:
        return {
            "error": "Prediction data is required"
        }, 400

    try:

        attendance = float(data.get("attendance"))
        assignment_score = float(data.get("assignment_score"))
        quiz_score = float(data.get("quiz_score"))
        study_hours = float(data.get("study_hours"))

    except (TypeError, ValueError):

        return {
            "error": "Attendance, assignment score, quiz score, and study hours must be numbers"
        }, 400

    # --------------------------------------------------------
    # Validate values
    # --------------------------------------------------------

    if not 0 <= attendance <= 100:
        return {
            "error": "Attendance must be between 0 and 100"
        }, 400

    if not 0 <= assignment_score <= 100:
        return {
            "error": "Assignment score must be between 0 and 100"
        }, 400

    if not 0 <= quiz_score <= 100:
        return {
            "error": "Quiz score must be between 0 and 100"
        }, 400

    if study_hours < 0:
        return {
            "error": "Study hours cannot be negative"
        }, 400

    # --------------------------------------------------------
    # ML prediction
    # --------------------------------------------------------

    prediction_result = model.predict(
        [[
            attendance,
            assignment_score,
            quiz_score,
            study_hours
        ]]
    )

    prediction = label_encoder.inverse_transform(
        prediction_result
    )[0]

    # --------------------------------------------------------
    # Find student
    # --------------------------------------------------------

    cur = mysql.connection.cursor()

    try:

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

        # ----------------------------------------------------
        # Save prediction
        # ----------------------------------------------------

        cur.execute(
            """
            INSERT INTO predictions
            (
                student_id,
                attendance,
                assignment_score,
                quiz_score,
                study_hours,
                prediction
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                student_id,
                attendance,
                assignment_score,
                quiz_score,
                study_hours,
                prediction
            )
        )

        mysql.connection.commit()

        return {
            "message": "Prediction generated successfully",
            "prediction": {
                "result": prediction,
                "attendance": attendance,
                "assignment_score": assignment_score,
                "quiz_score": quiz_score,
                "study_hours": study_hours
            }
        }, 201

    except Exception as e:

        mysql.connection.rollback()

        print("Prediction error:", e)

        return {
            "error": "Prediction failed"
        }, 500

    finally:

        cur.close()


# ============================================================
# STUDENT NOTES
# ============================================================

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
            SELECT COUNT(*) AS total_students
            FROM students
            """
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
            FROM quiz_results
            """
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
        # Students needing improvement
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT COUNT(DISTINCT student_id)
            AS students_needing_improvement
            FROM predictions p
            WHERE p.prediction = 'Needs Improvement'
              AND p.id = (
                  SELECT MAX(latest.id)
                  FROM predictions latest
                  WHERE latest.student_id = p.student_id
              )
            """
        )

        improvement_data = cur.fetchone()

        students_needing_improvement = (
            improvement_data[
                "students_needing_improvement"
            ]
        )

        # ----------------------------------------------------
        # Total predictions
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT COUNT(*) AS total_predictions
            FROM predictions
            """
        )

        total_predictions = (
            cur.fetchone()["total_predictions"]
        )

        # ----------------------------------------------------
        # Individual student performance
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                s.id AS student_id,
                s.full_name,
                s.grade,

                COUNT(DISTINCT qr.id)
                AS quiz_attempts,

                COALESCE(
                    AVG(100.0 * qr.score / NULLIF(qr.total_questions, 0)),
                    0
                ) AS average_quiz_score,

                p.prediction,
                p.attendance,
                p.assignment_score,
                p.quiz_score,
                p.study_hours

            FROM students s

            LEFT JOIN quiz_results qr
                ON s.id = qr.student_id

            LEFT JOIN predictions p
                ON s.id = p.student_id

            AND p.id = (
                SELECT MAX(p2.id)
                FROM predictions p2
                WHERE p2.student_id = s.id
            )

            GROUP BY
                s.id,
                s.full_name,
                s.grade,
                p.prediction,
                p.attendance,
                p.assignment_score,
                p.quiz_score,
                p.study_hours

            ORDER BY s.full_name
            """
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
                "students_needing_improvement":
                    students_needing_improvement,
                "total_predictions": total_predictions
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

        profiles = []
        for student in student_rows:
            metrics = fetch_student_subject_metrics(
                cur, student["student_id"], student["subject"]
            )
            profiles.append({**student, **metrics})

        assigned_student_ids = {profile["student_id"] for profile in profiles}
        active_student_ids = {
            profile["student_id"]
            for profile in profiles
            if profile["total_questions"] > 0
        }

        return {
            "assignments": assignments,
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

        cur.execute(
            """
            SELECT
                qar.topic,
                COUNT(*) AS total_questions,
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
            topics.append({"topic": row["topic"], **topic_metrics})
        topics.sort(key=lambda item: (item["accuracy_percent"], -item["total_questions"]))

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
            "topics": topics,
            "difficulties": difficulties,
            "recent_attempts": recent_attempts,
            "common_mistakes": common_mistakes
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
            "SELECT id FROM quiz_sessions WHERE id = %s AND created_by = %s",
            (lab_session_id, session["user_id"])
        )
        if not cur.fetchone():
            return {"error": "Lab quiz session not found"}, 404
        cur.execute(
            "UPDATE quiz_sessions SET is_closed = TRUE WHERE id = %s AND created_by = %s",
            (lab_session_id, session["user_id"])
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

    if not question or not question.strip():

        return {
            "error": "Question is required"
        }, 400

    question = question.strip()

    try:

        from assistant import generate_answer

        subject, answer = generate_answer(question)

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
            "answer": answer
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
            WHERE is_published = TRUE AND requires_session = FALSE
            ORDER BY id
            """
        )
        quizzes = []
        for quiz in cur.fetchall():
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
                WHERE is_published = TRUE AND requires_session = FALSE
                ORDER BY id
                LIMIT 1
                """
            )
        else:
            cur.execute(
                """
                SELECT id, title, subject, questions
                FROM quizzes
                WHERE id = %s AND is_published = TRUE AND requires_session = FALSE
                """,
                (quiz_id,)
            )

        quiz_data = cur.fetchone()

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
                questions,
                requires_session
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
        if bool(quiz_data["requires_session"]):
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
        # ML predictions
        # ----------------------------------------------------
        cur.execute("""
            SELECT COUNT(*) AS total_predictions
            FROM predictions
        """)

        total_predictions = cur.fetchone()["total_predictions"]

        # ----------------------------------------------------
        # Students needing improvement
        # ----------------------------------------------------
        cur.execute("""
            SELECT COUNT(DISTINCT student_id)
            AS students_needing_improvement
            FROM predictions p
            WHERE p.prediction = 'Needs Improvement'
              AND p.id = (
                  SELECT MAX(latest.id)
                  FROM predictions latest
                  WHERE latest.student_id = p.student_id
              )
        """)

        improvement = cur.fetchone()

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
                "total_quiz_attempts": int(total_quiz_attempts or 0),
                "total_predictions": int(total_predictions or 0),
                "students_needing_improvement": int(
                    improvement["students_needing_improvement"] or 0
                )
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
        host="127.0.0.1",
        port=5000,
        debug=True
    )
