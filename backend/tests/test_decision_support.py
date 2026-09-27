import unittest

from ai.ml.production.decision_support import (
    DECISION_SUPPORT_VERSION,
    build_teacher_decision_support,
)


class DecisionSupportTests(unittest.TestCase):
    @staticmethod
    def observed(quiz_questions=4, quiz_status="Needs attention", graded=2, average=55):
        return {
            "quiz": {"total_questions": quiz_questions, "status": quiz_status},
            "paper": {"graded_assessments": graded, "average_percent": average},
        }

    def test_attention_boundaries(self):
        expected = {
            0: "review",
            49.99: "review",
            50: "monitor",
            74.99: "monitor",
            75: "stronger_outlook",
            100: "stronger_outlook",
        }
        for prediction, level in expected.items():
            with self.subTest(prediction=prediction):
                result = build_teacher_decision_support(
                    "prediction_available", prediction, self.observed()
                )
                self.assertTrue(result["available"])
                self.assertEqual(result["attention_level"], level)
                self.assertEqual(result["version"], DECISION_SUPPORT_VERSION)

    def test_unavailable_states_have_no_attention_band(self):
        for status, prediction in (
            ("model_unavailable", None),
            ("insufficient_evidence", None),
            ("prediction_invalid", None),
            ("prediction_available", None),
            ("prediction_available", "58"),
        ):
            with self.subTest(status=status, prediction=prediction):
                result = build_teacher_decision_support(status, prediction, self.observed())
                self.assertFalse(result["available"])
                self.assertIsNone(result["attention_level"])
                self.assertEqual(result["evidence_alignment"], "not_applicable")

    def test_review_with_observed_concern_is_supporting(self):
        result = build_teacher_decision_support(
            "prediction_available", 49, self.observed()
        )
        self.assertEqual(result["evidence_alignment"], "supporting")

    def test_review_with_strong_observed_evidence_is_mixed(self):
        result = build_teacher_decision_support(
            "prediction_available", 49,
            self.observed(quiz_status="On track", average=80),
        )
        self.assertEqual(result["evidence_alignment"], "mixed")

    def test_stronger_forecast_with_observed_concern_is_mixed(self):
        result = build_teacher_decision_support(
            "prediction_available", 75, self.observed()
        )
        self.assertEqual(result["evidence_alignment"], "mixed")

    def test_limited_observed_evidence_is_limited(self):
        result = build_teacher_decision_support(
            "prediction_available", 58,
            self.observed(quiz_questions=1, graded=0, average=0),
        )
        self.assertEqual(result["evidence_alignment"], "limited")
        self.assertIn("limited", result["message"])

    def test_attendance_alone_does_not_create_concern(self):
        result = build_teacher_decision_support(
            "prediction_available", 49,
            {
                "quiz": {"total_questions": 0, "status": "No activity"},
                "paper": {"graded_assessments": 0, "average_percent": 0},
                "attendance": {"absent_days": 10},
            },
        )
        self.assertEqual(result["evidence_alignment"], "limited")

    def test_rule_basis_is_explicit(self):
        result = build_teacher_decision_support(
            "prediction_available", 58, self.observed()
        )
        self.assertEqual(result["rule_basis"], "deterministic_forecast_interpretation")
        self.assertNotIn("confidence", result["message"].lower())


if __name__ == "__main__":
    unittest.main()
