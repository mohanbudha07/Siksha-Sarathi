"""Student AI study-assistant API routes."""

import os

from flask import Blueprint, request, session

from ai.assistant import generate_answer
from backend.student_access import fetch_student_context
from backend.student_tutoring_context import build_student_tutoring_context, get_student_ai_context_options


def create_chatbot_blueprint(
    mysql,
    login_required,
    role_required,
    student_role
):
    chatbot = Blueprint("chatbot", __name__)

    @chatbot.get("/api/student/ai/context-options")
    @login_required
    @role_required(student_role)
    def student_ai_context_options_api():
        cur = mysql.connection.cursor()
        try:
            options = get_student_ai_context_options(cur, session["user_id"])
            return options, 200
        finally:
            cur.close()

    @chatbot.post("/api/student/ai")
    @login_required
    @role_required(student_role)
    def student_ai_api():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {"error": "Question is required"}, 400

        question = data.get("question")
        if not isinstance(question, str) or not question.strip():
            return {"error": "Question is required"}, 400

        question = question.strip()
        if len(question) > 1000:
            return {"error": "Question must be at most 1000 characters"}, 400

        subject_value = data.get("subject")
        selected_subject = None
        if subject_value is not None:
            selected_subject = str(subject_value).strip()
            if not selected_subject:
                selected_subject = None

        cur = mysql.connection.cursor()
        try:
            context = fetch_student_context(cur, session["user_id"])
            if not context or not context.get("current_class"):
                grounding = {"version": "1", "subject": None, "status": "general_only", "recommendations": [], "notes": [], "support_plans": [], "evidence_summary": {"recommendation_count": 0, "note_count": 0, "support_plan_count": 0, "subject_count": 0}}
            else:
                try:
                    grounding = build_student_tutoring_context(
                        cur,
                        session["user_id"],
                        selected_subject=selected_subject,
                        question=question,
                    )
                except ValueError:
                    return {"error": "Selected subject is not currently authorized"}, 400
            resolved_subject = selected_subject or grounding.get("subject") or __import__('ai.grounded_tutor', fromlist=['get_subject']).get_subject(question)
            subject, answer, mode = generate_answer(
                question,
                api_key=os.getenv("GEMINI_API_KEY"),
                model=os.getenv("GEMINI_MODEL"),
                subject=resolved_subject,
                grounding=grounding,
            )

            cur.execute(
                """
                INSERT INTO chat_history (user_id, question, answer)
                VALUES (%s, %s, %s)
                """,
                (session["user_id"], question, answer)
            )
            mysql.connection.commit()
            return {
                "subject": subject,
                "question": question,
                "answer": answer,
                "mode": mode,
                "grounding": {
                    "version": grounding.get("version") or "1",
                    "status": grounding.get("status") or "general_only",
                    "subject": grounding.get("subject"),
                    "sources": [
                        {"kind": "general", "title": "General tutor response"}
                    ] if not grounding.get("recommendations") and not grounding.get("notes") and not grounding.get("support_plans") else [
                        *[
                            {"kind": "recommendation", "title": item.get("title", "Learning recommendation")}
                            for item in (grounding.get("recommendations") or [])[:3]
                        ],
                        *[
                            {"kind": "note", "title": item.get("title", "Teacher note"), "chapter": item.get("chapter")}
                            for item in (grounding.get("notes") or [])[:3]
                        ],
                        *[
                            {"kind": "support_plan", "title": item.get("focus_area", "Teacher support plan")}
                            for item in (grounding.get("support_plans") or [])[:3]
                        ],
                    ]
                }
            }, 200
        except Exception as error:
            mysql.connection.rollback()
            print("AI assistant error:", error)
            return {"error": "AI assistant failed to generate a response"}, 500
        finally:
            cur.close()

    return chatbot
