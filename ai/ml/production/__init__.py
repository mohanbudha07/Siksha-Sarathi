"""Production-oriented ML feature extraction for Siksha Sarathi."""

from .feature_contract import (
    FEATURE_CONTRACT_VERSION,
    OUTPUT_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    METADATA_COLUMNS,
)
from .feature_builder import (
    build_feature_row_for_target,
    build_training_dataset,
    count_feature_evidence,
    generate_diagnostics,
    build_live_feature_row,
)
from .decision_support import DECISION_SUPPORT_VERSION, build_teacher_decision_support
from .training_readiness import (
    MIN_ELIGIBLE_ROWS,
    MIN_UNIQUE_STUDENTS,
    MIN_UNIQUE_TARGET_DATES,
    MIN_VALIDATION_ROWS,
    MIN_VALIDATION_STUDENTS,
    TRAINING_READINESS_VERSION,
    build_training_readiness_report,
    evaluate_training_dataset,
)

__all__ = [
    "OUTPUT_COLUMNS",
    "FEATURE_CONTRACT_VERSION",
    "MODEL_FEATURE_COLUMNS",
    "METADATA_COLUMNS",
    "build_feature_row_for_target",
    "build_training_dataset",
    "count_feature_evidence",
    "generate_diagnostics",
    "build_live_feature_row",
    "DECISION_SUPPORT_VERSION",
    "build_teacher_decision_support",
    "TRAINING_READINESS_VERSION",
    "MIN_ELIGIBLE_ROWS",
    "MIN_UNIQUE_STUDENTS",
    "MIN_UNIQUE_TARGET_DATES",
    "MIN_VALIDATION_ROWS",
    "MIN_VALIDATION_STUDENTS",
    "build_training_readiness_report",
    "evaluate_training_dataset",
]
