"""Student Learning Material access and Teacher management APIs."""

from flask import Blueprint, current_app, request, send_file, session

from backend.learning_materials import (
    MaterialUploadError,
    cleanup_staged_material_uploads,
    finalize_staged_material_uploads,
    safe_storage_path,
    stage_material_uploads,
)
from backend.student_access import (
    fetch_student_context,
    student_note_visibility_clause,
    student_note_visibility_params,
)
from backend.time_utils import serialize_nepal_datetime


class NoteRequestError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def _request_fields():
    if request.mimetype == "multipart/form-data":
        return request.form.to_dict()
    return request.get_json(silent=True)


def _resolve_teacher_target(cur, teacher_id, class_id, subject, student_id=None):
    try:
        class_id = int(class_id)
    except (TypeError, ValueError):
        raise NoteRequestError("Select an assigned class.") from None

    cur.execute(
        """SELECT c.id AS class_id, c.name AS class_name, c.grade,
                  c.section, sub.id AS subject_id, sub.name AS subject_name
           FROM teacher_class_subjects tcs
           INNER JOIN classes c ON c.id = tcs.class_id
           INNER JOIN subjects sub ON sub.id = tcs.subject_id
           WHERE tcs.teacher_user_id = %s AND tcs.class_id = %s
             AND LOWER(TRIM(sub.name)) = LOWER(TRIM(%s))
           LIMIT 1""",
        (teacher_id, class_id, subject),
    )
    assignment = cur.fetchone()
    if not assignment:
        raise NoteRequestError(
            "You are not assigned to teach this subject in the selected class.",
            403,
        )

    if student_id in (None, ""):
        return assignment, None
    try:
        student_id = int(student_id)
    except (TypeError, ValueError):
        raise NoteRequestError("Select a currently enrolled Student.") from None

    cur.execute(
        """SELECT s.id, s.full_name
           FROM students s
           INNER JOIN student_class_enrollments sce ON sce.student_id = s.id
           WHERE s.id = %s AND sce.class_id = %s AND sce.ended_at IS NULL
           LIMIT 1""",
        (student_id, class_id),
    )
    student = cur.fetchone()
    if not student:
        raise NoteRequestError(
            "The selected Student is not currently enrolled in this class."
        )
    return assignment, student


def _get_owned_note(cur, note_id, teacher_id):
    cur.execute(
        """SELECT n.id, n.title, n.subject, n.chapter, n.content,
                  n.created_at, n.uploaded_by, n.target_class_id,
                  n.target_student_id, c.name AS target_class_name,
                  s.full_name AS target_student_name
           FROM notes n
           LEFT JOIN classes c ON c.id = n.target_class_id
           LEFT JOIN students s ON s.id = n.target_student_id
           WHERE n.id = %s AND n.uploaded_by = %s""",
        (note_id, teacher_id),
    )
    return cur.fetchone()


def _get_note_attachments(cur, note_ids):
    attachments_by_note = {note_id: [] for note_id in note_ids}
    if not note_ids:
        return attachments_by_note
    placeholders = ", ".join(["%s"] * len(note_ids))
    cur.execute(
        f"""SELECT id, note_id, original_filename, mime_type, size_bytes,
                   created_at
            FROM note_attachments
            WHERE note_id IN ({placeholders})
            ORDER BY id""",
        tuple(note_ids),
    )
    for attachment in cur.fetchall():
        attachment["size_bytes"] = int(attachment["size_bytes"] or 0)
        attachment["created_at"] = serialize_nepal_datetime(
            attachment["created_at"]
        )
        attachments_by_note[attachment["note_id"]].append(attachment)
    return attachments_by_note


def _current_upload_root(upload_root):
    return upload_root or current_app.config["LEARNING_MATERIAL_UPLOAD_DIR"]


def _safe_delete_stored_file(upload_root, filename):
    if not filename:
        return
    try:
        safe_storage_path(upload_root, filename).unlink(missing_ok=True)
    except (OSError, ValueError):
        return


