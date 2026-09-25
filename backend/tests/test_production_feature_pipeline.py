import sqlite3
import unittest

from ai.ml.production.feature_builder import (
    build_feature_row_for_target,
    build_training_dataset,
    generate_diagnostics,
)
from ai.ml.production.build_training_dataset import repository_root
from ai.ml.production.feature_contract import OUTPUT_COLUMNS


class ProductionFeaturePipelineTests(unittest.TestCase):
    @staticmethod
    def _connect():
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        return connection

    def _seed_database(self, connection):
        connection.execute(
            """
            CREATE TABLE paper_assessments (
                id INTEGER PRIMARY KEY,
                class_id INTEGER,
                subject TEXT,
                assessment_date TEXT,
                max_marks REAL,
                is_published INTEGER
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE paper_assessment_scores (
                assessment_id INTEGER,
                student_id INTEGER,
                marks_obtained REAL,
                is_absent INTEGER,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE quiz_sessions (
                id INTEGER PRIMARY KEY,
                class_id INTEGER,
                student_id INTEGER
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE quizzes (
                id INTEGER PRIMARY KEY,
                subject TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE quiz_results (
                id INTEGER PRIMARY KEY,
                quiz_id INTEGER,
                quiz_session_id INTEGER,
                student_id INTEGER,
                score REAL,
                total_questions INTEGER,
                created_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE quiz_answer_results (
                id INTEGER PRIMARY KEY,
                quiz_result_id INTEGER,
                is_correct INTEGER,
                is_skipped INTEGER,
                created_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE monthly_attendance_summaries (
                id INTEGER PRIMARY KEY,
                class_id INTEGER,
                attendance_month TEXT,
                total_school_days INTEGER,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE monthly_attendance_records (
                summary_id INTEGER,
                student_id INTEGER,
                present_days INTEGER,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )

    def test_training_dataset_uses_production_contract(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute(
            "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (1, 7, 'Math', '2024-01-10', 100, 1)"
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (1, 11, 72, 0, '2024-01-10T08:00:00', '2024-01-10T08:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_sessions (id, class_id, student_id) VALUES (1, 7, 11)"
        )
        connection.execute(
            "INSERT INTO quizzes (id, subject) VALUES (1, 'Math')"
        )
        connection.execute(
            "INSERT INTO quiz_results (id, quiz_id, quiz_session_id, student_id, score, total_questions, created_at) VALUES (1, 1, 1, 11, 8, 10, '2024-01-08T09:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_answer_results (id, quiz_result_id, is_correct, is_skipped, created_at) VALUES (1, 1, 1, 0, '2024-01-08T09:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_answer_results (id, quiz_result_id, is_correct, is_skipped, created_at) VALUES (2, 1, 0, 0, '2024-01-08T09:01:00')"
        )
        connection.execute(
            "INSERT INTO monthly_attendance_summaries (id, class_id, attendance_month, total_school_days, created_at, updated_at) VALUES (1, 7, '2024-01-01', 24, '2024-01-01', '2024-01-01')"
        )
        connection.execute(
            "INSERT INTO monthly_attendance_records (summary_id, student_id, present_days, created_at, updated_at) VALUES (1, 11, 20, '2024-01-01', '2024-01-01')"
        )
        connection.commit()

        dataset = build_training_dataset(connection)
        self.assertEqual(list(dataset.columns), OUTPUT_COLUMNS)
        self.assertEqual(len(dataset), 1)
        row = dataset.iloc[0]
        self.assertEqual(row["has_quiz_evidence"], 1.0)
        self.assertEqual(row["has_prior_paper_evidence"], 0.0)
        self.assertEqual(row["has_attendance_evidence"], 1.0)

    def test_future_quiz_evidence_is_excluded(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute(
            "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (1, 7, 'Math', '2024-02-15', 100, 1)"
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (1, 11, 78, 0, '2024-02-15T08:00:00', '2024-02-15T08:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_sessions (id, class_id, student_id) VALUES (1, 7, 11)"
        )
        connection.execute(
            "INSERT INTO quizzes (id, subject) VALUES (1, 'Math')"
        )
        connection.execute(
            "INSERT INTO quiz_results (id, quiz_id, quiz_session_id, student_id, score, total_questions, created_at) VALUES (1, 1, 1, 11, 8, 10, '2024-02-14T09:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_results (id, quiz_id, quiz_session_id, student_id, score, total_questions, created_at) VALUES (2, 1, 1, 11, 9, 10, '2024-02-16T09:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_answer_results (id, quiz_result_id, is_correct, is_skipped, created_at) VALUES (1, 1, 1, 0, '2024-02-14T09:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_answer_results (id, quiz_result_id, is_correct, is_skipped, created_at) VALUES (2, 2, 1, 0, '2024-02-16T09:00:00')"
        )
        connection.commit()

        feature_row = build_feature_row_for_target(connection, {"student_id": 11, "class_id": 7, "subject": "Math", "assessment_id": 1, "assessment_date": "2024-02-15", "max_marks": 100, "marks_obtained": 78})
        self.assertEqual(feature_row["quiz_attempt_count"], 1.0)

    def test_ineligible_rows_are_filtered_out_by_default(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute(
            "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (1, 7, 'Math', '2024-04-01', 100, 1)"
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (1, 11, 72, 0, '2024-04-01T08:00:00', '2024-04-01T08:00:00')"
        )
        connection.commit()

        dataset = build_training_dataset(connection)
        self.assertEqual(len(dataset), 0)

        include_ineligible = build_training_dataset(connection, include_ineligible=True)
        self.assertEqual(len(include_ineligible), 1)
        self.assertFalse(include_ineligible.iloc[0]["eligible_for_prediction"])
        self.assertEqual(include_ineligible.iloc[0]["ineligible_reason"], "insufficient_academic_evidence")

    def test_attendance_only_evidence_is_not_eligible(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute(
            "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (1, 7, 'Math', '2024-04-01', 100, 1)"
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (1, 11, 72, 0, '2024-04-01T08:00:00', '2024-04-01T08:00:00')"
        )
        connection.execute(
            "INSERT INTO monthly_attendance_summaries (id, class_id, attendance_month, total_school_days, created_at, updated_at) VALUES (1, 7, '2024-03-01', 24, '2024-03-01', '2024-03-01')"
        )
        connection.execute(
            "INSERT INTO monthly_attendance_records (summary_id, student_id, present_days, created_at, updated_at) VALUES (1, 11, 20, '2024-03-01', '2024-03-01')"
        )
        connection.commit()

        row = build_training_dataset(connection, include_ineligible=True).iloc[0]
        self.assertFalse(row["eligible_for_prediction"])
        self.assertEqual(row["ineligible_reason"], "insufficient_academic_evidence")
        self.assertEqual(row["has_quiz_evidence"], 0.0)
        self.assertEqual(row["has_prior_paper_evidence"], 0.0)
        self.assertEqual(row["has_attendance_evidence"], 1.0)

    def test_prior_paper_evidence_can_make_target_eligible(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute(
            "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (1, 7, 'Math', '2024-03-01', 100, 1), (2, 7, 'Math', '2024-04-01', 100, 1)"
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (1, 11, 72, 0, '2024-03-01T08:00:00', '2024-03-01T08:00:00'), (2, 11, 80, 0, '2024-04-01T08:00:00', '2024-04-01T08:00:00')"
        )
        connection.commit()

        dataset = build_training_dataset(connection)
        self.assertEqual(len(dataset), 1)
        self.assertEqual(dataset.iloc[0]["target_assessment_id"], 2)
        self.assertEqual(dataset.iloc[0]["has_quiz_evidence"], 0.0)
        self.assertEqual(dataset.iloc[0]["has_prior_paper_evidence"], 1.0)

    def test_missing_target_date_has_distinct_reason(self):
        connection = self._connect()
        self._seed_database(connection)
        row = build_feature_row_for_target(
            connection,
            {
                "student_id": 11,
                "class_id": 7,
                "subject": "Math",
                "assessment_id": 1,
                "assessment_date": None,
                "max_marks": 100,
                "marks_obtained": 72,
            },
        )
        self.assertFalse(row["eligible_for_prediction"])
        self.assertEqual(row["ineligible_reason"], "missing_target_date")

    def test_subject_filter_uses_only_matching_evidence(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute(
            "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (1, 7, 'Math', '2024-03-05', 100, 1), (2, 7, 'Science', '2024-03-06', 100, 1)"
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (1, 11, 81, 0, '2024-03-05T08:00:00', '2024-03-05T08:00:00'), (2, 11, 70, 0, '2024-03-06T08:00:00', '2024-03-06T08:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_sessions (id, class_id, student_id) VALUES (1, 7, 11), (2, 7, 11)"
        )
        connection.execute(
            "INSERT INTO quizzes (id, subject) VALUES (1, 'Math'), (2, 'Science')"
        )
        connection.execute(
            "INSERT INTO quiz_results (id, quiz_id, quiz_session_id, student_id, score, total_questions, created_at) VALUES (1, 1, 1, 11, 8, 10, '2024-03-03T09:00:00'), (2, 2, 2, 11, 9, 10, '2024-03-04T09:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_answer_results (id, quiz_result_id, is_correct, is_skipped, created_at) VALUES (1, 1, 1, 0, '2024-03-03T09:00:00'), (2, 2, 1, 0, '2024-03-04T09:00:00')"
        )
        connection.commit()

        math_dataset = build_training_dataset(connection, subject='Math')
        self.assertEqual(len(math_dataset), 1)
        self.assertEqual(math_dataset.iloc[0]['subject'], 'Math')

    def test_question_evidence_counts_for_skipped_and_incorrect_answers(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute(
            "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (1, 7, 'Math', '2024-05-12', 100, 1)"
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (1, 11, 61, 0, '2024-05-12T08:00:00', '2024-05-12T08:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_sessions (id, class_id, student_id) VALUES (1, 7, 11)"
        )
        connection.execute(
            "INSERT INTO quizzes (id, subject) VALUES (1, 'Math')"
        )
        connection.execute(
            "INSERT INTO quiz_results (id, quiz_id, quiz_session_id, student_id, score, total_questions, created_at) VALUES (1, 1, 1, 11, 8, 10, '2024-05-02T09:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_answer_results (id, quiz_result_id, is_correct, is_skipped, created_at) VALUES (1, 1, 1, 0, '2024-05-02T09:00:00'), (2, 1, 0, 0, '2024-05-02T09:01:00'), (3, 1, 0, 1, '2024-05-02T09:02:00')"
        )
        connection.commit()

        feature_row = build_feature_row_for_target(connection, {"student_id": 11, "class_id": 7, "subject": "Math", "assessment_id": 1, "assessment_date": "2024-05-12", "max_marks": 100, "marks_obtained": 61})
        self.assertEqual(feature_row["incorrect_answer_count"], 2.0)
        self.assertEqual(feature_row["skipped_answer_rate"], 33.33)

    def test_diagnostics_report_includes_ready_counts(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute(
            "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (1, 7, 'Math', '2024-06-02', 100, 1), (2, 7, 'Math', '2024-06-09', 100, 1)"
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (1, 11, 70, 0, '2024-06-02T08:00:00', '2024-06-02T08:00:00'), (2, 11, 75, 0, '2024-06-09T08:00:00', '2024-06-09T08:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_sessions (id, class_id, student_id) VALUES (1, 7, 11)"
        )
        connection.execute(
            "INSERT INTO quizzes (id, subject) VALUES (1, 'Math')"
        )
        connection.execute(
            "INSERT INTO quiz_results (id, quiz_id, quiz_session_id, student_id, score, total_questions, created_at) VALUES (1, 1, 1, 11, 7, 10, '2024-05-30T09:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_answer_results (id, quiz_result_id, is_correct, is_skipped, created_at) VALUES (1, 1, 1, 0, '2024-05-30T09:00:00')"
        )
        connection.execute(
            "INSERT INTO monthly_attendance_summaries (id, class_id, attendance_month, total_school_days, created_at, updated_at) VALUES (1, 7, '2024-06-01', 30, '2024-06-01', '2024-06-01')"
        )
        connection.execute(
            "INSERT INTO monthly_attendance_records (summary_id, student_id, present_days, created_at, updated_at) VALUES (1, 11, 22, '2024-06-01', '2024-06-01')"
        )
        connection.commit()

        report = generate_diagnostics(connection)
        self.assertEqual(report["paper_assessments"], 2)
        self.assertEqual(report["usable_target_rows"], 2)
        self.assertEqual(report["targets_with_academic_evidence"], 2)
        self.assertEqual(report["targets_with_quiz_evidence"], 2)
        self.assertEqual(report["targets_with_prior_paper_evidence"], 1)
        self.assertEqual(report["targets_with_attendance_evidence"], 2)
        self.assertEqual(report["eligible_feature_snapshots"], 2)
        self.assertEqual(report["ineligible_feature_snapshots"], 0)
        self.assertEqual(report["ineligible_reason_counts"], {})
        self.assertIn("feature_columns", report)

    def test_target_percent_uses_marks_over_max_marks(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute(
            "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (1, 7, 'Math', '2024-07-10', 80, 1)"
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (1, 11, 64, 0, '2024-07-10T08:00:00', '2024-07-10T08:00:00')"
        )
        connection.commit()

        feature_row = build_feature_row_for_target(connection, {"student_id": 11, "class_id": 7, "subject": "Math", "assessment_id": 1, "assessment_date": "2024-07-10", "max_marks": 80, "marks_obtained": 64})
        self.assertEqual(feature_row["target_percent"], 80.0)

    def test_feature_snapshot_is_stable_across_repeated_calls(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute(
            "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (1, 7, 'Math', '2024-08-10', 100, 1)"
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (1, 11, 72, 0, '2024-08-10T08:00:00', '2024-08-10T08:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_sessions (id, class_id, student_id) VALUES (1, 7, 11)"
        )
        connection.execute(
            "INSERT INTO quizzes (id, subject) VALUES (1, 'Math')"
        )
        connection.execute(
            "INSERT INTO quiz_results (id, quiz_id, quiz_session_id, student_id, score, total_questions, created_at) VALUES (1, 1, 1, 11, 8, 10, '2024-08-07T09:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_answer_results (id, quiz_result_id, is_correct, is_skipped, created_at) VALUES (1, 1, 1, 0, '2024-08-07T09:00:00')"
        )
        connection.commit()

        target = {"student_id": 11, "class_id": 7, "subject": "Math", "assessment_id": 1, "assessment_date": "2024-08-10", "max_marks": 100, "marks_obtained": 72}
        first = build_feature_row_for_target(connection, target)
        second = build_feature_row_for_target(connection, target)
        self.assertEqual(first, second)

    def test_dotenv_discovery_points_to_repository_root(self):
        self.assertEqual(repository_root().name, "Siksha-Sarathi")
        self.assertTrue((repository_root() / ".env").exists())

    def test_model_feature_order_is_deterministic(self):
        connection = self._connect()
        self._seed_database(connection)
        self.assertEqual(
            list(build_training_dataset(connection).columns),
            OUTPUT_COLUMNS,
        )


if __name__ == "__main__":
    unittest.main()
