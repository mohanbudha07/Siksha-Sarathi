import sqlite3
import unittest
from unittest.mock import patch

import pandas as pd

from ai.ml.production.feature_builder import (
    build_feature_row_for_target,
    build_source_evidence_summary,
    build_training_dataset,
    generate_diagnostics,
)
from ai.ml.production.build_training_dataset import repository_root
from ai.ml.production.feature_contract import MODEL_FEATURE_COLUMNS, OUTPUT_COLUMNS, TARGET_COLUMN
from ai.ml.production.training_readiness import (
    MIN_ELIGIBLE_ROWS,
    MIN_UNIQUE_STUDENTS,
    MIN_UNIQUE_TARGET_DATES,
    MIN_VALIDATION_ROWS,
    MIN_VALIDATION_STUDENTS,
    _candidate_models,
    _evaluate_models,
    _temporal_split,
    build_admin_training_readiness_report,
    build_training_readiness_report,
    evaluate_training_dataset,
)


class ProductionFeaturePipelineTests(unittest.TestCase):
    @staticmethod
    def _readiness_dataset():
        dates = ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"]
        rows = []
        for date_index, target_date in enumerate(dates):
            for student_id in range(1, 31):
                row_index = date_index * 30 + student_id
                row = {
                    "student_id": student_id,
                    "subject": "Math",
                    "target_assessment_id": 1000 + row_index,
                    "target_assessment_date": target_date,
                    "target_class_id": 7,
                    "target_max_marks": 100.0,
                    "target_marks_obtained": 45.0 + student_id * 0.5 + date_index * 2,
                    "eligible_for_prediction": True,
                    "ineligible_reason": "",
                    TARGET_COLUMN: 45.0 + student_id * 0.5 + date_index * 2,
                }
                row.update(
                    {
                        column: float((student_id * 3 + date_index * 7 + feature_index) % 100)
                        for feature_index, column in enumerate(MODEL_FEATURE_COLUMNS)
                    }
                )
                rows.append(row)
        return pd.DataFrame(rows)

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
        connection.execute("CREATE TABLE students (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE classes (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE subjects (id INTEGER PRIMARY KEY)")

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

    def test_training_readiness_reports_insufficient_data(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute(
            "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (1, 7, 'Math', '2024-04-01', 100, 1)"
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (1, 11, 72, 0, '2024-04-01T08:00:00', '2024-04-01T08:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_sessions (id, class_id, student_id) VALUES (1, 7, 11)"
        )
        connection.execute(
            "INSERT INTO quizzes (id, subject) VALUES (1, 'Math')"
        )
        connection.execute(
            "INSERT INTO quiz_results (id, quiz_id, quiz_session_id, student_id, score, total_questions, created_at) VALUES (1, 1, 1, 11, 7, 10, '2024-03-28T09:00:00')"
        )
        connection.execute(
            "INSERT INTO quiz_answer_results (id, quiz_result_id, is_correct, is_skipped, created_at) VALUES (1, 1, 1, 0, '2024-03-28T09:00:00')"
        )
        connection.commit()

        report = build_training_readiness_report(connection)
        self.assertEqual(report["eligible_training_snapshots"], 1)
        self.assertEqual(report["readiness_state"], "insufficient_data")
        self.assertFalse(report["evaluation_ready"])

    def test_training_readiness_runs_temporal_holdout_evaluation(self):
        connection = self._connect()
        self._seed_database(connection)

        for student_id in range(1, 31):
            training_target_id = 1000 + student_id
            test_target_id = 2000 + student_id
            later_training_target_id = 5000 + student_id
            later_test_target_id = 6000 + student_id
            prior_training_id = 3000 + student_id
            prior_test_id = 4000 + student_id

            connection.execute(
                "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (?, 7, 'Math', '2024-01-01', 100, 1)",
                (prior_training_id,),
            )
            connection.execute(
                "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (?, ?, 62, 0, '2024-01-01T08:00:00', '2024-01-01T08:00:00')",
                (prior_training_id, student_id),
            )
            connection.execute(
                "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (?, 7, 'Math', '2024-01-15', 100, 1)",
                (training_target_id,),
            )
            connection.execute(
                "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (?, ?, 70, 0, '2024-01-15T08:00:00', '2024-01-15T08:00:00')",
                (training_target_id, student_id),
            )
            connection.execute(
                "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (?, 7, 'Math', '2024-02-01', 100, 1)",
                (prior_test_id,),
            )
            connection.execute(
                "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (?, ?, 68, 0, '2024-02-01T08:00:00', '2024-02-01T08:00:00')",
                (prior_test_id, student_id),
            )
            connection.execute(
                "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (?, 7, 'Math', '2024-02-15', 100, 1)",
                (test_target_id,),
            )
            connection.execute(
                "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (?, ?, 78, 0, '2024-02-15T08:00:00', '2024-02-15T08:00:00')",
                (test_target_id, student_id),
            )
            connection.execute(
                "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (?, 7, 'Math', '2024-03-01', 100, 1)",
                (later_training_target_id,),
            )
            connection.execute(
                "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (?, ?, 74, 0, '2024-03-01T08:00:00', '2024-03-01T08:00:00')",
                (later_training_target_id, student_id),
            )
            connection.execute(
                "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (?, 7, 'Math', '2024-03-15', 100, 1)",
                (later_test_target_id,),
            )
            connection.execute(
                "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (?, ?, 80, 0, '2024-03-15T08:00:00', '2024-03-15T08:00:00')",
                (later_test_target_id, student_id),
            )

            connection.execute(
                "INSERT INTO quiz_sessions (id, class_id, student_id) VALUES (?, 7, ?)",
                (training_target_id, student_id),
            )
            connection.execute(
                "INSERT INTO quizzes (id, subject) VALUES (?, 'Math')",
                (training_target_id,),
            )
            connection.execute(
                "INSERT INTO quiz_results (id, quiz_id, quiz_session_id, student_id, score, total_questions, created_at) VALUES (?, ?, ?, ?, 8, 10, '2024-01-10T07:00:00')",
                (training_target_id, training_target_id, training_target_id, student_id),
            )
            connection.execute(
                "INSERT INTO quiz_answer_results (id, quiz_result_id, is_correct, is_skipped, created_at) VALUES (?, ?, 1, 0, '2024-01-10T07:00:00')",
                (training_target_id, training_target_id),
            )

            connection.execute(
                "INSERT INTO quiz_sessions (id, class_id, student_id) VALUES (?, 7, ?)",
                (test_target_id, student_id),
            )
            connection.execute(
                "INSERT INTO quizzes (id, subject) VALUES (?, 'Math')",
                (test_target_id,),
            )
            connection.execute(
                "INSERT INTO quiz_results (id, quiz_id, quiz_session_id, student_id, score, total_questions, created_at) VALUES (?, ?, ?, ?, 9, 10, '2024-02-10T07:00:00')",
                (test_target_id, test_target_id, test_target_id, student_id),
            )
            connection.execute(
                "INSERT INTO quiz_answer_results (id, quiz_result_id, is_correct, is_skipped, created_at) VALUES (?, ?, 1, 0, '2024-02-10T07:00:00')",
                (test_target_id, test_target_id),
            )

            connection.execute(
                "INSERT INTO quiz_sessions (id, class_id, student_id) VALUES (?, 7, ?)",
                (later_training_target_id, student_id),
            )
            connection.execute(
                "INSERT INTO quizzes (id, subject) VALUES (?, 'Math')",
                (later_training_target_id,),
            )
            connection.execute(
                "INSERT INTO quiz_results (id, quiz_id, quiz_session_id, student_id, score, total_questions, created_at) VALUES (?, ?, ?, ?, 8, 10, '2024-03-05T07:00:00')",
                (later_training_target_id, later_training_target_id, later_training_target_id, student_id),
            )
            connection.execute(
                "INSERT INTO quiz_answer_results (id, quiz_result_id, is_correct, is_skipped, created_at) VALUES (?, ?, 1, 0, '2024-03-05T07:00:00')",
                (later_training_target_id, later_training_target_id),
            )

            connection.execute(
                "INSERT INTO quiz_sessions (id, class_id, student_id) VALUES (?, 7, ?)",
                (later_test_target_id, student_id),
            )
            connection.execute(
                "INSERT INTO quizzes (id, subject) VALUES (?, 'Math')",
                (later_test_target_id,),
            )
            connection.execute(
                "INSERT INTO quiz_results (id, quiz_id, quiz_session_id, student_id, score, total_questions, created_at) VALUES (?, ?, ?, ?, 9, 10, '2024-03-20T07:00:00')",
                (later_test_target_id, later_test_target_id, later_test_target_id, student_id),
            )
            connection.execute(
                "INSERT INTO quiz_answer_results (id, quiz_result_id, is_correct, is_skipped, created_at) VALUES (?, ?, 1, 0, '2024-03-20T07:00:00')",
                (later_test_target_id, later_test_target_id),
            )
        connection.commit()

        report = build_training_readiness_report(connection)
        self.assertGreaterEqual(report["eligible_training_snapshots"], 20)
        self.assertEqual(report["readiness_state"], "evaluation_ready")
        self.assertTrue(report["evaluation_ready"])
        self.assertIn("dummy_mae", report["baseline_evaluation"])
        self.assertIn("ridge_mae", report["baseline_evaluation"])

    def test_phase_7_minimum_guardrails_are_explicit(self):
        self.assertEqual(MIN_ELIGIBLE_ROWS, 100)
        self.assertEqual(MIN_UNIQUE_STUDENTS, 30)
        self.assertEqual(MIN_UNIQUE_TARGET_DATES, 4)
        self.assertEqual(MIN_VALIDATION_ROWS, 20)
        self.assertEqual(MIN_VALIDATION_STUDENTS, 10)

    def test_readiness_blocks_a_missing_feature_column(self):
        dataset = self._readiness_dataset().drop(columns=[MODEL_FEATURE_COLUMNS[0]])
        report = evaluate_training_dataset(dataset)
        self.assertIn("missing_feature_columns", report["blockers"])

    def test_readiness_blocks_a_non_numeric_feature(self):
        dataset = self._readiness_dataset()
        dataset[MODEL_FEATURE_COLUMNS[0]] = dataset[MODEL_FEATURE_COLUMNS[0]].astype(object)
        dataset.loc[0, MODEL_FEATURE_COLUMNS[0]] = "not-a-number"
        report = evaluate_training_dataset(dataset)
        self.assertIn("non_finite_features", report["blockers"])

    def test_readiness_blocks_a_nan_feature(self):
        dataset = self._readiness_dataset()
        dataset.loc[0, MODEL_FEATURE_COLUMNS[0]] = float("nan")
        report = evaluate_training_dataset(dataset)
        self.assertIn("non_finite_features", report["blockers"])

    def test_readiness_blocks_an_infinite_feature(self):
        dataset = self._readiness_dataset()
        dataset.loc[0, MODEL_FEATURE_COLUMNS[0]] = float("inf")
        report = evaluate_training_dataset(dataset)
        self.assertIn("non_finite_features", report["blockers"])

    def test_readiness_blocks_a_non_finite_target(self):
        dataset = self._readiness_dataset()
        dataset.loc[0, TARGET_COLUMN] = float("nan")
        report = evaluate_training_dataset(dataset)
        self.assertIn("non_finite_target", report["blockers"])

    def test_readiness_blocks_a_target_below_zero(self):
        dataset = self._readiness_dataset()
        dataset.loc[0, TARGET_COLUMN] = -0.1
        report = evaluate_training_dataset(dataset)
        self.assertIn("invalid_target_range", report["blockers"])

    def test_readiness_blocks_a_target_above_100(self):
        dataset = self._readiness_dataset()
        dataset.loc[0, TARGET_COLUMN] = 100.1
        report = evaluate_training_dataset(dataset)
        self.assertIn("invalid_target_range", report["blockers"])

    def test_readiness_blocks_a_missing_target_date(self):
        dataset = self._readiness_dataset()
        dataset.loc[0, "target_assessment_date"] = None
        report = evaluate_training_dataset(dataset)
        self.assertIn("missing_target_dates", report["blockers"])

    def test_readiness_blocks_duplicate_snapshot_identity(self):
        dataset = self._readiness_dataset()
        dataset.loc[1, "target_assessment_id"] = dataset.loc[0, "target_assessment_id"]
        dataset.loc[1, "student_id"] = dataset.loc[0, "student_id"]
        dataset.loc[1, "subject"] = dataset.loc[0, "subject"]
        report = evaluate_training_dataset(dataset)
        self.assertIn("duplicate_snapshot_identity", report["blockers"])

    def test_sufficient_dataset_is_ready_for_temporal_evaluation(self):
        report = evaluate_training_dataset(self._readiness_dataset())
        self.assertTrue(report["training_ready"])
        self.assertTrue(report["evaluation_ready"])
        self.assertEqual(report["readiness_state"], "evaluation_ready")

    def test_monitoring_readiness_does_not_run_baseline_models(self):
        with patch(
            "ai.ml.production.training_readiness._evaluate_models",
            side_effect=AssertionError("monitoring must not evaluate models"),
        ):
            report = evaluate_training_dataset(
                self._readiness_dataset(),
                run_baseline_evaluation=False,
            )
        self.assertTrue(report["evaluation_ready"])
        self.assertEqual(report["readiness_state"], "ready_for_evaluation")
        self.assertEqual(report["baseline_evaluation"]["status"], "not_run")
        self.assertEqual(report["validation_rows"], 30)
        self.assertEqual(report["validation_students"], 30)

    def test_source_evidence_summary_reports_empty_database_as_aggregate_zeros(self):
        connection = self._connect()
        self._seed_database(connection)
        report = build_source_evidence_summary(connection)
        self.assertEqual(
            report,
            {
                "total_students": 0,
                "quiz_attempts": 0,
                "students_with_quiz_attempts": 0,
                "published_paper_assessments": 0,
                "valid_scored_paper_rows": 0,
                "students_with_valid_paper_evidence": 0,
                "distinct_scored_paper_dates": 0,
                "attendance_records": 0,
                "subjects_with_academic_evidence": 0,
                "classes_with_academic_evidence": 0,
            },
        )

    def test_quiz_attempts_without_target_papers_are_not_eligible_snapshots(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute("INSERT INTO students (id) VALUES (11)")
        connection.execute("INSERT INTO classes (id) VALUES (7)")
        connection.execute("INSERT INTO subjects (id) VALUES (1)")
        connection.execute("INSERT INTO quiz_sessions (id, class_id, student_id) VALUES (1, 7, 11)")
        connection.execute("INSERT INTO quizzes (id, subject) VALUES (1, 'Math')")
        connection.execute(
            "INSERT INTO quiz_results (id, quiz_id, quiz_session_id, student_id, score, total_questions, created_at) VALUES (1, 1, 1, 11, 8, 10, '2024-02-01T09:00:00')"
        )
        connection.commit()

        report = build_admin_training_readiness_report(connection)
        self.assertEqual(report["source_evidence"]["quiz_attempts"], 1)
        self.assertEqual(report["source_evidence"]["students_with_quiz_attempts"], 1)
        self.assertEqual(report["source_evidence"]["published_paper_assessments"], 0)
        self.assertEqual(report["progress"]["eligible_snapshots"]["current"], 0)
        self.assertEqual(report["readiness"]["blockers"], ["empty_dataset"])

    def test_paper_score_without_prior_academic_evidence_is_not_eligible(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute("INSERT INTO students (id) VALUES (11)")
        connection.execute("INSERT INTO classes (id) VALUES (7)")
        connection.execute("INSERT INTO subjects (id) VALUES (1)")
        connection.execute(
            "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (1, 7, 'Math', '2024-03-01', 100, 1)"
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (1, 11, 72, 0, '2024-03-01T08:00:00', '2024-03-01T08:00:00')"
        )
        connection.commit()

        report = build_admin_training_readiness_report(connection)
        self.assertEqual(report["source_evidence"]["valid_scored_paper_rows"], 1)
        self.assertEqual(report["source_evidence"]["students_with_valid_paper_evidence"], 1)
        self.assertEqual(report["progress"]["eligible_snapshots"]["current"], 0)
        self.assertEqual(report["readiness"]["blockers"], ["empty_eligible_dataset"])

    def test_non_finite_paper_score_is_excluded_from_valid_source_evidence(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute(
            "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (1, 7, 'Math', '2024-03-01', 100, 1)"
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (1, 11, 'NaN', 0, '2024-03-01T08:00:00', '2024-03-01T08:00:00')"
        )
        connection.commit()

        report = build_source_evidence_summary(connection)
        self.assertEqual(report["published_paper_assessments"], 1)
        self.assertEqual(report["valid_scored_paper_rows"], 0)
        self.assertEqual(report["students_with_valid_paper_evidence"], 0)

    def test_genuine_prior_quiz_and_later_paper_produce_one_eligible_snapshot(self):
        connection = self._connect()
        self._seed_database(connection)
        connection.execute("INSERT INTO students (id) VALUES (11)")
        connection.execute("INSERT INTO classes (id) VALUES (7)")
        connection.execute("INSERT INTO subjects (id) VALUES (1)")
        connection.execute(
            "INSERT INTO paper_assessments (id, class_id, subject, assessment_date, max_marks, is_published) VALUES (1, 7, 'Math', '2024-03-01', 100, 1)"
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores (assessment_id, student_id, marks_obtained, is_absent, created_at, updated_at) VALUES (1, 11, 72, 0, '2024-03-01T08:00:00', '2024-03-01T08:00:00')"
        )
        connection.execute("INSERT INTO quiz_sessions (id, class_id, student_id) VALUES (1, 7, 11)")
        connection.execute("INSERT INTO quizzes (id, subject) VALUES (1, 'Math')")
        connection.execute(
            "INSERT INTO quiz_results (id, quiz_id, quiz_session_id, student_id, score, total_questions, created_at) VALUES (1, 1, 1, 11, 8, 10, '2024-02-01T09:00:00')"
        )
        connection.commit()

        report = build_admin_training_readiness_report(connection)
        self.assertEqual(report["source_evidence"]["quiz_attempts"], 1)
        self.assertEqual(report["source_evidence"]["valid_scored_paper_rows"], 1)
        self.assertEqual(report["source_evidence"]["distinct_scored_paper_dates"], 1)
        self.assertEqual(report["source_evidence"]["subjects_with_academic_evidence"], 1)
        self.assertEqual(report["source_evidence"]["classes_with_academic_evidence"], 1)
        self.assertEqual(report["progress"]["eligible_snapshots"]["current"], 1)

    def test_source_evidence_response_contains_no_individual_identity_fields(self):
        connection = self._connect()
        self._seed_database(connection)
        report = build_admin_training_readiness_report(connection)
        forbidden = {
            "student_id", "user_id", "teacher_user_id", "student_name", "full_name",
            "username", "email", "marks_obtained", "features", "feature_vector",
        }
        self.assertTrue(forbidden.isdisjoint(report["source_evidence"]))
        self.assertTrue(all(isinstance(value, int) for value in report["source_evidence"].values()))

    def test_temporal_split_keeps_train_dates_strictly_before_validation_dates(self):
        split = _temporal_split(self._readiness_dataset())
        self.assertTrue(split["split_ready"])
        self.assertLess(max(split["train_dates"]), min(split["validation_dates"]))

    def test_temporal_split_has_no_date_overlap(self):
        split = _temporal_split(self._readiness_dataset())
        self.assertTrue(split["split_ready"])
        self.assertSetEqual(set(split["train_dates"]) & set(split["validation_dates"]), set())

    def test_temporal_split_keeps_whole_target_dates_together(self):
        dataset = self._readiness_dataset()
        split = _temporal_split(dataset)
        self.assertTrue(split["split_ready"])
        self.assertEqual(len(split["train"]) + len(split["validation"]), len(dataset))
        for target_date, date_rows in dataset.groupby("target_assessment_date"):
            in_train = date_rows.index.isin(split["train"].index).all()
            in_validation = date_rows.index.isin(split["validation"].index).all()
            self.assertNotEqual(in_train, in_validation, target_date)

    def test_temporal_split_enforces_minimum_validation_rows(self):
        split = _temporal_split(self._readiness_dataset(), min_validation_rows=121)
        self.assertFalse(split["split_ready"])
        self.assertIn("below minimum required threshold (121)", split["reason"])

    def test_temporal_split_enforces_minimum_validation_students(self):
        split = _temporal_split(self._readiness_dataset(), min_validation_students=31)
        self.assertFalse(split["split_ready"])
        self.assertIn("below minimum required threshold (31)", split["reason"])

    def test_temporal_split_is_deterministic(self):
        dataset = self._readiness_dataset()
        first = _temporal_split(dataset)
        second = _temporal_split(dataset)
        self.assertEqual(first["train_dates"], second["train_dates"])
        self.assertEqual(first["validation_dates"], second["validation_dates"])
        self.assertEqual(first["train"].index.tolist(), second["train"].index.tolist())
        self.assertEqual(first["validation"].index.tolist(), second["validation"].index.tolist())

    def test_baseline_candidates_include_all_required_estimators(self):
        from sklearn.dummy import DummyRegressor
        from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        candidates = {name: estimator for name, estimator, _ in _candidate_models()}
        self.assertSetEqual(
            set(candidates),
            {"DummyRegressor", "Ridge", "RandomForestRegressor", "GradientBoostingRegressor"},
        )
        self.assertIsInstance(candidates["DummyRegressor"], DummyRegressor)
        self.assertIsInstance(candidates["Ridge"], Pipeline)
        self.assertIsInstance(candidates["Ridge"].named_steps["standardscaler"], StandardScaler)
        self.assertIsInstance(candidates["Ridge"].named_steps["ridge"], Ridge)
        self.assertIsInstance(candidates["RandomForestRegressor"], RandomForestRegressor)
        self.assertIsInstance(candidates["GradientBoostingRegressor"], GradientBoostingRegressor)

    def test_baseline_models_use_the_same_temporal_split(self):
        class RecordingEstimator:
            def __init__(self):
                self.fit_columns = None
                self.fit_indices = None
                self.predict_columns = None
                self.predict_indices = None

            def fit(self, features, target):
                self.fit_columns = list(features.columns)
                self.fit_indices = features.index.tolist()
                return self

            def predict(self, features):
                self.predict_columns = list(features.columns)
                self.predict_indices = features.index.tolist()
                return [60.0] * len(features)

        split = _temporal_split(self._readiness_dataset())
        estimators = [RecordingEstimator() for _ in range(4)]
        candidates = [
            ("DummyRegressor" if index == 0 else f"candidate_{index}", estimator, {})
            for index, estimator in enumerate(estimators)
        ]
        with patch("ai.ml.production.training_readiness._candidate_models", return_value=candidates):
            _evaluate_models(split["train"], split["validation"])

        for estimator in estimators:
            self.assertEqual(estimator.fit_indices, split["train"].index.tolist())
            self.assertEqual(estimator.predict_indices, split["validation"].index.tolist())

    def test_baseline_reports_mae_rmse_r2_and_improvement_vs_dummy(self):
        split = _temporal_split(self._readiness_dataset())
        report = _evaluate_models(split["train"], split["validation"])
        self.assertEqual(report["status"], "evaluated")
        self.assertEqual(len(report["models"]), 4)
        dummy_mae = next(model["mae"] for model in report["models"] if model["model_name"] == "DummyRegressor")
        for model in report["models"]:
            self.assertIn("mae", model)
            self.assertIn("rmse", model)
            self.assertIn("r2", model)
            self.assertIn("mae_improvement_vs_dummy", model)
            expected_improvement = 0.0 if dummy_mae == 0 else round(dummy_mae - model["mae"], 4)
            self.assertEqual(model["mae_improvement_vs_dummy"], expected_improvement)

    def test_estimators_receive_only_ordered_model_features(self):
        class RecordingEstimator:
            def __init__(self):
                self.fit_columns = None
                self.predict_columns = None

            def fit(self, features, target):
                self.fit_columns = list(features.columns)
                return self

            def predict(self, features):
                self.predict_columns = list(features.columns)
                return [60.0] * len(features)

        split = _temporal_split(self._readiness_dataset())
        estimators = [RecordingEstimator() for _ in range(4)]
        candidates = [
            ("DummyRegressor" if index == 0 else f"candidate_{index}", estimator, {})
            for index, estimator in enumerate(estimators)
        ]
        with patch("ai.ml.production.training_readiness._candidate_models", return_value=candidates):
            _evaluate_models(split["train"], split["validation"])

        forbidden_columns = {
            "student_id", "subject", "target_percent", "target_marks_obtained",
            "target_max_marks", "target_assessment_id", "target_assessment_date",
            "target_class_id", "eligible_for_prediction", "ineligible_reason",
        }
        for estimator in estimators:
            self.assertEqual(estimator.fit_columns, MODEL_FEATURE_COLUMNS)
            self.assertEqual(estimator.predict_columns, MODEL_FEATURE_COLUMNS)
            self.assertTrue(forbidden_columns.isdisjoint(estimator.fit_columns))
            self.assertTrue(forbidden_columns.isdisjoint(estimator.predict_columns))

    def test_repeated_evaluation_reproduces_split_metrics_and_report_metadata(self):
        dataset = self._readiness_dataset()
        first = evaluate_training_dataset(dataset)
        second = evaluate_training_dataset(dataset)

        self.assertEqual(first["TRAINING_READINESS_VERSION"], second["TRAINING_READINESS_VERSION"])
        self.assertEqual(first["FEATURE_CONTRACT_VERSION"], second["FEATURE_CONTRACT_VERSION"])
        for key in ("python_version", "pandas_version", "sklearn_version", "split_strategy",
                    "training_date_range", "validation_date_range", "model_parameters", "feature_names"):
            self.assertEqual(first["reproducibility"][key], second["reproducibility"][key])
        self.assertEqual(first["reproducibility"]["python_version"], __import__("sys").version.split()[0])
        self.assertEqual(first["reproducibility"]["pandas_version"], pd.__version__)
        self.assertIsNotNone(first["reproducibility"]["sklearn_version"])
        self.assertEqual(first["reproducibility"]["feature_names"], MODEL_FEATURE_COLUMNS)
        self.assertTrue(first["reproducibility"]["evaluation_timestamp"].endswith("Z"))
        self.assertEqual(first["eligible_training_snapshots"], second["eligible_training_snapshots"])
        self.assertEqual(first["unique_students"], second["unique_students"])
        self.assertEqual(first["unique_target_dates"], second["unique_target_dates"])
        first_models = first["baseline_evaluation"]["models"]
        second_models = second["baseline_evaluation"]["models"]
        self.assertEqual([model["model_name"] for model in first_models], [model["model_name"] for model in second_models])
        self.assertEqual(first_models, second_models)

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

        changes_before = connection.total_changes
        report = generate_diagnostics(connection)
        self.assertEqual(connection.total_changes, changes_before)
        self.assertEqual(report["paper_assessments"], 2)
        self.assertEqual(report["usable_target_rows"], 2)
        self.assertEqual(report["targets_with_academic_evidence"], 2)
        self.assertEqual(report["targets_with_quiz_evidence"], 2)
        self.assertEqual(report["targets_with_prior_paper_evidence"], 1)
        self.assertEqual(report["targets_with_attendance_evidence"], 2)
        self.assertEqual(report["eligible_feature_snapshots"], 2)
        self.assertEqual(report["ineligible_feature_snapshots"], 0)
        self.assertEqual(report["ineligible_reason_counts"], {})
        self.assertEqual(report["students_with_evidence"], 1)
        self.assertEqual(report["unique_eligible_students"], 1)
        self.assertEqual(report["snapshots_per_eligible_student"], {"11": 2})
        self.assertEqual(report["subjects_represented"], ["Math"])
        self.assertEqual(report["classes_represented"], [7])
        self.assertEqual(report["eligible_snapshots_by_subject"], {"Math": 2})
        self.assertEqual(report["eligible_snapshots_by_class"], {"7": 2})
        self.assertEqual(report["evidence_presence_counts"], {"quiz": 2, "prior_paper": 1, "attendance": 2})
        self.assertEqual(report["readiness_level"], "DATA AVAILABLE; REVIEW DIVERSITY")
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
        root = repository_root()
        self.assertTrue((root / ".env.example").is_file())
        self.assertTrue((root / "backend").is_dir())
        self.assertTrue((root / "ai").is_dir())

    def test_model_feature_order_is_deterministic(self):
        connection = self._connect()
        self._seed_database(connection)
        self.assertEqual(
            list(build_training_dataset(connection).columns),
            OUTPUT_COLUMNS,
        )


if __name__ == "__main__":
    unittest.main()
