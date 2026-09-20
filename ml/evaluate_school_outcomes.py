"""Read-only, time-aware evaluation of Grade 10 paper exam outcomes.

Run from the repository root: python -m ml.evaluate_school_outcomes --subject Science
This script never updates the application model or any database record.
"""

import argparse
from datetime import date, datetime
import os


FEATURES = (
    "previous_paper_pct", "lab_quiz_pct", "lab_quiz_count",
    "attendance_rate", "attendance_days",
)


def day(value):
    return value.date() if isinstance(value, datetime) else date.fromisoformat(value[:10]) if isinstance(value, str) else value


def recorded_before(row, exam_day):
    """An edited historical record cannot be reconstructed at its old value."""
    return all(row.get(field) is not None and day(row[field]) < exam_day
               for field in ("created_at", "updated_at"))


def build_examples(exams, papers, quizzes, attendance):
    """Return independent feature snapshots; no data on or after the exam day."""
    examples = []
    for exam in exams:
        exam_day = day(exam["assessment_date"])
        if (not exam["is_published"] or exam["is_absent"]
                or exam["marks_obtained"] is None or not exam["max_marks"]
                or not 0 <= exam["marks_obtained"] <= exam["max_marks"]):
            continue
        student, class_id, subject = exam["student_id"], exam["class_id"], exam["subject"]
        earlier = [p for p in papers if p["student_id"] == student
                   and p["class_id"] == class_id and p["subject"] == subject
                   and p["assessment_id"] != exam["assessment_id"]
                   and p["is_published"] and not p["is_absent"]
                   and p["marks_obtained"] is not None and p["max_marks"]
                   and 0 <= p["marks_obtained"] <= p["max_marks"]
                   and day(p["assessment_date"]) < exam_day
                   and recorded_before(p, exam_day)]
        if not earlier:
            continue
        latest = max(earlier, key=lambda p: (day(p["assessment_date"]), p["assessment_id"]))
        lab = [q for q in quizzes if q["student_id"] == student
               and q["class_id"] == class_id and q["subject"] == subject
               and q["total_questions"] and q["score"] is not None
               and q.get("created_at") is not None and day(q["created_at"]) < exam_day]
        days = [a for a in attendance if a["student_id"] == student
                and a["class_id"] == class_id and a["status"] in ("present", "absent", "late", "excused")
                and day(a["attendance_date"]) < exam_day and recorded_before(a, exam_day)]
        examples.append({
            "student_id": student, "exam_day": exam_day,
            "target_pct": 100 * float(exam["marks_obtained"]) / float(exam["max_marks"]),
            "previous_paper_pct": 100 * float(latest["marks_obtained"]) / float(latest["max_marks"]),
            "lab_quiz_pct": sum(100 * float(q["score"]) / q["total_questions"] for q in lab) / len(lab) if lab else 0,
            "lab_quiz_count": len(lab),
            "attendance_rate": sum(a["status"] in ("present", "late") for a in days) / len(days) if days else 0,
            "attendance_days": len(days),
        })
    return examples


def evaluate(examples, minimum_students=30, minimum_test_students=10):
    """Compare a simple baseline and Ridge on a future exam date, if feasible."""
    students = {e["student_id"] for e in examples}
    dates = sorted({e["exam_day"] for e in examples})
    report = {"examples": len(examples), "students": len(students), "exam_dates": len(dates)}
    if len(students) < minimum_students or len(dates) < 2:
        report["reason"] = (f"Need at least {minimum_students} distinct students with earlier paper marks "
                            "and two exam dates before comparing models.")
        return report
    # Test on the last date. Never split an exam between training and testing.
    cutoff = dates[-1]
    train = [e for e in examples if e["exam_day"] < cutoff]
    test = [e for e in examples if e["exam_day"] == cutoff]
    if len({e["student_id"] for e in train}) < minimum_students or len({e["student_id"] for e in test}) < minimum_test_students:
        report["reason"] = (f"Need {minimum_students} training students before the latest exam "
                            f"and {minimum_test_students} students on that exam; no evaluation was run.")
        return report

    from sklearn.dummy import DummyRegressor
    from sklearn.linear_model import Ridge
    from sklearn.metrics import mean_absolute_error
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    x_train = [[e[f] for f in FEATURES] for e in train]
    x_test = [[e[f] for f in FEATURES] for e in test]
    y_train = [e["target_pct"] for e in train]
    y_test = [e["target_pct"] for e in test]
    baseline = DummyRegressor(strategy="mean").fit(x_train, y_train)
    candidate = make_pipeline(StandardScaler(), Ridge(alpha=10)).fit(x_train, y_train)
    report.update({
        "train_students": len({e["student_id"] for e in train}),
        "test_students": len({e["student_id"] for e in test}),
        "test_date": cutoff.isoformat(),
        "baseline_mae": round(mean_absolute_error(y_test, baseline.predict(x_test)), 2),
        "ridge_mae": round(mean_absolute_error(y_test, candidate.predict(x_test)), 2),
    })
    return report


