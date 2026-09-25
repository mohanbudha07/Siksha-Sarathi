import hashlib
import json
import math
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np

from ai.ml.production.artifact_loader import (
    ARTIFACT_CORRUPT,
    ARTIFACT_FILE_MISSING,
    ARTIFACT_INCOMPATIBLE,
    ARTIFACT_MANIFEST_MISSING,
    ModelLoadResult,
    ProductionArtifactLoader,
)
from ai.ml.production.feature_contract import FEATURE_CONTRACT_VERSION, MODEL_FEATURE_COLUMNS, TARGET_COLUMN
from ai.ml.production.prediction_service import (
    INSUFFICIENT_EVIDENCE,
    MODEL_UNAVAILABLE,
    PREDICTION_AVAILABLE,
    PREDICTION_INVALID,
    PredictionService,
)
from ai.ml.production.feature_builder import build_live_feature_row


class StubModel:
    def __init__(self, prediction):
        self.prediction = prediction
        self.received_columns = None

    def predict(self, frame):
        self.received_columns = list(frame.columns)
        return [self.prediction]


class StubLoader:
    def __init__(self, model, manifest=None):
        self.result = ModelLoadResult(
            status=PREDICTION_AVAILABLE,
            model=model,
            manifest=manifest or valid_manifest(),
        )

    def load(self):
        return self.result


def valid_manifest(**overrides):
    manifest = {
        "artifact_version": "test-model-1",
        "model_type": "test-stub",
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "feature_names": list(MODEL_FEATURE_COLUMNS),
        "target_name": TARGET_COLUMN,
        "target_unit": "percentage / 0-100 paper-assessment score",
        "training_timestamp": "2026-01-01T00:00:00+00:00",
        "training_data_source": "test fixture only",
        "training_row_count": 1,
        "unique_student_count": 1,
        "validation_strategy": "test fixture",
        "primary_metric": "MAE",
        "validation_metrics": {"mae": 1.0},
        "model_file": "model.joblib",
        "checksum_sha256": "0" * 64,
    }
    manifest.update(overrides)
    return manifest


