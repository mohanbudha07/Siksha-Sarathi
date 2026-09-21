"""Teacher and student computer-lab quiz-session routes."""

from datetime import datetime, timezone

from flask import Blueprint, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from routes.quiz import (
    lab_session_state,
    parse_quiz_questions,
    public_quiz_payload,
    quiz_has_open_lab_session
)


def parse_session_datetime(value, field_name):
    """Normalize an ISO-8601 value to a naive UTC datetime for MySQL."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"{field_name} must be a valid ISO date and time"
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def create_lab_quiz_blueprint(
    mysql,
    login_required,
    role_required,
    student_role,
    teacher_role
):
    lab_quiz = Blueprint("lab_quiz", __name__)

    @lab_quiz.route("/api/teacher/quiz-sessions", methods=["GET", "POST"])
    @login_required
    @role_required(teacher_role)
    def teacher_quiz_sessions_api():
        cur = mysql.connection.cursor()
        try:
            if request.method == "GET":
                cur.execute(
                    """
                    SELECT qs.id, qs.quiz_id, qs.class_id,
                           qs.starts_at, qs.ends_at, qs.is_closed,
                           qs.created_at, q.title, q.subject,
                           c.name AS class_name,
                           (SELECT COUNT(*) FROM quiz_results qr
                            WHERE qr.quiz_session_id = qs.id)
                               AS submission_count
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
                    item["submission_count"] = int(
                        item["submission_count"] or 0
                    )
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
                return {
                    "error": "Access code must contain 4 to 20 characters"
                }, 400
            try:
                starts_at = parse_session_datetime(
                    data.get("starts_at"), "Start time"
                )
                ends_at = parse_session_datetime(
                    data.get("ends_at"), "End time"
                )
            except ValueError as error:
                return {"error": str(error)}, 400
            if ends_at <= starts_at:
                return {"error": "End time must be after start time"}, 400
            if (ends_at - starts_at).total_seconds() > 8 * 60 * 60:
                return {
                    "error": "A lab session cannot be longer than 8 hours"
                }, 400

            cur.execute(
                """
                SELECT q.id
                FROM quizzes q
                INNER JOIN teacher_class_subjects tcs
                    ON tcs.teacher_user_id = %s
                   AND tcs.class_id = %s
                   AND LOWER(tcs.subject) = LOWER(q.subject)
                WHERE q.id = %s
                  AND q.created_by = %s
                  AND q.is_published = TRUE
                """,
                (session["user_id"], class_id, quiz_id, session["user_id"])
            )
            if not cur.fetchone():
                return {
                    "error": (
                        "Published quiz or class-subject assignment not found"
                    )
                }, 404

            cur.execute(
                """
                INSERT INTO quiz_sessions
                    (quiz_id, class_id, created_by, access_code_hash,
                     starts_at, ends_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    quiz_id,
                    class_id,
                    session["user_id"],
                    generate_password_hash(access_code),
                    starts_at,
                    ends_at
                )
            )
            lab_session_id = cur.lastrowid
            cur.execute(
                "UPDATE quizzes SET requires_session = TRUE WHERE id = %s",
                (quiz_id,)
            )
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

    @lab_quiz.post(
        "/api/teacher/quiz-sessions/<int:lab_session_id>/close"
    )
    @login_required
    @role_required(teacher_role)
    def teacher_close_quiz_session_api(lab_session_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT id, quiz_id FROM quiz_sessions
                   WHERE id = %s AND created_by = %s""",
                (lab_session_id, session["user_id"])
            )
            stored_session = cur.fetchone()
            if not stored_session:
                return {"error": "Lab quiz session not found"}, 404
            cur.execute(
                """UPDATE quiz_sessions SET is_closed = TRUE
                   WHERE id = %s AND created_by = %s""",
                (lab_session_id, session["user_id"])
            )
            still_protected = quiz_has_open_lab_session(
                cur, stored_session["quiz_id"]
            )
            cur.execute(
                "UPDATE quizzes SET requires_session = %s WHERE id = %s",
                (still_protected, stored_session["quiz_id"])
            )
            mysql.connection.commit()
            return {"message": "Lab quiz session closed"}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Lab quiz session close error:", error)
            return {"error": "Failed to close lab quiz session"}, 500
        finally:
            cur.close()

    @lab_quiz.get("/api/student/quiz-sessions")
    @login_required
    @role_required(student_role)
    def student_quiz_sessions_api():
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "SELECT id AS student_id FROM students WHERE user_id = %s",
                (session["user_id"],)
            )
            student = cur.fetchone()
            if not student:
                return {"error": "Student profile not found"}, 404
            cur.execute(
                """
                SELECT qs.id, qs.quiz_id, qs.class_id,
                       qs.starts_at, qs.ends_at, qs.is_closed,
                       q.title, q.subject, c.name AS class_name,
                       (SELECT COUNT(*) FROM quiz_results qr
                        WHERE qr.quiz_session_id = qs.id
                          AND qr.student_id = %s) AS submitted
                FROM quiz_sessions qs
                INNER JOIN student_class_enrollments sce
                    ON sce.class_id = qs.class_id AND sce.student_id = %s
                INNER JOIN quizzes q
                    ON q.id = qs.quiz_id AND q.is_published = TRUE
                INNER JOIN classes c ON c.id = qs.class_id
                ORDER BY qs.starts_at DESC, qs.id DESC
                """,
                (student["student_id"], student["student_id"])
            )
            lab_sessions = cur.fetchall()
            for item in lab_sessions:
                item["state"] = (
                    "submitted"
                    if int(item["submitted"] or 0)
                    else lab_session_state(item)
                )
                item["submitted"] = bool(item["submitted"])
                item["is_closed"] = bool(item["is_closed"])
            return {"sessions": lab_sessions}, 200
        finally:
            cur.close()

    @lab_quiz.post(
        "/api/student/quiz-sessions/<int:lab_session_id>/start"
    )
    @login_required
    @role_required(student_role)
    def student_start_quiz_session_api(lab_session_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {"error": "Access code is required"}, 400
        access_code = str(data.get("access_code") or "").strip()
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "SELECT id FROM students WHERE user_id = %s",
                (session["user_id"],)
            )
            student = cur.fetchone()
            if not student:
                return {"error": "Student profile not found"}, 404
            cur.execute(
                """
                SELECT qs.id AS session_id, qs.quiz_id,
                       qs.starts_at, qs.ends_at, qs.is_closed,
                       qs.access_code_hash,
                       q.id, q.title, q.subject, q.questions
                FROM quiz_sessions qs
                INNER JOIN quizzes q
                    ON q.id = qs.quiz_id AND q.is_published = TRUE
                INNER JOIN student_class_enrollments sce
                    ON sce.class_id = qs.class_id AND sce.student_id = %s
                WHERE qs.id = %s
                """,
                (student["id"], lab_session_id)
            )
            stored_session = cur.fetchone()
            if not stored_session:
                return {"error": "Lab quiz session not found"}, 404
            if lab_session_state(stored_session) != "active":
                return {"error": "Lab quiz session is not active"}, 409
            if not check_password_hash(
                stored_session["access_code_hash"], access_code
            ):
                return {"error": "Invalid access code"}, 403
            cur.execute(
                """SELECT COUNT(*) AS attempts FROM quiz_results
                   WHERE quiz_session_id = %s AND student_id = %s""",
                (lab_session_id, student["id"])
            )
            if int(cur.fetchone()["attempts"] or 0) > 0:
                return {
                    "error": "This lab quiz has already been submitted"
                }, 409
            try:
                questions = parse_quiz_questions(
                    stored_session["questions"], stored_session["subject"]
                )
            except (TypeError, ValueError):
                return {"error": "Quiz questions are invalid"}, 500
            access = dict(session.get("lab_quiz_access") or {})
            access[str(lab_session_id)] = True
            session["lab_quiz_access"] = access
            return {
                "session_id": lab_session_id,
                "quiz": public_quiz_payload(stored_session, questions)
            }, 200
        finally:
            cur.close()

    return lab_quiz
