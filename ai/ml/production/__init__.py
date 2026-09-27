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
from .model_monitoring import (
    MODEL_MONITORING_VERSION,
    build_model_monitoring_report,
    summarize_monitoring_status,
)
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
from .model_training import (
    MIN_MAE_IMPROVEMENT_VS_DUMMY,
    MODEL_APPROVAL_POLICY_VERSION,
    MODEL_TRAINING_VERSION,
    assess_candidate_approval,
    promote_candidate,
    run_training_pipeline,
)
from .learning_recommendations import (
    LEARNING_RECOMMENDATION_VERSION,
    build_learning_recommendations,
    recommendation_source_kind,
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
    "MODEL_MONITORING_VERSION",
    "build_model_monitoring_report",
    "summarize_monitoring_status",
    "TRAINING_READINESS_VERSION",
    "MIN_ELIGIBLE_ROWS",
    "MIN_UNIQUE_STUDENTS",
    "MIN_UNIQUE_TARGET_DATES",
    "MIN_VALIDATION_ROWS",
    "MIN_VALIDATION_STUDENTS",
    "build_training_readiness_report",
    "evaluate_training_dataset",
    "MODEL_TRAINING_VERSION",
    "MODEL_APPROVAL_POLICY_VERSION",
    "MIN_MAE_IMPROVEMENT_VS_DUMMY",
    "assess_candidate_approval",
    "run_training_pipeline",
    "promote_candidate",
    "LEARNING_RECOMMENDATION_VERSION",
    "build_learning_recommendations",
    "recommendation_source_kind",
]