def _attachment_response(upload_root, attachment):
    try:
        path = safe_storage_path(upload_root, attachment["stored_filename"])
    except ValueError:
        return {"error": "Attachment not found"}, 404
    if not path.is_file():
        return {"error": "Attachment not found"}, 404
    response = send_file(
        path,
        mimetype=attachment["mime_type"] or "application/octet-stream",
        as_attachment=True,
        download_name=attachment["original_filename"],
        conditional=False,
        max_age=0,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _assert_note_assignment(cur, teacher_id, note, require_class=True):
    if note["target_class_id"] is None:
        if require_class:
            raise NoteRequestError(
                "Choose a class in the material details before managing attachments."
            )
        cur.execute(
            """SELECT 1 FROM teacher_class_subjects tcs
               INNER JOIN subjects sub ON sub.id = tcs.subject_id
               WHERE tcs.teacher_user_id = %s
                 AND LOWER(TRIM(sub.name)) = LOWER(TRIM(%s))
               LIMIT 1""",
            (teacher_id, note["subject"]),
        )
    else:
        cur.execute(
            """SELECT 1 FROM teacher_class_subjects tcs
               INNER JOIN subjects sub ON sub.id = tcs.subject_id
               WHERE tcs.teacher_user_id = %s AND tcs.class_id = %s
                 AND LOWER(TRIM(sub.name)) = LOWER(TRIM(%s))
               LIMIT 1""",
            (teacher_id, note["target_class_id"], note["subject"]),
        )
    if not cur.fetchone():
        raise NoteRequestError(
            "Your current teaching assignment does not allow this material change.",
            403,
        )


def create_notes_blueprint(
    mysql,
    login_required,
    role_required,
    student_role,
    teacher_role,
    upload_root=None,
):
    notes = Blueprint("notes", __name__)

    @notes.get("/api/student/notes")
    @login_required
    @role_required(student_role)
    def student_notes_api():
        cur = mysql.connection.cursor()
        try:
            context = fetch_student_context(cur, session["user_id"])
            if not context or not context["current_class"]:
                return {"notes": []}, 200
            class_id = context["current_class"]["id"]
            student_id = context["student_id"]
            cur.execute(
                f"""SELECT n.id, n.title, n.subject, n.chapter, n.content,
                          n.created_at, c.name AS target_class_name,
                          CASE
                              WHEN n.target_class_id IS NULL THEN 'legacy'
                              WHEN n.target_student_id IS NULL THEN 'class'
                              ELSE 'student'
                          END AS audience_type
                   FROM notes n
                   LEFT JOIN classes c ON c.id = n.target_class_id
                   WHERE {student_note_visibility_clause('n')}
                   ORDER BY n.created_at DESC, n.id DESC""",
                student_note_visibility_params(class_id, student_id),
            )
            materials = cur.fetchall()
            attachments = _get_note_attachments(
                cur, [material["id"] for material in materials]
            )
            for material in materials:
                material["created_at"] = serialize_nepal_datetime(
                    material["created_at"]
                )
                material["attachments"] = attachments[material["id"]]
                material["attachment_count"] = len(material["attachments"])
            return {"notes": materials}, 200
        finally:
            cur.close()

    @notes.get("/api/teacher/notes")
    @login_required
    @role_required(teacher_role)
    def teacher_notes_api():
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT n.id, n.title, n.subject, n.chapter, n.content,
                          n.created_at, n.target_class_id,
                          n.target_student_id, c.name AS target_class_name,
                          s.full_name AS target_student_name,
                          CASE
                              WHEN n.target_class_id IS NULL THEN 'legacy'
                              WHEN n.target_student_id IS NULL THEN 'class'
                              ELSE 'student'
                          END AS audience_type
                   FROM notes n
                   LEFT JOIN classes c ON c.id = n.target_class_id
                   LEFT JOIN students s ON s.id = n.target_student_id
                   WHERE n.uploaded_by = %s
                   ORDER BY n.created_at DESC, n.id DESC""",
                (session["user_id"],)
            )
            materials = cur.fetchall()
            attachments = _get_note_attachments(
                cur, [material["id"] for material in materials]
            )
            for material in materials:
                material["created_at"] = serialize_nepal_datetime(
                    material["created_at"]
                )
                material["attachments"] = attachments[material["id"]]
                material["attachment_count"] = len(material["attachments"])
            return {"notes": materials}, 200
        finally:
            cur.close()

    @notes.get("/api/teacher/notes/options")
    @login_required
    @role_required(teacher_role)
    def teacher_note_options_api():
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT DISTINCT c.id AS class_id, c.name AS class_name,
                          c.grade, c.section, sub.id AS subject_id,
                          sub.name AS subject_name
                   FROM teacher_class_subjects tcs
                   INNER JOIN classes c ON c.id = tcs.class_id
                   INNER JOIN subjects sub ON sub.id = tcs.subject_id
                   WHERE tcs.teacher_user_id = %s
                   ORDER BY c.grade, c.section, c.name, sub.name""",
                (session["user_id"],),
            )
            assignments = cur.fetchall()
            cur.execute(
                """SELECT DISTINCT s.id AS student_id, s.full_name,
                          sce.class_id
                   FROM teacher_class_subjects tcs
                   INNER JOIN student_class_enrollments sce
                     ON sce.class_id = tcs.class_id AND sce.ended_at IS NULL
                   INNER JOIN students s ON s.id = sce.student_id
                   WHERE tcs.teacher_user_id = %s
                   ORDER BY sce.class_id, s.full_name""",
                (session["user_id"],),
            )
            return {
                "assignments": assignments,
                "students": cur.fetchall(),
            }, 200
        finally:
            cur.close()

    @notes.post("/api/teacher/notes")
    @login_required
    @role_required(teacher_role)
    def teacher_upload_note_api():
        data = _request_fields()
        if not isinstance(data, dict) or not data:
            return {"error": "Learning Material data is required."}, 400
        title = str(data.get("title") or "").strip()
        subject = str(data.get("subject") or "").strip()
        chapter = str(data.get("chapter") or "").strip()
        content = str(data.get("content") or "").strip()
        class_id = data.get("class_id")
        if not title or len(title) > 200:
            return {"error": "Enter a title of 200 characters or fewer."}, 400
        if not subject or len(subject) > 100:
            return {"error": "Select a subject."}, 400
        if not chapter or len(chapter) > 100:
            return {"error": "Enter a chapter of 100 characters or fewer."}, 400
        if len(content.encode("utf-8")) > 64000:
            return {"error": "Written content must be 64 KB or smaller."}, 400

        cur = mysql.connection.cursor()
        staged = []
        root = _current_upload_root(upload_root)
        try:
            assignment, student = _resolve_teacher_target(
                cur, session["user_id"], class_id, subject,
                data.get("student_id"),
            )
            try:
                staged = stage_material_uploads(
                    request.files.getlist("files"), root
                )
            except MaterialUploadError as error:
                return {"error": str(error)}, error.status_code
            if not content and not staged:
                cleanup_staged_material_uploads(root, staged)
                return {
                    "error": "Add written content or at least one attachment."
                }, 400

            cur.execute(
                """INSERT INTO notes
                       (title, subject, chapter, content, uploaded_by,
                        target_class_id, target_student_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    title, assignment["subject_name"], chapter, content,
                    session["user_id"], assignment["class_id"],
                    student["id"] if student else None,
                ),
            )
            note_id = cur.lastrowid
            finalize_staged_material_uploads(root, staged)
            for item in staged:
                cur.execute(
                    """INSERT INTO note_attachments
                           (note_id, original_filename, stored_filename,
                            mime_type, size_bytes)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (
                        note_id, item["original_filename"],
                        item["stored_filename"], item["mime_type"],
                        item["size_bytes"],
                    ),
                )
            mysql.connection.commit()
            return {
                "message": "Learning material uploaded.",
                "note_id": note_id,
                "attachment_count": len(staged),
            }, 201
        except NoteRequestError as error:
            cleanup_staged_material_uploads(root, staged)
            return {"error": str(error)}, error.status_code
        except Exception as error:
            mysql.connection.rollback()
            cleanup_staged_material_uploads(root, staged)
            print("Teacher Learning Material upload error:", error)
            return {"error": "Unable to upload Learning Material."}, 500
        finally:
            cur.close()

    @notes.get("/api/teacher/notes/<int:note_id>")
    @login_required
    @role_required(teacher_role)
    def teacher_note_detail_api(note_id):
        cur = mysql.connection.cursor()
        try:
            note = _get_owned_note(cur, note_id, session["user_id"])
            if not note:
                return {"error": "Note not found"}, 404
            note["attachments"] = _get_note_attachments(cur, [note_id])[note_id]
            note["created_at"] = serialize_nepal_datetime(note["created_at"])
            note["attachment_count"] = len(note["attachments"])
            note["audience_type"] = (
                "legacy" if note["target_class_id"] is None
                else "student" if note["target_student_id"] is not None
                else "class"
            )
            return {"note": note}, 200
        finally:
            cur.close()

    @notes.put("/api/teacher/notes/<int:note_id>")
    @login_required
    @role_required(teacher_role)
    def teacher_update_note_api(note_id):
        data = _request_fields()
        if not isinstance(data, dict) or not data:
            return {"error": "Learning Material data is required."}, 400

        title = str(data.get("title") or "").strip()
        subject = str(data.get("subject") or "").strip()
        chapter = str(data.get("chapter") or "").strip()
        content = str(data.get("content") or "").strip()
        if not title or len(title) > 200 or not subject or not chapter or len(chapter) > 100:
            return {"error": "Enter a title, subject, and chapter."}, 400
        if len(content.encode("utf-8")) > 64000:
            return {"error": "Written content must be 64 KB or smaller."}, 400

        cur = mysql.connection.cursor()
        try:
            existing = _get_owned_note(cur, note_id, session["user_id"])
            if not existing:
                return {"error": "Note not found"}, 404
            assignment, student = _resolve_teacher_target(
                cur,
                session["user_id"],
                data.get("class_id"),
                subject,
                data.get("student_id"),
            )
            cur.execute(
                "SELECT COUNT(*) AS attachment_count FROM note_attachments WHERE note_id = %s",
                (note_id,),
            )
            attachment_count = int(cur.fetchone()["attachment_count"] or 0)
            if not content and not attachment_count:
                return {
                    "error": "Add written content or at least one attachment."
                }, 400

            cur.execute(
                """UPDATE notes
                   SET title = %s, subject = %s, chapter = %s, content = %s,
                       target_class_id = %s, target_student_id = %s
                   WHERE id = %s AND uploaded_by = %s""",
                (
                    title,
                    assignment["subject_name"],
                    chapter,
                    content,
                    assignment["class_id"],
                    student["id"] if student else None,
                    note_id,
                    session["user_id"]
                )
            )
            mysql.connection.commit()
            return {"message": "Learning Material updated."}, 200
        except NoteRequestError as error:
            return {"error": str(error)}, error.status_code
        except Exception as error:
            mysql.connection.rollback()
            print("Teacher Learning Material update error:", error)
            return {"error": "Unable to update Learning Material."}, 500
        finally:
            cur.close()

    @notes.delete("/api/teacher/notes/<int:note_id>")
    @login_required
    @role_required(teacher_role)
    def teacher_delete_note_api(note_id):
        cur = mysql.connection.cursor()
        filenames = []
        try:
            if not _get_owned_note(cur, note_id, session["user_id"]):
                return {"error": "Note not found"}, 404
            cur.execute(
                "SELECT stored_filename FROM note_attachments WHERE note_id = %s",
                (note_id,),
            )
            filenames = [item["stored_filename"] for item in cur.fetchall()]
            cur.execute("DELETE FROM note_attachments WHERE note_id = %s", (note_id,))
            cur.execute(
                "DELETE FROM notes WHERE id = %s AND uploaded_by = %s",
                (note_id, session["user_id"])
            )
            mysql.connection.commit()
            root = _current_upload_root(upload_root)
            for filename in filenames:
                _safe_delete_stored_file(root, filename)
            return {"message": "Learning Material deleted."}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Teacher Learning Material deletion error:", error)
            return {"error": "Unable to delete Learning Material."}, 500
        finally:
            cur.close()

    @notes.get(
        "/api/student/notes/<int:note_id>/attachments/<int:attachment_id>/download"
    )
    @login_required
    @role_required(student_role)
    def student_download_note_attachment_api(note_id, attachment_id):
        cur = mysql.connection.cursor()
        try:
            context = fetch_student_context(cur, session["user_id"])
            if not context or not context["current_class"]:
                return {"error": "Attachment not found"}, 404
            cur.execute(
                f"""SELECT n.id FROM notes n
                    WHERE n.id = %s AND {student_note_visibility_clause('n')}""",
                (note_id, *student_note_visibility_params(
                    context["current_class"]["id"], context["student_id"]
                )),
            )
            if not cur.fetchone():
                return {"error": "Attachment not found"}, 404
            cur.execute(
                """SELECT id, original_filename, stored_filename, mime_type
                   FROM note_attachments
                   WHERE id = %s AND note_id = %s""",
                (attachment_id, note_id),
            )
            attachment = cur.fetchone()
            if not attachment:
                return {"error": "Attachment not found"}, 404
            return _attachment_response(_current_upload_root(upload_root), attachment)
        finally:
            cur.close()

    @notes.get(
        "/api/teacher/notes/<int:note_id>/attachments/<int:attachment_id>/download"
    )
    @login_required
    @role_required(teacher_role)
    def teacher_download_note_attachment_api(note_id, attachment_id):
        cur = mysql.connection.cursor()
        try:
            if not _get_owned_note(cur, note_id, session["user_id"]):
                return {"error": "Attachment not found"}, 404
            cur.execute(
                """SELECT id, original_filename, stored_filename, mime_type
                   FROM note_attachments
                   WHERE id = %s AND note_id = %s""",
                (attachment_id, note_id),
            )
            attachment = cur.fetchone()
            if not attachment:
                return {"error": "Attachment not found"}, 404
            return _attachment_response(_current_upload_root(upload_root), attachment)
        finally:
            cur.close()

    @notes.post("/api/teacher/notes/<int:note_id>/attachments")
    @login_required
    @role_required(teacher_role)
    def teacher_add_note_attachments_api(note_id):
        cur = mysql.connection.cursor()
        staged = []
        root = _current_upload_root(upload_root)
        try:
            note = _get_owned_note(cur, note_id, session["user_id"])
            if not note:
                return {"error": "Learning Material not found"}, 404
            _assert_note_assignment(cur, session["user_id"], note)
            cur.execute(
                "SELECT COUNT(*) AS attachment_count FROM note_attachments WHERE note_id = %s",
                (note_id,),
            )
            existing_count = int(cur.fetchone()["attachment_count"] or 0)
            try:
                staged = stage_material_uploads(request.files.getlist("files"), root)
            except MaterialUploadError as error:
                return {"error": str(error)}, error.status_code
            if not staged:
                return {"error": "Choose at least one attachment."}, 400
            if existing_count + len(staged) > 10:
                cleanup_staged_material_uploads(root, staged)
                return {
                    "error": "A Learning Material can include at most 10 files."
                }, 400

            finalize_staged_material_uploads(root, staged)
            for item in staged:
                cur.execute(
                    """INSERT INTO note_attachments
                           (note_id, original_filename, stored_filename,
                            mime_type, size_bytes)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (
                        note_id, item["original_filename"],
                        item["stored_filename"], item["mime_type"],
                        item["size_bytes"],
                    ),
                )
            mysql.connection.commit()
            return {
                "message": "Attachments added.",
                "attachment_count": existing_count + len(staged),
            }, 201
        except NoteRequestError as error:
            cleanup_staged_material_uploads(root, staged)
            return {"error": str(error)}, error.status_code
        except Exception as error:
            mysql.connection.rollback()
            cleanup_staged_material_uploads(root, staged)
            print("Teacher attachment upload error:", error)
            return {"error": "Unable to add attachments."}, 500
        finally:
            cur.close()

    @notes.delete(
        "/api/teacher/notes/<int:note_id>/attachments/<int:attachment_id>"
    )
    @login_required
    @role_required(teacher_role)
    def teacher_remove_note_attachment_api(note_id, attachment_id):
        cur = mysql.connection.cursor()
        attachment = None
        try:
            note = _get_owned_note(cur, note_id, session["user_id"])
            if not note:
                return {"error": "Attachment not found"}, 404
            _assert_note_assignment(cur, session["user_id"], note)
            cur.execute(
                """SELECT id, stored_filename FROM note_attachments
                   WHERE id = %s AND note_id = %s""",
                (attachment_id, note_id),
            )
            attachment = cur.fetchone()
            if not attachment:
                return {"error": "Attachment not found"}, 404
            cur.execute(
                "SELECT COUNT(*) AS attachment_count FROM note_attachments WHERE note_id = %s",
                (note_id,),
            )
            attachment_count = int(cur.fetchone()["attachment_count"] or 0)
            if not str(note["content"] or "").strip() and attachment_count <= 1:
                return {
                    "error": "Add written content before removing the final attachment."
                }, 400
            cur.execute(
                "DELETE FROM note_attachments WHERE id = %s AND note_id = %s",
                (attachment_id, note_id),
            )
            mysql.connection.commit()
            _safe_delete_stored_file(
                _current_upload_root(upload_root), attachment["stored_filename"]
            )
            return {"message": "Attachment removed."}, 200
        except NoteRequestError as error:
            return {"error": str(error)}, error.status_code
        except Exception as error:
            mysql.connection.rollback()
            print("Teacher attachment deletion error:", error)
            return {"error": "Unable to remove attachment."}, 500
        finally:
            cur.close()

    return notes
