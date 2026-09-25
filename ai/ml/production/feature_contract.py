"""Production feature contract for next-paper prediction."""

from __future__ import annotations

FEATURE_CONTRACT_VERSION = "1"

METADATA_COLUMNS = [
    "student_id",
    "subject",
    "target_assessment_id",
    "target_assessment_date",
    "target_class_id",
    "target_max_marks",
    "target_marks_obtained",
    "eligible_for_prediction",
    "ineligible_reason",
]

MODEL_FEATURE_COLUMNS = [
    "quiz_attempt_count",
    "quiz_average_percent",
    "recent_quiz_average_percent",
    "has_quiz_evidence",
    "incorrect_answer_count",
    "skipped_answer_rate",
    "prior_paper_count",
    "prior_paper_average_percent",
    "latest_prior_paper_percent",
    "has_prior_paper_evidence",
    "attendance_percent",
    "absent_days",
    "total_attendance_days",
    "has_attendance_evidence",
    "days_since_last_quiz",
    "recent_evidence_count",
]

TARGET_COLUMN = "target_percent"
OUTPUT_COLUMNS = METADATA_COLUMNS + MODEL_FEATURE_COLUMNS + [TARGET_COLUMN]


def deterministic_feature_columns(frame):
    """Return the production feature schema in the required deterministic order."""
    if frame is None:
        return list(OUTPUT_COLUMNS)
    available = [column for column in OUTPUT_COLUMNS if column in frame.columns]
    missing = [column for column in OUTPUT_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required feature columns: {missing}")
    return available
