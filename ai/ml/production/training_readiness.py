"""Local training-readiness and temporal evaluation checks for Siksha Sarathi.

This module intentionally never writes to the database and never creates a
production artifact. It evaluates whether the real local dataset is structurally
suitable for serious model training and whether a time-safe holdout can be
run without random row leakage.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from ai.ml.production.feature_builder import (
    build_source_evidence_summary,
    build_training_dataset,
)
from ai.ml.production.feature_contract import (
    FEATURE_CONTRACT_VERSION,
    METADATA_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    TARGET_COLUMN,
)

TRAINING_READINESS_VERSION = "1"

MIN_ELIGIBLE_ROWS = 100
MIN_UNIQUE_STUDENTS = 30
MIN_UNIQUE_TARGET_DATES = 4
MIN_VALIDATION_ROWS = 20
MIN_VALIDATION_STUDENTS = 10


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _safe_iso(value):
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        return pd.to_datetime(value).isoformat()
    except Exception:
        return str(value)


def _coerce_date(value):
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "date"):
        return value.date()
    if isinstance(value, str):
        value = value[:10]
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def _clean_date_series(series):
    return [_coerce_date(value) for value in series]


def _compute_aggregate_summary(dataset: pd.DataFrame) -> Dict[str, Any]:
    if dataset is None or dataset.empty:
        return {
            "eligible_rows": 0,
            "unique_students": 0,
            "unique_target_dates": 0,
            "subjects_represented": 0,
            "classes_represented": 0,
            "earliest_target_date": None,
            "latest_target_date": None,
            "rows_by_subject": {},
            "rows_by_class": {},
            "rows_by_target_date": {},
            "quiz_evidence_coverage": 0.0,
            "prior_paper_evidence_coverage": 0.0,
            "attendance_evidence_coverage": 0.0,
            "snapshots_per_student": {"min": 0, "median": 0.0, "mean": 0.0, "max": 0},
        }

    eligible = dataset[dataset["eligible_for_prediction"]].copy()
    if eligible.empty:
        return {
            "eligible_rows": 0,
            "unique_students": 0,
            "unique_target_dates": 0,
            "subjects_represented": 0,
            "classes_represented": 0,
            "earliest_target_date": None,
            "latest_target_date": None,
            "rows_by_subject": {},
            "rows_by_class": {},
            "rows_by_target_date": {},
            "quiz_evidence_coverage": 0.0,
            "prior_paper_evidence_coverage": 0.0,
            "attendance_evidence_coverage": 0.0,
            "snapshots_per_student": {"min": 0, "median": 0.0, "mean": 0.0, "max": 0},
        }

    eligible = eligible.copy()
    eligible["_target_date"] = pd.to_datetime(_clean_date_series(eligible["target_assessment_date"]), errors="coerce")
    valid_dates = eligible["_target_date"].dropna()
    counts_by_student = eligible["student_id"].value_counts()
    by_subject = eligible["subject"].value_counts().sort_index()
    by_class = eligible["target_class_id"].value_counts().sort_index()
    by_date = eligible["_target_date"].dt.strftime("%Y-%m-%d").value_counts().sort_index()

    snapshots_per_student = counts_by_student.to_list()
    if snapshots_per_student:
        snapshot_summary = {
            "min": int(min(snapshots_per_student)),
            "median": float(np.median(snapshots_per_student)),
            "mean": float(np.mean(snapshots_per_student)),
            "max": int(max(snapshots_per_student)),
        }
    else:
        snapshot_summary = {"min": 0, "median": 0.0, "mean": 0.0, "max": 0}

    return {
        "eligible_rows": int(len(eligible)),
        "unique_students": int(eligible["student_id"].nunique()),
        "unique_target_dates": int(valid_dates.nunique()),
        "subjects_represented": int(by_subject.shape[0]),
        "classes_represented": int(by_class.shape[0]),
        "earliest_target_date": valid_dates.min().strftime("%Y-%m-%d") if not valid_dates.empty else None,
        "latest_target_date": valid_dates.max().strftime("%Y-%m-%d") if not valid_dates.empty else None,
        "rows_by_subject": {str(subject): int(count) for subject, count in by_subject.items()},
        "rows_by_class": {str(class_id): int(count) for class_id, count in by_class.items()},
        "rows_by_target_date": {str(date): int(count) for date, count in by_date.items()},
        "quiz_evidence_coverage": float(eligible["has_quiz_evidence"].mean()) if not eligible.empty else 0.0,
        "prior_paper_evidence_coverage": float(eligible["has_prior_paper_evidence"].mean()) if not eligible.empty else 0.0,
        "attendance_evidence_coverage": float(eligible["has_attendance_evidence"].mean()) if not eligible.empty else 0.0,
        "snapshots_per_student": snapshot_summary,
    }


def _extract_blockers(dataset: pd.DataFrame) -> List[str]:
    blockers: List[str] = []
    if dataset is None:
        return ["empty_dataset"]
    if dataset.empty:
        return ["empty_dataset"]

    required_columns = list(METADATA_COLUMNS) + list(MODEL_FEATURE_COLUMNS) + [TARGET_COLUMN]
    missing_required = [column for column in required_columns if column not in dataset.columns]
    if missing_required:
        blockers.append("missing_feature_columns")

    if "target_percent" not in dataset.columns:
        blockers.append("missing_target_percent")

    if missing_required:
        missing_metadata = [column for column in METADATA_COLUMNS if column not in dataset.columns]
        if missing_metadata:
            blockers.append("missing_required_metadata")

    feature_columns = [column for column in MODEL_FEATURE_COLUMNS if column in dataset.columns]
    if feature_columns and feature_columns != MODEL_FEATURE_COLUMNS:
        blockers.append("feature_column_order_mismatch")

    if "target_assessment_date" in dataset.columns:
        date_missing = dataset["target_assessment_date"].isna().any()
        if date_missing:
            blockers.append("missing_target_dates")

    if {"student_id", "subject", "target_assessment_id"}.issubset(dataset.columns):
        identity = dataset[["student_id", "subject", "target_assessment_id"]].astype(str).fillna("nan")
        duplicate_mask = identity.duplicated(keep=False)
        if duplicate_mask.any():
            blockers.append("duplicate_snapshot_identity")

    if {"eligible_for_prediction", "ineligible_reason"}.issubset(dataset.columns):
        if dataset["eligible_for_prediction"].dtype != bool:
            try:
                dataset["eligible_for_prediction"] = dataset["eligible_for_prediction"].astype(bool)
            except Exception:
                pass
        if dataset["eligible_for_prediction"].eq(False).any() and len(dataset) > 0:
            blockers.append("ineligible_rows_present")

    if TARGET_COLUMN in dataset.columns:
        target_numeric = pd.to_numeric(dataset[TARGET_COLUMN], errors="coerce")
        if target_numeric.isna().any():
            blockers.append("non_finite_target")
        if ((target_numeric < 0) | (target_numeric > 100)).any():
            blockers.append("invalid_target_range")

    if feature_columns:
        feature_frame = dataset[feature_columns].copy()
        feature_numeric = feature_frame.apply(pd.to_numeric, errors="coerce")
        if feature_numeric.isna().values.any():
            blockers.append("non_finite_features")
        if np.isinf(feature_numeric.to_numpy(dtype=float, na_value=np.nan)).any():
            blockers.append("non_finite_features")

    return sorted(set(blockers))


def _temporal_split(dataset: pd.DataFrame, min_validation_rows: int = MIN_VALIDATION_ROWS, min_validation_students: int = MIN_VALIDATION_STUDENTS):
    eligible = dataset[dataset["eligible_for_prediction"]].copy()
    if eligible.empty:
        return {
            "train": pd.DataFrame(columns=eligible.columns),
            "validation": pd.DataFrame(columns=eligible.columns),
            "train_dates": [],
            "validation_dates": [],
            "reason": "No eligible rows for temporal validation.",
            "split_ready": False,
        }

    eligible = eligible.copy()
    eligible["_target_date"] = pd.to_datetime(_clean_date_series(eligible["target_assessment_date"]), errors="coerce")
    valid = eligible.dropna(subset=["_target_date"]).copy()
    if valid.empty:
        return {
            "train": pd.DataFrame(columns=eligible.columns),
            "validation": pd.DataFrame(columns=eligible.columns),
            "train_dates": [],
            "validation_dates": [],
            "reason": "No valid target dates for temporal validation.",
            "split_ready": False,
        }

    unique_dates = sorted(valid["_target_date"].drop_duplicates().tolist())
    if len(unique_dates) < 2:
        return {
            "train": pd.DataFrame(columns=valid.columns),
            "validation": pd.DataFrame(columns=valid.columns),
            "train_dates": [],
            "validation_dates": unique_dates,
            "reason": "Need at least two distinct target dates for temporal validation.",
            "split_ready": False,
        }

    validation_count = max(1, int(math.ceil(len(unique_dates) * 0.2)))
    if validation_count >= len(unique_dates):
        validation_count = max(1, len(unique_dates) - 1)

    validation_dates = unique_dates[-validation_count:]
    for extra_dates in range(validation_count, len(unique_dates) + 1):
        candidate_dates = unique_dates[-extra_dates:]
        candidate_validation = valid[valid["_target_date"].isin(candidate_dates)].copy()
        if len(candidate_validation) >= min_validation_rows and candidate_validation["student_id"].nunique() >= min_validation_students:
            validation_dates = candidate_dates
            break
    else:
        validation_dates = unique_dates[-1:]

    train_dates = [date for date in unique_dates if date not in validation_dates]

    train = valid[valid["_target_date"].isin(train_dates)].copy()
    validation = valid[valid["_target_date"].isin(validation_dates)].copy()

    train_dates_str = [date.isoformat() for date in train_dates]
    validation_dates_str = [date.isoformat() for date in validation_dates]
    if not train_dates or not validation_dates:
        return {
            "train": train,
            "validation": validation,
            "train_dates": train_dates_str,
            "validation_dates": validation_dates_str,
            "reason": "Temporal validation requires both train and validation dates.",
            "split_ready": False,
        }

    if max(train_dates) >= min(validation_dates):
        return {
            "train": train,
            "validation": validation,
            "train_dates": train_dates_str,
            "validation_dates": validation_dates_str,
            "reason": "Temporal validation failed: training dates overlap validation dates.",
            "split_ready": False,
        }

    if len(validation) < min_validation_rows:
        return {
            "train": train,
            "validation": validation,
            "train_dates": train_dates_str,
            "validation_dates": validation_dates_str,
            "reason": f"Validation rows below minimum required threshold ({min_validation_rows}).",
            "split_ready": False,
        }

    validation_students = validation["student_id"].nunique()
    if validation_students < min_validation_students:
        return {
            "train": train,
            "validation": validation,
            "train_dates": train_dates_str,
            "validation_dates": validation_dates_str,
            "reason": f"Validation students below minimum required threshold ({min_validation_students}).",
            "split_ready": False,
        }

    return {
        "train": train,
        "validation": validation,
        "train_dates": train_dates_str,
        "validation_dates": validation_dates_str,
        "reason": "Temporal validation split is valid.",
        "split_ready": True,
    }


def _secondary_grouped_robustness(dataset: pd.DataFrame):
    if dataset is None or dataset.empty:
        return {
            "status": "skipped",
            "reason": "No eligible dataset available for grouped robustness checking.",
            "n_groups": 0,
            "n_splits": 0,
            "results": {},
        }

    eligible = dataset[dataset["eligible_for_prediction"]].copy()
    if eligible.empty:
        return {
            "status": "skipped",
            "reason": "No eligible rows for grouped robustness checking.",
            "n_groups": 0,
            "n_splits": 0,
            "results": {},
        }

    if eligible["student_id"].nunique() < 10:
        return {
            "status": "skipped",
            "reason": "Insufficient students for secondary grouped robustness checking.",
            "n_groups": int(eligible["student_id"].nunique()),
            "n_splits": 0,
            "results": {},
        }

    try:
        from sklearn.model_selection import GroupShuffleSplit
        from sklearn.dummy import DummyRegressor
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import mean_absolute_error

        groups = eligible["student_id"].astype(int)
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
        train_idx, test_idx = next(splitter.split(eligible[MODEL_FEATURE_COLUMNS], eligible[TARGET_COLUMN], groups=groups))
        train = eligible.iloc[train_idx].copy()
        test = eligible.iloc[test_idx].copy()

        x_train = train[MODEL_FEATURE_COLUMNS].copy()
        x_test = test[MODEL_FEATURE_COLUMNS].copy()
        y_train = train[TARGET_COLUMN].astype(float)
        y_test = test[TARGET_COLUMN].astype(float)

        dummy = DummyRegressor(strategy="mean").fit(x_train, y_train)
        ridge = make_pipeline(StandardScaler(), Ridge(alpha=10.0)).fit(x_train, y_train)
        dummy_mae = mean_absolute_error(y_test, dummy.predict(x_test))
        ridge_mae = mean_absolute_error(y_test, ridge.predict(x_test))
        return {
            "status": "run",
            "reason": "Secondary student-group robustness check executed.",
            "n_groups": int(eligible["student_id"].nunique()),
            "n_splits": 1,
            "results": {
                "dummy_mae": round(float(dummy_mae), 4),
                "ridge_mae": round(float(ridge_mae), 4),
                "train_students": int(train["student_id"].nunique()),
                "validation_students": int(test["student_id"].nunique()),
            },
        }
    except Exception as exc:
        return {
            "status": "skipped",
            "reason": f"Secondary grouped robustness was not runnable: {exc}",
            "n_groups": int(eligible["student_id"].nunique()),
            "n_splits": 0,
            "results": {},
        }


def _candidate_models():
    from sklearn.dummy import DummyRegressor
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return [
        (
            "DummyRegressor",
            DummyRegressor(strategy="mean"),
            {"strategy": "mean"},
        ),
        (
            "Ridge",
            make_pipeline(StandardScaler(), Ridge(alpha=10.0)),
            {"alpha": 10.0},
        ),
        (
            "RandomForestRegressor",
            RandomForestRegressor(
                n_estimators=200,
                random_state=42,
                n_jobs=-1,
                max_depth=8,
                min_samples_leaf=2,
            ),
            {
                "n_estimators": 200,
                "random_state": 42,
                "max_depth": 8,
                "min_samples_leaf": 2,
            },
        ),
        (
            "GradientBoostingRegressor",
            GradientBoostingRegressor(random_state=42, n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8),
            {
                "random_state": 42,
                "n_estimators": 200,
                "max_depth": 2,
                "learning_rate": 0.05,
                "subsample": 0.8,
            },
        ),
    ]


def _evaluate_models(train: pd.DataFrame, validation: pd.DataFrame) -> Dict[str, Any]:
    if train.empty or validation.empty:
        return {
            "status": "skipped",
            "reason": "No train/validation split available.",
            "models": [],
            "best_validation_mae_model": None,
            "dummy_mae": None,
            "mae_improvement": None,
        }

    X_train = train[MODEL_FEATURE_COLUMNS].copy()
    X_validation = validation[MODEL_FEATURE_COLUMNS].copy()
    y_train = train[TARGET_COLUMN].astype(float)
    y_validation = validation[TARGET_COLUMN].astype(float)

    models = []
    dummy_ref = None
    for name, estimator, params in _candidate_models():
        estimator.fit(X_train, y_train)
        preds = estimator.predict(X_validation)
        mae = float(np.mean(np.abs(preds - y_validation)))
        rmse = float(np.sqrt(np.mean((preds - y_validation) ** 2)))
        r2 = float(1.0 - (np.sum((y_validation - preds) ** 2) / np.sum((y_validation - y_validation.mean()) ** 2))) if np.sum((y_validation - y_validation.mean()) ** 2) > 0 else 1.0
        if name == "DummyRegressor":
            dummy_ref = mae
        models.append(
            {
                "model_name": name,
                "mae": round(mae, 4),
                "rmse": round(rmse, 4),
                "r2": round(r2, 4),
                "params": params,
                "mae_improvement_vs_dummy": 0.0 if dummy_ref is None and name == "DummyRegressor" else (0.0 if dummy_ref == 0 else round(dummy_ref - mae, 4)),
            }
        )

    for entry in models:
        if entry["model_name"] == "DummyRegressor":
            continue
        dummy_mae = next(item["mae"] for item in models if item["model_name"] == "DummyRegressor")
        entry["mae_improvement_vs_dummy"] = 0.0 if dummy_mae == 0 else round(dummy_mae - entry["mae"], 4)

    models_sorted = sorted(models, key=lambda record: record["mae"])
    best_model_name = models_sorted[0]["model_name"] if models_sorted else None
    best_model_mae = models_sorted[0]["mae"] if models_sorted else None
    dummy_mae = next((item["mae"] for item in models if item["model_name"] == "DummyRegressor"), None)
    improvement = None if dummy_mae is None else (0.0 if dummy_mae == 0 else round(dummy_mae - best_model_mae, 4))
    ridge_model = next((entry for entry in models_sorted if entry["model_name"] == "Ridge"), None)
    return {
        "status": "evaluated",
        "reason": "Temporal validation metrics computed for all candidate baselines.",
        "models": models_sorted,
        "best_validation_mae_model": best_model_name,
        "best_validation_mae": best_model_mae,
        "dummy_mae": dummy_mae,
        "ridge_mae": ridge_model["mae"] if ridge_model is not None else None,
        "mae_improvement_vs_dummy": improvement,
        "feature_names": list(MODEL_FEATURE_COLUMNS),
    }


def _validate_dataset_for_readiness(dataset: pd.DataFrame) -> Dict[str, Any]:
    blockers = _extract_blockers(dataset)
    report = {
        "blockers": blockers,
        "training_ready": False,
        "evaluation_ready": False,
        "deployment_ready": False,
        "readiness_state": "PIPELINE_ONLY",
    }

    if dataset is None or dataset.empty:
        report["readiness_state"] = "PIPELINE_ONLY"
        return report

    if blockers:
        report["readiness_state"] = "DATA_QUALITY_BLOCKED"
        return report

    if len(dataset) < MIN_ELIGIBLE_ROWS:
        report["readiness_state"] = "INSUFFICIENT_DATA"
        return report

    if dataset["student_id"].nunique() < MIN_UNIQUE_STUDENTS:
        report["readiness_state"] = "INSUFFICIENT_DATA"
        return report

    if dataset["target_assessment_date"].notna().sum() == 0:
        report["readiness_state"] = "DATA_QUALITY_BLOCKED"
        blockers.append("missing_target_dates")
        report["blockers"] = blockers
        return report

    unique_dates = dataset["target_assessment_date"].dropna().nunique()
    if unique_dates < MIN_UNIQUE_TARGET_DATES:
        report["readiness_state"] = "INSUFFICIENT_DATA"
        return report

    report["training_ready"] = True
    report["readiness_state"] = "READY_FOR_EVALUATION"
    return report


def evaluate_training_dataset(
    dataset: pd.DataFrame,
    *,
    subject: str | None = None,
    run_baseline_evaluation: bool = True,
):
    """Return a privacy-safe readiness evaluation from a DataFrame, with a deterministic temporal split when valid."""
    report = {
        "TRAINING_READINESS_VERSION": TRAINING_READINESS_VERSION,
        "FEATURE_CONTRACT_VERSION": FEATURE_CONTRACT_VERSION,
        "subject": subject,
        "training_ready": False,
        "evaluation_ready": False,
        "deployment_ready": False,
        "readiness_state": "pipeline_only",
        "state": "PIPELINE_ONLY",
        "blockers": [],
        "privacy_safe_summary": {},
        "secondary_student_group_robustness": {
            "status": "skipped",
            "reason": "No eligible dataset available.",
            "n_groups": 0,
            "n_splits": 0,
            "results": {},
        },
        "reproducibility": {
            "python_version": sys.version.split()[0],
            "pandas_version": pd.__version__,
            "sklearn_version": None,
            "evaluation_timestamp": dt.datetime.utcnow().isoformat() + "Z",
            "split_strategy": "temporal_unique_target_dates",
            "training_date_range": None,
            "validation_date_range": None,
            "feature_names": list(MODEL_FEATURE_COLUMNS),
            "model_parameters": {},
        },
        "baseline_evaluation": {},
    }

    if dataset is None:
        report["readiness_state"] = "pipeline_only"
        report["state"] = "PIPELINE_ONLY"
        return report

    if dataset.empty:
        report["readiness_state"] = "pipeline_only"
        report["state"] = "PIPELINE_ONLY"
        return report

    if not set(MODEL_FEATURE_COLUMNS).issubset(set(dataset.columns)):
        report["blockers"] = ["missing_feature_columns"]
        report["readiness_state"] = "data_quality_blocked"
        report["state"] = "DATA_QUALITY_BLOCKED"
        return report

    report["blockers"] = _extract_blockers(dataset)
    if report["blockers"]:
        report["readiness_state"] = "data_quality_blocked"
        report["state"] = "DATA_QUALITY_BLOCKED"
        return report

    dataset = dataset.copy()
    dataset["target_assessment_date"] = pd.to_datetime(_clean_date_series(dataset["target_assessment_date"]), errors="coerce")
    dataset["target_percent"] = pd.to_numeric(dataset[TARGET_COLUMN], errors="coerce")
    dataset["eligible_for_prediction"] = dataset["eligible_for_prediction"].astype(bool)

    eligible = dataset[dataset["eligible_for_prediction"]].copy()
    if eligible.empty:
        report["readiness_state"] = "insufficient_data"
        report["state"] = "INSUFFICIENT_DATA"
        report["privacy_safe_summary"] = _compute_aggregate_summary(eligible)
        return report

    summary = _compute_aggregate_summary(eligible)
    report["privacy_safe_summary"] = summary
    report["eligible_training_snapshots"] = int(summary.get("eligible_rows", 0))
    report["unique_students"] = int(summary.get("unique_students", 0))
    report["unique_target_dates"] = int(summary.get("unique_target_dates", 0))
    report["subjects_represented"] = int(summary.get("subjects_represented", 0))
    report["classes_represented"] = int(summary.get("classes_represented", 0))

    if len(eligible) < MIN_ELIGIBLE_ROWS:
        report["readiness_state"] = "insufficient_data"
        report["state"] = "INSUFFICIENT_DATA"
        return report
    if eligible["student_id"].nunique() < MIN_UNIQUE_STUDENTS:
        report["readiness_state"] = "insufficient_data"
        report["state"] = "INSUFFICIENT_DATA"
        return report
    if eligible["target_assessment_date"].dropna().nunique() < MIN_UNIQUE_TARGET_DATES:
        report["readiness_state"] = "insufficient_data"
        report["state"] = "INSUFFICIENT_DATA"
        return report

    report["training_ready"] = True
    report["readiness_state"] = "evaluation_ready"
    report["state"] = "READY_FOR_EVALUATION"

    temporal = _temporal_split(eligible, min_validation_rows=MIN_VALIDATION_ROWS, min_validation_students=MIN_VALIDATION_STUDENTS)
    if not temporal["split_ready"]:
        report["readiness_state"] = "insufficient_data"
        report["state"] = "INSUFFICIENT_DATA"
        report["blockers"].append("insufficient_temporal_validation")
        report["baseline_evaluation"] = {}
        return report

    train = temporal["train"].copy()
    validation = temporal["validation"].copy()
    report["training_ready"] = True
    report["evaluation_ready"] = True
    report["readiness_state"] = "evaluation_ready"
    report["state"] = "EVALUATED_NOT_DEPLOYED"
    report["deployment_ready"] = False
    report["reproducibility"]["training_date_range"] = [
        min(temporal["train_dates"]),
        max(temporal["train_dates"]),
    ] if temporal["train_dates"] else None
    report["reproducibility"]["validation_date_range"] = [
        min(temporal["validation_dates"]),
        max(temporal["validation_dates"]),
    ] if temporal["validation_dates"] else None
    report["validation_rows"] = int(len(validation))
    report["validation_students"] = int(validation["student_id"].nunique())

    if run_baseline_evaluation:
        try:
            import sklearn
            report["reproducibility"]["sklearn_version"] = sklearn.__version__
        except Exception:
            report["reproducibility"]["sklearn_version"] = None

        report["baseline_evaluation"] = _evaluate_models(train, validation)
        report["reproducibility"]["model_parameters"] = {
            model["model_name"]: model["params"] for model in report["baseline_evaluation"].get("models", [])
        }
        report["secondary_student_group_robustness"] = _secondary_grouped_robustness(eligible)
    else:
        report["readiness_state"] = "ready_for_evaluation"
        report["state"] = "READY_FOR_EVALUATION"
        report["baseline_evaluation"] = {
            "status": "not_run",
            "reason": "Model evaluation is not run by the readiness monitoring endpoint.",
            "models": [],
        }
    return report


def build_training_readiness_report(
    connection,
    subject=None,
    *,
    minimum_eligible_snapshots=MIN_ELIGIBLE_ROWS,
    run_baseline_evaluation=True,
):
    """Build a privacy-safe readiness report from the canonical production dataset."""
    dataset = build_training_dataset(connection, subject=subject, include_ineligible=True)
    if dataset is None or dataset.empty:
        return {
            "TRAINING_READINESS_VERSION": TRAINING_READINESS_VERSION,
            "FEATURE_CONTRACT_VERSION": FEATURE_CONTRACT_VERSION,
            "subject": subject,
            "training_ready": False,
            "evaluation_ready": False,
            "deployment_ready": False,
            "readiness_state": "pipeline_only",
            "state": "PIPELINE_ONLY",
            "blockers": ["empty_dataset"],
            "eligible_training_snapshots": 0,
            "unique_students": 0,
            "unique_target_dates": 0,
            "subjects_represented": 0,
            "classes_represented": 0,
            "privacy_safe_summary": _compute_aggregate_summary(dataset),
            "eligible_training_snapshots": 0,
            "unique_students": 0,
            "unique_target_dates": 0,
            "subjects_represented": 0,
            "classes_represented": 0,
            "secondary_student_group_robustness": {
                "status": "skipped",
                "reason": "No dataset available.",
                "n_groups": 0,
                "n_splits": 0,
                "results": {},
            },
        }

    eligible_dataset = dataset[dataset["eligible_for_prediction"]].copy() if "eligible_for_prediction" in dataset.columns else dataset.copy()
    if eligible_dataset.empty:
        return {
            "TRAINING_READINESS_VERSION": TRAINING_READINESS_VERSION,
            "FEATURE_CONTRACT_VERSION": FEATURE_CONTRACT_VERSION,
            "subject": subject,
            "training_ready": False,
            "evaluation_ready": False,
            "deployment_ready": False,
            "readiness_state": "insufficient_data",
            "state": "INSUFFICIENT_DATA",
            "blockers": ["empty_eligible_dataset"],
            "privacy_safe_summary": _compute_aggregate_summary(eligible_dataset),
            "eligible_training_snapshots": 0,
            "unique_students": 0,
            "unique_target_dates": 0,
            "subjects_represented": 0,
            "classes_represented": 0,
            "eligible_training_snapshots": 0,
            "unique_students": 0,
            "unique_target_dates": 0,
            "subjects_represented": 0,
            "classes_represented": 0,
            "secondary_student_group_robustness": {
                "status": "skipped",
                "reason": "No eligible rows for grouped robustness checking.",
                "n_groups": 0,
                "n_splits": 0,
                "results": {},
            },
        }

    report = evaluate_training_dataset(
        eligible_dataset,
        subject=subject,
        run_baseline_evaluation=run_baseline_evaluation,
    )
    report["all_dataset_summary"] = _compute_aggregate_summary(dataset)
    if not dataset["eligible_for_prediction"].all() if "eligible_for_prediction" in dataset.columns else False:
        report["blockers"] = sorted(set(report.get("blockers", [])) | {"ineligible_rows_present"})
    return report


def build_admin_training_readiness_report(connection):
    """Build the admin-safe Phase 8 response from canonical Phase 7 readiness."""
    phase7 = build_training_readiness_report(
        connection,
        run_baseline_evaluation=False,
    )
    summary = phase7.get("privacy_safe_summary") or {}
    eligible_snapshots = int(
        phase7.get("eligible_training_snapshots", summary.get("eligible_rows", 0)) or 0
    )
    unique_students = int(phase7.get("unique_students", summary.get("unique_students", 0)) or 0)
    unique_target_dates = int(
        phase7.get("unique_target_dates", summary.get("unique_target_dates", 0)) or 0
    )
    evaluation_ready = bool(phase7.get("evaluation_ready"))

    progress = {
        "eligible_snapshots": {
            "current": eligible_snapshots,
            "required": MIN_ELIGIBLE_ROWS,
            "met": eligible_snapshots >= MIN_ELIGIBLE_ROWS,
            "available": True,
        },
        "unique_students": {
            "current": unique_students,
            "required": MIN_UNIQUE_STUDENTS,
            "met": unique_students >= MIN_UNIQUE_STUDENTS,
            "available": True,
        },
        "unique_target_dates": {
            "current": unique_target_dates,
            "required": MIN_UNIQUE_TARGET_DATES,
            "met": unique_target_dates >= MIN_UNIQUE_TARGET_DATES,
            "available": True,
        },
        "validation_rows": {
            "current": int(phase7["validation_rows"]) if evaluation_ready else None,
            "required": MIN_VALIDATION_ROWS,
            "met": bool(evaluation_ready and phase7["validation_rows"] >= MIN_VALIDATION_ROWS),
            "available": evaluation_ready,
        },
        "validation_students": {
            "current": int(phase7["validation_students"]) if evaluation_ready else None,
            "required": MIN_VALIDATION_STUDENTS,
            "met": bool(evaluation_ready and phase7["validation_students"] >= MIN_VALIDATION_STUDENTS),
            "available": evaluation_ready,
        },
    }

    state = phase7.get("readiness_state", "pipeline_only")
    state_explanations = {
        "pipeline_only": "The feature pipeline is available, but no eligible historical training snapshots exist yet.",
        "insufficient_data": "Some genuine evidence exists, but one or more Phase 7 data or temporal validation gates are not met.",
        "data_quality_blocked": "The available dataset has a structural or data-quality issue that must be resolved at its source.",
        "ready_for_evaluation": "The Phase 7 data and temporal holdout gates are met. This monitoring request did not run model evaluation.",
        "evaluation_ready": "The Phase 7 data and temporal holdout gates are met.",
        "evaluated_not_deployed": "Evaluation has been completed, but deployment is a separate later-phase decision.",
    }
    blocker_messages = {
        "empty_dataset": "No valid scored paper-assessment target rows exist yet; no eligible historical training snapshots are available.",
        "empty_eligible_dataset": "Scored targets exist, but none has earlier qualifying quiz or paper evidence for the same student, class, and subject.",
        "ineligible_rows_present": "Some source assessment rows do not meet the historical snapshot eligibility rules.",
        "insufficient_temporal_validation": "Not enough historical target dates, validation rows, or validation students are available for a time-safe holdout.",
        "missing_feature_columns": "The canonical feature dataset is missing required model features.",
        "missing_required_metadata": "The canonical feature dataset is missing required assessment metadata.",
        "non_finite_features": "One or more model features are not finite numeric values.",
        "non_finite_target": "One or more assessment targets are not finite numeric values.",
        "invalid_target_range": "One or more assessment targets fall outside the valid 0 to 100 range.",
        "missing_target_dates": "One or more target assessments do not have a valid date.",
        "duplicate_snapshot_identity": "The source data contains duplicate historical snapshot identities.",
    }
    blocker_codes = [str(code) for code in phase7.get("blockers", [])]
    messages = [blocker_messages[code] for code in blocker_codes if code in blocker_messages]
    for key, label in (
        ("eligible_snapshots", "eligible historical snapshots"),
        ("unique_students", "students with eligible snapshots"),
        ("unique_target_dates", "distinct eligible target dates"),
    ):
        gate = progress[key]
        if gate["available"] and not gate["met"]:
            messages.append(f"The {label} gate is not met ({gate['current']} of {gate['required']}).")
    if not evaluation_ready:
        messages.append("Validation coverage becomes measurable once enough historical target dates exist for a temporal holdout.")

    safe_blockers = [code for code in blocker_codes if code in blocker_messages]
    return {
        "readiness": {
            "state": state,
            "state_explanation": state_explanations.get(state, "The dataset has not passed all Phase 7 readiness checks."),
            "training_ready": bool(phase7.get("training_ready")),
            "evaluation_ready": evaluation_ready,
            "deployment_ready": False,
            "blockers": safe_blockers,
            "blocker_messages": list(dict.fromkeys(messages)),
            "warnings": [],
        },
        "progress": progress,
        "source_evidence": build_source_evidence_summary(connection),
        "guidance": [
            "Eligible historical snapshots require a scored paper assessment with earlier quiz or paper evidence for the same student, class, and subject.",
            "Genuine quiz activity can contribute evidence for a later paper assessment; quiz attempts alone are not eligible training snapshots.",
            "Teachers should record and publish valid paper assessment scores as part of normal academic activity.",
            "Evidence must accumulate across multiple students and distinct target assessment dates.",
            "Attendance alone does not make a historical snapshot academically eligible.",
        ],
    }


def repository_root():
    return Path(__file__).resolve().parents[3]


def _connect_runtime():
    import MySQLdb
    from MySQLdb.cursors import DictCursor

    load_dotenv(_repo_root() / ".env")
    return MySQLdb.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER", "siksha_user"),
        passwd=os.getenv("MYSQL_PASSWORD", ""),
        db=os.getenv("MYSQL_DB", "siksha_sarathi"),
        cursorclass=DictCursor,
        autocommit=True,
    )


def main():
    parser = argparse.ArgumentParser(description="Assess whether the local Siksha Sarathi dataset is ready for training/evaluation in Phase 7.")
    parser.add_argument("--subject", help="Optional subject filter.")
    parser.add_argument("--json", help="Optional privacy-safe JSON report output path.")
    args = parser.parse_args()

    connection = _connect_runtime()
    try:
        report = build_training_readiness_report(connection, subject=args.subject)
        print(json.dumps({
            "TRAINING_READINESS_VERSION": report.get("TRAINING_READINESS_VERSION"),
            "FEATURE_CONTRACT_VERSION": report.get("FEATURE_CONTRACT_VERSION"),
            "subject": report.get("subject"),
            "training_ready": report.get("training_ready"),
            "evaluation_ready": report.get("evaluation_ready"),
            "deployment_ready": report.get("deployment_ready"),
            "readiness_state": report.get("readiness_state"),
            "blockers": report.get("blockers", []),
            "privacy_safe_summary": report.get("privacy_safe_summary", {}),
            "secondary_student_group_robustness": report.get("secondary_student_group_robustness", {}),
            "baseline_evaluation": report.get("baseline_evaluation", {}),
        }, sort_keys=True, default=str))

        if args.json:
            out_path = Path(args.json)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "TRAINING_READINESS_VERSION": report.get("TRAINING_READINESS_VERSION"),
                "FEATURE_CONTRACT_VERSION": report.get("FEATURE_CONTRACT_VERSION"),
                "subject": report.get("subject"),
                "training_ready": report.get("training_ready"),
                "evaluation_ready": report.get("evaluation_ready"),
                "deployment_ready": report.get("deployment_ready"),
                "readiness_state": report.get("readiness_state"),
                "blockers": report.get("blockers", []),
                "privacy_safe_summary": report.get("privacy_safe_summary", {}),
                "secondary_student_group_robustness": report.get("secondary_student_group_robustness", {}),
                "baseline_evaluation": report.get("baseline_evaluation", {}),
            }
            out_path.write_text(json.dumps(payload, sort_keys=True, default=str), encoding="utf-8")
            print(f"Wrote privacy-safe readiness JSON to {args.json}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
