"""Deterministic teacher decision support after prediction validation.

These bands are product heuristics, not pass/fail boundaries, probabilities,
confidence estimates, diagnoses, or automatic intervention decisions.
"""

from __future__ import annotations

import math

DECISION_SUPPORT_VERSION = "1"

REVIEW_THRESHOLD = 50.0
_STRONGER_OUTLOOK_THRESHOLD = 75.0


def _valid_prediction(status, prediction_percent):
    return (
        status == "prediction_available"
        and isinstance(prediction_percent, (int, float))
        and not isinstance(prediction_percent, bool)
        and math.isfinite(float(prediction_percent))
        and 0.0 <= float(prediction_percent) <= 100.0
    )


def _observed_flags(observed):
    observed = observed if isinstance(observed, dict) else {}
    quiz = observed.get("quiz") if isinstance(observed.get("quiz"), dict) else {}
    paper = observed.get("paper") if isinstance(observed.get("paper"), dict) else {}

    quiz_questions = int(quiz.get("total_questions") or 0)
    quiz_status = str(quiz.get("status") or "")
    graded_papers = int(paper.get("graded_assessments") or 0)
    paper_average = float(paper.get("average_percent") or 0)
    quiz_concern = quiz_questions > 0 and quiz_status == "Needs attention"
    paper_concern = graded_papers >= 2 and paper_average < 60
    quiz_strong = quiz_questions >= 4 and quiz_status == "On track"
    paper_strong = graded_papers >= 2 and paper_average >= 75
    enough_observed = quiz_questions >= 4 or graded_papers >= 2
    observed_concern = quiz_concern or paper_concern
    observed_strong = quiz_strong or paper_strong
    return observed_concern, observed_strong, enough_observed


def _message(attention_level, evidence_alignment):
    if evidence_alignment == "limited":
        return (
            "A forecast is available, but the observed academic record is still "
            "limited. Treat the estimate cautiously."
        )
    if attention_level == "review" and evidence_alignment == "supporting":
        return (
            "The forecast suggests review, and recorded academic evidence also "
            "shows areas that may need attention. Check the detailed evidence "
            "before planning support."
        )
    if attention_level == "review" and evidence_alignment == "mixed":
        return (
            "The forecast suggests review, but recorded academic evidence is "
            "mixed. Review the student's recent work before deciding on support."
        )
    if attention_level == "monitor":
        return (
            "The forecast suggests monitoring. Continue reviewing new quiz and "
            "paper evidence before making changes."
        )
    if attention_level == "stronger_outlook":
        return (
            "The forecast is comparatively stronger. Continue normal monitoring "
            "and use observed evidence to identify any specific gaps."
        )
    return "Decision support requires a valid production forecast."


def build_teacher_decision_support(status, prediction_percent, observed=None):
    """Return a pure, deterministic interpretation for an authorized teacher."""
    unavailable = {
        "available": False,
        "version": DECISION_SUPPORT_VERSION,
        "attention_level": None,
        "evidence_alignment": "not_applicable",
        "message": "Decision support requires a valid production forecast.",
        "rule_basis": "deterministic_forecast_interpretation",
    }
    if not _valid_prediction(status, prediction_percent):
        return unavailable

    prediction = float(prediction_percent)
    if prediction < REVIEW_THRESHOLD:
        attention_level = "review"
    elif prediction < _STRONGER_OUTLOOK_THRESHOLD:
        attention_level = "monitor"
    else:
        attention_level = "stronger_outlook"

    observed_concern, observed_strong, enough_observed = _observed_flags(observed)
    if not enough_observed:
        evidence_alignment = "limited"
    elif (attention_level == "review" and observed_concern) or (
        attention_level == "stronger_outlook" and observed_strong
    ):
        evidence_alignment = "supporting"
    elif (attention_level == "review" and observed_strong) or (
        attention_level == "stronger_outlook" and observed_concern
    ):
        evidence_alignment = "mixed"
    else:
        evidence_alignment = "mixed" if observed_concern or observed_strong else "limited"

    return {
        "available": True,
        "version": DECISION_SUPPORT_VERSION,
        "attention_level": attention_level,
        "evidence_alignment": evidence_alignment,
        "message": _message(attention_level, evidence_alignment),
        "rule_basis": "deterministic_forecast_interpretation",
    }
