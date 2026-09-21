"""Teacher paper-assessment and marks-management API routes."""

from datetime import datetime

from flask import Blueprint, request, session

PAPER_ASSESSMENT_TYPES = {
    "class_test", "unit_test", "terminal_exam", "assignment", "practical"
}


def validate_paper_assessment_payload(data):
    if not isinstance(data, dict):
        raise ValueError("Assessment data is required")
    title = str(data.get("title") or "").strip()
    subject = str(data.get("subject") or "").strip()
    assessment_type = str(data.get("assessment_type") or "").strip().lower()
    academic_year = str(data.get("academic_year") or "").strip()
    term = str(data.get("term") or "").strip()
    try:
        class_id = int(data.get("class_id"))
    except (TypeError, ValueError) as error:
        raise ValueError("Class is required") from error
    try:
        assessment_date = datetime.strptime(
            str(data.get("assessment_date") or ""), "%Y-%m-%d"
        ).date()
    except ValueError as error:
        raise ValueError("Assessment date must use YYYY-MM-DD") from error
    try:
        max_marks = round(float(data.get("max_marks")), 2)
    except (TypeError, ValueError) as error:
        raise ValueError("Maximum marks must be a number") from error

    if not 2 <= len(title) <= 150:
        raise ValueError("Title must contain 2 to 150 characters")
    if not subject or len(subject) > 100:
        raise ValueError("Subject is required and must be at most 100 characters")
    if assessment_type not in PAPER_ASSESSMENT_TYPES:
        raise ValueError("Assessment type is invalid")
    if not 0 < max_marks <= 1000:
        raise ValueError("Maximum marks must be greater than 0 and at most 1000")
    if len(academic_year) > 20:
        raise ValueError("Academic year must be at most 20 characters")
    if len(term) > 50:
        raise ValueError("Term must be at most 50 characters")

    return {
        "class_id": class_id,
        "subject": subject,
        "title": title,
        "assessment_type": assessment_type,
        "assessment_date": assessment_date.isoformat(),
        "max_marks": max_marks,
        "academic_year": academic_year,
        "term": term,
        "is_published": bool(data.get("is_published", False))
    }


def teacher_has_class_subject(cur, teacher_id, class_id, subject):
    cur.execute(
        """
        SELECT id FROM teacher_class_subjects
        WHERE teacher_user_id = %s AND class_id = %s
          AND LOWER(subject) = LOWER(%s)
        """,
        (teacher_id, class_id, subject)
    )
    return bool(cur.fetchone())


def fetch_teacher_paper_assessment(cur, assessment_id, teacher_id):
    cur.execute(
        """
        SELECT pa.id, pa.teacher_user_id, pa.class_id, pa.subject, pa.title,
               pa.assessment_type, pa.assessment_date, pa.max_marks,
               pa.academic_year, pa.term, pa.is_published, pa.created_at,
               c.name AS class_name, c.grade, c.section
        FROM paper_assessments pa
        INNER JOIN classes c ON c.id = pa.class_id
        WHERE pa.id = %s AND pa.teacher_user_id = %s
        """,
        (assessment_id, teacher_id)
    )
    assessment = cur.fetchone()
    if assessment:
        assessment["max_marks"] = float(assessment["max_marks"])
        assessment["is_published"] = bool(assessment["is_published"])
    return assessment


