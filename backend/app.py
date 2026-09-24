from flask import Flask, request, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash
from functools import wraps
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from backend.routes.admin import create_admin_blueprint
from backend.routes.assessments import create_assessments_blueprint
from backend.routes.attendance import create_attendance_blueprint
from backend.routes.auth import create_auth_blueprint
from backend.routes.chatbot import create_chatbot_blueprint
from backend.routes.lab_quiz import create_lab_quiz_blueprint
from backend.routes.notes import create_notes_blueprint
from backend.routes.quiz import (
    create_quiz_blueprint,
    parse_quiz_questions,
    quiz_has_open_lab_session
)

import os
import json
import secrets
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables from the repository root .env file.
repository_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(repository_root, ".env"))

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


@app.errorhandler(429)
def login_rate_limit_exceeded(_error):
    return {
        "error": "Too many login attempts. Please wait before trying again."
    }, 429


app.register_blueprint(create_auth_blueprint(
    mysql=mysql,
    limiter=limiter,
    login_required=login_required
))

app.register_blueprint(create_notes_blueprint(
    mysql=mysql,
    login_required=login_required,
    role_required=role_required,
    student_role=STUDENT,
    teacher_role=TEACHER
))

app.register_blueprint(create_chatbot_blueprint(
    mysql=mysql,
    login_required=login_required,
    role_required=role_required,
    student_role=STUDENT
))

app.register_blueprint(create_quiz_blueprint(
    mysql=mysql,
    login_required=login_required,
    role_required=role_required,
    student_role=STUDENT,
    teacher_role=TEACHER
))

app.register_blueprint(create_lab_quiz_blueprint(
    mysql=mysql,
    login_required=login_required,
    role_required=role_required,
    student_role=STUDENT,
    teacher_role=TEACHER
))

app.register_blueprint(create_assessments_blueprint(
    mysql=mysql,
    login_required=login_required,
    role_required=role_required,
    teacher_role=TEACHER
))

app.register_blueprint(create_attendance_blueprint(
    mysql=mysql,
    login_required=login_required,
    role_required=role_required,
    teacher_role=TEACHER
))

app.register_blueprint(create_admin_blueprint(
    mysql=mysql,
    login_required=login_required,
    role_required=role_required,
    admin_role=ADMIN
))


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
        for record in recent_attendance:
            record["attendance_month"] = serialize_api_date(
                record["attendance_month"]
            )
            record["total_school_days"] = int(record["total_school_days"])
            record["present_days"] = int(record["present_days"])
            record["absent_days"] = int(record["absent_days"])

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
# API SERIALIZATION HELPERS
# ============================================================


def serialize_api_date(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


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
