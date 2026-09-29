"""Teacher monthly paper-register attendance API routes."""

from datetime import datetime

from flask import Blueprint, request, session

def serialize_api_date(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def parse_whole_number(value):
    if isinstance(value, bool):
        raise ValueError("A whole number is required")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return int(value.strip())
    raise ValueError("A whole number is required")


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
        class_id = parse_whole_number(data.get("class_id"))
    except (TypeError, ValueError) as error:
        raise ValueError("Class is required") from error
    try:
        attendance_month = datetime.strptime(
            str(data.get("attendance_month") or ""), "%Y-%m"
        ).date().replace(day=1)
    except ValueError as error:
        raise ValueError("Attendance month must use YYYY-MM") from error
    try:
        total_school_days = parse_whole_number(data.get("total_school_days"))
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
                             c.name AS class_name, c.grade, c.section,
                             EXISTS (
                                     SELECT 1 FROM class_teacher_assignments cta
                                     WHERE cta.class_id = mas.class_id
                                         AND cta.teacher_user_id = %s
                                         AND cta.ended_at IS NULL
                             ) AS can_manage
        FROM monthly_attendance_summaries mas
        INNER JOIN classes c ON c.id = mas.class_id
                WHERE mas.id = %s
                    AND (
                            mas.teacher_user_id = %s
                            OR EXISTS (
                                    SELECT 1 FROM class_teacher_assignments cta
                                    WHERE cta.class_id = mas.class_id
                                        AND cta.teacher_user_id = %s
                                        AND cta.ended_at IS NULL
                            )
                    )
        """,
                (teacher_id, summary_id, teacher_id, teacher_id)
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
    teacher_role,
    student_role,
    admin_role
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
                               AS absent_days,
                           CASE WHEN EXISTS (
                               SELECT 1 FROM class_teacher_assignments cta
                               WHERE cta.class_id = mas.class_id
                                 AND cta.teacher_user_id = %s
                                 AND cta.ended_at IS NULL
                           ) THEN 1 ELSE 0 END AS can_manage
                    FROM monthly_attendance_summaries mas
                    INNER JOIN classes c ON c.id = mas.class_id
                    LEFT JOIN monthly_attendance_records mar ON mar.summary_id = mas.id
                    WHERE mas.teacher_user_id = %s
                       OR EXISTS (
                           SELECT 1 FROM class_teacher_assignments cta
                           WHERE cta.class_id = mas.class_id
                             AND cta.teacher_user_id = %s
                             AND cta.ended_at IS NULL
                       )
                    GROUP BY mas.id, mas.class_id, mas.attendance_month,
                             mas.total_school_days, c.name
                    ORDER BY mas.attendance_month DESC, mas.id DESC
                    """,
                    (session["user_id"], session["user_id"], session["user_id"])
                )
                summaries = cur.fetchall()
                for item in summaries:
                    item["attendance_month"] = serialize_api_date(
                        item["attendance_month"]
                    )
                    for field in (
                        "total_school_days", "recorded_students", "present_days",
                        "absent_days", "can_manage"
                    ):
                        item[field] = int(item[field] or 0)
                    possible_days = (
                        item["total_school_days"] * item["recorded_students"]
                    )
                    item["attendance_percent"] = (
                        round(100 * item["present_days"] / possible_days, 2)
                        if possible_days else None
                    )
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
            if request.method in ("PUT", "DELETE") and not attendance["can_manage"]:
                return {"error": "Active class teacher assignment not found"}, 403
            if request.method == "DELETE":
                cur.execute(
                    "DELETE FROM monthly_attendance_summaries WHERE id = %s",
                    (summary_id,)
                )
                mysql.connection.commit()
                return {"message": "Monthly attendance summary deleted"}, 200
            if request.method == "PUT":
                data = request.get_json(silent=True)
                if not isinstance(data, dict):
                    return {"error": "Monthly attendance data is required"}, 400
                try:
                    total_school_days = parse_whole_number(
                        data.get("total_school_days")
                    )
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
                       mar.present_days, mar.note,
                       CASE WHEN EXISTS (
                           SELECT 1 FROM student_class_enrollments current
                           WHERE current.student_id = s.id
                             AND current.class_id = %s
                             AND current.ended_at IS NULL
                       ) THEN 1 ELSE 0 END AS currently_enrolled
                FROM students s
                LEFT JOIN monthly_attendance_records mar
                    ON mar.student_id = s.id AND mar.summary_id = %s
                WHERE mar.id IS NOT NULL
                   OR EXISTS (
                       SELECT 1 FROM student_class_enrollments current
                       WHERE current.student_id = s.id
                         AND current.class_id = %s
                         AND current.ended_at IS NULL
                   )
                ORDER BY s.full_name, s.id
                """,
                (attendance["class_id"], summary_id, attendance["class_id"])
            )
            return {
                "summary": attendance,
                "students": cur.fetchall()
            }, 200
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
                """SELECT student_id FROM student_class_enrollments
                   WHERE class_id = %s AND ended_at IS NULL
                   UNION
                   SELECT student_id FROM monthly_attendance_records
                   WHERE summary_id = %s""",
                (attendance["class_id"], summary_id)
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
                    present_days = parse_whole_number(
                        record.get("present_days")
                    )
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

    @attendance.get("/api/student/attendance")
    @login_required
    @role_required(student_role)
    def student_attendance_api():
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
                """SELECT mas.attendance_month, mas.class_id, c.name AS class_name,
                          c.grade, c.section, mas.total_school_days,
                          mar.present_days, mar.note
                   FROM monthly_attendance_records mar
                   INNER JOIN monthly_attendance_summaries mas
                     ON mas.id = mar.summary_id
                   INNER JOIN classes c ON c.id = mas.class_id
                   WHERE mar.student_id = %s
                   ORDER BY mas.attendance_month DESC, mas.id DESC""",
                (student["id"],)
            )
            records = []
            total_school_days = 0
            total_present_days = 0
            for row in cur.fetchall():
                school_days = int(row["total_school_days"] or 0)
                present_days = int(row["present_days"] or 0)
                total_school_days += school_days
                total_present_days += present_days
                records.append({
                    "attendance_month": serialize_api_date(
                        row["attendance_month"]
                    ),
                    "class_id": row["class_id"],
                    "class_name": row["class_name"],
                    "grade": row["grade"],
                    "section": row["section"],
                    "total_school_days": school_days,
                    "present_days": present_days,
                    "absent_days": school_days - present_days,
                    "attendance_percent": round(
                        100 * present_days / school_days, 2
                    ) if school_days else None,
                    "note": row["note"]
                })
            absent_days = total_school_days - total_present_days
            return {
                "summary": {
                    "recorded_months": len(records),
                    "total_school_days": total_school_days,
                    "present_days": total_present_days,
                    "absent_days": absent_days,
                    "attendance_percent": round(
                        100 * total_present_days / total_school_days, 2
                    ) if total_school_days else None
                },
                "records": records
            }, 200
        except Exception as error:
            print("Student attendance error:", error)
            return {"error": "Failed to load student attendance"}, 500
        finally:
            cur.close()

    @attendance.get("/api/admin/attendance")
    @login_required
    @role_required(admin_role)
    def admin_attendance_api():
        class_id = request.args.get("class_id", "").strip()
        month = request.args.get("month", "").strip()
        conditions = []
        parameters = []
        if class_id:
            try:
                class_id = int(class_id)
            except ValueError:
                return {"error": "Class must be a whole number"}, 400
            conditions.append("mas.class_id = %s")
            parameters.append(class_id)
        if month:
            try:
                month = datetime.strptime(month, "%Y-%m").date().replace(day=1)
            except ValueError:
                return {"error": "Month must use YYYY-MM"}, 400
            conditions.append("mas.attendance_month = %s")
            parameters.append(month.isoformat())
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "SELECT id, name, grade, section FROM classes "
                "ORDER BY grade, section, name"
            )
            classes = cur.fetchall()
            cur.execute(
                f"""SELECT mas.id, mas.class_id, c.name AS class_name,
                           c.grade, c.section, mas.attendance_month,
                           mas.total_school_days, creator.username AS created_by,
                           class_teacher.username AS class_teacher,
                           COUNT(mar.id) AS recorded_students,
                           COALESCE(SUM(mar.present_days), 0) AS present_days,
                           COALESCE(SUM(mas.total_school_days - mar.present_days), 0)
                               AS absent_days
                    FROM monthly_attendance_summaries mas
                    INNER JOIN classes c ON c.id = mas.class_id
                    LEFT JOIN users creator ON creator.id = mas.teacher_user_id
                    LEFT JOIN class_teacher_assignments cta
                      ON cta.class_id = c.id AND cta.ended_at IS NULL
                    LEFT JOIN users class_teacher
                      ON class_teacher.id = cta.teacher_user_id
                    LEFT JOIN monthly_attendance_records mar
                      ON mar.summary_id = mas.id
                    {where_clause}
                    GROUP BY mas.id, mas.class_id, c.name, c.grade, c.section,
                             mas.attendance_month, mas.total_school_days,
                             creator.username, class_teacher.username
                    ORDER BY mas.attendance_month DESC, c.grade, c.section, c.name""",
                tuple(parameters)
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
                possible_days = (
                    item["total_school_days"] * item["recorded_students"]
                )
                item["attendance_percent"] = round(
                    100 * item["present_days"] / possible_days, 2
                ) if possible_days else None
            return {"classes": classes, "summaries": summaries}, 200
        except Exception as error:
            print("Admin attendance overview error:", error)
            return {"error": "Failed to load attendance overview"}, 500
        finally:
            cur.close()

    @attendance.get("/api/admin/attendance/<int:summary_id>")
    @login_required
    @role_required(admin_role)
    def admin_attendance_detail_api(summary_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT mas.id, mas.class_id, c.name AS class_name,
                          c.grade, c.section, mas.attendance_month,
                          mas.total_school_days, creator.username AS created_by,
                          class_teacher.username AS class_teacher
                   FROM monthly_attendance_summaries mas
                   INNER JOIN classes c ON c.id = mas.class_id
                   LEFT JOIN users creator ON creator.id = mas.teacher_user_id
                   LEFT JOIN class_teacher_assignments cta
                     ON cta.class_id = c.id AND cta.ended_at IS NULL
                   LEFT JOIN users class_teacher
                     ON class_teacher.id = cta.teacher_user_id
                   WHERE mas.id = %s""",
                (summary_id,)
            )
            summary = cur.fetchone()
            if not summary:
                return {"error": "Attendance register not found"}, 404
            summary["attendance_month"] = serialize_api_date(
                summary["attendance_month"]
            )
            summary["total_school_days"] = int(summary["total_school_days"])
            cur.execute(
                """SELECT s.id AS student_id, s.full_name,
                          mar.present_days, mar.note
                   FROM monthly_attendance_records mar
                   INNER JOIN students s ON s.id = mar.student_id
                   WHERE mar.summary_id = %s
                   ORDER BY s.full_name, s.id""",
                (summary_id,)
            )
            students = []
            for row in cur.fetchall():
                present_days = int(row["present_days"] or 0)
                school_days = summary["total_school_days"]
                students.append({
                    "student_id": row["student_id"],
                    "full_name": row["full_name"],
                    "present_days": present_days,
                    "absent_days": school_days - present_days,
                    "attendance_percent": round(
                        100 * present_days / school_days, 2
                    ) if school_days else None,
                    "note": row["note"]
                })
            return {"summary": summary, "students": students}, 200
        except Exception as error:
            print("Admin attendance detail error:", error)
            return {"error": "Failed to load attendance register"}, 500
        finally:
            cur.close()


    return attendance
