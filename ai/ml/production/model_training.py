"""Guarded local candidate training, packaging, and explicit promotion."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
from uuid import uuid4

import joblib
import pandas as pd

from ai.ml.production.artifact_loader import DEFAULT_ARTIFACT_DIR, ProductionArtifactLoader
from ai.ml.production.feature_contract import (
    FEATURE_CONTRACT_VERSION,
    MODEL_FEATURE_COLUMNS,
    TARGET_COLUMN,
)
from ai.ml.production.feature_builder import build_training_dataset
from ai.ml.production.training_readiness import (
    MIN_ELIGIBLE_ROWS,
    MIN_UNIQUE_STUDENTS,
    MIN_UNIQUE_TARGET_DATES,
    MIN_VALIDATION_ROWS,
    MIN_VALIDATION_STUDENTS,
    TRAINING_READINESS_VERSION,
    _candidate_models,
    _evaluate_models,
    _temporal_split,
    evaluate_training_dataset,
)
from ai.ml.production.prediction_service import _normalize_prediction_scalar

MODEL_TRAINING_VERSION = "1"
MODEL_APPROVAL_POLICY_VERSION = "1"
MIN_MAE_IMPROVEMENT_VS_DUMMY = 0.10
TARGET_UNIT = "percentage / 0-100 paper-assessment score"
VALIDATION_STRATEGY = "temporal_unique_target_dates"


def _finite_metric(value):
    if value is None or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _valid_candidate_metrics(metrics):
    if not isinstance(metrics, dict):
        return False
    if not _finite_metric(metrics.get("mae")) or not _finite_metric(metrics.get("rmse")):
        return False
    r2 = metrics.get("r2")
    return r2 is None or _finite_metric(r2)


def _is_within(path, parent):
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def assess_candidate_approval(evaluation: dict[str, Any]) -> dict[str, Any]:
    """Apply the fixed temporal-MAE policy without fitting or writing files."""
    models = evaluation.get("models", []) if isinstance(evaluation, dict) else []
    dummy = next(
        (model for model in models if model.get("model_name") == "DummyRegressor"),
        None,
    )
    if dummy is None or not _finite_metric(dummy.get("mae")):
        return {
            "status": "candidate_rejected",
            "approval_policy_version": MODEL_APPROVAL_POLICY_VERSION,
            "reason": "dummy_baseline_unavailable",
            "reasons": ["A finite DummyRegressor temporal-validation MAE is required."],
        }

    fixed_candidate_names = {
        name for name, _estimator, _params in _candidate_models()
        if name != "DummyRegressor"
    }
    candidates = [
        model for model in models
        if model.get("model_name") != "DummyRegressor"
        and model.get("model_name") in fixed_candidate_names
        and _valid_candidate_metrics(model)
    ]
    if not candidates:
        return {
            "status": "candidate_rejected",
            "approval_policy_version": MODEL_APPROVAL_POLICY_VERSION,
            "reason": "no_valid_non_dummy_candidate",
            "reasons": ["No non-Dummy candidate has finite MAE and RMSE metrics."],
            "dummy_mae": float(dummy["mae"]),
        }

    candidate = min(candidates, key=lambda model: float(model["mae"]))
    candidate_mae = float(candidate["mae"])
    dummy_mae = float(dummy["mae"])
    if dummy_mae <= candidate_mae:
        return {
            "status": "candidate_rejected",
            "approval_policy_version": MODEL_APPROVAL_POLICY_VERSION,
            "reason": "dummy_best_or_tied",
            "model_name": "DummyRegressor",
            "candidate_mae": candidate_mae,
            "dummy_mae": dummy_mae,
            "reasons": ["The DummyRegressor baseline has the best or tied temporal-validation MAE."],
        }

    if dummy_mae <= 0:
        return {
            "status": "candidate_rejected",
            "approval_policy_version": MODEL_APPROVAL_POLICY_VERSION,
            "reason": "baseline_improvement_undefined",
            "model_name": candidate["model_name"],
            "candidate_mae": candidate_mae,
            "dummy_mae": dummy_mae,
            "reasons": ["Relative improvement cannot be established against a zero-MAE baseline."],
        }

    relative_improvement = (dummy_mae - candidate_mae) / dummy_mae
    common = {
        "approval_policy_version": MODEL_APPROVAL_POLICY_VERSION,
        "model_name": candidate["model_name"],
        "primary_metric": "mae",
        "candidate_mae": candidate_mae,
        "dummy_mae": dummy_mae,
        "relative_mae_improvement": relative_improvement,
        "candidate_metrics": {
            key: candidate.get(key) for key in ("mae", "rmse", "r2")
        },
        "dummy_baseline_metrics": {
            key: dummy.get(key) for key in ("mae", "rmse", "r2")
        },
    }
    if relative_improvement < MIN_MAE_IMPROVEMENT_VS_DUMMY:
        return {
            **common,
            "status": "candidate_rejected",
            "reason": "insufficient_improvement_vs_dummy",
            "reasons": [
                "The candidate does not meet the configured minimum relative MAE improvement over DummyRegressor."
            ],
        }

    return {
        **common,
        "status": "candidate_approval_eligible",
        "reason": "approval_policy_passed",
        "reasons": [
            "Phase 7 readiness and temporal validation gates passed.",
            "The non-Dummy candidate has finite metrics and meets the configured relative MAE improvement policy.",
        ],
    }


def _readiness_counts(report):
    summary = report.get("privacy_safe_summary") or {}
    return {
        "eligible_snapshots": int(report.get("eligible_training_snapshots", summary.get("eligible_rows", 0)) or 0),
        "unique_students": int(report.get("unique_students", summary.get("unique_students", 0)) or 0),
        "unique_target_dates": int(report.get("unique_target_dates", summary.get("unique_target_dates", 0)) or 0),
    }


def _refusal(readiness, reason="dataset_not_ready"):
    counts = _readiness_counts(readiness)
    return {
        "status": "training_refused",
        "reason": reason,
        "readiness_state": readiness.get("readiness_state", "pipeline_only"),
        "training_ready": bool(readiness.get("training_ready")),
        "evaluation_ready": bool(readiness.get("evaluation_ready")),
        "blockers": list(readiness.get("blockers") or ["readiness_thresholds_not_met"]),
        "counts": counts,
        "thresholds": {
            "eligible_snapshots": MIN_ELIGIBLE_ROWS,
            "unique_students": MIN_UNIQUE_STUDENTS,
            "unique_target_dates": MIN_UNIQUE_TARGET_DATES,
            "validation_rows": MIN_VALIDATION_ROWS,
            "validation_students": MIN_VALIDATION_STUDENTS,
        },
        "files_created": False,
        "estimator_fit_called": False,
    }


def _safe_evaluation_report(readiness, split, evaluation, approval):
    counts = _readiness_counts(readiness)
    return {
        "model_training_version": MODEL_TRAINING_VERSION,
        "approval_policy_version": MODEL_APPROVAL_POLICY_VERSION,
        "readiness_version": TRAINING_READINESS_VERSION,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "readiness_state": readiness.get("readiness_state"),
        "training_ready": bool(readiness.get("training_ready")),
        "evaluation_ready": bool(readiness.get("evaluation_ready")),
        "deployment_ready": False,
        "training_row_count": counts["eligible_snapshots"],
        "unique_student_count": counts["unique_students"],
        "unique_target_date_count": counts["unique_target_dates"],
        "validation_row_count": int(len(split["validation"])),
        "validation_student_count": int(split["validation"]["student_id"].nunique()),
        "training_target_date_range": [
            min(split["train_dates"]), max(split["train_dates"])
        ],
        "validation_target_date_range": [
            min(split["validation_dates"]), max(split["validation_dates"])
        ],
        "validation_strategy": VALIDATION_STRATEGY,
        "candidate_selection_metric": "temporal_validation_mae",
        "feature_names": list(MODEL_FEATURE_COLUMNS),
        "candidate_evaluation": _json_safe(evaluation),
        "approval": approval,
        "approved_for_promotion": approval.get("status") == "candidate_approval_eligible",
    }


def _package_evaluation_report(report, eligible_dataset, approval):
    fixed_candidates = {
        name: params for name, _estimator, params in _candidate_models()
    }
    raw_evaluation = report.get("candidate_evaluation", {})
    safe_models = []
    if isinstance(raw_evaluation, dict):
        for item in raw_evaluation.get("models", []):
            name = item.get("model_name")
            if name not in fixed_candidates:
                continue
            safe_models.append({
                "model_name": name,
                "mae": float(item["mae"]) if _finite_metric(item.get("mae")) else None,
                "rmse": float(item["rmse"]) if _finite_metric(item.get("rmse")) else None,
                "r2": float(item["r2"]) if _finite_metric(item.get("r2")) else None,
                "params": fixed_candidates[name],
            })
    safe_candidate_evaluation = {
        "status": "evaluated" if safe_models else "unavailable",
        "models": safe_models,
        "best_validation_mae_model": next(
            (item["model_name"] for item in safe_models if item["model_name"] == approval.get("model_name")),
            None,
        ),
        "best_validation_mae": approval.get("candidate_mae"),
        "dummy_mae": approval.get("dummy_mae"),
        "feature_names": list(MODEL_FEATURE_COLUMNS),
    }
    counts = {
        "training_row_count": int(len(eligible_dataset)),
        "unique_student_count": int(eligible_dataset["student_id"].nunique()),
        "unique_target_date_count": int(eligible_dataset["target_assessment_date"].nunique()),
    }
    validation_dates = report.get("validation_target_date_range", [])
    training_dates = report.get("training_target_date_range", [])
    safe = {
        key: report[key]
        for key in (
            "readiness_state", "training_ready", "evaluation_ready",
            "validation_row_count", "validation_student_count",
            "training_target_date_range", "validation_target_date_range",
        )
        if key in report
    }
    safe.update(counts)
    safe.update({
        "model_training_version": MODEL_TRAINING_VERSION,
        "approval_policy_version": MODEL_APPROVAL_POLICY_VERSION,
        "readiness_version": TRAINING_READINESS_VERSION,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "deployment_ready": False,
        "training_target_date_range": [str(value) for value in training_dates],
        "validation_target_date_range": [str(value) for value in validation_dates],
        "validation_strategy": VALIDATION_STRATEGY,
        "candidate_selection_metric": "temporal_validation_mae",
        "feature_names": list(MODEL_FEATURE_COLUMNS),
        "candidate_evaluation": safe_candidate_evaluation,
        "approval": approval,
        "approved_for_promotion": approval.get("status") == "candidate_approval_eligible",
    })
    return safe


def _sha256_bytes(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _smoke_predict(model, eligible_dataset):
    sample = eligible_dataset.loc[:, MODEL_FEATURE_COLUMNS].iloc[[0]].copy()
    prediction = _normalize_prediction_scalar(model.predict(sample))
    if not math.isfinite(prediction) or not 0.0 <= prediction <= 100.0:
        raise ValueError("smoke prediction is outside the supported range")
    return prediction


def package_approved_candidate(
    *,
    model,
    model_name: str,
    eligible_dataset: pd.DataFrame,
    evaluation_report: dict[str, Any],
    approval: dict[str, Any],
    output_dir,
) -> dict[str, Any]:
    """Package an already approved full-data fit into an explicit staging path."""
    destination = Path(output_dir)
    if approval.get("status") != "candidate_approval_eligible":
        return {"status": "candidate_rejected", "reason": "approval_policy_not_passed", "files_created": False}
    if model_name == "DummyRegressor" or approval.get("model_name") != model_name:
        return {"status": "candidate_rejected", "reason": "dummy_or_mismatched_candidate", "files_created": False}
    recomputed_approval = assess_candidate_approval({
        "models": [
            {"model_name": "DummyRegressor", **approval.get("dummy_baseline_metrics", {})},
            {"model_name": model_name, **approval.get("candidate_metrics", {})},
        ]
    })
    if recomputed_approval.get("status") != "candidate_approval_eligible":
        return {"status": "candidate_rejected", "reason": "approval_policy_not_passed", "files_created": False}
    if destination.exists():
        return {"status": "candidate_rejected", "reason": "staging_directory_exists", "files_created": False}
    if _is_within(destination, DEFAULT_ARTIFACT_DIR):
        return {"status": "candidate_rejected", "reason": "staging_must_be_outside_active_artifacts", "files_created": False}
    if eligible_dataset.empty or list(eligible_dataset.loc[:, MODEL_FEATURE_COLUMNS].columns) != MODEL_FEATURE_COLUMNS:
        return {"status": "candidate_rejected", "reason": "invalid_training_feature_contract", "files_created": False}

    temporary_directory = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_directory = Path(tempfile.mkdtemp(
            prefix=f".{destination.name}.staging-",
            dir=destination.parent,
        ))
        model_path = temporary_directory / "model.joblib"
        joblib.dump(model, model_path)
        checksum = _sha256_bytes(model_path)
        created_at = datetime.now(timezone.utc)
        artifact_version = "local-v1-" + created_at.strftime("%Y%m%dT%H%M%SZ")
        counts = {
            "training_row_count": int(len(eligible_dataset)),
            "unique_student_count": int(eligible_dataset["student_id"].nunique()),
        }
        target_dates = pd.to_datetime(eligible_dataset["target_assessment_date"], errors="coerce").dropna()
        target_date_range = [
            target_dates.min().date().isoformat(),
            target_dates.max().date().isoformat(),
        ] if not target_dates.empty else []
        manifest = {
            "artifact_version": artifact_version,
            "model_type": model_name,
            "feature_contract_version": FEATURE_CONTRACT_VERSION,
            "feature_names": list(MODEL_FEATURE_COLUMNS),
            "target_name": TARGET_COLUMN,
            "target_unit": TARGET_UNIT,
            "training_timestamp": created_at.isoformat(),
            "training_data_source": "local_siksha_sarathi_mysql",
            **counts,
            "validation_strategy": VALIDATION_STRATEGY,
            "primary_metric": "MAE",
            "validation_metrics": approval["candidate_metrics"],
            "model_file": "model.joblib",
            "checksum_sha256": checksum,
            "training_version": MODEL_TRAINING_VERSION,
            "approval_policy_version": MODEL_APPROVAL_POLICY_VERSION,
            "readiness_version": TRAINING_READINESS_VERSION,
            "candidate_selection_metric": "temporal_validation_mae",
            "dummy_baseline_metrics": approval["dummy_baseline_metrics"],
            "candidate_metrics": approval["candidate_metrics"],
            "relative_mae_improvement": approval["relative_mae_improvement"],
            "training_target_date_range": target_date_range,
            "approved_for_promotion": True,
            "smoke_test_passed": False,
        }
        manifest_path = temporary_directory / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        staged_load = ProductionArtifactLoader(temporary_directory).load()
        if not staged_load.available:
            raise ValueError("staged artifact failed runtime loader validation")
        _smoke_predict(staged_load.model, eligible_dataset)
        manifest["smoke_test_passed"] = True
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        final_load = ProductionArtifactLoader(temporary_directory).load()
        if not final_load.available:
            raise ValueError("final staged artifact failed runtime loader validation")

        safe_report = _package_evaluation_report(
            evaluation_report,
            eligible_dataset,
            recomputed_approval,
        )
        safe_report["status"] = "candidate_packaged"
        (temporary_directory / "evaluation_report.json").write_text(
            json.dumps(safe_report, indent=2, sort_keys=True, allow_nan=False),
            encoding="utf-8",
        )
        os.replace(temporary_directory, destination)
        temporary_directory = None
        return {
            "status": "candidate_packaged",
            "model_name": model_name,
            "artifact_version": artifact_version,
            "approval_policy_version": MODEL_APPROVAL_POLICY_VERSION,
            "approved_for_promotion": True,
            "smoke_test_passed": True,
            "files_created": ["model.joblib", "manifest.json", "evaluation_report.json"],
        }
    except Exception:
        return {
            "status": "package_validation_failed",
            "reason": "Staged model failed packaging validation.",
            "files_created": False,
        }
    finally:
        if temporary_directory is not None:
            shutil.rmtree(temporary_directory, ignore_errors=True)


def run_training_pipeline(
    dataset: pd.DataFrame,
    *,
    output_dir=None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Gate, temporally evaluate, approve, and optionally package a candidate."""
    if dataset is None:
        dataset = pd.DataFrame()
    if "eligible_for_prediction" in dataset.columns:
        eligible = dataset[dataset["eligible_for_prediction"].astype(bool)].copy()
    else:
        eligible = dataset.copy()

    readiness = evaluate_training_dataset(eligible, run_baseline_evaluation=False)
    if not readiness.get("training_ready") or not readiness.get("evaluation_ready"):
        if not readiness.get("blockers"):
            readiness = dict(readiness)
            if dataset.empty:
                readiness["blockers"] = ["empty_dataset"]
            elif eligible.empty:
                readiness["blockers"] = ["empty_eligible_dataset"]
        return _refusal(readiness)

    split = _temporal_split(eligible)
    if not split["split_ready"]:
        readiness = dict(readiness)
        readiness["evaluation_ready"] = False
        readiness["blockers"] = list(readiness.get("blockers", [])) + ["insufficient_temporal_validation"]
        return _refusal(readiness)

    try:
        evaluation = _evaluate_models(split["train"], split["validation"])
    except Exception:
        return {
            "status": "candidate_rejected",
            "reason": "candidate_evaluation_failed",
            "readiness_state": readiness.get("readiness_state"),
            "counts": _readiness_counts(readiness),
            "files_created": False,
            "estimator_fit_called": True,
        }
    approval = assess_candidate_approval(evaluation)
    evaluation_report = _safe_evaluation_report(readiness, split, evaluation, approval)
    common = {
        "model_training_version": MODEL_TRAINING_VERSION,
        "approval_policy_version": MODEL_APPROVAL_POLICY_VERSION,
        "readiness_state": readiness.get("readiness_state"),
        "counts": _readiness_counts(readiness),
        "candidate_evaluation": _json_safe(evaluation),
        "approval": approval,
        "evaluation_report": evaluation_report,
        "files_created": False,
        "estimator_fit_called": True,
    }
    if approval["status"] != "candidate_approval_eligible":
        return {"status": "candidate_rejected", **common}
    if dry_run or output_dir is None:
        return {"status": "candidate_approval_eligible", **common}
    destination = Path(output_dir)
    if destination.exists():
        return {
            "status": "candidate_rejected",
            "reason": "staging_directory_exists",
            **common,
        }
    if _is_within(destination, DEFAULT_ARTIFACT_DIR):
        return {
            "status": "candidate_rejected",
            "reason": "staging_must_be_outside_active_artifacts",
            **common,
        }

    selected_model = approval["model_name"]
    final_estimator = next(
        estimator for name, estimator, _params in _candidate_models()
        if name == selected_model
    )
    try:
        final_estimator.fit(
            eligible.loc[:, MODEL_FEATURE_COLUMNS].copy(),
            eligible[TARGET_COLUMN].astype(float),
        )
    except Exception:
        return {"status": "candidate_rejected", "reason": "final_full_data_fit_failed", **common}
    package_result = package_approved_candidate(
        model=final_estimator,
        model_name=selected_model,
        eligible_dataset=eligible,
        evaluation_report=evaluation_report,
        approval=approval,
        output_dir=destination,
    )
    return {**package_result, **common, "files_created": package_result.get("files_created", False)}


