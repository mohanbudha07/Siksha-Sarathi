"""Safe loading and validation of future production model artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Optional

import joblib

from ai.ml.production.feature_contract import (
    FEATURE_CONTRACT_VERSION,
    MODEL_FEATURE_COLUMNS,
    TARGET_COLUMN,
)

MODEL_UNAVAILABLE = "model_unavailable"
ARTIFACT_MANIFEST_MISSING = "artifact_manifest_missing"
ARTIFACT_FILE_MISSING = "artifact_file_missing"
ARTIFACT_INCOMPATIBLE = "artifact_incompatible"
ARTIFACT_CORRUPT = "artifact_corrupt"

DEFAULT_ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
DEFAULT_MANIFEST_NAME = "manifest.json"

_REQUIRED_MANIFEST_FIELDS = (
    "artifact_version",
    "model_type",
    "feature_contract_version",
    "feature_names",
    "target_name",
    "target_unit",
    "training_timestamp",
    "training_data_source",
    "training_row_count",
    "unique_student_count",
    "validation_strategy",
    "primary_metric",
    "validation_metrics",
    "model_file",
    "checksum_sha256",
)


@dataclass(frozen=True)
class ModelLoadResult:
    """Stable result of an attempted production artifact load."""

    status: str
    model: Any = None
    manifest: Optional[dict] = None
    reason: str = ""

    @property
    def available(self):
        return self.status == "prediction_available" and self.model is not None


class ProductionArtifactLoader:
    """Validate and cache a production artifact without selecting legacy files."""

    def __init__(self, artifact_dir=DEFAULT_ARTIFACT_DIR, manifest_name=DEFAULT_MANIFEST_NAME):
        self.artifact_dir = Path(artifact_dir)
        self.manifest_path = self.artifact_dir / manifest_name
        self._cached_result = None

    def reset(self):
        self._cached_result = None

    def load(self, force_reload=False):
        if self._cached_result is not None and not force_reload:
            return self._cached_result
        result = self._load_uncached()
        self._cached_result = result
        return result

    def _load_uncached(self):
        if not self.manifest_path.is_file():
            return ModelLoadResult(
                status=ARTIFACT_MANIFEST_MISSING,
                reason="production manifest is unavailable",
            )

        try:
            manifest = json.loads(self.manifest_path.read_text())
        except (OSError, UnicodeError, json.JSONDecodeError):
            return ModelLoadResult(
                status=ARTIFACT_CORRUPT,
                reason="production manifest cannot be read",
            )

        validation_error = validate_manifest(manifest)
        if validation_error:
            return ModelLoadResult(
                status=ARTIFACT_INCOMPATIBLE,
                manifest=manifest if isinstance(manifest, dict) else None,
                reason=validation_error,
            )

        model_path = _safe_model_path(self.artifact_dir, manifest["model_file"])
        if model_path is None:
            return ModelLoadResult(
                status=ARTIFACT_INCOMPATIBLE,
                manifest=manifest,
                reason="model_file must be a relative path inside the artifact directory",
            )
        if not model_path.is_file():
            return ModelLoadResult(
                status=ARTIFACT_FILE_MISSING,
                manifest=manifest,
                reason="production model file is unavailable",
            )

        checksum = manifest["checksum_sha256"]
        if _sha256(model_path) != checksum:
            return ModelLoadResult(
                status=ARTIFACT_CORRUPT,
                manifest=manifest,
                reason="production model checksum does not match",
            )

        try:
            model = joblib.load(model_path)
        except Exception:
            return ModelLoadResult(
                status=ARTIFACT_CORRUPT,
                manifest=manifest,
                reason="production model cannot be loaded",
            )
        if not callable(getattr(model, "predict", None)):
            return ModelLoadResult(
                status=ARTIFACT_INCOMPATIBLE,
                manifest=manifest,
                reason="production model does not provide predict",
            )
        return ModelLoadResult(
            status="prediction_available",
            model=model,
            manifest=manifest,
        )


def validate_manifest(manifest):
    """Return a safe validation message, or an empty string when valid."""
    if not isinstance(manifest, dict):
        return "manifest must be an object"
    missing = [field for field in _REQUIRED_MANIFEST_FIELDS if field not in manifest]
    if missing:
        return "manifest is missing required fields"
    string_fields = (
        "artifact_version",
        "model_type",
        "feature_contract_version",
        "target_name",
        "target_unit",
        "training_timestamp",
        "training_data_source",
        "validation_strategy",
        "primary_metric",
        "model_file",
    )
    if any(not isinstance(manifest[field], str) or not manifest[field].strip() for field in string_fields):
        return "manifest contains invalid text metadata"
    if manifest["feature_contract_version"] != FEATURE_CONTRACT_VERSION:
        return "feature contract version does not match"
    if manifest["feature_names"] != list(MODEL_FEATURE_COLUMNS):
        return "feature names or order do not match"
    if manifest["target_name"] != TARGET_COLUMN:
        return "target name does not match"
    if manifest["target_unit"] != "percentage / 0-100 paper-assessment score":
        return "target unit does not match"
    if not isinstance(manifest["feature_names"], list) or not all(
        isinstance(name, str) for name in manifest["feature_names"]
    ):
        return "feature_names must be an ordered string list"
    if not isinstance(manifest["training_row_count"], int) or manifest["training_row_count"] < 0:
        return "training_row_count must be a non-negative integer"
    if not isinstance(manifest["unique_student_count"], int) or manifest["unique_student_count"] < 0:
        return "unique_student_count must be a non-negative integer"
    if not isinstance(manifest["validation_metrics"], dict):
        return "validation_metrics must be an object"
    if (
        not isinstance(manifest["checksum_sha256"], str)
        or len(manifest["checksum_sha256"]) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in manifest["checksum_sha256"])
    ):
        return "checksum_sha256 is invalid"
    if _safe_model_path(Path("/tmp/artifacts"), manifest["model_file"]) is None:
        return "model_file must be a relative path inside the artifact directory"
    return ""


def _safe_model_path(artifact_dir, model_file):
    candidate = Path(model_file)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    root = Path(artifact_dir).resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
