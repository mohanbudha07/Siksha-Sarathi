"""Safe, idempotent monitoring audit recording for served production forecasts."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

AUDIT_IDENTITY_FIELDS = (
    "student_id",
    "class_id",
    "subject",
    "as_of_date",
    "model_version",
)


def normalize_audit_subject(value):
    """Normalize the subject used in audit identity as a deterministic, stable key."""
    if value is None:
        return ""
    return str(value).strip().lower()


def normalize_audit_model_version(value):
    """Normalize model version so blank values are rejected before insert."""
    if value is None:
        return ""
    return str(value).strip()


def _fetch_scalar(cursor):
    try:
        row = cursor.fetchone()
    except Exception:
        return None
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()), None)
    if isinstance(row, (tuple, list)):
        return row[0] if row else None
    return row


def _safe_float(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _manifest_field(manifest, *keys):
    if not isinstance(manifest, dict):
        return None
    current = manifest
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _connection_is_sqlite(connection):
    if connection is None:
        return False
    if hasattr(connection, "connection"):
        candidate = getattr(connection, "connection")
        if candidate is not None and hasattr(candidate, "execute"):
            return "sqlite3" in str(type(candidate)).lower() or "sqlite" in str(type(candidate)).lower()
    return "sqlite3" in str(type(connection)).lower() or "sqlite" in str(type(connection)).lower()


def record_prediction_audit(
    connection,
    teacher_user_id,
    student_id,
    class_id,
    subject,
    as_of_date,
    prediction_result,
    validated_manifest,
    model_version=None,
):
    """Persist a single immutable audit row for a valid production forecast.

    The insert is intentionally idempotent by logical identity and fail-closed for
    any non-valid prediction state. Only safe metadata is persisted; raw features,
    evidence payloads, and artifact paths are never stored.
    """
    if not isinstance(prediction_result, dict):
        return {"recorded": False, "reason": "invalid_prediction_result"}

    status = prediction_result.get("status")
    if status != "prediction_available":
        return {"recorded": False, "reason": "not_prediction_available"}

    prediction_percent = _safe_float(prediction_result.get("prediction_percent"))
    if prediction_percent is None or prediction_percent < 0.0 or prediction_percent > 100.0:
        return {"recorded": False, "reason": "invalid_prediction_percent"}

    safe_model_version = normalize_audit_model_version(model_version or prediction_result.get("model_version"))
    if not safe_model_version:
        return {"recorded": False, "reason": "missing_model_version"}

    normalized_subject = normalize_audit_subject(subject)
    if not normalized_subject:
        return {"recorded": False, "reason": "missing_subject"}

    validation_metrics = validated_manifest.get("validation_metrics") if isinstance(validated_manifest, dict) else {}
    validation_mae = _safe_float(validation_metrics.get("mae")) if isinstance(validation_metrics, dict) else None
    training_timestamp = validated_manifest.get("training_timestamp") if isinstance(validated_manifest, dict) else None

    row = {
        "student_id": int(student_id),
        "teacher_user_id": int(teacher_user_id),
        "class_id": int(class_id),
        "subject": normalized_subject,
        "as_of_date": str(as_of_date),
        "prediction_status": status,
        "prediction_percent": float(prediction_percent),
        "fallback": prediction_result.get("fallback"),
        "reason": prediction_result.get("reason"),
        "model_version": str(safe_model_version),
        "model_type": None,
        "artifact_version": None,
        "feature_contract_version": None,
        "validation_mae": validation_mae,
        "model_training_timestamp": training_timestamp,
    }

    if isinstance(validated_manifest, dict):
        row["model_type"] = validated_manifest.get("model_type")
        row["artifact_version"] = validated_manifest.get("artifact_version")
        row["feature_contract_version"] = validated_manifest.get("feature_contract_version")
        row["model_training_timestamp"] = validated_manifest.get("training_timestamp")

    sqlite_mode = _connection_is_sqlite(connection)
    cursor = None
    try:
        cursor = connection.cursor()
        select_sql = (
            "SELECT 1 FROM ml_prediction_audits "
            "WHERE student_id = ? AND class_id = ? AND subject = ? "
            "AND as_of_date = ? AND model_version = ? LIMIT 1"
            if sqlite_mode else
            "SELECT 1 FROM ml_prediction_audits "
            "WHERE student_id = %s AND class_id = %s AND subject = %s "
            "AND as_of_date = %s AND model_version = %s LIMIT 1"
        )
        cursor.execute(
            select_sql,
            (
                row["student_id"],
                row["class_id"],
                row["subject"],
                row["as_of_date"],
                row["model_version"],
            ),
        )
        if _fetch_scalar(cursor) is not None:
            return {"recorded": False, "reason": "already_recorded"}

        insert_sql = (
            "INSERT OR IGNORE INTO ml_prediction_audits ("
            "student_id, teacher_user_id, class_id, subject, as_of_date, prediction_status, "
            "prediction_percent, fallback, reason, model_version, model_type, artifact_version, "
            "feature_contract_version, validation_mae, model_training_timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            if sqlite_mode else
            "INSERT IGNORE INTO ml_prediction_audits ("
            "student_id, teacher_user_id, class_id, subject, as_of_date, prediction_status, "
            "prediction_percent, fallback, reason, model_version, model_type, artifact_version, "
            "feature_contract_version, validation_mae, model_training_timestamp) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        cursor.execute(
            insert_sql,
            (
                row["student_id"],
                row["teacher_user_id"],
                row["class_id"],
                row["subject"],
                row["as_of_date"],
                row["prediction_status"],
                row["prediction_percent"],
                row["fallback"],
                row["reason"],
                row["model_version"],
                row["model_type"],
                row["artifact_version"],
                row["feature_contract_version"],
                row["validation_mae"],
                row["model_training_timestamp"],
            ),
        )
        if sqlite_mode:
            cursor.execute("SELECT changes()")
            inserted = (_fetch_scalar(cursor) or 0) > 0
        else:
            inserted = getattr(cursor, "rowcount", 0) > 0
        if not inserted:
            return {"recorded": False, "reason": "already_recorded"}
        connection.commit()
        return {"recorded": True, "reason": "created"}
    except Exception as exc:
        try:
            connection.rollback()
        except Exception:
            pass
        message = str(exc).lower()
        if "duplicate" in message or "unique" in message or "uq_ml_prediction_audit_identity" in message:
            return {"recorded": False, "reason": "already_recorded"}
        return {"recorded": False, "reason": "audit_write_failed"}
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass

    return {"recorded": False, "reason": "audit_write_failed"}
