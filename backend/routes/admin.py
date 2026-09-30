"""Administrator school setup and account-management API routes."""

from flask import Blueprint, request
import re
from werkzeug.security import generate_password_hash

from ai.ml.production.training_readiness import build_admin_training_readiness_report
from backend.time_utils import serialize_nepal_datetime


ADMIN_USER_PAGE_SIZES = frozenset({10, 25, 50, 100})
ADMIN_EMAIL_PATTERN = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def create_admin_blueprint(mysql, login_required, role_required, admin_role):
    admin = Blueprint("admin", __name__)

    def set_user_active_status(user_id, is_active):
        cur = mysql.connection.cursor()
        try:
            cur.execute("SELECT role, is_active FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if not user or user["role"] not in {"student", "teacher"}:
                return {"error": "Student or Teacher account not found."}, 404
            if bool(user["is_active"]) == is_active:
                return {
                    "message": f"{user['role'].capitalize()} account is already {'active' if is_active else 'inactive'}.",
                    "is_active": is_active,
                }, 200
            if is_active:
                cur.execute(
                    "UPDATE users SET is_active = TRUE, deactivated_at = NULL WHERE id = %s",
                    (user_id,),
                )
                message = f"{user['role'].capitalize()} account reactivated."
            else:
                cur.execute(
                    "UPDATE users SET is_active = FALSE, deactivated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (user_id,),
                )
                message = f"{user['role'].capitalize()} account deactivated."
            mysql.connection.commit()
            return {"message": message, "is_active": is_active}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Admin account status update error:", type(error).__name__)
            return {"error": "Unable to update account status."}, 500
        finally:
            cur.close()

    @admin.get("/api/admin/ml/training-readiness")
    @login_required
    @role_required(admin_role)
    def admin_ml_training_readiness_api():
        try:
            report = build_admin_training_readiness_report(mysql.connection)
        except Exception:
            return {"error": "Unable to load ML readiness information."}, 500
        return report, 200

    @admin.get("/api/admin/accounts")
    @login_required
    @role_required(admin_role)
    def admin_list_users_api():
        role = str(request.args.get("role", "student")).strip().lower()
        status = str(request.args.get("status", "active")).strip().lower()
        search = str(request.args.get("search", "")).strip()
        try:
            page = int(request.args.get("page", 1))
            page_size = int(request.args.get("page_size", 25))
        except (TypeError, ValueError):
            return {"error": "Page and page size must be valid integers."}, 400
        if role not in {"student", "teacher", "admin"}:
            return {"error": "Role must be student, teacher, or admin."}, 400
        if status not in {"active", "inactive", "all"}:
            return {"error": "Status must be active, inactive, or all."}, 400
        if page < 1 or page_size not in ADMIN_USER_PAGE_SIZES:
            return {"error": "Page must be positive and page size must be 10, 25, 50, or 100."}, 400
        cur = mysql.connection.cursor()
        try:
            where = "u.role = %s"
            params = [role]
            if status != "all":
                where += " AND u.is_active = %s"
                params.append(status == "active")
            if search:
                if role == "student":
                    where += " AND (s.full_name LIKE %s OR u.email LIKE %s)"
                else:
                    where += " AND (u.username LIKE %s OR u.email LIKE %s)"
                params.extend([f"%{search}%", f"%{search}%"])
            join = "LEFT JOIN students s ON s.user_id = u.id" if role == "student" else ""
            cur.execute(
                f"SELECT COUNT(*) AS total FROM users u {join} WHERE {where}",
                tuple(params),
            )
            total = int(cur.fetchone()["total"] or 0)
            if role == "student":
                select = """u.id AS user_id, u.role, s.id AS student_id, s.full_name,
                    u.email, s.grade, c.id AS class_id, c.name AS class_name,
                    c.section, sce.academic_year, u.is_active, u.deactivated_at,
                    u.created_at"""
                joins = """INNER JOIN students s ON s.user_id = u.id
                    LEFT JOIN student_class_enrollments sce
                      ON sce.student_id = s.id AND sce.ended_at IS NULL
                    LEFT JOIN classes c ON c.id = sce.class_id"""
                order = "s.full_name, u.id"
            elif role == "teacher":
                select = """u.id AS user_id, u.username, u.username AS name,
                    u.email, u.is_active,
                    u.deactivated_at, u.created_at,
                    (SELECT COUNT(*) FROM teacher_class_subjects tcs
                     WHERE tcs.teacher_user_id = u.id) AS assignment_count"""
                joins = ""
                order = "u.username, u.id"
            else:
                select = "u.id AS user_id, u.username, u.email, u.is_active, u.deactivated_at, u.created_at"
                joins = ""
                order = "u.username, u.id"
            cur.execute(
                f"""SELECT {select} FROM users u {joins}
                    WHERE {where} ORDER BY {order} LIMIT %s OFFSET %s""",
                (*params, page_size, (page - 1) * page_size),
            )
            rows = cur.fetchall()
            return {
                "items": [
                    {**row,
                     "is_active": bool(row["is_active"]),
                     "created_at": serialize_nepal_datetime(row["created_at"]),
                     "deactivated_at": serialize_nepal_datetime(row["deactivated_at"])}
                    for row in rows
                ],
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
                "role": role,
                "status": status,
            }, 200
        finally:
            cur.close()

    @admin.get("/api/admin/users")
    @login_required
    @role_required(admin_role)
    def admin_list_users_legacy_api():
        """Keep the existing grouped response available to older consumers."""
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT id, username, email, role, created_at
                   FROM users WHERE role IN ('admin', 'teacher')
                   ORDER BY role, username"""
            )
            staff = cur.fetchall()
            cur.execute(
                """SELECT u.id AS user_id, s.id AS student_id,
                          s.full_name, u.email, u.role, s.grade,
                          (SELECT sce.class_id
                           FROM student_class_enrollments sce
                           WHERE sce.student_id = s.id AND sce.ended_at IS NULL
                           ORDER BY sce.created_at DESC, sce.id DESC LIMIT 1) AS class_id,
                          (SELECT c.name
                           FROM student_class_enrollments sce
                           INNER JOIN classes c ON c.id = sce.class_id
                           WHERE sce.student_id = s.id AND sce.ended_at IS NULL
                           ORDER BY sce.created_at DESC, sce.id DESC LIMIT 1) AS class_name
                   FROM students s
                   INNER JOIN users u ON u.id = s.user_id
                   ORDER BY s.full_name"""
            )
            return {
                "admins": [user for user in staff if user["role"] == "admin"],
                "teachers": [user for user in staff if user["role"] == "teacher"],
                "students": cur.fetchall(),
            }, 200
        finally:
            cur.close()

    @admin.get("/api/admin/users/<int:user_id>")
    @login_required
    @role_required(admin_role)
    def admin_user_detail_api(user_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT id AS user_id, username, username AS name, email, role, is_active,
                          deactivated_at, created_at
                   FROM users WHERE id = %s AND role IN ('student', 'teacher')""",
                (user_id,),
            )
            user = cur.fetchone()
            if not user:
                return {"error": "Account not found."}, 404
            detail = dict(user)
            detail["is_active"] = bool(detail["is_active"])
            detail["created_at"] = serialize_nepal_datetime(detail["created_at"])
            detail["deactivated_at"] = serialize_nepal_datetime(detail["deactivated_at"])
            if user["role"] == "student":
                cur.execute(
                    """SELECT s.id AS student_id, s.full_name, s.grade,
                              c.id AS class_id, c.name AS class_name, c.section,
                              sce.academic_year
                       FROM students s
                       LEFT JOIN student_class_enrollments sce
                         ON sce.student_id = s.id AND sce.ended_at IS NULL
                       LEFT JOIN classes c ON c.id = sce.class_id
                       WHERE s.user_id = %s
                       ORDER BY sce.started_at DESC, sce.id DESC LIMIT 1""",
                    (user_id,),
                )
                detail.update(cur.fetchone() or {})
            else:
                cur.execute(
                    """SELECT c.id AS class_id, c.name AS class_name,
                              c.grade, c.section, sub.id AS subject_id,
                              sub.name AS subject_name, sub.code AS subject_code
                       FROM teacher_class_subjects tcs
                       INNER JOIN classes c ON c.id = tcs.class_id
                       INNER JOIN subjects sub ON sub.id = tcs.subject_id
                       WHERE tcs.teacher_user_id = %s
                       ORDER BY c.grade, c.section, sub.name""",
                    (user_id,),
                )
                detail["assignments"] = cur.fetchall()
            return {"user": detail}, 200
        finally:
            cur.close()

    @admin.put("/api/admin/students/<int:student_id>")
    @login_required
    @role_required(admin_role)
    def admin_update_student_api(student_id):
        data = request.get_json(silent=True)
        full_name = str((data or {}).get("full_name") or "").strip()
        email = str((data or {}).get("email") or "").strip().lower()
        if not full_name or len(full_name) > 100:
            return {"error": "Student full name is required and must be at most 100 characters."}, 400
        if not email or len(email) > 100 or not ADMIN_EMAIL_PATTERN.fullmatch(email):
            return {"error": "Enter a valid email address of 100 characters or fewer."}, 400
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT s.user_id FROM students s
                   INNER JOIN users u ON u.id = s.user_id
                   WHERE s.id = %s AND u.role = 'student'""",
                (student_id,),
            )
            student = cur.fetchone()
            if not student:
                return {"error": "Student not found."}, 404
            cur.execute("SELECT id FROM users WHERE LOWER(email) = %s AND id <> %s", (email, student["user_id"]))
            if cur.fetchone():
                return {"error": "Email already registered."}, 409
            cur.execute("UPDATE users SET username = %s, email = %s WHERE id = %s", (full_name, email, student["user_id"]))
            cur.execute("UPDATE students SET full_name = %s WHERE id = %s", (full_name, student_id))
            mysql.connection.commit()
            return {"message": "Student account updated."}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Admin student update error:", type(error).__name__)
            return {"error": "Unable to update Student account."}, 500
        finally:
            cur.close()

    @admin.put("/api/admin/teachers/<int:user_id>")
    @login_required
    @role_required(admin_role)
    def admin_update_teacher_api(user_id):
        data = request.get_json(silent=True)
        name = str((data or {}).get("username", (data or {}).get("name")) or "").strip()
        email = str((data or {}).get("email") or "").strip().lower()
        if not name or len(name) > 100:
            return {"error": "Teacher name is required and must be at most 100 characters."}, 400
        if not email or len(email) > 100 or not ADMIN_EMAIL_PATTERN.fullmatch(email):
            return {"error": "Enter a valid email address of 100 characters or fewer."}, 400
        cur = mysql.connection.cursor()
        try:
            cur.execute("SELECT id FROM users WHERE id = %s AND role = 'teacher'", (user_id,))
            if not cur.fetchone():
                return {"error": "Teacher not found."}, 404
            cur.execute("SELECT id FROM users WHERE LOWER(email) = %s AND id <> %s", (email, user_id))
            if cur.fetchone():
                return {"error": "Email already registered."}, 409
            cur.execute("UPDATE users SET username = %s, email = %s WHERE id = %s", (name, email, user_id))
            mysql.connection.commit()
            return {"message": "Teacher account updated."}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Admin teacher update error:", type(error).__name__)
            return {"error": "Unable to update Teacher account."}, 500
        finally:
            cur.close()

    @admin.post("/api/admin/users/<int:user_id>/reset-password")
    @login_required
    @role_required(admin_role)
    def admin_reset_user_password_api(user_id):
        data = request.get_json(silent=True)
        password = str((data or {}).get("temporary_password") or "")
        if len(password) < 8 or not password.strip():
            return {"error": "Temporary password must contain at least 8 non-whitespace characters."}, 400
        cur = mysql.connection.cursor()
        try:
            cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if not user or user["role"] not in {"student", "teacher"}:
                return {"error": "Student or Teacher account not found."}, 404
            cur.execute(
                "UPDATE users SET password = %s, must_change_password = TRUE WHERE id = %s",
                (generate_password_hash(password), user_id),
            )
            mysql.connection.commit()
            return {"message": "Temporary password reset. The user must change it at next login."}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Admin password reset error:", type(error).__name__)
            return {"error": "Unable to reset account password."}, 500
        finally:
            cur.close()

    @admin.post("/api/admin/users/<int:user_id>/deactivate")
    @login_required
    @role_required(admin_role)
    def admin_deactivate_user_api(user_id):
        return set_user_active_status(user_id, False)

    @admin.post("/api/admin/users/<int:user_id>/reactivate")
    @login_required
    @role_required(admin_role)
    def admin_reactivate_user_api(user_id):
        return set_user_active_status(user_id, True)

    @admin.post("/api/admin/admins")
    @login_required
    @role_required(admin_role)
    def admin_create_admin_api():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {"error": "Admin data is required"}, 400
        username = str(data.get("username") or "").strip()
        email = str(data.get("email") or "").strip().lower()
        password = str(data.get("password") or "")
        if not username or not email or "@" not in email:
            return {"error": "Admin name and a valid email are required"}, 400
        if len(password) < 8:
            return {
                "error": "Password must contain at least 8 characters"
            }, 400
        cur = mysql.connection.cursor()
        try:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                return {"error": "Email already registered"}, 409
            cur.execute(
                     """INSERT INTO users
                         (username, email, password, role, must_change_password)
                         VALUES (%s, %s, %s, 'admin', TRUE)""",
                (username, email, generate_password_hash(password))
            )
            admin_id = cur.lastrowid
            mysql.connection.commit()
            return {"message": "Admin account created", "admin_id": admin_id}, 201
        except Exception as error:
            mysql.connection.rollback()
            print("Admin account creation error:", error)
            return {"error": "Unable to create admin"}, 500
        finally:
            cur.close()

    @admin.post("/api/admin/students")
    @login_required
    @role_required(admin_role)
    def admin_create_student_api():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {"error": "Student data is required"}, 400
        full_name = str(data.get("full_name") or "").strip()
        email = str(data.get("email") or "").strip().lower()
        password = str(data.get("password") or "")
        try:
            class_id = int(data.get("class_id"))
        except (TypeError, ValueError):
            class_id = 0
        if not full_name or not email or "@" not in email:
            return {"error": "Student name and a valid email are required"}, 400
        if len(password) < 8:
            return {
                "error": "Password must contain at least 8 characters"
            }, 400
        if not class_id:
            return {"error": "Class is required"}, 400
        cur = mysql.connection.cursor()
        try:
            cur.execute("SELECT id, grade FROM classes WHERE id = %s", (class_id,))
            selected_class = cur.fetchone()
            if not selected_class:
                return {"error": "Class not found"}, 404
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                return {"error": "Email already registered"}, 409
            cur.execute(
                     """INSERT INTO users
                         (username, email, password, role, must_change_password)
                         VALUES (%s, %s, %s, 'student', TRUE)""",
                (full_name, email, generate_password_hash(password))
            )
            user_id = cur.lastrowid
            cur.execute(
                """INSERT INTO students (user_id, full_name, grade)
                   VALUES (%s, %s, %s)""",
                (user_id, full_name, selected_class["grade"])
            )
            student_id = cur.lastrowid
            cur.execute(
                """INSERT INTO student_class_enrollments
                   (student_id, class_id, started_at)
                   VALUES (%s, %s, CURRENT_TIMESTAMP)""",
                (student_id, class_id)
            )
            mysql.connection.commit()
            return {
                "message": "Student account created",
                "student_id": student_id,
                "user_id": user_id
            }, 201
        except Exception as error:
            mysql.connection.rollback()
            print("Admin student creation error:", error)
            return {"error": "Unable to create student"}, 500
        finally:
            cur.close()

    @admin.get("/api/admin/school-setup")
    @login_required
    @role_required(admin_role)
    def admin_school_setup_api():
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "SELECT id, name, grade, section FROM classes "
                "ORDER BY grade, section"
            )
            classes = cur.fetchall()
            cur.execute(
                "SELECT id, name, code, created_at FROM subjects "
                "ORDER BY name"
            )
            subjects = cur.fetchall()
            cur.execute(
                """SELECT id, username, email FROM users
                         WHERE role = 'teacher' AND is_active = TRUE ORDER BY username"""
            )
            teachers = cur.fetchall()
            cur.execute(
                """SELECT s.id AS student_id, s.full_name, s.grade, u.email,
                          c.id AS class_id, c.name AS class_name,
                          c.grade AS class_grade, c.section
                   FROM students s
                   INNER JOIN users u ON u.id = s.user_id
                   LEFT JOIN student_class_enrollments sce
                     ON sce.student_id = s.id
                    AND sce.ended_at IS NULL
                   LEFT JOIN classes c ON c.id = sce.class_id
                   ORDER BY s.full_name"""
            )
            students = cur.fetchall()
            cur.execute(
                """SELECT tcs.id, tcs.teacher_user_id,
                          u.username AS teacher_name,
                          tcs.class_id, c.name AS class_name,
                          tcs.subject_id, sub.name AS subject
                   FROM teacher_class_subjects tcs
                   INNER JOIN users u ON u.id = tcs.teacher_user_id
                   INNER JOIN classes c ON c.id = tcs.class_id
                   INNER JOIN subjects sub ON sub.id = tcs.subject_id
                   ORDER BY c.name, sub.name, u.username"""
            )
            assignments = cur.fetchall()
            cur.execute(
                """SELECT cta.id, cta.teacher_user_id,
                          u.username AS teacher_name,
                          cta.class_id, c.name AS class_name,
                          cta.academic_year, cta.started_at
                   FROM class_teacher_assignments cta
                   INNER JOIN users u ON u.id = cta.teacher_user_id
                   INNER JOIN classes c ON c.id = cta.class_id
                   WHERE cta.ended_at IS NULL
                   ORDER BY c.name, u.username"""
            )
            current_class_teachers = cur.fetchall()
            cur.execute(
                """SELECT cta.id, cta.teacher_user_id,
                          u.username AS teacher_name,
                          cta.class_id, c.name AS class_name,
                          cta.academic_year, cta.started_at, cta.ended_at,
                          CASE WHEN cta.ended_at IS NULL THEN 1 ELSE 0 END AS current
                   FROM class_teacher_assignments cta
                   INNER JOIN users u ON u.id = cta.teacher_user_id
                   INNER JOIN classes c ON c.id = cta.class_id
                   ORDER BY c.name, cta.started_at DESC, cta.id DESC"""
            )
            class_teacher_history = cur.fetchall()
            for item in current_class_teachers:
                item["started_at"] = serialize_nepal_datetime(item["started_at"])
            for item in class_teacher_history:
                item["started_at"] = serialize_nepal_datetime(item["started_at"])
                item["ended_at"] = serialize_nepal_datetime(item["ended_at"])
            return {
                "classes": classes,
                "subjects": subjects,
                "teachers": teachers,
                "students": students,
                "assignments": assignments,
                "current_class_teachers": current_class_teachers,
                "class_teacher_history": class_teacher_history
            }, 200
        finally:
            cur.close()

    @admin.post("/api/admin/subjects")
    @login_required
    @role_required(admin_role)
    def admin_create_subject_api():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {"error": "Subject data is required"}, 400
        name = str(data.get("name") or "").strip()
        code = str(data.get("code") or "").strip().upper()
        if not name:
            return {"error": "Subject name is required"}, 400
        if len(name) > 100 or len(code) > 30:
            return {"error": "Subject information is too long"}, 400
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "SELECT id FROM subjects WHERE LOWER(name) = LOWER(%s)",
                (name,)
            )
            if cur.fetchone():
                return {"error": "Subject name already exists"}, 409
            if code:
                cur.execute("SELECT id FROM subjects WHERE code = %s", (code,))
                if cur.fetchone():
                    return {"error": "Subject code already exists"}, 409
            cur.execute(
                "INSERT INTO subjects (name, code) VALUES (%s, %s)",
                (name, code or None)
            )
            subject_id = cur.lastrowid
            mysql.connection.commit()
            return {
                "message": "Subject created",
                "subject_id": subject_id
            }, 201
        except Exception as error:
            mysql.connection.rollback()
            print("Admin subject creation error:", error)
            return {"error": "Unable to create subject"}, 500
        finally:
            cur.close()

    @admin.post("/api/admin/classes")
    @login_required
    @role_required(admin_role)
    def admin_create_class_api():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {"error": "Class data is required"}, 400
        name = str(data.get("name") or "").strip()
        grade = str(data.get("grade") or "").strip()
        section = str(data.get("section") or "Default").strip()
        if not name or not grade or not section:
            return {
                "error": "Class name, grade and section are required"
            }, 400
        if len(name) > 100 or len(grade) > 20 or len(section) > 50:
            return {"error": "Class information is too long"}, 400
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "SELECT id FROM classes WHERE grade = %s AND section = %s",
                (grade, section)
            )
            if cur.fetchone():
                return {"error": "This grade and section already exist"}, 409
            cur.execute(
                "INSERT INTO classes (name, grade, section) VALUES (%s, %s, %s)",
                (name, grade, section)
            )
            class_id = cur.lastrowid
            mysql.connection.commit()
            return {"message": "Class created", "class_id": class_id}, 201
        except Exception as error:
            mysql.connection.rollback()
            print("Admin class creation error:", error)
            return {"error": "Unable to create class"}, 500
        finally:
            cur.close()

    @admin.post("/api/admin/teachers")
    @login_required
    @role_required(admin_role)
    def admin_create_teacher_api():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {"error": "Teacher data is required"}, 400
        username = str(data.get("username") or "").strip()
        email = str(data.get("email") or "").strip().lower()
        password = str(data.get("password") or "")
        if not username or not email or "@" not in email:
            return {
                "error": "Teacher name and a valid email are required"
            }, 400
        if len(password) < 8:
            return {
                "error": "Password must contain at least 8 characters"
            }, 400
        cur = mysql.connection.cursor()
        try:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                return {"error": "Email already registered"}, 409
            cur.execute(
                     """INSERT INTO users
                         (username, email, password, role, must_change_password)
                         VALUES (%s, %s, %s, 'teacher', TRUE)""",
                (username, email, generate_password_hash(password))
            )
            teacher_id = cur.lastrowid
            mysql.connection.commit()
            return {
                "message": "Teacher account created",
                "teacher_id": teacher_id
            }, 201
        except Exception as error:
            mysql.connection.rollback()
            print("Admin teacher creation error:", error)
            return {"error": "Unable to create teacher"}, 500
        finally:
            cur.close()

    @admin.put("/api/admin/students/<int:student_id>/class")
    @login_required
    @role_required(admin_role)
    def admin_enroll_student_api(student_id):
        data = request.get_json(silent=True)
        try:
            class_id = int(data.get("class_id")) if isinstance(data, dict) else 0
        except (TypeError, ValueError):
            class_id = 0
        if not class_id:
            return {"error": "Class is required"}, 400
        academic_year = str((data or {}).get("academic_year") or "").strip() if isinstance(data, dict) else ""
        transfer_note = str((data or {}).get("transfer_note") or "").strip() if isinstance(data, dict) else ""
        cur = mysql.connection.cursor()
        try:
            cur.execute("SELECT id, grade FROM students WHERE id = %s", (student_id,))
            student = cur.fetchone()
            if not student:
                return {"error": "Student not found"}, 404
            cur.execute("SELECT id, grade FROM classes WHERE id = %s", (class_id,))
            selected_class = cur.fetchone()
            if not selected_class:
                return {"error": "Class not found"}, 404

            cur.execute(
                """SELECT id, class_id, started_at, ended_at
                   FROM student_class_enrollments
                   WHERE student_id = %s AND ended_at IS NULL
                   ORDER BY started_at DESC, id DESC
                   LIMIT 1""",
                (student_id,)
            )
            current_enrollment = cur.fetchone()

            if current_enrollment and current_enrollment["class_id"] == class_id:
                return {"message": "Student is already enrolled in this class", "student_id": student_id}, 200

            if current_enrollment:
                cur.execute(
                    """UPDATE student_class_enrollments
                       SET ended_at = CURRENT_TIMESTAMP
                       WHERE id = %s AND ended_at IS NULL""",
                    (current_enrollment["id"],)
                )

            cur.execute(
                """INSERT INTO student_class_enrollments
                   (student_id, class_id, academic_year, started_at, transfer_note)
                   VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s)""",
                (student_id, class_id, academic_year or None, transfer_note or None)
            )
            cur.execute(
                "UPDATE students SET grade = %s WHERE id = %s",
                (selected_class["grade"], student_id)
            )
            mysql.connection.commit()
            return {"message": "Student enrolled in class", "student_id": student_id}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Admin enrollment error:", error)
            return {"error": "Unable to enroll student"}, 500
        finally:
            cur.close()

    @admin.get("/api/admin/students/<int:student_id>/enrollment-history")
    @login_required
    @role_required(admin_role)
    def admin_student_enrollment_history_api(student_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute("SELECT id FROM students WHERE id = %s", (student_id,))
            if not cur.fetchone():
                return {"error": "Student not found"}, 404
            cur.execute(
                """SELECT sce.id, sce.class_id, c.name AS class_name, c.grade, c.section,
                          sce.academic_year, sce.started_at, sce.ended_at, sce.transfer_note,
                          CASE WHEN sce.ended_at IS NULL THEN 1 ELSE 0 END AS current
                   FROM student_class_enrollments sce
                   INNER JOIN classes c ON c.id = sce.class_id
                   WHERE sce.student_id = %s
                   ORDER BY sce.started_at DESC, sce.id DESC""",
                (student_id,)
            )
            history = cur.fetchall()
            serialized = []
            for row in history:
                serialized.append({
                    "id": row["id"],
                    "class_id": row["class_id"],
                    "class_name": row["class_name"],
                    "grade": row["grade"],
                    "section": row["section"],
                    "academic_year": row["academic_year"],
                    "started_at": serialize_nepal_datetime(row["started_at"]),
                    "ended_at": serialize_nepal_datetime(row["ended_at"]),
                    "transfer_note": row["transfer_note"],
                    "current": bool(row["current"])
                })
            return {"student_id": student_id, "history": serialized}, 200
        finally:
            cur.close()

    @admin.post("/api/admin/teacher-assignments")
    @login_required
    @role_required(admin_role)
    def admin_create_teacher_assignment_api():
        data = request.get_json(silent=True)
        try:
            teacher_id = int(data.get("teacher_user_id"))
            class_id = int(data.get("class_id"))
        except (AttributeError, TypeError, ValueError):
            return {"error": "Teacher and class are required"}, 400
        try:
            subject_id = int(data.get("subject_id"))
        except (AttributeError, TypeError, ValueError):
            return {"error": "Subject is required"}, 400
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "SELECT id FROM users WHERE id = %s AND role = 'teacher' AND is_active = TRUE",
                (teacher_id,)
            )
            if not cur.fetchone():
                return {"error": "Teacher not found"}, 404
            cur.execute("SELECT id FROM classes WHERE id = %s", (class_id,))
            if not cur.fetchone():
                return {"error": "Class not found"}, 404
            cur.execute("SELECT id FROM subjects WHERE id = %s", (subject_id,))
            if not cur.fetchone():
                return {"error": "Subject not found"}, 404

            cur.execute(
                """SELECT id FROM teacher_class_subjects
                   WHERE teacher_user_id = %s AND class_id = %s
                     AND subject_id = %s""",
                (teacher_id, class_id, subject_id)
            )
            existing_assignment = cur.fetchone()

            if existing_assignment:
                assignment_id = existing_assignment["id"]
                mysql.connection.commit()
                return {
                    "message": "Teacher assignment saved",
                    "assignment_id": assignment_id,
                    "updated": True
                }, 200

            cur.execute(
                """INSERT INTO teacher_class_subjects
                         (teacher_user_id, class_id, subject_id)
                         VALUES (%s, %s, %s)""",
                (teacher_id, class_id, subject_id)
            )
            assignment_id = cur.lastrowid
            mysql.connection.commit()
            return {
                "message": "Teacher assignment created",
                "assignment_id": assignment_id
            }, 201
        except Exception as error:
            mysql.connection.rollback()
            print("Admin assignment error:", error)
            return {"error": "Unable to assign teacher"}, 500
        finally:
            cur.close()

    @admin.delete("/api/admin/teacher-assignments/<int:assignment_id>")
    @login_required
    @role_required(admin_role)
    def admin_delete_teacher_assignment_api(assignment_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT teacher_user_id, class_id
                   FROM teacher_class_subjects WHERE id = %s""",
                (assignment_id,)
            )
            assignment = cur.fetchone()
            if not assignment:
                return {"error": "Teacher assignment not found"}, 404
            cur.execute(
                "DELETE FROM teacher_class_subjects WHERE id = %s",
                (assignment_id,)
            )
            mysql.connection.commit()
            return {"message": "Teacher assignment removed"}, 200
        finally:
            cur.close()

    @admin.post("/api/admin/class-teacher-assignments")
    @login_required
    @role_required(admin_role)
    def admin_create_class_teacher_assignment_api():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {"error": "Class teacher data is required"}, 400
        try:
            teacher_id = int(data.get("teacher_user_id"))
            class_id = int(data.get("class_id"))
        except (TypeError, ValueError):
            return {"error": "Teacher and class are required"}, 400
        academic_year = str(data.get("academic_year") or "").strip() or None
        if academic_year is not None and len(academic_year) > 20:
            return {"error": "Academic year must be at most 20 characters"}, 400
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "SELECT id FROM users WHERE id = %s AND role = 'teacher' AND is_active = TRUE",
                (teacher_id,)
            )
            if not cur.fetchone():
                return {"error": "Teacher not found"}, 404
            cur.execute("SELECT id FROM classes WHERE id = %s", (class_id,))
            if not cur.fetchone():
                return {"error": "Class not found"}, 404
            cur.execute(
                """SELECT id, teacher_user_id, academic_year
                   FROM class_teacher_assignments
                   WHERE class_id = %s AND ended_at IS NULL
                   ORDER BY id DESC LIMIT 1""",
                (class_id,)
            )
            current = cur.fetchone()
            if (current and current["teacher_user_id"] == teacher_id
                    and current["academic_year"] == academic_year):
                return {
                    "message": "Class teacher assignment is already current",
                    "assignment_id": current["id"],
                    "updated": False
                }, 200
            cur.execute(
                """SELECT id
                   FROM class_teacher_assignments
                   WHERE teacher_user_id = %s AND ended_at IS NULL
                     AND class_id <> %s""",
                (teacher_id, class_id)
            )
            teacher_current = cur.fetchall()
            assignment_ids_to_end = {
                row["id"] for row in teacher_current
            }
            if current:
                assignment_ids_to_end.add(current["id"])
            for assignment_id_to_end in assignment_ids_to_end:
                cur.execute(
                    "UPDATE class_teacher_assignments SET ended_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (assignment_id_to_end,)
                )
            cur.execute(
                """INSERT INTO class_teacher_assignments
                   (teacher_user_id, class_id, academic_year, started_at)
                   VALUES (%s, %s, %s, CURRENT_TIMESTAMP)""",
                (teacher_id, class_id, academic_year)
            )
            assignment_id = cur.lastrowid
            mysql.connection.commit()
            return {
                "message": "Class teacher assignment created",
                "assignment_id": assignment_id
            }, 201
        except Exception as error:
            mysql.connection.rollback()
            print("Admin class teacher assignment error:", error)
            return {"error": "Unable to assign class teacher"}, 500
        finally:
            cur.close()

    @admin.post("/api/admin/class-teacher-assignments/<int:assignment_id>/end")
    @login_required
    @role_required(admin_role)
    def admin_end_class_teacher_assignment_api(assignment_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """UPDATE class_teacher_assignments
                   SET ended_at = CURRENT_TIMESTAMP
                   WHERE id = %s AND ended_at IS NULL""",
                (assignment_id,)
            )
            cur.execute(
                "SELECT id FROM class_teacher_assignments WHERE id = %s AND ended_at IS NOT NULL",
                (assignment_id,)
            )
            if not cur.fetchone():
                return {"error": "Active class teacher assignment not found"}, 404
            mysql.connection.commit()
            return {"message": "Class teacher responsibility ended"}, 200
        finally:
            cur.close()

    return admin
