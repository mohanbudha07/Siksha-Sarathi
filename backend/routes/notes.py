"""Student reading notes and teacher note-management API routes."""

from flask import Blueprint, request, session


def create_notes_blueprint(
    mysql,
    login_required,
    role_required,
    student_role,
    teacher_role
):
    notes = Blueprint("notes", __name__)

    @notes.get("/api/student/notes")
    @login_required
    @role_required(student_role)
    def student_notes_api():
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """
                SELECT id, title, subject, chapter, content, created_at
                FROM notes
                ORDER BY created_at DESC
                """
            )
            return {"notes": cur.fetchall()}, 200
        finally:
            cur.close()

    @notes.get("/api/teacher/notes")
    @login_required
    @role_required(teacher_role)
    def teacher_notes_api():
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """
                SELECT id, title, subject, chapter, content, created_at
                FROM notes
                WHERE uploaded_by = %s
                ORDER BY created_at DESC
                """,
                (session["user_id"],)
            )
            return {"notes": cur.fetchall()}, 200
        finally:
            cur.close()

    @notes.post("/api/teacher/notes")
    @login_required
    @role_required(teacher_role)
    def teacher_upload_note_api():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not data:
            return {"error": "Note data is required"}, 400

        title = str(data.get("title") or "").strip()
        subject = str(data.get("subject") or "").strip()
        chapter = str(data.get("chapter") or "").strip()
        content = str(data.get("content") or "").strip()
        if not all([title, subject, chapter, content]):
            return {"error": "All note fields are required"}, 400

        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """
                INSERT INTO notes
                    (title, subject, chapter, content, uploaded_by)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (title, subject, chapter, content, session["user_id"])
            )
            mysql.connection.commit()
            return {"message": "Note uploaded successfully"}, 201
        except Exception as error:
            mysql.connection.rollback()
            print("Teacher note upload error:", error)
            return {"error": "Failed to upload note"}, 500
        finally:
            cur.close()

    @notes.get("/api/teacher/notes/<int:note_id>")
    @login_required
    @role_required(teacher_role)
    def teacher_note_detail_api(note_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """
                SELECT id, title, subject, chapter, content, created_at
                FROM notes
                WHERE id = %s AND uploaded_by = %s
                """,
                (note_id, session["user_id"])
            )
            note = cur.fetchone()
            if not note:
                return {"error": "Note not found"}, 404
            return {"note": note}, 200
        finally:
            cur.close()

    @notes.put("/api/teacher/notes/<int:note_id>")
    @login_required
    @role_required(teacher_role)
    def teacher_update_note_api(note_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not data:
            return {"error": "Note data is required"}, 400

        title = str(data.get("title") or "").strip()
        subject = str(data.get("subject") or "").strip()
        chapter = str(data.get("chapter") or "").strip()
        content = str(data.get("content") or "").strip()
        if not all([title, subject, chapter, content]):
            return {"error": "All note fields are required"}, 400

        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """
                SELECT id FROM notes
                WHERE id = %s AND uploaded_by = %s
                """,
                (note_id, session["user_id"])
            )
            if not cur.fetchone():
                return {"error": "Note not found"}, 404

            cur.execute(
                """
                UPDATE notes
                SET title = %s, subject = %s, chapter = %s, content = %s
                WHERE id = %s AND uploaded_by = %s
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
            return {"message": "Note updated successfully"}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Teacher note update error:", error)
            return {"error": "Failed to update note"}, 500
        finally:
            cur.close()

    @notes.delete("/api/teacher/notes/<int:note_id>")
    @login_required
    @role_required(teacher_role)
    def teacher_delete_note_api(note_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """
                SELECT id FROM notes
                WHERE id = %s AND uploaded_by = %s
                """,
                (note_id, session["user_id"])
            )
            if not cur.fetchone():
                return {"error": "Note not found"}, 404

            cur.execute(
                """
                DELETE FROM notes
                WHERE id = %s AND uploaded_by = %s
                """,
                (note_id, session["user_id"])
            )
            mysql.connection.commit()
            return {"message": "Note deleted successfully"}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Teacher note deletion error:", error)
            return {"error": "Failed to delete note"}, 500
        finally:
            cur.close()

    return notes