def run_training_from_connection(
    connection,
    *,
    subject=None,
    output_dir=None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Build real canonical source features and run the gated training flow."""
    dataset = build_training_dataset(
        connection,
        subject=subject,
        include_ineligible=True,
    )
    return run_training_pipeline(dataset, output_dir=output_dir, dry_run=dry_run)


def _manifest_approval(manifest):
    candidate_metrics = manifest.get("candidate_metrics")
    dummy_metrics = manifest.get("dummy_baseline_metrics")
    if not isinstance(candidate_metrics, dict) or not isinstance(dummy_metrics, dict):
        return {"status": "candidate_rejected", "reason": "approval_metrics_missing"}
    return assess_candidate_approval({
        "models": [
            {"model_name": "DummyRegressor", **dummy_metrics},
            {"model_name": manifest.get("model_type"), **candidate_metrics},
        ]
    })


def _staged_report_is_safe(staging: Path) -> bool:
    try:
        report = json.loads((staging / "evaluation_report.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    forbidden_keys = {
        "student_id", "user_id", "teacher_user_id", "student_name", "full_name",
        "username", "email", "marks_obtained", "features", "feature_vector",
        "raw_rows", "database_password", "mysql_password", "absolute_path",
    }

    def values_are_safe(value):
        if isinstance(value, dict):
            return all(
                str(key).lower() not in forbidden_keys and values_are_safe(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return all(values_are_safe(item) for item in value)
        if isinstance(value, str):
            lowered = value.lower()
            return (
                not value.startswith(("/", "\\"))
                and ":\\" not in value
                and "mysql_password" not in lowered
                and "database_password" not in lowered
            )
        return True

    return (
        isinstance(report, dict)
        and report.get("feature_names") == list(MODEL_FEATURE_COLUMNS)
        and report.get("approved_for_promotion") is True
        and values_are_safe(report)
    )


def promote_candidate(
    staging_dir,
    *,
    production_dir=DEFAULT_ARTIFACT_DIR,
    replace_existing: bool = False,
) -> dict[str, Any]:
    """Explicitly promote a validated staging bundle with rollback retention."""
    staging = Path(staging_dir)
    allowed_files = {"model.joblib", "manifest.json", "evaluation_report.json"}
    if (
        not staging.is_dir()
        or staging.is_symlink()
        or {entry.name for entry in staging.iterdir()} != allowed_files
        or any(not entry.is_file() or entry.is_symlink() for entry in staging.iterdir())
    ):
        return {"status": "promotion_refused", "reason": "staged_bundle_contents_invalid"}
    if not _staged_report_is_safe(staging):
        return {"status": "promotion_refused", "reason": "staged_evaluation_report_invalid"}
    staged = ProductionArtifactLoader(staging).load()
    if not staged.available or not staged.manifest:
        return {"status": "promotion_refused", "reason": "staged_artifact_invalid"}
    manifest = staged.manifest
    approval = _manifest_approval(manifest)
    if (
        not manifest.get("approved_for_promotion")
        or not manifest.get("smoke_test_passed")
        or manifest.get("approval_policy_version") != MODEL_APPROVAL_POLICY_VERSION
        or approval.get("status") != "candidate_approval_eligible"
        or approval.get("model_name") != manifest.get("model_type")
    ):
        return {"status": "promotion_refused", "reason": "candidate_not_approved"}

    production = Path(production_dir)
    if _is_within(staging, production):
        return {"status": "promotion_refused", "reason": "staging_and_active_paths_must_be_separate"}
    if production.is_symlink() or (production.exists() and not production.is_dir()):
        return {"status": "promotion_refused", "reason": "active_artifact_path_invalid"}
    existing_content = production.exists() and any(production.iterdir())
    if existing_content and not replace_existing:
        return {
            "status": "promotion_refused",
            "reason": "explicit_replacement_confirmation_required",
        }

    temporary_directory = None
    backup_directory = None
    moved_existing = False
    try:
        production.parent.mkdir(parents=True, exist_ok=True)
        temporary_directory = Path(tempfile.mkdtemp(
            prefix=f".{production.name}.promotion-",
            dir=production.parent,
        ))
        temporary_directory.rmdir()
        shutil.copytree(staging, temporary_directory)
        copied = ProductionArtifactLoader(temporary_directory).load()
        if not copied.available:
            raise ValueError("copied candidate failed artifact-loader validation")
        copied_manifest = copied.manifest or {}
        if _sha256_bytes(temporary_directory / copied_manifest["model_file"]) != copied_manifest["checksum_sha256"]:
            raise ValueError("copied candidate checksum verification failed")

        if existing_content:
            backup_name = f"{production.name}.backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}"
            backup_directory = production.with_name(backup_name)
            os.replace(production, backup_directory)
            moved_existing = True
        elif production.exists():
            production.rmdir()

        try:
            os.replace(temporary_directory, production)
            temporary_directory = None
        except Exception:
            if moved_existing and backup_directory is not None:
                os.replace(backup_directory, production)
                moved_existing = False
            raise
        return {
            "status": "artifact_promoted",
            "artifact_version": manifest["artifact_version"],
            "backup_retained": moved_existing,
            "restart_backend": True,
        }
    except Exception:
        return {"status": "promotion_refused", "reason": "promotion_transaction_failed"}
    finally:
        if temporary_directory is not None and temporary_directory.exists():
            shutil.rmtree(temporary_directory, ignore_errors=True)