def create_assessments_blueprint(
    mysql,
    login_required,
    role_required,
    teacher_role
):
    assessments = Blueprint("assessments", __name__)

    @assessments.route("/api/teacher/paper-assessments", methods=["GET", "POST"])
    @login_required
    @role_required(teacher_role)
    def teacher_paper_assessments_api():
        cur = mysql.connection.cursor()
        try:
            if request.method == "GET":
                cur.execute(
                    """
                    SELECT pa.id, pa.class_id, pa.subject, pa.title,
                           pa.assessment_type, pa.assessment_date, pa.max_marks,
                           pa.academic_year, pa.term, pa.is_published,
                           c.name AS class_name,
                           (SELECT COUNT(*) FROM paper_assessment_scores pas
                            WHERE pas.assessment_id = pa.id) AS recorded_students
                    FROM paper_assessments pa
                    INNER JOIN classes c ON c.id = pa.class_id
                    WHERE pa.teacher_user_id = %s
                    ORDER BY pa.assessment_date DESC, pa.id DESC
                    """,
                    (session["user_id"],)
                )
                assessments = cur.fetchall()
                for item in assessments:
                    item["max_marks"] = float(item["max_marks"])
                    item["is_published"] = bool(item["is_published"])
                    item["recorded_students"] = int(item["recorded_students"] or 0)
                return {"assessments": assessments}, 200

            try:
                assessment = validate_paper_assessment_payload(
                    request.get_json(silent=True)
                )
            except ValueError as error:
                return {"error": str(error)}, 400
            if not teacher_has_class_subject(
                cur, session["user_id"], assessment["class_id"], assessment["subject"]
            ):
                return {"error": "Class-subject assignment not found"}, 404
            cur.execute(
                """
                INSERT INTO paper_assessments
                    (teacher_user_id, class_id, subject, title, assessment_type,
                     assessment_date, max_marks, academic_year, term, is_published)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (session["user_id"], assessment["class_id"], assessment["subject"],
                 assessment["title"], assessment["assessment_type"],
                 assessment["assessment_date"], assessment["max_marks"],
                 assessment["academic_year"], assessment["term"],
                 assessment["is_published"])
            )
            assessment_id = cur.lastrowid
            mysql.connection.commit()
            return {
                "message": "Paper assessment created successfully",
                "assessment_id": assessment_id
            }, 201
        except Exception as error:
            mysql.connection.rollback()
            print("Paper assessment error:", error)
            return {"error": "Failed to manage paper assessment"}, 500
        finally:
            cur.close()


    @assessments.route("/api/teacher/paper-assessments/<int:assessment_id>",
               methods=["GET", "PUT", "DELETE"])
    @login_required
    @role_required(teacher_role)
    def teacher_paper_assessment_api(assessment_id):
        cur = mysql.connection.cursor()
        try:
            existing = fetch_teacher_paper_assessment(
                cur, assessment_id, session["user_id"]
            )
            if not existing:
                return {"error": "Paper assessment not found"}, 404

            if request.method == "DELETE":
                cur.execute(
                    "DELETE FROM paper_assessments WHERE id = %s AND teacher_user_id = %s",
                    (assessment_id, session["user_id"])
                )
                mysql.connection.commit()
                return {"message": "Paper assessment deleted"}, 200

            if request.method == "PUT":
                try:
                    assessment = validate_paper_assessment_payload(
                        request.get_json(silent=True)
                    )
                except ValueError as error:
                    return {"error": str(error)}, 400
                if not teacher_has_class_subject(
                    cur, session["user_id"], assessment["class_id"],
                    assessment["subject"]
                ):
                    return {"error": "Class-subject assignment not found"}, 404
                cur.execute(
                    """
                    SELECT COUNT(*) AS score_count,
                           MAX(marks_obtained) AS highest_marks
                    FROM paper_assessment_scores
                    WHERE assessment_id = %s
                    """,
                    (assessment_id,)
                )
                score_summary = cur.fetchone()
                if int(score_summary["score_count"] or 0) > 0:
                    if int(assessment["class_id"]) != int(existing["class_id"]):
                        return {
                            "error": "Class cannot be changed after marks are recorded"
                        }, 409
                    highest_marks = score_summary["highest_marks"]
                    if (
                        highest_marks is not None
                        and float(highest_marks) > assessment["max_marks"]
                    ):
                        return {
                            "error": "Maximum marks cannot be lower than a recorded score"
                        }, 409
                cur.execute(
                    """
                    UPDATE paper_assessments
                    SET class_id = %s, subject = %s, title = %s,
                        assessment_type = %s, assessment_date = %s,
                        max_marks = %s, academic_year = %s, term = %s,
                        is_published = %s
                    WHERE id = %s AND teacher_user_id = %s
                    """,
                    (assessment["class_id"], assessment["subject"], assessment["title"],
                     assessment["assessment_type"], assessment["assessment_date"],
                     assessment["max_marks"], assessment["academic_year"],
                     assessment["term"], assessment["is_published"], assessment_id,
                     session["user_id"])
                )
                mysql.connection.commit()
                return {"message": "Paper assessment updated"}, 200

            cur.execute(
                """
                SELECT s.id AS student_id, s.full_name, s.grade,
                       pas.marks_obtained, pas.is_absent, pas.remarks
                FROM student_class_enrollments sce
                INNER JOIN students s ON s.id = sce.student_id
                LEFT JOIN paper_assessment_scores pas
                    ON pas.student_id = s.id AND pas.assessment_id = %s
                WHERE sce.class_id = %s
                ORDER BY s.full_name, s.id
                """,
                (assessment_id, existing["class_id"])
            )
            students = cur.fetchall()
            for student in students:
                student["is_absent"] = bool(student["is_absent"] or False)
                if student["marks_obtained"] is not None:
                    student["marks_obtained"] = float(student["marks_obtained"])
                    student["percentage"] = round(
                        100 * student["marks_obtained"] / existing["max_marks"], 2
                    )
                else:
                    student["percentage"] = None
            return {"assessment": existing, "students": students}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Paper assessment detail error:", error)
            return {"error": "Failed to manage paper assessment"}, 500
        finally:
            cur.close()


    @assessments.route("/api/teacher/paper-assessments/<int:assessment_id>/scores",
               methods=["PUT"])
    @login_required
    @role_required(teacher_role)
    def teacher_paper_assessment_scores_api(assessment_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("scores"), list):
            return {"error": "Scores must be provided as a list"}, 400
        publish = data.get("is_published")
        if publish is not None and not isinstance(publish, bool):
            return {"error": "Publish status must be true or false"}, 400

        cur = mysql.connection.cursor()
        try:
            assessment = fetch_teacher_paper_assessment(
                cur, assessment_id, session["user_id"]
            )
            if not assessment:
                return {"error": "Paper assessment not found"}, 404
            cur.execute(
                """
                SELECT s.id FROM student_class_enrollments sce
                INNER JOIN students s ON s.id = sce.student_id
                WHERE sce.class_id = %s
                """,
                (assessment["class_id"],)
            )
            enrolled_ids = {int(row["id"]) for row in cur.fetchall()}
            normalized = []
            seen_ids = set()
            for index, score in enumerate(data["scores"], start=1):
                if not isinstance(score, dict):
                    return {"error": f"Score {index} is invalid"}, 400
                try:
                    student_id = int(score.get("student_id"))
                except (TypeError, ValueError):
                    return {"error": f"Score {index} requires a student"}, 400
                if student_id not in enrolled_ids:
                    return {"error": "Score contains a student outside this class"}, 400
                if student_id in seen_ids:
                    return {"error": "Each student can appear only once"}, 400
                seen_ids.add(student_id)
                raw_is_absent = score.get("is_absent", False)
                if not isinstance(raw_is_absent, (bool, int)) or raw_is_absent not in {
                    False, True, 0, 1
                }:
                    return {"error": "Absent status must be true or false"}, 400
                is_absent = bool(raw_is_absent)
                marks = score.get("marks_obtained")
                if is_absent:
                    marks = None
                else:
                    try:
                        marks = round(float(marks), 2)
                    except (TypeError, ValueError):
                        return {"error": "Marks are required for present students"}, 400
                    if not 0 <= marks <= assessment["max_marks"]:
                        return {
                            "error": f"Marks must be between 0 and {assessment['max_marks']}"
                        }, 400
                remarks = str(score.get("remarks") or "").strip()
                if len(remarks) > 500:
                    return {"error": "Remarks must be at most 500 characters"}, 400
                normalized.append((student_id, marks, is_absent, remarks))

            if publish is True and (not enrolled_ids or seen_ids != enrolled_ids):
                return {"error": "Record marks or absence for every enrolled student before publishing"}, 400

            cur.execute(
                "DELETE FROM paper_assessment_scores WHERE assessment_id = %s",
                (assessment_id,)
            )
            for student_id, marks, is_absent, remarks in normalized:
                cur.execute(
                    """
                    INSERT INTO paper_assessment_scores
                        (assessment_id, student_id, marks_obtained, is_absent, remarks)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (assessment_id, student_id, marks, is_absent, remarks)
                )
            if publish is not None:
                cur.execute(
                    """UPDATE paper_assessments SET is_published = %s
                       WHERE id = %s AND teacher_user_id = %s""",
                    (publish, assessment_id, session["user_id"])
                )
            mysql.connection.commit()
            return {
                "message": "Paper assessment scores saved",
                "recorded_students": len(normalized)
            }, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Paper assessment scores error:", error)
            return {"error": "Failed to save paper assessment scores"}, 500
        finally:
            cur.close()


    return assessments
