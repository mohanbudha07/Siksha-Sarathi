import sqlite3
import unittest
from types import SimpleNamespace

from backend.ml_prediction_audit import normalize_audit_subject, record_prediction_audit
from ai.ml.production.model_monitoring import (
    MODEL_MONITORING_VERSION,
    build_model_monitoring_report,
    summarize_monitoring_status,
)


class ModelMonitoringTests(unittest.TestCase):
    def test_monitoring_reports_no_model_without_fabricating_metrics(self):
        report = build_model_monitoring_report(None)
        self.assertEqual(report["status"], "model_unavailable")
        self.assertFalse(report["available"])
        self.assertFalse(report["model_loaded"])
        self.assertEqual(report["monitoring_version"], MODEL_MONITORING_VERSION)
        self.assertIn("no validated production artifact", report["reason"])
        self.assertFalse(report["retraining_required"])
        self.assertEqual(report["validation_metrics"], {})

    def test_monitoring_uses_real_manifest_metadata_when_artifact_exists(self):
        result = SimpleNamespace(
            available=True,
            status="prediction_available",
            manifest={
                "artifact_version": "v-monitor-1",
                "model_type": "gradient_boosting",
                "feature_contract_version": "1",
                "training_timestamp": "2026-09-01T00:00:00+00:00",
                "validation_metrics": {"mae": 12.1, "rmse": 18.7},
            },
        )
        report = build_model_monitoring_report(result, as_of_date="2026-09-26")
        self.assertTrue(report["available"])
        self.assertEqual(report["artifact_version"], "v-monitor-1")
        self.assertEqual(report["model_type"], "gradient_boosting")
        self.assertEqual(report["validation_metrics"], {"mae": 12.1, "rmse": 18.7})
        self.assertIn("staleness_days", report)

    def test_monitoring_summary_rejects_fake_positive_readiness(self):
        summary = summarize_monitoring_status(
            None,
            monitored_metrics={"accuracy": 0.99, "drift": 0.01},
        )
        self.assertEqual(summary["status"], "model_unavailable")
        self.assertFalse(summary["retraining_required"])
        self.assertEqual(summary["validation_metrics"], {})

    def test_prediction_available_records_audit(self):
        db = sqlite3.connect(":memory:")
        db.execute(
            """
            CREATE TABLE ml_prediction_audits (
                id INTEGER PRIMARY KEY,
                student_id INTEGER NOT NULL,
                teacher_user_id INTEGER NOT NULL,
                class_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                prediction_status TEXT NOT NULL,
                prediction_percent REAL,
                fallback TEXT,
                reason TEXT,
                model_version TEXT,
                model_type TEXT,
                artifact_version TEXT,
                feature_contract_version TEXT,
                validation_mae REAL,
                model_training_timestamp TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, class_id, subject, as_of_date, model_version)
            )
            """
        )
        result = record_prediction_audit(
            db,
            teacher_user_id=2,
            student_id=1,
            class_id=1,
            subject=" Science ",
            as_of_date="2026-09-26",
            prediction_result={
                "status": "prediction_available",
                "prediction_percent": 72.5,
                "fallback": None,
                "reason": None,
            },
            validated_manifest={
                "artifact_version": "v-1",
                "model_type": "gradient_boosting",
                "feature_contract_version": "1",
                "validation_metrics": {"mae": 8.2},
                "training_timestamp": "2026-09-01T00:00:00+00:00",
            },
            model_version="v-1",
        )
        self.assertTrue(result["recorded"])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM ml_prediction_audits").fetchone()[0], 1)

    def test_repeated_same_forecast_is_idempotent(self):
        db = sqlite3.connect(":memory:")
        db.execute(
            """
            CREATE TABLE ml_prediction_audits (
                id INTEGER PRIMARY KEY,
                student_id INTEGER NOT NULL,
                teacher_user_id INTEGER NOT NULL,
                class_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                prediction_status TEXT NOT NULL,
                prediction_percent REAL,
                fallback TEXT,
                reason TEXT,
                model_version TEXT NOT NULL,
                model_type TEXT,
                artifact_version TEXT,
                feature_contract_version TEXT,
                validation_mae REAL,
                model_training_timestamp TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, class_id, subject, as_of_date, model_version)
            )
            """
        )
        first = record_prediction_audit(
            db, 2, 1, 1, "Science", "2026-09-26",
            {"status": "prediction_available", "prediction_percent": 72.0, "fallback": None, "reason": None},
            {"artifact_version": "v-1", "model_type": "gradient_boosting", "feature_contract_version": "1", "validation_metrics": {"mae": 8.2}, "training_timestamp": "2026-09-01T00:00:00+00:00"},
            model_version="v-1",
        )
        second = record_prediction_audit(
            db, 2, 1, 1, "SCIENCE", "2026-09-26",
            {"status": "prediction_available", "prediction_percent": 81.0, "fallback": None, "reason": None},
            {"artifact_version": "v-1", "model_type": "gradient_boosting", "feature_contract_version": "1", "validation_metrics": {"mae": 8.2}, "training_timestamp": "2026-09-01T00:00:00+00:00"},
            model_version="v-1",
        )
        self.assertTrue(first["recorded"])
        self.assertFalse(second["recorded"])
        row = db.execute("SELECT prediction_percent FROM ml_prediction_audits WHERE student_id = 1 AND class_id = 1 AND subject = 'science' AND as_of_date = '2026-09-26' AND model_version = 'v-1'").fetchone()
        self.assertEqual(row[0], 72.0)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM ml_prediction_audits").fetchone()[0], 1)

    def test_subject_normalization_prevents_duplicate_audits(self):
        self.assertEqual(normalize_audit_subject(" science "), "science")
        self.assertEqual(normalize_audit_subject("SCIENCE"), "science")

    def test_model_unavailable_does_not_record_audit(self):
        db = sqlite3.connect(":memory:")
        db.execute(
            "CREATE TABLE ml_prediction_audits (id INTEGER PRIMARY KEY, student_id INTEGER, teacher_user_id INTEGER, class_id INTEGER, subject TEXT, as_of_date TEXT, prediction_status TEXT, prediction_percent REAL, fallback TEXT, reason TEXT, model_version TEXT, model_type TEXT, artifact_version TEXT, feature_contract_version TEXT, validation_mae REAL, model_training_timestamp TEXT)"
        )
        result = record_prediction_audit(
            db, 2, 1, 1, "Science", "2026-09-26",
            {"status": "model_unavailable", "prediction_percent": None, "fallback": "observed_analytics", "reason": "no model"},
            {"artifact_version": "v-1", "model_type": "gradient_boosting", "feature_contract_version": "1", "validation_metrics": {"mae": 8.2}, "training_timestamp": "2026-09-01T00:00:00+00:00"},
            model_version="v-1",
        )
        self.assertFalse(result["recorded"])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM ml_prediction_audits").fetchone()[0], 0)

    def test_insufficient_evidence_does_not_record_audit(self):
        db = sqlite3.connect(":memory:")
        db.execute(
            "CREATE TABLE ml_prediction_audits (id INTEGER PRIMARY KEY, student_id INTEGER, teacher_user_id INTEGER, class_id INTEGER, subject TEXT, as_of_date TEXT, prediction_status TEXT, prediction_percent REAL, fallback TEXT, reason TEXT, model_version TEXT, model_type TEXT, artifact_version TEXT, feature_contract_version TEXT, validation_mae REAL, model_training_timestamp TEXT)"
        )
        result = record_prediction_audit(
            db, 2, 1, 1, "Science", "2026-09-26",
            {"status": "insufficient_evidence", "prediction_percent": None, "fallback": "observed_analytics", "reason": "not enough data"},
            {"artifact_version": "v-1", "model_type": "gradient_boosting", "feature_contract_version": "1", "validation_metrics": {"mae": 8.2}, "training_timestamp": "2026-09-01T00:00:00+00:00"},
            model_version="v-1",
        )
        self.assertFalse(result["recorded"])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM ml_prediction_audits").fetchone()[0], 0)

    def test_prediction_invalid_does_not_record_audit(self):
        db = sqlite3.connect(":memory:")
        db.execute(
            "CREATE TABLE ml_prediction_audits (id INTEGER PRIMARY KEY, student_id INTEGER, teacher_user_id INTEGER, class_id INTEGER, subject TEXT, as_of_date TEXT, prediction_status TEXT, prediction_percent REAL, fallback TEXT, reason TEXT, model_version TEXT, model_type TEXT, artifact_version TEXT, feature_contract_version TEXT, validation_mae REAL, model_training_timestamp TEXT)"
        )
        result = record_prediction_audit(
            db, 2, 1, 1, "Science", "2026-09-26",
            {"status": "prediction_invalid", "prediction_percent": None, "fallback": "observed_analytics", "reason": "bad model output"},
            {"artifact_version": "v-1", "model_type": "gradient_boosting", "feature_contract_version": "1", "validation_metrics": {"mae": 8.2}, "training_timestamp": "2026-09-01T00:00:00+00:00"},
            model_version="v-1",
        )
        self.assertFalse(result["recorded"])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM ml_prediction_audits").fetchone()[0], 0)

    def test_invalid_prediction_percent_does_not_record_audit(self):
        db = sqlite3.connect(":memory:")
        db.execute(
            "CREATE TABLE ml_prediction_audits (id INTEGER PRIMARY KEY, student_id INTEGER, teacher_user_id INTEGER, class_id INTEGER, subject TEXT, as_of_date TEXT, prediction_status TEXT, prediction_percent REAL, fallback TEXT, reason TEXT, model_version TEXT, model_type TEXT, artifact_version TEXT, feature_contract_version TEXT, validation_mae REAL, model_training_timestamp TEXT)"
        )
        result = record_prediction_audit(
            db, 2, 1, 1, "Science", "2026-09-26",
            {"status": "prediction_available", "prediction_percent": 101.0, "fallback": None, "reason": None},
            {"artifact_version": "v-1", "model_type": "gradient_boosting", "feature_contract_version": "1", "validation_metrics": {"mae": 8.2}, "training_timestamp": "2026-09-01T00:00:00+00:00"},
            model_version="v-1",
        )
        self.assertFalse(result["recorded"])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM ml_prediction_audits").fetchone()[0], 0)

    def test_audit_contains_safe_model_metadata(self):
        db = sqlite3.connect(":memory:")
        db.execute(
            "CREATE TABLE ml_prediction_audits (id INTEGER PRIMARY KEY, student_id INTEGER, teacher_user_id INTEGER, class_id INTEGER, subject TEXT, as_of_date TEXT, prediction_status TEXT, prediction_percent REAL, fallback TEXT, reason TEXT, model_version TEXT, model_type TEXT, artifact_version TEXT, feature_contract_version TEXT, validation_mae REAL, model_training_timestamp TEXT)"
        )
        result = record_prediction_audit(
            db, 2, 1, 1, "Science", "2026-09-26",
            {"status": "prediction_available", "prediction_percent": 72.5, "fallback": None, "reason": None},
            {"artifact_version": "v-1", "model_type": "gradient_boosting", "feature_contract_version": "1", "validation_metrics": {"mae": 8.2}, "training_timestamp": "2026-09-01T00:00:00+00:00"},
            model_version="v-1",
        )
        row = db.execute("SELECT prediction_percent, model_version, model_type, artifact_version, feature_contract_version, validation_mae, model_training_timestamp, subject FROM ml_prediction_audits").fetchone()
        self.assertEqual(row[0], 72.5)
        self.assertEqual(row[1], "v-1")
        self.assertEqual(row[2], "gradient_boosting")
        self.assertEqual(row[3], "v-1")
        self.assertEqual(row[4], "1")
        self.assertEqual(row[5], 8.2)
        self.assertEqual(row[6], "2026-09-01T00:00:00+00:00")
        self.assertEqual(row[7], "science")
        self.assertTrue(result["recorded"])

    def test_audit_does_not_store_raw_features(self):
        db = sqlite3.connect(":memory:")
        db.execute(
            "CREATE TABLE ml_prediction_audits (id INTEGER PRIMARY KEY, student_id INTEGER, teacher_user_id INTEGER, class_id INTEGER, subject TEXT, as_of_date TEXT, prediction_status TEXT, prediction_percent REAL, fallback TEXT, reason TEXT, model_version TEXT, model_type TEXT, artifact_version TEXT, feature_contract_version TEXT, validation_mae REAL, model_training_timestamp TEXT)"
        )
        record_prediction_audit(
            db, 2, 1, 1, "Science", "2026-09-26",
            {"status": "prediction_available", "prediction_percent": 72.5, "fallback": None, "reason": None},
            {"artifact_version": "v-1", "model_type": "gradient_boosting", "feature_contract_version": "1", "validation_metrics": {"mae": 8.2}, "training_timestamp": "2026-09-01T00:00:00+00:00"},
            model_version="v-1",
        )
        row = db.execute("SELECT * FROM ml_prediction_audits").fetchone()
        self.assertIsNotNone(row)
        columns = [column[0] for column in db.execute("PRAGMA table_info(ml_prediction_audits)").fetchall()]
        self.assertNotIn("raw_features", columns)
        self.assertNotIn("evidence_json", columns)

    def test_monitoring_summary_rejects_fake_positive_readiness(self):
        summary = summarize_monitoring_status(
            None,
            monitored_metrics={"accuracy": 0.99, "drift": 0.01},
        )
        self.assertEqual(summary["status"], "model_unavailable")
        self.assertFalse(summary["retraining_required"])
        self.assertEqual(summary["validation_metrics"], {})


if __name__ == "__main__":
    unittest.main()
