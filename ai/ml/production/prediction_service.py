"""Framework-independent, fail-closed production prediction service."""

from __future__ import annotations

import math
import numbers

import numpy as np
import pandas as pd

from ai.ml.production.artifact_loader import ProductionArtifactLoader
from ai.ml.production.feature_builder import build_live_feature_row
from ai.ml.production.feature_contract import FEATURE_CONTRACT_VERSION, MODEL_FEATURE_COLUMNS

PREDICTION_AVAILABLE = "prediction_available"
MODEL_UNAVAILABLE = "model_unavailable"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"
PREDICTION_INVALID = "prediction_invalid"
FALLBACK_MODE = "observed_analytics"


class PredictionService:
    """Run a prediction only when evidence, artifact, and output are valid."""

    def __init__(self, loader=None):
        self.loader = loader or ProductionArtifactLoader()

    def predict(self, connection, student_id, class_id, subject, as_of_date):
        try:
            load_result = self.loader.load()
        except Exception:
            return {
                "status": MODEL_UNAVAILABLE,
                "prediction_percent": None,
                "reason": "production model could not be loaded",
                "model_status": MODEL_UNAVAILABLE,
                "fallback": FALLBACK_MODE,
                "feature_contract_version": FEATURE_CONTRACT_VERSION,
                "as_of_date": str(as_of_date),
                "evidence": {},
            }
        if not load_result.available:
            return {
                "status": MODEL_UNAVAILABLE,
                "prediction_percent": None,
                "reason": load_result.reason or load_result.status,
                "model_status": load_result.status,
                "fallback": FALLBACK_MODE,
                "feature_contract_version": FEATURE_CONTRACT_VERSION,
                "as_of_date": str(as_of_date),
                "evidence": {},
            }

        try:
            live_row = build_live_feature_row(
                connection,
                student_id=student_id,
                class_id=class_id,
                subject=subject,
                as_of_date=as_of_date,
            )
        except Exception:
            return _fallback_result("prediction_invalid", "feature construction failed")

        base_result = {
            "feature_contract_version": FEATURE_CONTRACT_VERSION,
            "evidence": live_row["evidence"],
            "as_of_date": live_row["as_of_date"],
        }
        if not live_row["eligible_for_prediction"]:
            return {
                **base_result,
                "status": INSUFFICIENT_EVIDENCE,
                "prediction_percent": None,
                "reason": live_row["ineligible_reason"],
                "fallback": FALLBACK_MODE,
            }

        try:
            feature_frame = pd.DataFrame(
                [[live_row["features"][column] for column in MODEL_FEATURE_COLUMNS]],
                columns=MODEL_FEATURE_COLUMNS,
            )
            predictions = load_result.model.predict(feature_frame)
            prediction = _normalize_prediction_scalar(predictions)
        except Exception:
            return {
                **base_result,
                "status": PREDICTION_INVALID,
                "prediction_percent": None,
                "reason": "model returned an invalid prediction",
                "model_version": _manifest_value(load_result, "artifact_version"),
                "fallback": FALLBACK_MODE,
            }

        if not math.isfinite(prediction) or not 0.0 <= prediction <= 100.0:
            return {
                **base_result,
                "status": PREDICTION_INVALID,
                "prediction_percent": None,
                "reason": "model returned a prediction outside 0-100 percentage range",
                "model_version": _manifest_value(load_result, "artifact_version"),
                "fallback": FALLBACK_MODE,
            }

        return {
            **base_result,
            "status": PREDICTION_AVAILABLE,
            "prediction_percent": prediction,
            "model_version": _manifest_value(load_result, "artifact_version"),
            "model_type": _manifest_value(load_result, "model_type"),
        }


def _manifest_value(load_result, key):
    if not load_result.manifest:
        return None
    return load_result.manifest.get(key)


def _normalize_prediction_scalar(predictions):
    """Accept exactly one real numeric prediction and reject ambiguous values."""
    if predictions is None or isinstance(predictions, (bool, str, bytes)):
        raise ValueError("prediction must be numeric")
    if isinstance(predictions, np.ndarray):
        if predictions.size != 1:
            raise ValueError("prediction must contain exactly one value")
        return _normalize_prediction_scalar(predictions.reshape(-1)[0].item())
    if isinstance(predictions, (list, tuple)):
        if len(predictions) != 1:
            raise ValueError("prediction must contain exactly one value")
        return _normalize_prediction_scalar(predictions[0])
    if isinstance(predictions, np.generic):
        if np.issubdtype(predictions.dtype, np.bool_):
            raise ValueError("prediction must be numeric")
        return _normalize_prediction_scalar(predictions.item())
    if isinstance(predictions, numbers.Real) and not isinstance(predictions, bool):
        return float(predictions)
    raise ValueError("prediction must be numeric")


def _fallback_result(status, reason):
    return {
        "status": status,
        "prediction_percent": None,
        "reason": reason,
        "fallback": FALLBACK_MODE,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
    }
