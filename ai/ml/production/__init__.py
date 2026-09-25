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
]