def fetch_records(connection, subject):
    """Read only Grade 10 records; no names, emails, or remarks are selected."""
    cursor = connection.cursor()
    try:
        cursor.execute("""
            SELECT pa.id AS assessment_id, pas.student_id, pa.class_id,
                   pa.subject, pa.assessment_type, pa.assessment_date,
                   pa.max_marks, pa.is_published, pas.marks_obtained, pas.is_absent,
                   pa.created_at AS assessment_created_at,
                   pas.created_at, pas.updated_at
            FROM paper_assessments pa
            JOIN paper_assessment_scores pas ON pas.assessment_id = pa.id
            JOIN classes c ON c.id = pa.class_id
            WHERE TRIM(c.grade) = '10' AND pa.subject = %s
        """, (subject,))
        papers = cursor.fetchall()
        # Assessment creation after the target day is excluded from prior evidence.
        for p in papers:
            if p["created_at"] and p["assessment_created_at"]:
                p["created_at"] = max(p["created_at"], p["assessment_created_at"])
            else:
                p["created_at"] = None
        cursor.execute("""
            SELECT qr.student_id, qs.class_id, q.subject, qr.score,
                   qr.total_questions, answers.submitted_at AS created_at
            FROM quiz_results qr
            JOIN quiz_sessions qs ON qs.id = qr.quiz_session_id
            JOIN quizzes q ON q.id = qr.quiz_id
            JOIN classes c ON c.id = qs.class_id
            JOIN (
                SELECT quiz_result_id, MAX(created_at) AS submitted_at
                FROM quiz_answer_results
                GROUP BY quiz_result_id
            ) answers ON answers.quiz_result_id = qr.id
            WHERE TRIM(c.grade) = '10' AND q.subject = %s
        """, (subject,))
        quizzes = cursor.fetchall()
        cursor.execute("""
            SELECT ar.student_id, ats.class_id, ats.attendance_date, ar.status,
                   GREATEST(ar.created_at, ats.created_at) AS created_at,
                   GREATEST(ar.updated_at, ats.updated_at) AS updated_at
            FROM attendance_records ar
            JOIN attendance_sessions ats ON ats.id = ar.attendance_session_id
            JOIN classes c ON c.id = ats.class_id
            WHERE TRIM(c.grade) = '10'
        """)
        attendance = cursor.fetchall()
    finally:
        cursor.close()
    exams = [p for p in papers if p["assessment_type"] == "terminal_exam"]
    return exams, papers, quizzes, attendance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True, help="Exact Grade 10 subject name, e.g. Science")
    args = parser.parse_args()
    from dotenv import load_dotenv
    import MySQLdb
    from MySQLdb.cursors import DictCursor

    load_dotenv()
    connection = MySQLdb.connect(host=os.getenv("MYSQL_HOST", "localhost"),
                                 user=os.getenv("MYSQL_USER", "siksha_user"),
                                 passwd=os.getenv("MYSQL_PASSWORD", ""),
                                 db=os.getenv("MYSQL_DB", "siksha_sarathi"),
                                 cursorclass=DictCursor)
    try:
        examples = build_examples(*fetch_records(connection, args.subject))
        report = evaluate(examples)
    finally:
        connection.close()
    print(f"Grade 10 {args.subject}: {report['examples']} usable exam outcomes, "
          f"{report['students']} students, {report['exam_dates']} exam dates")
    if "reason" in report:
        print(f"No model comparison: {report['reason']}")
    else:
        print(f"Future exam {report['test_date']}: {report['train_students']} training students, "
              f"{report['test_students']} test students")
        print(f"Mean-score baseline MAE: {report['baseline_mae']} percentage points")
        print(f"Ridge MAE: {report['ridge_mae']} percentage points")
        print("Exploratory result only; repeated students, delayed data entry, and school differences need review.")


if __name__ == "__main__":
    main()
