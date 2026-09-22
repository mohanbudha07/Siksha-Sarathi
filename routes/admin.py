"""Administrator school setup and account-management API routes."""

from flask import Blueprint, request
from werkzeug.security import generate_password_hash


def create_admin_blueprint(mysql, login_required, role_required, admin_role):
    admin = Blueprint("admin", __name__)

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
                """SELECT id, username, email FROM users
                   WHERE role = 'teacher' ORDER BY username"""
            )
            teachers = cur.fetchall()
            cur.execute(
                """SELECT s.id AS student_id, s.full_name, s.grade, u.email,
                          c.id AS class_id, c.name AS class_name
                   FROM students s
                   INNER JOIN users u ON u.id = s.user_id
                   LEFT JOIN student_class_enrollments sce
                     ON sce.student_id = s.id
                   LEFT JOIN classes c ON c.id = sce.class_id
                   ORDER BY s.full_name, c.name"""
            )
            students = cur.fetchall()
            cur.execute(
                """SELECT tcs.id, tcs.teacher_user_id,
                          u.username AS teacher_name,
                          tcs.class_id, c.name AS class_name, tcs.subject,
                          CASE WHEN cta.teacher_user_id IS NULL THEN 0 ELSE 1 END
                              AS is_class_teacher
                   FROM teacher_class_subjects tcs
                   INNER JOIN users u ON u.id = tcs.teacher_user_id
                   INNER JOIN classes c ON c.id = tcs.class_id
                   LEFT JOIN class_teacher_assignments cta
                     ON cta.class_id = tcs.class_id
                    AND cta.teacher_user_id = tcs.teacher_user_id
                   ORDER BY c.name, tcs.subject, u.username"""
            )
            assignments = cur.fetchall()
            for assignment in assignments:
                assignment["is_class_teacher"] = bool(
                    assignment["is_class_teacher"]
                )
            return {
                "classes": classes,
                "teachers": teachers,
                "students": students,
                "assignments": assignments
            }, 200
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
                """INSERT INTO users (username, email, password, role)
                   VALUES (%s, %s, %s, 'teacher')""",
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
        cur = mysql.connection.cursor()
        try:
            cur.execute("SELECT id FROM students WHERE id = %s", (student_id,))
            if not cur.fetchone():
                return {"error": "Student not found"}, 404
            cur.execute("SELECT id, grade FROM classes WHERE id = %s", (class_id,))
            selected_class = cur.fetchone()
            if not selected_class:
                return {"error": "Class not found"}, 404
            cur.execute(
                "DELETE FROM student_class_enrollments WHERE student_id = %s",
                (student_id,)
            )
            cur.execute(
                """INSERT INTO student_class_enrollments (student_id, class_id)
                   VALUES (%s, %s)""",
                (student_id, class_id)
            )
            cur.execute(
                "UPDATE students SET grade = %s WHERE id = %s",
                (selected_class["grade"], student_id)
            )
            mysql.connection.commit()
            return {"message": "Student enrolled in class"}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Admin enrollment error:", error)
            return {"error": "Unable to enroll student"}, 500
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
        subject = str(data.get("subject") or "").strip()
        is_class_teacher = data.get("is_class_teacher", False)
        if not subject or len(subject) > 100:
            return {
                "error": "Subject is required and must be at most 100 characters"
            }, 400
        if not isinstance(is_class_teacher, bool):
            return {
                "error": "Class teacher status must be true or false"
            }, 400
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "SELECT id FROM users WHERE id = %s AND role = 'teacher'",
                (teacher_id,)
            )
            if not cur.fetchone():
                return {"error": "Teacher not found"}, 404
            cur.execute("SELECT id FROM classes WHERE id = %s", (class_id,))
            if not cur.fetchone():
                return {"error": "Class not found"}, 404
            cur.execute(
                """SELECT id FROM teacher_class_subjects
                   WHERE teacher_user_id = %s AND class_id = %s
                     AND LOWER(subject) = LOWER(%s)""",
                (teacher_id, class_id, subject)
            )
            if cur.fetchone():
                return {
                    "error": "Teacher already has this class-subject assignment"
                }, 409
            cur.execute(
                """INSERT INTO teacher_class_subjects
                   (teacher_user_id, class_id, subject) VALUES (%s, %s, %s)""",
                (teacher_id, class_id, subject)
            )
            assignment_id = cur.lastrowid
            if is_class_teacher:
                cur.execute(
                    "DELETE FROM class_teacher_assignments WHERE class_id = %s",
                    (class_id,)
                )
                cur.execute(
                    """INSERT INTO class_teacher_assignments
                       (teacher_user_id, class_id) VALUES (%s, %s)""",
                    (teacher_id, class_id)
                )
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
            cur.execute(
                """SELECT id FROM teacher_class_subjects
                   WHERE teacher_user_id = %s AND class_id = %s LIMIT 1""",
                (assignment["teacher_user_id"], assignment["class_id"])
            )
            if not cur.fetchone():
                cur.execute(
                    """DELETE FROM class_teacher_assignments
                       WHERE teacher_user_id = %s AND class_id = %s""",
                    (assignment["teacher_user_id"], assignment["class_id"])
                )
            mysql.connection.commit()
            return {"message": "Teacher assignment removed"}, 200
        finally:
            cur.close()

    return admin
