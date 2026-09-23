"""Check that offline evaluation uses only observable prior evidence."""

from datetime import date, datetime, timedelta
import sqlite3
import unittest

import sklearn  # Load before the existing Flask tests temporarily patch module imports.

from ai.ml.evaluate_school_outcomes import build_examples, evaluate, fetch_records


def paper(student, assessment_id, assessment_date, marks, kind="class_test", **changes):
    row = dict(student_id=student, class_id=1, subject="Science",
               assessment_id=assessment_id, assessment_date=assessment_date,
               assessment_type=kind, max_marks=100, marks_obtained=marks,
               is_absent=False, is_published=True,
               created_at=datetime.combine(assessment_date - timedelta(days=1), datetime.min.time()),
               updated_at=datetime.combine(assessment_date - timedelta(days=1), datetime.min.time()))
    row.update(changes)
    return row


class SchoolOutcomeEvaluationTests(unittest.TestCase):
    def test_legacy_quiz_results_without_timestamp_can_supply_lab_evidence(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.create_function("GREATEST", 2, max)
        db.executescript("""
            CREATE TABLE classes(id INTEGER, grade TEXT);
            CREATE TABLE paper_assessments(id INTEGER, class_id INTEGER, subject TEXT,
                assessment_type TEXT, assessment_date DATE, max_marks INTEGER,
                is_published INTEGER, created_at TEXT);
            CREATE TABLE paper_assessment_scores(assessment_id INTEGER, student_id INTEGER,
                marks_obtained INTEGER, is_absent INTEGER, created_at TEXT, updated_at TEXT);
            CREATE TABLE quiz_sessions(id INTEGER, class_id INTEGER);
            CREATE TABLE quizzes(id INTEGER, subject TEXT);
            CREATE TABLE quiz_results(id INTEGER, student_id INTEGER, quiz_id INTEGER,
                quiz_session_id INTEGER, score INTEGER, total_questions INTEGER);
            CREATE TABLE quiz_answer_results(quiz_result_id INTEGER, created_at TEXT);
            CREATE TABLE attendance_sessions(id INTEGER, class_id INTEGER, attendance_date DATE,
                created_at TEXT, updated_at TEXT);
            CREATE TABLE attendance_records(attendance_session_id INTEGER, student_id INTEGER,
                status TEXT, created_at TEXT, updated_at TEXT);
            INSERT INTO classes VALUES(1, '10');
            INSERT INTO paper_assessments VALUES
                (1, 1, 'Science', 'class_test', '2026-09-01', 100, 1, '2026-09-01'),
                (2, 1, 'Science', 'terminal_exam', '2026-09-15', 100, 1, '2026-09-14');
            INSERT INTO paper_assessment_scores VALUES
                (1, 1, 35, 0, '2026-09-01', '2026-09-01'),
                (2, 1, 70, 0, '2026-09-15', '2026-09-15');
            INSERT INTO quiz_sessions VALUES(1, 1);
            INSERT INTO quizzes VALUES(1, 'Science');
            INSERT INTO quiz_results VALUES(1, 1, 1, 1, 1, 2);
            INSERT INTO quiz_answer_results VALUES
                (1, '2026-09-10 10:00:00'), (1, '2026-09-10 10:00:01');
        """)

        class Cursor:
            def __init__(self):
                self.cursor = db.cursor()

            def execute(self, query, args=()):
                self.cursor.execute(query.replace("%s", "?"), args)

            def fetchall(self):
                return [dict(row) for row in self.cursor.fetchall()]

            def close(self):
                self.cursor.close()

        class Connection:
            def cursor(self):
                return Cursor()

        try:
            exams, papers, quizzes, attendance = fetch_records(Connection(), "Science")
            self.assertEqual(quizzes[0]["created_at"], "2026-09-10 10:00:01")
            self.assertEqual(build_examples(exams, papers, quizzes, attendance)[0]["lab_quiz_count"], 1)
        finally:
            db.close()

    def test_excludes_exam_day_and_later_records_and_late_edits(self):
        target = date(2026, 9, 15)
        earlier = paper(1, 1, date(2026, 9, 1), 40)
        edited_later = paper(1, 2, date(2026, 9, 3), 95,
                             updated_at=datetime(2026, 9, 16))
        same_day = paper(1, 3, target, 100)
        exam = paper(1, 4, target, 70, kind="terminal_exam")
        lab = [dict(student_id=1, class_id=1, subject="Science", score=1,
                    total_questions=2, created_at=datetime(2026, 9, 14)),
               dict(student_id=1, class_id=1, subject="Science", score=2,
                    total_questions=2, created_at=datetime(2026, 9, 15))]
        attendance = [dict(student_id=1, class_id=1, status="present",
                           attendance_date=date(2026, 9, 14),
                           created_at=datetime(2026, 9, 14), updated_at=datetime(2026, 9, 14)),
                      dict(student_id=1, class_id=1, status="absent",
                           attendance_date=target,
                           created_at=datetime(2026, 9, 15), updated_at=datetime(2026, 9, 15))]
        examples = build_examples([exam], [earlier, edited_later, same_day, exam], lab, attendance)
        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0]["previous_paper_pct"], 40)
        self.assertEqual(examples[0]["lab_quiz_pct"], 50)
        self.assertEqual(examples[0]["lab_quiz_count"], 1)
        self.assertEqual(examples[0]["attendance_days"], 1)
        self.assertEqual(examples[0]["target_pct"], 70)

    def test_absence_and_no_previous_mark_are_not_zero_score_targets(self):
        target = date(2026, 9, 15)
        exams = [paper(1, 1, target, None, kind="terminal_exam", is_absent=True),
                 paper(2, 2, target, 0, kind="terminal_exam")]
        self.assertEqual(build_examples(exams, exams, [], []), [])
        prior = paper(2, 3, date(2026, 9, 1), 30)
        self.assertEqual(build_examples(exams, [prior, *exams], [], [])[0]["target_pct"], 0)

    def test_single_student_reports_insufficient_data(self):
        result = evaluate([dict(student_id=1, exam_day=date(2026, 9, 15))])
        self.assertEqual(result["students"], 1)
        self.assertIn("Need at least 30", result["reason"])
        self.assertNotIn("ridge_mae", result)

    def test_future_exam_is_held_out_for_comparison(self):
        examples = []
        for student in range(1, 31):
            for exam_day in (date(2026, 6, 1), date(2026, 9, 1)):
                examples.append(dict(student_id=student, exam_day=exam_day,
                                     target_pct=40 + student,
                                     previous_paper_pct=35 + student,
                                     lab_quiz_pct=50, lab_quiz_count=2,
                                     attendance_rate=.9, attendance_days=20))
        report = evaluate(examples)
        self.assertEqual(report["test_date"], "2026-09-01")
        self.assertEqual(report["test_students"], 30)
        self.assertIn("baseline_mae", report)
        self.assertIn("ridge_mae", report)


if __name__ == "__main__":
    unittest.main()