class ProductionRuntimeTests(unittest.TestCase):
    @staticmethod
    def _connect():
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        return connection

    def _seed_database(self, connection):
        connection.executescript(
            """
            CREATE TABLE paper_assessments (
                id INTEGER PRIMARY KEY,
                class_id INTEGER,
                subject TEXT,
                assessment_date TEXT,
                max_marks REAL,
                is_published INTEGER
            );
            CREATE TABLE paper_assessment_scores (
                assessment_id INTEGER,
                student_id INTEGER,
                marks_obtained REAL,
                is_absent INTEGER,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE quiz_sessions (id INTEGER PRIMARY KEY, class_id INTEGER, student_id INTEGER);
            CREATE TABLE quizzes (id INTEGER PRIMARY KEY, subject TEXT);
            CREATE TABLE quiz_results (
                id INTEGER PRIMARY KEY,
                quiz_id INTEGER,
                quiz_session_id INTEGER,
                student_id INTEGER,
                score REAL,
                total_questions INTEGER,
                created_at TEXT
            );
            CREATE TABLE quiz_answer_results (
                id INTEGER PRIMARY KEY,
                quiz_result_id INTEGER,
                is_correct INTEGER,
                is_skipped INTEGER,
                created_at TEXT
            );
            CREATE TABLE monthly_attendance_summaries (
                id INTEGER PRIMARY KEY,
                class_id INTEGER,
                attendance_month TEXT,
                total_school_days INTEGER,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE monthly_attendance_records (
                summary_id INTEGER,
                student_id INTEGER,
                present_days INTEGER,
                created_at TEXT,
                updated_at TEXT
            );
            """
        )

    def _add_quiz(self, connection, quiz_id=1, result_id=1, student_id=11, subject="Math", created_at="2024-02-01T09:00:00"):
        connection.execute("INSERT INTO quiz_sessions VALUES (?, ?, ?)", (quiz_id, 7, student_id))
        connection.execute("INSERT INTO quizzes VALUES (?, ?)", (quiz_id, subject))
        connection.execute(
            "INSERT INTO quiz_results VALUES (?, ?, ?, ?, ?, ?, ?)",
            (result_id, quiz_id, quiz_id, student_id, 8, 10, created_at),
        )
        connection.execute(
            "INSERT INTO quiz_answer_results VALUES (?, ?, ?, ?, ?)",
            (result_id, result_id, 1, 0, created_at),
        )

    def _add_paper(self, connection, assessment_id, student_id=11, subject="Math", assessment_date="2024-02-01", created_at="2024-02-01T08:00:00"):
        connection.execute(
            "INSERT INTO paper_assessments VALUES (?, ?, ?, ?, ?, ?)",
            (assessment_id, 7, subject, assessment_date, 100, 1),
        )
        connection.execute(
            "INSERT INTO paper_assessment_scores VALUES (?, ?, ?, ?, ?, ?)",
            (assessment_id, student_id, 70, 0, created_at, created_at),
        )

    def _add_attendance(self, connection, student_id=11, month="2024-02-01"):
        connection.execute(
            "INSERT INTO monthly_attendance_summaries VALUES (?, ?, ?, ?, ?, ?)",
            (1, 7, month, 20, month, month),
        )
        connection.execute(
            "INSERT INTO monthly_attendance_records VALUES (?, ?, ?, ?, ?)",
            (1, student_id, 18, month, month),
        )

    def _eligible_connection(self):
        connection = self._connect()
        self._seed_database(connection)
        self._add_quiz(connection)
        connection.commit()
        return connection

    def test_missing_production_artifact_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            result = ProductionArtifactLoader(directory).load()
        self.assertEqual(result.status, ARTIFACT_MANIFEST_MISSING)
        self.assertIsNone(result.model)

    def test_missing_manifest_and_missing_artifact_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(valid_manifest()))
            result = ProductionArtifactLoader(directory).load()
        self.assertEqual(result.status, ARTIFACT_FILE_MISSING)

    def test_manifest_version_and_feature_order_are_validated(self):
        for overrides, expected in (
            ({"feature_contract_version": "wrong"}, ARTIFACT_INCOMPATIBLE),
            ({"feature_names": list(reversed(MODEL_FEATURE_COLUMNS))}, ARTIFACT_INCOMPATIBLE),
            ({"target_name": "wrong_target"}, ARTIFACT_INCOMPATIBLE),
        ):
            with self.subTest(overrides=overrides):
                with tempfile.TemporaryDirectory() as directory:
                    Path(directory, "manifest.json").write_text(json.dumps(valid_manifest(**overrides)))
                    result = ProductionArtifactLoader(directory).load()
                self.assertEqual(result.status, expected)

    def test_missing_and_malformed_checksums_are_incompatible(self):
        for checksum in (None, "not-a-sha256"):
            with self.subTest(checksum=checksum):
                with tempfile.TemporaryDirectory() as directory:
                    manifest = valid_manifest()
                    if checksum is None:
                        del manifest["checksum_sha256"]
                    else:
                        manifest["checksum_sha256"] = checksum
                    Path(directory, "manifest.json").write_text(json.dumps(manifest))
                    result = ProductionArtifactLoader(directory).load()
                self.assertEqual(result.status, ARTIFACT_INCOMPATIBLE)

    def test_checksum_is_verified_before_deserialization(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory, "model.joblib")
            model_path.write_bytes(b"untrusted bytes")
            Path(directory, "manifest.json").write_text(json.dumps(valid_manifest()))
            with patch("ai.ml.production.artifact_loader.joblib.load") as load:
                result = ProductionArtifactLoader(directory).load()
            self.assertEqual(result.status, ARTIFACT_CORRUPT)
            load.assert_not_called()

    def test_absolute_and_traversal_model_paths_are_rejected(self):
        for model_file in ("/tmp/model.joblib", "../model.joblib"):
            with self.subTest(model_file=model_file):
                with tempfile.TemporaryDirectory() as directory:
                    Path(directory, "manifest.json").write_text(
                        json.dumps(valid_manifest(model_file=model_file))
                    )
                    result = ProductionArtifactLoader(directory).load()
                self.assertEqual(result.status, ARTIFACT_INCOMPATIBLE)

    def test_corrupt_model_and_checksum_mismatch_are_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory, "model.joblib")
            model_path.write_bytes(b"not a joblib model")
            Path(directory, "manifest.json").write_text(json.dumps(valid_manifest()))
            result = ProductionArtifactLoader(directory).load()
            self.assertEqual(result.status, ARTIFACT_CORRUPT)

        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory, "model.joblib")
            joblib.dump(StubModel(70), model_path)
            manifest = valid_manifest(checksum_sha256="0" * 64)
            Path(directory, "manifest.json").write_text(json.dumps(manifest))
            result = ProductionArtifactLoader(directory).load()
            self.assertEqual(result.status, ARTIFACT_CORRUPT)

    def test_legacy_artifact_is_never_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            joblib.dump(StubModel(70), Path(directory, "performance_model.pkl"))
            result = ProductionArtifactLoader(directory).load()
        self.assertEqual(result.status, ARTIFACT_MANIFEST_MISSING)

    def test_live_features_are_ordered_and_target_free(self):
        connection = self._eligible_connection()
        before = connection.total_changes
        row = build_live_feature_row(connection, 11, 7, "Math", "2024-02-15")
        self.assertEqual(row["feature_names"], MODEL_FEATURE_COLUMNS)
        self.assertEqual(list(row["features"]), MODEL_FEATURE_COLUMNS)
        self.assertTrue(row["eligible_for_prediction"])
        self.assertEqual(row["evidence"]["academic_evidence_count"], 1)
        self.assertEqual(connection.total_changes, before)

    def test_insufficient_academic_evidence_returns_fallback(self):
        connection = self._connect()
        self._seed_database(connection)
        self._add_attendance(connection)
        connection.commit()
        result = PredictionService(StubLoader(StubModel(70))).predict(connection, 11, 7, "Math", "2024-02-15")
        self.assertEqual(result["status"], INSUFFICIENT_EVIDENCE)
        self.assertEqual(result["fallback"], "observed_analytics")

    def test_future_quiz_paper_attendance_and_other_scope_are_excluded(self):
        connection = self._connect()
        self._seed_database(connection)
        self._add_quiz(connection, created_at="2024-02-16T09:00:00")
        self._add_quiz(connection, quiz_id=2, result_id=2, student_id=12, subject="Math", created_at="2024-02-01T09:00:00")
        self._add_quiz(connection, quiz_id=3, result_id=3, student_id=11, subject="Science", created_at="2024-02-01T09:00:00")
        self._add_paper(connection, 1, assessment_date="2024-02-16", created_at="2024-02-16T08:00:00")
        self._add_attendance(connection, month="2024-02-16")
        connection.commit()
        result = PredictionService(StubLoader(StubModel(70))).predict(connection, 11, 7, "Math", "2024-02-15")
        self.assertEqual(result["status"], INSUFFICIENT_EVIDENCE)

    def test_quiz_on_cutoff_date_is_excluded(self):
        connection = self._connect()
        self._seed_database(connection)
        self._add_quiz(connection, created_at="2024-02-15T09:00:00")
        connection.commit()
        result = build_live_feature_row(connection, 11, 7, "Math", "2024-02-15")
        self.assertFalse(result["eligible_for_prediction"])
        self.assertEqual(result["evidence"]["academic_evidence_count"], 0)

    def test_paper_on_cutoff_date_is_excluded(self):
        connection = self._connect()
        self._seed_database(connection)
        self._add_paper(connection, 1, assessment_date="2024-02-15", created_at="2024-02-01T08:00:00")
        connection.commit()
        result = build_live_feature_row(connection, 11, 7, "Math", "2024-02-15")
        self.assertFalse(result["eligible_for_prediction"])
        self.assertEqual(result["evidence"]["academic_evidence_count"], 0)

    def test_attendance_on_cutoff_date_is_excluded(self):
        connection = self._connect()
        self._seed_database(connection)
        self._add_attendance(connection, month="2024-02-15")
        connection.commit()
        result = build_live_feature_row(connection, 11, 7, "Math", "2024-02-15")
        self.assertFalse(result["eligible_for_prediction"])
        self.assertEqual(result["evidence"]["has_attendance_evidence"], 0)

    def test_valid_stub_model_produces_prediction_with_exact_schema(self):
        connection = self._eligible_connection()
        model = StubModel(72.5)
        result = PredictionService(StubLoader(model)).predict(connection, 11, 7, "Math", "2024-02-15")
        self.assertEqual(result["status"], PREDICTION_AVAILABLE)
        self.assertEqual(result["prediction_percent"], 72.5)
        self.assertEqual(model.received_columns, MODEL_FEATURE_COLUMNS)
        self.assertEqual(result["feature_contract_version"], FEATURE_CONTRACT_VERSION)

    def test_invalid_predictions_fall_back(self):
        connection = self._eligible_connection()
        for value in ("not numeric", math.nan, math.inf, -1, 101):
            with self.subTest(value=value):
                result = PredictionService(StubLoader(StubModel(value))).predict(
                    connection, 11, 7, "Math", "2024-02-15"
                )
                self.assertEqual(result["status"], PREDICTION_INVALID)
                self.assertIsNone(result["prediction_percent"])
                self.assertEqual(result["fallback"], "observed_analytics")

    def test_numeric_scalars_and_single_element_arrays_are_accepted(self):
        connection = self._eligible_connection()
        for value in (72, 72.5, np.float32(72.5), [72.5], np.array([72.5])):
            with self.subTest(value=value):
                result = PredictionService(StubLoader(StubModel(value))).predict(
                    connection, 11, 7, "Math", "2024-02-15"
                )
                self.assertEqual(result["status"], PREDICTION_AVAILABLE)
                self.assertEqual(result["prediction_percent"], 72.5 if value != 72 else 72.0)

    def test_empty_multiple_and_boolean_predictions_are_rejected(self):
        connection = self._eligible_connection()
        for value in (None, True, [], [70, 71], np.array([]), np.array([70, 71])):
            with self.subTest(value=value):
                result = PredictionService(StubLoader(StubModel(value))).predict(
                    connection, 11, 7, "Math", "2024-02-15"
                )
                self.assertEqual(result["status"], PREDICTION_INVALID)

    def test_absent_model_does_not_crash_service(self):
        connection = self._eligible_connection()
        with tempfile.TemporaryDirectory() as directory:
            service = PredictionService(ProductionArtifactLoader(directory))
            result = service.predict(connection, 11, 7, "Math", "2024-02-15")
        self.assertEqual(result["status"], "model_unavailable")
        self.assertEqual(result["model_status"], ARTIFACT_MANIFEST_MISSING)
        self.assertEqual(result["fallback"], "observed_analytics")

    def test_loader_cache_and_force_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory, "model.joblib")
            joblib.dump(StubModel(70), model_path)
            manifest = valid_manifest(
                checksum_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest()
            )
            Path(directory, "manifest.json").write_text(json.dumps(manifest))
            loader = ProductionArtifactLoader(directory)
            first = loader.load()
            second = loader.load()
            self.assertIs(first, second)
            loader.reset()
            third = loader.load()
            self.assertIsNot(first, third)


if __name__ == "__main__":
    unittest.main()
