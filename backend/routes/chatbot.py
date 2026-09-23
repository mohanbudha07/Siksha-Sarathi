"""Student AI study-assistant API routes."""

from flask import Blueprint, request, session

from ai.assistant import generate_answer


def create_chatbot_blueprint(
    mysql,
    login_required,
    role_required,
    student_role
):
    chatbot = Blueprint("chatbot", __name__)

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

        try:
            subject, answer, mode = generate_answer(question)
            cur = mysql.connection.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO chat_history (user_id, question, answer)
                    VALUES (%s, %s, %s)
                    """,
                    (session["user_id"], question, answer)
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
        except Exception as error:
            mysql.connection.rollback()
            print("AI assistant error:", error)
            return {
                "error": "AI assistant failed to generate a response"
            }, 500

    return chatbot
