"""Official one-way notices and publication-time recipient delivery."""

from flask import Blueprint, request, session


NOTICE_ROLES = {"student", "teacher", "admin"}
ADMIN_AUDIENCES = {"all", "students", "teachers", "class", "student", "teacher"}


def parse_id(value, message):
    if isinstance(value, bool):
        raise ValueError(message)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(message) from error
    if parsed < 1 or str(value).strip() != str(parsed):
        raise ValueError(message)
    return parsed


def normalized_content(data):
    if not isinstance(data, dict):
        raise ValueError("Notice data is required")
    if "recipient_ids" in data or "user_ids" in data:
        raise ValueError("Recipients are derived from the selected audience")
    title = str(data.get("title") or "").strip()
    body = str(data.get("body") or "").strip()
    if not title or len(title) > 200:
        raise ValueError("Title is required and must be at most 200 characters")
    if not body or len(body) > 5000:
        raise ValueError("Body is required and must be at most 5000 characters")
    return title, body


def fetch_user_role(cur, user_id):
    cur.execute(
        "SELECT role, must_change_password FROM users WHERE id = %s",
        (user_id,)
    )
    row = cur.fetchone()
    if not row or row["role"] not in NOTICE_ROLES:
        return None, ({"error": "Authentication required"}, 401)
    if bool(row["must_change_password"]):
        return None, ({
            "error": "Password change required before using this feature"
        }, 403)
    return row["role"], None


def active_class_students(cur, class_id):
    cur.execute(
        """SELECT s.user_id
           FROM students s
           INNER JOIN student_class_enrollments sce
             ON sce.student_id = s.id AND sce.ended_at IS NULL
           WHERE sce.class_id = %s
           ORDER BY s.id""",
        (class_id,)
    )
    return [int(row["user_id"]) for row in cur.fetchall()]


def teacher_has_active_class(cur, teacher_id, class_id):
    cur.execute(
        """SELECT id FROM class_teacher_assignments
           WHERE teacher_user_id = %s AND class_id = %s
             AND ended_at IS NULL""",
        (teacher_id, class_id)
    )
    return cur.fetchone() is not None


def teacher_has_class_scope(cur, teacher_id, class_id):
    cur.execute(
        """SELECT 1 AS allowed
           WHERE EXISTS (
               SELECT 1 FROM class_teacher_assignments cta
               WHERE cta.teacher_user_id = %s AND cta.class_id = %s
                 AND cta.ended_at IS NULL
           ) OR EXISTS (
               SELECT 1 FROM teacher_class_subjects tcs
               WHERE tcs.teacher_user_id = %s AND tcs.class_id = %s
           )
           LIMIT 1""",
        (teacher_id, class_id, teacher_id, class_id)
    )
    return cur.fetchone() is not None


