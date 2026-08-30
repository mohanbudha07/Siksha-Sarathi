from flask import Flask, request, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask_cors import CORS

import os
import json
import joblib


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

app.config["MYSQL_HOST"] = "localhost"
app.config["MYSQL_USER"] = "siksha_user"
app.config["MYSQL_PASSWORD"] = "Siksha123!"
app.config["MYSQL_DB"] = "siksha_sarathi"
app.config["MYSQL_CURSORCLASS"] = "DictCursor"

app.secret_key = "your_super_secret_key_123"

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
                COALESCE(AVG(score), 0) AS average_score
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
                COALESCE(AVG(score), 0) AS average_quiz_score
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
            FROM predictions
            WHERE prediction = 'Needs Improvement'
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
                    AVG(qr.score),
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

    if not data:
        return {
            "error": "Note data is required"
        }, 400

    title = data.get("title")
    subject = data.get("subject")
    chapter = data.get("chapter")
    content = data.get("content")

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

@app.route("/api/student/quiz", methods=["GET"])
@login_required
@role_required(STUDENT)
def student_quiz_api():

    cur = mysql.connection.cursor()

    try:

        # Get the first available quiz
        cur.execute(
            """
            SELECT
                id,
                title,
                subject,
                questions
            FROM quizzes
            ORDER BY id
            LIMIT 1
            """
        )

        quiz_data = cur.fetchone()

        if not quiz_data:

            return {
                "error": "No quiz available"
            }, 404

        try:

            questions = json.loads(
                quiz_data["questions"]
            )

        except (TypeError, json.JSONDecodeError):

            return {
                "error": "Quiz questions are invalid"
            }, 500

        return {
            "quiz": {
                "id": quiz_data["id"],
                "title": quiz_data["title"],
                "subject": quiz_data["subject"],
                "questions": questions
            }
        }, 200

    finally:

        cur.close()


@app.route("/api/student/quiz/submit", methods=["POST"])
@login_required
@role_required(STUDENT)
def submit_student_quiz():

    data = request.get_json(silent=True)

    if not data:

        return {
            "error": "No quiz data provided"
        }, 400

    quiz_id = data.get("quiz_id")
    answers = data.get("answers", {})

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
                questions
            FROM quizzes
            WHERE id = %s
            """,
            (quiz_id,)
        )

        quiz_data = cur.fetchone()

        if not quiz_data:

            return {
                "error": "Quiz not found"
            }, 404

        try:

            questions = json.loads(
                quiz_data["questions"]
            )

        except (TypeError, json.JSONDecodeError):

            return {
                "error": "Quiz questions are invalid"
            }, 500

        # ----------------------------------------------------
        # Calculate score
        # ----------------------------------------------------

        score = 0

        for index, question in enumerate(questions):

            answer = answers.get(str(index))

            if answer == question.get("answer"):
                score += 1

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

        # ----------------------------------------------------
        # Save result
        # ----------------------------------------------------

        cur.execute(
            """
            INSERT INTO quiz_results
            (
                student_id,
                quiz_id,
                score
            )
            VALUES
            (
                %s,
                %s,
                %s
            )
            """,
            (
                student_id,
                quiz_id,
                score
            )
        )

        mysql.connection.commit()

        return {
            "message": "Quiz submitted successfully",
            "quiz_id": quiz_id,
            "score": score,
            "total": len(questions)
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
            FROM predictions
            WHERE prediction = 'Needs Improvement'
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