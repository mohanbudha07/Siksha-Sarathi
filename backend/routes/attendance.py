"""Teacher monthly paper-register attendance API routes."""

from datetime import datetime

from flask import Blueprint, request, session

def serialize_api_date(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def teacher_has_class_assignment(cur, teacher_id, class_id):
    cur.execute(
        """
        SELECT id FROM class_teacher_assignments
                WHERE teacher_user_id = %s AND class_id = %s
                    AND ended_at IS NULL
        """,
        (teacher_id, class_id)
    )
    return cur.fetchone() is not None


def validate_attendance_summary_payload(data):
    if not isinstance(data, dict):
        raise ValueError("Monthly attendance data is required")
    try:
        class_id = int(data.get("class_id"))
    except (TypeError, ValueError) as error:
        raise ValueError("Class is required") from error
    try:
        attendance_month = datetime.strptime(
            str(data.get("attendance_month") or ""), "%Y-%m"
        ).date().replace(day=1)
    except ValueError as error:
        raise ValueError("Attendance month must use YYYY-MM") from error
    try:
        total_school_days = int(data.get("total_school_days"))
    except (TypeError, ValueError) as error:
        raise ValueError("Total school days must be a whole number") from error
    if not 1 <= total_school_days <= 31:
        raise ValueError("Total school days must be between 1 and 31")
    return {
        "class_id": class_id,
        "attendance_month": attendance_month.isoformat(),
        "total_school_days": total_school_days
    }


def fetch_teacher_attendance_summary(cur, summary_id, teacher_id):
    cur.execute(
        """
        SELECT mas.id, mas.teacher_user_id, mas.class_id,
               mas.attendance_month, mas.total_school_days, mas.created_at,
               c.name AS class_name, c.grade, c.section
        FROM monthly_attendance_summaries mas
        INNER JOIN classes c ON c.id = mas.class_id
        WHERE mas.id = %s AND mas.teacher_user_id = %s
        """,
        (summary_id, teacher_id)
    )
    attendance = cur.fetchone()
    if attendance:
        attendance["attendance_month"] = serialize_api_date(
            attendance["attendance_month"]
        )
        attendance["total_school_days"] = int(attendance["total_school_days"])
    return attendance


def create_attendance_blueprint(
    mysql,
    login_required,
    role_required,
    teacher_role
):
    attendance = Blueprint("attendance", __name__)

    @attendance.route("/api/teacher/monthly-attendance", methods=["GET", "POST"])
    @login_required
    @role_required(teacher_role)
    def teacher_monthly_attendance_api():
        cur = mysql.connection.cursor()
        try:
            if request.method == "GET":
                cur.execute(
                    """
                    SELECT c.id AS class_id, c.name AS class_name,
                           c.grade, c.section
                    FROM class_teacher_assignments cta
                    INNER JOIN classes c ON c.id = cta.class_id
                                        WHERE cta.teacher_user_id = %s
                                            AND cta.ended_at IS NULL
                    ORDER BY c.grade, c.section, c.name
                    """,
                    (session["user_id"],)
                )
                assigned_classes = cur.fetchall()
                cur.execute(
                    """
                    SELECT mas.id, mas.class_id, mas.attendance_month,
                           mas.total_school_days, c.name AS class_name,
                           COUNT(mar.id) AS recorded_students,
                           COALESCE(SUM(mar.present_days), 0) AS present_days,
                           COALESCE(SUM(mas.total_school_days - mar.present_days), 0)
                               AS absent_days
                    FROM monthly_attendance_summaries mas
                    INNER JOIN classes c ON c.id = mas.class_id
                    LEFT JOIN monthly_attendance_records mar ON mar.summary_id = mas.id
                    WHERE mas.teacher_user_id = %s
                    GROUP BY mas.id, mas.class_id, mas.attendance_month,
                             mas.total_school_days, c.name
                    ORDER BY mas.attendance_month DESC, mas.id DESC
                    """,
                    (session["user_id"],)
                )
                summaries = cur.fetchall()
                for item in summaries:
                    item["attendance_month"] = serialize_api_date(
                        item["attendance_month"]
                    )
                    for field in (
                        "total_school_days", "recorded_students", "present_days",
                        "absent_days"
                    ):
                        item[field] = int(item[field] or 0)
                return {
                    "assigned_classes": assigned_classes,
                    "summaries": summaries
                }, 200

            try:
                attendance = validate_attendance_summary_payload(
                    request.get_json(silent=True)
                )
            except ValueError as error:
                return {"error": str(error)}, 400
            if not teacher_has_class_assignment(
                cur, session["user_id"], attendance["class_id"]
            ):
                return {"error": "Class teacher assignment not found"}, 404
            cur.execute(
                """
                SELECT id FROM monthly_attendance_summaries
                WHERE class_id = %s AND attendance_month = %s
                """,
                (attendance["class_id"], attendance["attendance_month"])
            )
            if cur.fetchone():
                return {
                    "error": "Attendance already exists for this class and month"
                }, 409
            cur.execute(
                """
                INSERT INTO monthly_attendance_summaries
                    (teacher_user_id, class_id, attendance_month, total_school_days)
                VALUES (%s, %s, %s, %s)
                """,
                (session["user_id"], attendance["class_id"],
                 attendance["attendance_month"], attendance["total_school_days"])
            )
            summary_id = cur.lastrowid
            mysql.connection.commit()
            return {
                "message": "Monthly attendance summary created",
                "attendance_summary_id": summary_id
            }, 201
        except Exception as error:
            mysql.connection.rollback()
            print("Attendance session error:", error)
            return {"error": "Failed to manage attendance session"}, 500
        finally:
            cur.close()


    @attendance.route("/api/teacher/monthly-attendance/<int:summary_id>",
               methods=["GET", "PUT", "DELETE"])
    @login_required
    @role_required(teacher_role)
    def teacher_monthly_attendance_detail_api(summary_id):
        cur = mysql.connection.cursor()
        try:
            attendance = fetch_teacher_attendance_summary(
                cur, summary_id, session["user_id"]
            )
            if not attendance:
                return {"error": "Monthly attendance summary not found"}, 404
            if request.method in ("PUT", "DELETE") and not teacher_has_class_assignment(
                cur, session["user_id"], attendance["class_id"]
            ):
                return {"error": "Active class teacher assignment not found"}, 403
            if request.method == "DELETE":
                cur.execute(
                    "DELETE FROM monthly_attendance_summaries WHERE id = %s AND teacher_user_id = %s",
                    (summary_id, session["user_id"])
                )
                mysql.connection.commit()
                return {"message": "Monthly attendance summary deleted"}, 200
            if request.method == "PUT":
                data = request.get_json(silent=True)
                if not isinstance(data, dict):
                    return {"error": "Monthly attendance data is required"}, 400
                try:
                    total_school_days = int(data.get("total_school_days"))
                except (TypeError, ValueError):
                    return {"error": "Total school days must be a whole number"}, 400
                if not 1 <= total_school_days <= 31:
                    return {"error": "Total school days must be between 1 and 31"}, 400
                cur.execute(
                    "SELECT COALESCE(MAX(present_days), 0) AS maximum_present_days "
                    "FROM monthly_attendance_records WHERE summary_id = %s",
                    (summary_id,)
                )
                maximum_present_days = int(
                    cur.fetchone()["maximum_present_days"] or 0
                )
                if maximum_present_days > total_school_days:
                    return {
                        "error": (
                            "Total school days cannot be lower than an existing "
                            f"present-days value ({maximum_present_days})"
                        )
                    }, 400
                cur.execute(
                    "UPDATE monthly_attendance_summaries "
                    "SET total_school_days = %s WHERE id = %s",
                    (total_school_days, summary_id)
                )
                mysql.connection.commit()
                return {
                    "message": "Total school days updated",
                    "total_school_days": total_school_days
                }, 200

            cur.execute(
                """
                SELECT s.id AS student_id, s.full_name, s.grade,
                       mar.present_days, mar.note
                FROM student_class_enrollments sce
                INNER JOIN students s ON s.id = sce.student_id
                LEFT JOIN monthly_attendance_records mar
                    ON mar.student_id = s.id AND mar.summary_id = %s
                WHERE sce.class_id = %s
                ORDER BY s.full_name, s.id
                """,
                (summary_id, attendance["class_id"])
            )
            return {"summary": attendance, "students": cur.fetchall()}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Attendance detail error:", error)
            return {"error": "Failed to manage attendance session"}, 500
        finally:
            cur.close()


    @attendance.route(
        "/api/teacher/monthly-attendance/<int:summary_id>/records",
        methods=["PUT"]
    )
    @login_required
    @role_required(teacher_role)
    def teacher_monthly_attendance_records_api(summary_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("records"), list):
            return {"error": "Attendance records must be provided as a list"}, 400
        cur = mysql.connection.cursor()
        try:
            attendance = fetch_teacher_attendance_summary(
                cur, summary_id, session["user_id"]
            )
            if not attendance:
                return {"error": "Monthly attendance summary not found"}, 404
            if not teacher_has_class_assignment(
                cur, session["user_id"], attendance["class_id"]
            ):
                return {"error": "Active class teacher assignment not found"}, 403
            cur.execute(
                "SELECT student_id FROM student_class_enrollments WHERE class_id = %s",
                (attendance["class_id"],)
            )
            enrolled_ids = {int(row["student_id"]) for row in cur.fetchall()}
            normalized = []
            seen_ids = set()
            for index, record in enumerate(data["records"], start=1):
                if not isinstance(record, dict):
                    return {"error": f"Attendance record {index} is invalid"}, 400
                try:
                    student_id = int(record.get("student_id"))
                except (TypeError, ValueError):
                    return {"error": f"Attendance record {index} requires a student"}, 400
                if student_id not in enrolled_ids:
                    return {"error": "Attendance contains a student outside this class"}, 400
                if student_id in seen_ids:
                    return {"error": "Each student can appear only once"}, 400
                seen_ids.add(student_id)
                try:
                    present_days = int(record.get("present_days"))
                except (TypeError, ValueError):
                    return {"error": "Present days must be a whole number"}, 400
                if not 0 <= present_days <= attendance["total_school_days"]:
                    return {
                        "error": (
                            "Present days must be between 0 and "
                            f'{attendance["total_school_days"]}'
                        )
                    }, 400
                note = str(record.get("note") or "").strip()
                if len(note) > 255:
                    return {"error": "Attendance note must be at most 255 characters"}, 400
                normalized.append((student_id, present_days, note))
            if seen_ids != enrolled_ids:
                return {"error": "Attendance must include every enrolled student"}, 400

            cur.execute(
                "DELETE FROM monthly_attendance_records WHERE summary_id = %s",
                (summary_id,)
            )
            for student_id, present_days, note in normalized:
                cur.execute(
                    """
                    INSERT INTO monthly_attendance_records
                        (summary_id, student_id, present_days, note)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (summary_id, student_id, present_days, note)
                )
            mysql.connection.commit()
            return {
                "message": "Monthly attendance saved",
                "recorded_students": len(normalized)
            }, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Attendance records error:", error)
            return {"error": "Failed to save attendance"}, 500
        finally:
            cur.close()


    return attendance