def publish_notice(cur, connection, publisher_id, title, body, visibility,
                   audience_type, target_class_id=None,
                   target_subject_id=None, target_user_id=None,
                   recipient_ids=None):
    recipients = sorted(set(recipient_ids or []))
    if not recipients:
        raise ValueError("No eligible recipients were found for this notice.")
    cur.execute(
        """INSERT INTO notices
           (created_by_user_id, title, body, visibility, audience_type,
            target_class_id, target_subject_id, target_user_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (publisher_id, title, body, visibility, audience_type,
         target_class_id, target_subject_id, target_user_id)
    )
    notice_id = cur.lastrowid
    for user_id in recipients:
        cur.execute(
            "INSERT INTO notice_recipients (notice_id, user_id) VALUES (%s, %s)",
            (notice_id, user_id)
        )
    connection.commit()
    return notice_id, len(recipients)


def create_notices_blueprint(
    mysql,
    login_required,
    role_required,
    student_role,
    teacher_role,
    admin_role
):
    notices = Blueprint("notices", __name__)

    @notices.post("/api/admin/notices")
    @login_required
    @role_required(admin_role)
    def admin_publish_notice_api():
        data = request.get_json(silent=True)
        try:
            title, body = normalized_content(data)
            visibility = str(data.get("visibility") or "internal").strip()
            audience_type = str(data.get("audience_type") or "").strip()
            if visibility not in {"internal", "public"}:
                raise ValueError("Visibility must be internal or public")
            if audience_type not in ADMIN_AUDIENCES:
                raise ValueError("Audience type is invalid for Admin publishing")
            if visibility == "public" and audience_type != "all":
                raise ValueError("Public notices must target the entire institution")
        except (ValueError, TypeError) as error:
            return {"error": str(error)}, 400

        user_id = session["user_id"]
        cur = mysql.connection.cursor()
        try:
            target_class_id = None
            target_subject_id = None
            target_user_id = None
            if audience_type == "all":
                cur.execute(
                    "SELECT id FROM users WHERE role IN ('student','teacher','admin')"
                )
                recipient_ids = [int(row["id"]) for row in cur.fetchall()]
            elif audience_type == "students":
                cur.execute(
                    """SELECT u.id FROM users u
                       INNER JOIN students s ON s.user_id = u.id
                       WHERE u.role = 'student' ORDER BY u.id"""
                )
                recipient_ids = [int(row["id"]) for row in cur.fetchall()]
            elif audience_type == "teachers":
                cur.execute(
                    "SELECT id FROM users WHERE role = 'teacher' ORDER BY id"
                )
                recipient_ids = [int(row["id"]) for row in cur.fetchall()]
            elif audience_type == "class":
                try:
                    target_class_id = parse_id(data.get("class_id"), "Class is required")
                except ValueError as error:
                    return {"error": str(error)}, 400
                cur.execute("SELECT id FROM classes WHERE id = %s", (target_class_id,))
                if not cur.fetchone():
                    return {"error": "Class not found"}, 404
                recipient_ids = active_class_students(cur, target_class_id)
            elif audience_type == "student":
                try:
                    student_id = parse_id(data.get("student_id"), "Student is required")
                except ValueError as error:
                    return {"error": str(error)}, 400
                cur.execute(
                    "SELECT user_id FROM students WHERE id = %s", (student_id,)
                )
                student = cur.fetchone()
                if not student:
                    return {"error": "Student not found"}, 404
                target_user_id = int(student["user_id"])
                recipient_ids = [target_user_id]
            else:
                try:
                    target_user_id = parse_id(
                        data.get("teacher_user_id"), "Teacher is required"
                    )
                except ValueError as error:
                    return {"error": str(error)}, 400
                cur.execute(
                    "SELECT id FROM users WHERE id = %s AND role = 'teacher'",
                    (target_user_id,)
                )
                if not cur.fetchone():
                    return {"error": "Teacher not found"}, 404
                recipient_ids = [target_user_id]

            try:
                notice_id, delivered = publish_notice(
                    cur, mysql.connection, user_id, title, body, visibility,
                    audience_type, target_class_id, target_subject_id,
                    target_user_id, recipient_ids
                )
            except ValueError as error:
                mysql.connection.rollback()
                return {"error": str(error)}, 400
            return {"notice_id": notice_id, "delivered_count": delivered}, 201
        except Exception as error:
            mysql.connection.rollback()
            print("Admin notice publish error:", error)
            return {"error": "Unable to publish notice"}, 500
        finally:
            cur.close()

    @notices.get("/api/admin/notices/options")
    @login_required
    @role_required(admin_role)
    def admin_notice_options_api():
        cur = mysql.connection.cursor()
        try:
            cur.execute("SELECT id, name, grade, section FROM classes ORDER BY grade, section")
            classes = cur.fetchall()
            cur.execute(
                """SELECT s.id AS student_id, s.full_name,
                          c.name AS class_name
                   FROM students s
                   LEFT JOIN student_class_enrollments sce
                     ON sce.student_id = s.id AND sce.ended_at IS NULL
                   LEFT JOIN classes c ON c.id = sce.class_id
                   ORDER BY s.full_name"""
            )
            students = cur.fetchall()
            cur.execute(
                "SELECT id AS teacher_user_id, username FROM users "
                "WHERE role = 'teacher' ORDER BY username"
            )
            teachers = cur.fetchall()
            return {"classes": classes, "students": students, "teachers": teachers}, 200
        finally:
            cur.close()

    @notices.get("/api/teacher/notices/options")
    @login_required
    @role_required(teacher_role)
    def teacher_notice_options_api():
        teacher_id = session["user_id"]
        cur = None
        try:
            cur = mysql.connection.cursor()
            cur.execute(
                """SELECT c.id AS class_id, c.name AS class_name,
                          c.grade, c.section
                   FROM class_teacher_assignments cta
                   INNER JOIN classes c ON c.id = cta.class_id
                   WHERE cta.teacher_user_id = %s AND cta.ended_at IS NULL
                   ORDER BY c.grade, c.section, c.name""",
                (teacher_id,)
            )
            class_teacher_classes = cur.fetchall()
            cur.execute(
                """SELECT DISTINCT c.id AS class_id, c.name AS class_name,
                          c.grade, c.section, sub.id AS subject_id,
                          sub.name AS subject_name
                   FROM teacher_class_subjects tcs
                   INNER JOIN classes c ON c.id = tcs.class_id
                   INNER JOIN subjects sub ON sub.id = tcs.subject_id
                   WHERE tcs.teacher_user_id = %s
                   ORDER BY c.grade, c.section, sub.name""",
                (teacher_id,)
            )
            subject_assignments = cur.fetchall()
            cur.execute(
                                """SELECT student_id, full_name, class_id, class_name
                                     FROM (
                                             SELECT DISTINCT s.id AS student_id, s.full_name,
                                                            sce.class_id, c.name AS class_name,
                                                            c.grade, c.section
                                             FROM students s
                                             INNER JOIN student_class_enrollments sce
                                                 ON sce.student_id = s.id AND sce.ended_at IS NULL
                                             INNER JOIN classes c ON c.id = sce.class_id
                                             WHERE EXISTS (
                                                     SELECT 1 FROM class_teacher_assignments cta
                                                     WHERE cta.teacher_user_id = %s
                                                         AND cta.class_id = sce.class_id AND cta.ended_at IS NULL
                                             ) OR EXISTS (
                                                     SELECT 1 FROM teacher_class_subjects tcs
                                                     WHERE tcs.teacher_user_id = %s
                                                         AND tcs.class_id = sce.class_id
                                             )
                                     ) AS eligible_students
                                     ORDER BY grade, section, full_name""",
                (teacher_id, teacher_id)
            )
            students = cur.fetchall()
            return {
                "class_teacher_classes": class_teacher_classes,
                "subject_assignments": subject_assignments,
                "students": students
            }, 200
        except Exception as error:
            print("Teacher notice options failed:", type(error).__name__)
            return {"error": "Unable to load notice options"}, 500
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception as error:
                    print("Teacher notice options cursor close failed:", type(error).__name__)

    @notices.post("/api/teacher/notices")
    @login_required
    @role_required(teacher_role)
    def teacher_publish_notice_api():
        data = request.get_json(silent=True)
        try:
            title, body = normalized_content(data)
            visibility = str(data.get("visibility") or "internal").strip()
            audience_type = str(data.get("audience_type") or "").strip()
            if visibility != "internal":
                raise ValueError("Teachers can publish internal notices only")
            if audience_type not in {"class", "subject", "student"}:
                raise ValueError("Audience type is invalid for Teacher publishing")
        except (ValueError, TypeError) as error:
            return {"error": str(error)}, 400

        teacher_id = session["user_id"]
        cur = mysql.connection.cursor()
        try:
            target_class_id = None
            target_subject_id = None
            target_user_id = None
            if audience_type in {"class", "subject"}:
                try:
                    target_class_id = parse_id(data.get("class_id"), "Class is required")
                except ValueError as error:
                    return {"error": str(error)}, 400
                cur.execute("SELECT id FROM classes WHERE id = %s", (target_class_id,))
                if not cur.fetchone():
                    return {"error": "Class not found"}, 404
                if audience_type == "class":
                    if not teacher_has_active_class(cur, teacher_id, target_class_id):
                        return {"error": "Active class teacher assignment not found"}, 403
                else:
                    try:
                        target_subject_id = parse_id(
                            data.get("subject_id"), "Subject is required"
                        )
                    except ValueError as error:
                        return {"error": str(error)}, 400
                    cur.execute(
                        """SELECT id FROM teacher_class_subjects
                           WHERE teacher_user_id = %s AND class_id = %s
                             AND subject_id = %s""",
                        (teacher_id, target_class_id, target_subject_id)
                    )
                    if not cur.fetchone():
                        return {"error": "Teacher is not assigned to this class and subject"}, 403
                recipient_ids = active_class_students(cur, target_class_id)
                audience_label = audience_type
            else:
                try:
                    student_id = parse_id(data.get("student_id"), "Student is required")
                except ValueError as error:
                    return {"error": str(error)}, 400
                cur.execute(
                    """SELECT s.user_id, sce.class_id
                       FROM students s
                       INNER JOIN student_class_enrollments sce
                         ON sce.student_id = s.id AND sce.ended_at IS NULL
                       WHERE s.id = %s""",
                    (student_id,)
                )
                student = cur.fetchone()
                if not student:
                    return {"error": "Student has no current enrollment"}, 404
                if not teacher_has_class_scope(
                    cur, teacher_id, student["class_id"]
                ):
                    return {"error": "Teacher is not authorized for this student"}, 403
                target_user_id = int(student["user_id"])
                recipient_ids = [target_user_id]
                audience_label = "student"

            try:
                notice_id, delivered = publish_notice(
                    cur, mysql.connection, teacher_id, title, body, "internal",
                    audience_label, target_class_id, target_subject_id,
                    target_user_id, recipient_ids
                )
            except ValueError as error:
                mysql.connection.rollback()
                return {"error": str(error)}, 400
            return {"notice_id": notice_id, "delivered_count": delivered}, 201
        except Exception as error:
            mysql.connection.rollback()
            print("Teacher notice publish error:", error)
            return {"error": "Unable to publish notice"}, 500
        finally:
            cur.close()

    @notices.get("/api/notices")
    @login_required
    def notice_inbox_api():
        cur = mysql.connection.cursor()
        try:
            user_id = session["user_id"]
            role, error = fetch_user_role(cur, user_id)
            if error:
                return error
            cur.execute(
                """SELECT n.id, n.title, n.body, n.visibility,
                          n.audience_type, creator.username AS created_by,
                          creator.role AS created_by_role, n.created_at,
                          nr.delivered_at, nr.read_at
                   FROM notice_recipients nr
                   INNER JOIN notices n ON n.id = nr.notice_id
                   INNER JOIN users creator ON creator.id = n.created_by_user_id
                   WHERE nr.user_id = %s
                   ORDER BY n.created_at DESC, n.id DESC""",
                (user_id,)
            )
            inbox = []
            unread_count = 0
            for row in cur.fetchall():
                is_read = row["read_at"] is not None
                unread_count += not is_read
                inbox.append({
                    **row,
                    "created_at": str(row["created_at"]),
                    "delivered_at": str(row["delivered_at"]),
                    "read_at": str(row["read_at"]) if is_read else None,
                    "is_read": is_read
                })
            return {"unread_count": unread_count, "notices": inbox}, 200
        finally:
            cur.close()

    @notices.get("/api/notices/unread-count")
    @login_required
    def notice_unread_count_api():
        cur = mysql.connection.cursor()
        try:
            user_id = session["user_id"]
            role, error = fetch_user_role(cur, user_id)
            if error:
                return error
            cur.execute(
                """SELECT COUNT(*) AS unread_count FROM notice_recipients
                   WHERE user_id = %s AND read_at IS NULL""",
                (user_id,)
            )
            return {"unread_count": int(cur.fetchone()["unread_count"] or 0)}, 200
        finally:
            cur.close()

    @notices.patch("/api/notices/<int:notice_id>/read")
    @login_required
    def mark_notice_read_api(notice_id):
        cur = mysql.connection.cursor()
        try:
            user_id = session["user_id"]
            role, error = fetch_user_role(cur, user_id)
            if error:
                return error
            cur.execute(
                """SELECT id FROM notice_recipients
                   WHERE notice_id = %s AND user_id = %s""",
                (notice_id, user_id)
            )
            if not cur.fetchone():
                return {"error": "Notice not found"}, 404
            cur.execute(
                """UPDATE notice_recipients
                   SET read_at = COALESCE(read_at, CURRENT_TIMESTAMP)
                   WHERE notice_id = %s AND user_id = %s""",
                (notice_id, user_id)
            )
            mysql.connection.commit()
            return {"message": "Notice marked as read"}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Notice read update error:", error)
            return {"error": "Unable to update notice read state"}, 500
        finally:
            cur.close()

    @notices.get("/api/notices/sent")
    @login_required
    def sent_notices_api():
        cur = mysql.connection.cursor()
        try:
            user_id = session["user_id"]
            role, error = fetch_user_role(cur, user_id)
            if error:
                return error
            if role not in {teacher_role, admin_role}:
                return {"error": "Access denied"}, 403
            cur.execute(
                """SELECT n.id, n.title, n.body, n.visibility, n.audience_type,
                          n.target_class_id, n.target_subject_id,
                          n.target_user_id, n.created_at,
                          COUNT(nr.id) AS delivered_count,
                          COALESCE(SUM(nr.read_at IS NOT NULL), 0) AS read_count,
                          COUNT(nr.id) - COALESCE(SUM(nr.read_at IS NOT NULL), 0)
                              AS unread_count
                   FROM notices n
                   LEFT JOIN notice_recipients nr ON nr.notice_id = n.id
                   WHERE n.created_by_user_id = %s
                   GROUP BY n.id, n.title, n.body, n.visibility, n.audience_type,
                            n.target_class_id, n.target_subject_id,
                            n.target_user_id, n.created_at
                   ORDER BY n.created_at DESC, n.id DESC""",
                (user_id,)
            )
            sent = cur.fetchall()
            for row in sent:
                row["created_at"] = str(row["created_at"])
                for key in ("delivered_count", "read_count", "unread_count"):
                    row[key] = int(row[key] or 0)
            return {"notices": sent}, 200
        finally:
            cur.close()

    @notices.get("/api/public/notices")
    def public_notices_api():
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT id, title, body, created_at FROM notices
                   WHERE visibility = 'public' AND audience_type = 'all'
                   ORDER BY created_at DESC, id DESC LIMIT 10"""
            )
            public_notices = cur.fetchall()
            for notice in public_notices:
                notice["created_at"] = str(notice["created_at"])
            return {"notices": public_notices}, 200
        except Exception as error:
            print("Public notices error:", error)
            return {"error": "Unable to load public notices"}, 500
        finally:
            cur.close()

    return notices