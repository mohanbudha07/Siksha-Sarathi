"""Student identity and current-class access helpers."""


def fetch_student_context(cur, user_id):
    cur.execute(
        """SELECT s.id AS student_id, s.full_name, s.grade,
                  c.id AS class_id, c.name AS class_name,
                  c.grade AS class_grade, c.section
           FROM students s
           LEFT JOIN student_class_enrollments sce
             ON sce.student_id = s.id
            AND sce.id = (
                SELECT latest.id
                FROM student_class_enrollments latest
                WHERE latest.student_id = s.id
                ORDER BY latest.created_at DESC, latest.id DESC
                LIMIT 1
            )
           LEFT JOIN classes c ON c.id = sce.class_id
           WHERE s.user_id = %s""",
        (user_id,)
    )
    student = cur.fetchone()
    if not student:
        return None

    current_class = None
    subjects = []
    if student["class_id"] is not None:
        current_class = {
            "id": student["class_id"],
            "name": student["class_name"],
            "grade": student["class_grade"],
            "section": student["section"]
        }
        cur.execute(
            """SELECT DISTINCT sub.id, sub.name, sub.code
               FROM teacher_class_subjects tcs
               INNER JOIN subjects sub ON sub.id = tcs.subject_id
               WHERE tcs.class_id = %s
               ORDER BY sub.name""",
            (student["class_id"],)
        )
        subjects = cur.fetchall()

    return {
        "student": {
            "student_id": student["student_id"],
            "full_name": student["full_name"],
            "grade": student["grade"]
        },
        "student_id": student["student_id"],
        "current_class": current_class,
        "subjects": subjects,
        "subject_names": {
            str(subject["name"]).strip().casefold()
            for subject in subjects
        }
    }