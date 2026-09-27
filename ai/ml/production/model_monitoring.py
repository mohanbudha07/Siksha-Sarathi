"""Safe, truthful monitoring for future production ML artifacts.

This module intentionally never fabricates a model, readiness claim, or
retraining recommendation. It reports only the real current state: either no
validated production artifact exists, or a real artifact manifest is available.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Dict, Optional

MODEL_MONITORING_VERSION = "1"
MIN_MONITORING_OUTCOMES = 20
MIN_MONITORING_STUDENTS = 10
MIN_SUBJECT_MONITORING_OUTCOMES = 10
RELATIVE_MAE_DEGRADATION_TRIGGER = 0.25
MODEL_STALE_DAYS = 180


def _safe_manifest_value(manifest, key, default=None):
    if not isinstance(manifest, dict):
        return default
    value = manifest.get(key)
    return default if value is None else value


def _parse_iso_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            normalized = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def _safe_float(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _normalize_subject(value):
    return str(value or "").strip().lower()


def calculate_actual_percent(marks_obtained, max_marks):
    """Compute a valid actual percentage only when marks and maximum are finite."""
    marks = _safe_float(marks_obtained)
    maximum = _safe_float(max_marks)
    if marks is None or maximum is None or maximum <= 0:
        return None
    percent = 100.0 * marks / maximum
    if not math.isfinite(percent) or percent < 0.0 or percent > 100.0:
        return None
    return percent


def choose_next_assessment_for_audit(audit_row, paper_rows):
    """Return the earliest later published assessment that qualifies for monitoring."""
    if not isinstance(audit_row, dict):
        return {"state": "no_later_assessment", "assessment_id": None}
    as_of = _parse_iso_datetime(audit_row.get("as_of_date"))
    if as_of is None:
        return {"state": "no_later_assessment", "assessment_id": None}
    as_of_date = as_of.date() if hasattr(as_of, "date") else _coerce_date_value(audit_row.get("as_of_date"))
    student_id = audit_row.get("student_id")
    class_id = audit_row.get("class_id")
    subject = _normalize_subject(audit_row.get("subject"))
    candidates = []
    for paper in paper_rows or []:
        if not isinstance(paper, dict):
            continue
        paper_date = _coerce_date_value(paper.get("assessment_date"))
        if paper_date is None or paper_date <= as_of_date:
            continue
        if int(paper.get("student_id") or -1) != int(student_id or -1):
            continue
        if int(paper.get("class_id") or -1) != int(class_id or -1):
            continue
        if _normalize_subject(paper.get("subject")) != subject:
            continue
        if not bool(paper.get("is_published")):
            continue
        candidates.append(paper)
    if not candidates:
        return {"state": "no_later_assessment", "assessment_id": None}
    chosen = min(candidates, key=lambda row: (_coerce_date_value(row.get("assessment_date")) or date.max, int(row.get("id") or 0)))
    chosen_id = chosen.get("id")
    student_score = None
    for row in paper_rows or []:
        if not isinstance(row, dict):
            continue
        if int(row.get("assessment_id") or -1) == int(chosen_id or -1) and int(row.get("student_id") or -1) == int(student_id or -1):
            student_score = row
            break
    if student_score is None:
        return {"state": "pending_score", "assessment_id": chosen_id}
    if bool(student_score.get("is_absent")):
        return {"state": "absent", "assessment_id": chosen_id}
    actual = calculate_actual_percent(student_score.get("marks_obtained"), student_score.get("max_marks"))
    if actual is None:
        return {"state": "pending_score", "assessment_id": chosen_id}
    return {"state": "matched", "assessment_id": chosen_id, "actual_percent": actual}


def _coerce_date_value(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def build_monitoring_observations(audit_rows, paper_rows, outcome_rows):
    """Create normalized monitoring observations while keeping the model-version boundary intact."""
    observations = []
    by_assessment_model = {}
    for audit in audit_rows or []:
        if not isinstance(audit, dict):
            continue
        if audit.get("prediction_status") != "prediction_available":
            continue
        prediction_value = _safe_float(audit.get("prediction_percent"))
        if prediction_value is None or prediction_value < 0.0 or prediction_value > 100.0:
            continue
        subject = _normalize_subject(audit.get("subject"))
        if not subject:
            continue
        candidate = choose_next_assessment_for_audit(audit, paper_rows or [])
        state = candidate.get("state")
        if state == "matched":
            actual_percent = _safe_float(candidate.get("actual_percent"))
            if actual_percent is None:
                continue
            error = prediction_value - actual_percent
            observation = {
                "student_id": int(audit.get("student_id") or 0),
                "subject": subject,
                "model_version": str(audit.get("model_version") or "unknown"),
                "assessment_id": int(candidate.get("assessment_id") or 0),
                "prediction_percent": prediction_value,
                "actual_percent": actual_percent,
                "error": error,
                "outcome_state": "matched",
                "as_of_date": audit.get("as_of_date"),
            }
            key = (observation["student_id"], observation["assessment_id"], observation["model_version"])
            current = by_assessment_model.get(key)
            if current is None or _coerce_date_value(observation["as_of_date"]) > _coerce_date_value(current["as_of_date"]):
                by_assessment_model[key] = observation
        elif state in {"pending_score", "absent", "no_later_assessment"}:
            observations.append({
                "student_id": int(audit.get("student_id") or 0),
                "subject": subject,
                "model_version": str(audit.get("model_version") or "unknown"),
                "assessment_id": candidate.get("assessment_id"),
                "outcome_state": state,
                "prediction_percent": prediction_value,
            })
    observations.extend(by_assessment_model.values())
    return sorted(observations, key=lambda item: (item.get("subject") or "", item.get("student_id") or 0, item.get("assessment_id") or 0, item.get("model_version") or ""))


def calculate_monitoring_metrics(observations):
    """Compute aggregate dense metrics for valid numeric outcomes."""
    numeric = [item["error"] for item in observations if isinstance(item, dict) and "error" in item and _safe_float(item.get("error")) is not None]
    if not numeric:
        return {
            "observation_count": 0,
            "unique_student_count": 0,
            "mae": None,
            "rmse": None,
            "mean_signed_error": None,
        }
    errors = [float(value) for value in numeric]
    unique_students = len({int(item.get("student_id")) for item in observations if item.get("student_id") is not None and "error" in item})
    mae = sum(abs(error) for error in errors) / len(errors)
    rmse = math.sqrt(sum(error * error for error in errors) / len(errors))
    mean_signed_error = sum(errors) / len(errors)
    return {
        "observation_count": len(errors),
        "unique_student_count": unique_students,
        "mae": mae,
        "rmse": rmse,
        "mean_signed_error": mean_signed_error,
    }


def evaluate_monitoring_dataset(observations, validation_mae=None, model_training_timestamp=None, reference_date=None, training_ready=False, evaluation_ready=False):
    """Return the review signal and readiness summary used by the monitoring contract."""
    metrics = calculate_monitoring_metrics(observations)
    numeric_validation_mae = _safe_float(validation_mae)
    reference_day = reference_date or date.today()
    if isinstance(reference_day, datetime):
        reference_day = reference_day.date()
    if isinstance(model_training_timestamp, str):
        training_dt = _parse_iso_datetime(model_training_timestamp)
    else:
        training_dt = model_training_timestamp
    age_days = None
    if training_dt is not None:
        if hasattr(training_dt, "date"):
            training_day = training_dt.date()
        else:
            training_day = _coerce_date_value(training_dt)
        if training_day is not None:
            age_days = (reference_day - training_day).days
    monitoring_evidence_sufficient = (
        metrics["observation_count"] >= MIN_MONITORING_OUTCOMES and metrics["unique_student_count"] >= MIN_MONITORING_STUDENTS
    )
    performance_review_needed = False
    if monitoring_evidence_sufficient and numeric_validation_mae is not None and numeric_validation_mae > 0 and metrics["mae"] is not None:
        threshold = numeric_validation_mae * (1.0 + RELATIVE_MAE_DEGRADATION_TRIGGER)
        performance_review_needed = metrics["mae"] > threshold
    staleness_review_needed = age_days is not None and age_days > MODEL_STALE_DAYS
    retraining_data_ready = bool(training_ready and evaluation_ready)
    retraining_review_recommended = retraining_data_ready and (performance_review_needed or staleness_review_needed)
    return {
        "metrics": metrics,
        "monitoring_evidence_sufficient": monitoring_evidence_sufficient,
        "performance_review_needed": performance_review_needed,
        "staleness_review_needed": staleness_review_needed,
        "retraining_data_ready": retraining_data_ready,
        "retraining_review_recommended": retraining_review_recommended,
        "model_age_days": age_days,
        "validation_mae": numeric_validation_mae,
        "reference_date": str(reference_day),
    }


def build_model_monitoring_report(load_result, as_of_date=None):
    """Return a truthful monitoring snapshot for the current production state."""
    if load_result is None:
        return {
            "monitoring_version": MODEL_MONITORING_VERSION,
            "status": "model_unavailable",
            "available": False,
            "model_loaded": False,
            "reason": "no validated production artifact is available",
            "fallback": "observed_analytics",
            "retraining_required": False,
            "evaluation_window_days": None,
            "staleness_days": None,
            "artifact_version": None,
            "model_type": None,
            "feature_contract_version": None,
            "training_timestamp": None,
            "validation_metrics": {},
            "as_of_date": str(as_of_date) if as_of_date is not None else None,
        }

    manifest = getattr(load_result, "manifest", None) or {}
    status = getattr(load_result, "status", "model_unavailable")
    available = bool(getattr(load_result, "available", False))
    report = {
        "monitoring_version": MODEL_MONITORING_VERSION,
        "status": status if status == "prediction_available" else "model_unavailable",
        "available": available,
        "model_loaded": available,
        "reason": (
            "production artifact is available and ready for monitoring"
            if available
            else "no validated production artifact is available"
        ),
        "fallback": "observed_analytics",
        "retraining_required": False,
        "evaluation_window_days": None,
        "staleness_days": None,
        "artifact_version": _safe_manifest_value(manifest, "artifact_version"),
        "model_type": _safe_manifest_value(manifest, "model_type"),
        "feature_contract_version": _safe_manifest_value(manifest, "feature_contract_version"),
        "training_timestamp": _safe_manifest_value(manifest, "training_timestamp"),
        "validation_metrics": _safe_manifest_value(manifest, "validation_metrics", {}),
        "as_of_date": str(as_of_date) if as_of_date is not None else None,
    }

    if available and report["training_timestamp"]:
        timestamp = _parse_iso_datetime(report["training_timestamp"])
        if timestamp is not None and as_of_date is not None:
            if isinstance(as_of_date, datetime):
                as_of = as_of_date
            else:
                as_of = _parse_iso_datetime(str(as_of_date))
            if as_of is not None:
                if timestamp.tzinfo is None and as_of.tzinfo is not None:
                    timestamp = timestamp.replace(tzinfo=as_of.tzinfo)
                elif timestamp.tzinfo is not None and as_of.tzinfo is None:
                    as_of = as_of.replace(tzinfo=timestamp.tzinfo)
                delta_days = (as_of - timestamp).days
                report["staleness_days"] = max(0, delta_days)
                report["evaluation_window_days"] = max(0, delta_days)

    if not available:
        report["validation_metrics"] = {}
        report["artifact_version"] = None
        report["model_type"] = None
        report["feature_contract_version"] = None
        report["training_timestamp"] = None

    return report


def summarize_monitoring_status(load_result, monitored_metrics=None, as_of_date=None):
    """Present a read-only summary without claiming any model health beyond reality."""
    report = build_model_monitoring_report(load_result, as_of_date=as_of_date)
    metrics = monitored_metrics or {}
    if report["available"] and isinstance(metrics, dict):
        report["observed_metrics"] = dict(metrics)
        report["validation_metrics"] = {key: value for key, value in metrics.items() if isinstance(key, str)}
    else:
        report["observed_metrics"] = {}
        report["validation_metrics"] = {}

    if not report["available"]:
        report["status"] = "model_unavailable"
        report["retraining_required"] = False
        report["monitoring_state"] = "no_model"
        return report

    report["monitoring_state"] = "artifact_present"
    report["retraining_required"] = False
    return report
