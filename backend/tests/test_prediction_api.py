"""Authorization and privacy tests for the production prediction API."""

from datetime import date
import importlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ai.ml.production.artifact_loader import ProductionArtifactLoader
from ai.ml.production.prediction_service import PredictionService


try:
    fixture = importlib.import_module("test_quiz_statistics")
except ModuleNotFoundError:
    fixture = importlib.import_module("backend.tests.test_quiz_statistics")


class StubPredictionService:
    def __init__(self, result=None, available=False):
        self.result = result or {
            "status": "model_unavailable",
            "prediction_percent": None,
            "fallback": "observed_analytics",
            "reason": "no validated production artifact is available",
            "evidence": {
                "academic_evidence_count": 2,
                "quiz_attempt_count": 1,
                "prior_paper_count": 1,
                "has_quiz_evidence": 1,
                "has_prior_paper_evidence": 1,
                "has_attendance_evidence": 0,
                "raw_features": {"should": "never leak"},
            },
            "internal_path": "/private/model.joblib",
            "checksum_sha256": "private-checksum",
            "manifest": {"private": "metadata"},
        }
        self.calls = []
        self.loader = SimpleNamespace(
            load=lambda: SimpleNamespace(
                available=available,
                status=("prediction_available" if available else "artifact_manifest_missing"),
                manifest=(
                    {
                        "artifact_version": "v-test",
                        "model_type": "stub",
                        "target_name": "target_percent",
                    }
                    if available else None
                ),
            )
        )

    def predict(self, connection, **kwargs):
        self.calls.append({"connection": connection, **kwargs})
        return self.result


class PredictionApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.QuizStatisticsTests.setUpClass()
        cls.backend = fixture.QuizStatisticsTests.backend

    def setUp(self):
        fixture.QuizStatisticsTests.setUp(self)
        self.original_service = self.backend.app.extensions.get("prediction_service")
        self.original_today_provider = self.backend.app.extensions.get(
            "prediction_today_provider"
        )
        self.service = StubPredictionService()
        self.backend.app.extensions["prediction_service"] = self.service
        self.backend.app.extensions["prediction_today_provider"] = lambda: date(2026, 9, 26)
        self.client = self.backend.app.test_client()

    def tearDown(self):
        if self.original_service is not None:
            self.backend.app.extensions["prediction_service"] = self.original_service
        else:
            self.backend.app.extensions.pop("prediction_service", None)
        if self.original_today_provider is not None:
            self.backend.app.extensions["prediction_today_provider"] = self.original_today_provider
        else:
            self.backend.app.extensions.pop("prediction_today_provider", None)
        fixture.QuizStatisticsTests.tearDown(self)

    def login(self, role):
        fixture.QuizStatisticsTests.login(self, role)

    def request_prediction(self, student_id=1, query="subject=Science"):
        return self.client.get(
            f"/api/teacher/students/{student_id}/prediction?{query}"
        )

    def test_teacher_endpoint_authentication_and_roles(self):
        self.login("student")
        self.assertEqual(self.request_prediction().status_code, 403)
        self.login("admin")
        self.assertEqual(self.request_prediction().status_code, 403)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.request_prediction().status_code, 401)
        self.assertEqual(self.service.calls, [])

    def test_password_change_lifecycle_blocks_prediction(self):
        self.login("teacher")
        self.db.execute("UPDATE users SET must_change_password=1 WHERE id=2")
        self.db.commit()
        response = self.request_prediction()
        self.assertEqual(response.status_code, 403)
        self.assertIn("Password change required", response.json["error"])
        self.assertEqual(self.service.calls, [])

    def test_subject_is_required_and_blank_subject_is_rejected(self):
        self.login("teacher")
        for query in ("", "subject=%20%20%20"):
            with self.subTest(query=query):
                self.assertEqual(self.request_prediction(query=query).status_code, 400)
        self.assertEqual(self.service.calls, [])

    def test_date_validation_and_today_or_past_acceptance(self):
        self.login("teacher")
        for query in (
            "subject=Science&as_of_date=2026-9-26",
            "subject=Science&as_of_date=2026-02-30",
            "subject=Science&as_of_date=2026-09-27",
        ):
            with self.subTest(query=query):
                self.assertEqual(self.request_prediction(query=query).status_code, 400)
        for cutoff in ("2026-09-26", "2026-09-25"):
            response = self.request_prediction(
                query=f"subject=Science&as_of_date={cutoff}"
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["as_of_date"], cutoff)
        self.assertEqual(len(self.service.calls), 2)

    def test_omitted_date_uses_injected_nepal_today(self):
        self.login("teacher")
        response = self.request_prediction(query="subject=Science")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["as_of_date"], "2026-09-26")
        self.assertEqual(self.service.calls[0]["as_of_date"], "2026-09-26")

    def test_authorized_scope_uses_canonical_subject_and_server_class(self):
        self.login("teacher")
        changes_before = self.db.total_changes
        response = self.request_prediction(query="subject=%20sCIence%20&as_of_date=2026-09-25")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.service.calls[0]["student_id"], 1)
        self.assertEqual(self.service.calls[0]["class_id"], 1)
        self.assertEqual(self.service.calls[0]["subject"], "Science")
        self.assertEqual(self.service.calls[0]["as_of_date"], "2026-09-25")
        self.assertEqual(self.db.total_changes, changes_before)
        self.assertEqual(response.json["student"], {
            "id": 1,
            "subject": "Science",
            "class_id": 1,
        })

    def test_teacher_cannot_access_unrelated_student_or_unassigned_subject(self):
        self.login("teacher")
        self.db.execute("INSERT INTO subjects VALUES(2,'Mathematics','MATH','2026-01-01')")
        self.db.execute("INSERT INTO teacher_class_subjects VALUES(2,4,2,1,'2026-01-01')")
        self.db.commit()
        self.assertEqual(self.request_prediction(student_id=2).status_code, 404)
        self.assertEqual(self.request_prediction(query="subject=Mathematics").status_code, 404)
        self.assertEqual(self.service.calls, [])

    def test_class_teacher_responsibility_alone_does_not_authorize(self):
        self.login("teacher")
        self.db.execute("DELETE FROM teacher_class_subjects WHERE teacher_user_id=2")
        self.db.commit()
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM class_teacher_assignments WHERE teacher_user_id=2 AND class_id=1"
            ).fetchone()[0],
            1,
        )
        self.assertEqual(self.request_prediction().status_code, 404)
        self.assertEqual(self.service.calls, [])

    def test_client_cannot_override_class_scope(self):
        self.login("teacher")
        response = self.request_prediction(query="subject=Science&class_id=2")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.service.calls, [])

    def test_service_states_return_http_200_without_fake_prediction(self):
        self.login("teacher")
        expected_states = (
            ("model_unavailable", None),
            ("insufficient_evidence", None),
            ("prediction_invalid", None),
            ("prediction_available", 73.5),
        )
        for status, percent in expected_states:
            with self.subTest(status=status):
                self.service.result = {
                    "status": status,
                    "prediction_percent": percent,
                    "fallback": None if status == "prediction_available" else "observed_analytics",
                    "reason": None if status == "prediction_available" else "safe fallback",
                    "evidence": {"academic_evidence_count": 1},
                }
                response = self.request_prediction()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["prediction"]["status"], status)
                self.assertEqual(response.json["prediction"]["prediction_percent"], percent)

    def test_teacher_response_does_not_expose_features_or_artifact_metadata(self):
        self.login("teacher")
        response = self.request_prediction()
        self.assertEqual(response.status_code, 200)
        serialized = response.get_data(as_text=True)
        for forbidden in ("raw_features", "internal_path", "checksum_sha256", "manifest", "Student One"):
            self.assertNotIn(forbidden, serialized)
        self.assertNotIn("/private", serialized)
        self.assertNotIn("should", serialized)

    def test_admin_runtime_status_auth_roles_and_safe_fields(self):
        path = "/api/admin/ml/runtime-status"
        self.login("teacher")
        self.assertEqual(self.client.get(path).status_code, 403)
        self.login("student")
        self.assertEqual(self.client.get(path).status_code, 403)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get(path).status_code, 401)

        self.login("admin")
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "model_unavailable")
        self.assertFalse(response.json["model_loaded"])
        self.assertEqual(response.json["feature_contract_version"], "1")
        self.assertEqual(response.json["fallback"], "observed_analytics")
        serialized = response.get_data(as_text=True)
        for forbidden in ("path", "checksum", "manifest", "/private"):
            self.assertNotIn(forbidden, serialized)

    def test_current_real_loader_result_is_reported_as_model_unavailable(self):
        self.login("teacher")
        self.backend.app.extensions["prediction_service"] = PredictionService(
            ProductionArtifactLoader()
        )
        response = self.request_prediction()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["prediction"]["status"], "model_unavailable")
        self.assertIsNone(response.json["prediction"]["prediction_percent"])
        self.assertEqual(response.json["prediction"]["fallback"], "observed_analytics")

    def test_api_requests_do_not_write_prediction_rows(self):
        self.login("teacher")
        before = self.db.total_changes
        response = self.request_prediction()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.total_changes, before)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
