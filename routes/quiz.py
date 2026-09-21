"""Shared quiz helpers and ordinary student quiz API routes."""

import json
from datetime import datetime, timezone

from flask import Blueprint, request, session


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
            or any(
                not isinstance(option, str) or not option.strip()
                for option in options
            )
            or len(set(options)) != len(options)
            or question.get("answer") not in options
        ):
            raise ValueError(
                "Question must have unique options and a valid answer"
            )

        topic = question.get("topic")
        difficulty = question.get("difficulty")
        curriculum_code = question.get("curriculum_code")
        cognitive_level = question.get("cognitive_level")
        if topic is not None and (
            not isinstance(topic, str) or not topic.strip()
        ):
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
                "recall",
                "understanding",
                "application",
                "higher_order",
                "unspecified"
            }
        ):
            raise ValueError("Question cognitive level is invalid")

        normalized_question = dict(question)
        normalized_question["topic"] = (
            topic.strip() if isinstance(topic, str) else fallback_topic
        )
        normalized_question["difficulty"] = (
            difficulty.strip().lower()
            if isinstance(difficulty, str) else "unspecified"
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


def create_quiz_blueprint(
    mysql,
    login_required,
    role_required,
    student_role
):
    quiz = Blueprint("quiz", __name__)

    @quiz.get("/api/student/quizzes")
    @login_required
    @role_required(student_role)
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
            for stored_quiz in cur.fetchall():
                if quiz_has_open_lab_session(cur, stored_quiz["id"]):
                    continue
                try:
                    question_count = len(parse_quiz_questions(
                        stored_quiz["questions"],
                        stored_quiz["subject"] or "General"
                    ))
                except (TypeError, ValueError):
                    continue
                quizzes.append({
                    "id": stored_quiz["id"],
                    "title": stored_quiz["title"],
                    "subject": stored_quiz["subject"],
                    "question_count": question_count
                })
            return {"quizzes": quizzes}, 200
        finally:
            cur.close()

    @quiz.get("/api/student/quiz")
    @login_required
    @role_required(student_role)
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
                return {"error": "No quiz available"}, 404
            try:
                questions = parse_quiz_questions(
                    quiz_data["questions"], quiz_data["subject"] or "General"
                )
            except (TypeError, ValueError):
                return {"error": "Quiz questions are invalid"}, 500
            return {"quiz": public_quiz_payload(quiz_data, questions)}, 200
        finally:
            cur.close()

    @quiz.post("/api/student/quiz/submit")
    @login_required
    @role_required(student_role)
    def submit_student_quiz():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not data:
            return {"error": "No quiz data provided"}, 400

        quiz_id = data.get("quiz_id")
        answers = data.get("answers", {})
        raw_lab_session_id = data.get("quiz_session_id")
        if not quiz_id:
            return {"error": "Quiz ID is required"}, 400
        if not isinstance(answers, dict):
            return {"error": "Answers must be an object"}, 400

        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """
                SELECT id, subject, questions
                FROM quizzes
                WHERE id = %s AND is_published = TRUE
                """,
                (quiz_id,)
            )
            quiz_data = cur.fetchone()
            if not quiz_data:
                return {"error": "Quiz not found"}, 404
            try:
                questions = parse_quiz_questions(
                    quiz_data["questions"], quiz_data["subject"] or "General"
                )
            except (TypeError, ValueError):
                return {"error": "Quiz questions are invalid"}, 500

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

            cur.execute(
                "SELECT id FROM students WHERE user_id = %s",
                (session["user_id"],)
            )
            student = cur.fetchone()
            if not student:
                return {"error": "Student profile not found"}, 404
            student_id = student["id"]

            lab_session_id = None
            requires_session = quiz_has_open_lab_session(cur, quiz_id)
            if requires_session:
                try:
                    lab_session_id = int(raw_lab_session_id)
                except (TypeError, ValueError):
                    return {"error": "An active lab quiz session is required"}, 403
                if not (session.get("lab_quiz_access") or {}).get(
                    str(lab_session_id)
                ):
                    return {
                        "error": "Start the lab quiz with its access code first"
                    }, 403
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
                    """SELECT COUNT(*) AS attempts FROM quiz_results
                       WHERE quiz_session_id = %s AND student_id = %s""",
                    (lab_session_id, student_id)
                )
                if int(cur.fetchone()["attempts"] or 0) > 0:
                    return {
                        "error": "This lab quiz has already been submitted"
                    }, 409
            elif raw_lab_session_id is not None:
                return {"error": "This quiz does not use a lab session"}, 400

            cur.execute(
                """
                INSERT INTO quiz_results
                    (student_id, quiz_id, score, total_questions, quiz_session_id)
                VALUES (%s, %s, %s, %s, %s)
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
            for detail in answer_details:
                cur.execute(
                    """
                    INSERT INTO quiz_answer_results
                    (
                        quiz_result_id, question_index, question_text, topic,
                        difficulty, curriculum_code, cognitive_level,
                        selected_answer, correct_answer, is_correct, is_skipped
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        quiz_result_id,
                        detail["question_index"],
                        detail["question_text"],
                        detail["topic"],
                        detail["difficulty"],
                        detail["curriculum_code"],
                        detail["cognitive_level"],
                        detail["selected_answer"],
                        detail["correct_answer"],
                        detail["is_correct"],
                        detail["is_skipped"]
                    )
                )
            mysql.connection.commit()
            return {
                "message": "Quiz submitted successfully",
                "quiz_id": quiz_id,
                "score": score,
                "total": len(questions),
                "skipped": sum(
                    detail["is_skipped"] for detail in answer_details
                )
            }, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Quiz submission error:", error)
            return {"error": "Quiz submission failed"}, 500
        finally:
            cur.close()

    return quiz
