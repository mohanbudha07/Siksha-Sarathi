"""Time-safe feature extraction for the next-paper prediction contract.

Calendar-date cutoffs intentionally exclude same-day evidence because precise
event timing is not consistently available across the source tables.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from ai.ml.evaluate_school_outcomes import day, recorded_before
from ai.ml.production.feature_contract import (
    METADATA_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    OUTPUT_COLUMNS,
    TARGET_COLUMN,
)


def _as_date(value):
    if value is None:
        return None
    if hasattr(value, "date"):
        return value.date()
    if isinstance(value, str):
        value = value[:10]
        try:
            return pd.to_datetime(value).date()
        except Exception:
            return None
    return pd.to_datetime(value).date()


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_percent(numerator, denominator):
    if denominator in (None, 0):
        return 0.0
    return round(100.0 * float(numerator) / float(denominator), 2)


def _eligibility_for_evidence(target_day, quiz_attempt_count, prior_paper_count):
    """Apply the academic-evidence eligibility rule in one place."""
    if target_day is None:
        return False, "missing_target_date"
    academic_evidence_count = quiz_attempt_count + prior_paper_count
    if academic_evidence_count < 1:
        return False, "insufficient_academic_evidence"
    return True, ""


def _normalize_row(row):
    if hasattr(row, "keys"):
        return dict(row)
    if isinstance(row, dict):
        return row
    return dict(row)


def _fetch_table_columns(connection, table_name):
    try:
        cursor = connection.cursor()
        try:
            pragma = cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in pragma.fetchall()]
            return set(columns)
        finally:
            cursor.close()
    except Exception:
        return set()


def _scalar_query(connection, query):
    cursor = connection.cursor()
    try:
        cursor.execute(query)
        row = cursor.fetchone()
        if row is None:
            return 0
        if hasattr(row, "keys"):
            return row[list(row.keys())[0]]
        return row[0]
    except Exception:
        return 0
    finally:
        cursor.close()


def _database_counts(connection):
    return {
        "total_db_students": int(_scalar_query(connection, "SELECT COUNT(*) FROM students")),
        "total_db_classes": int(_scalar_query(connection, "SELECT COUNT(*) FROM classes")),
        "subject_catalog_rows": int(_scalar_query(connection, "SELECT COUNT(*) FROM subjects")),
    }


def _readiness_breakdown(training):
    if training.empty:
        return {
            "students_with_evidence": 0,
            "unique_eligible_students": 0,
            "snapshots_per_eligible_student": {},
            "subjects_represented": [],
            "classes_represented": [],
            "target_assessment_dates_represented": [],
            "eligible_snapshots_by_subject": {},
            "eligible_snapshots_by_class": {},
            "eligible_snapshots_by_target_date": {},
            "evidence_presence_counts": {
                "quiz": 0,
                "prior_paper": 0,
                "attendance": 0,
            },
            "readiness_level": "PIPELINE ONLY",
        }

    eligible = training[training["eligible_for_prediction"]]
    students_with_evidence = int(training["student_id"].nunique())
    eligible_student_counts = eligible["student_id"].value_counts().sort_index()
    subject_counts = eligible["subject"].value_counts().sort_index()
    class_counts = eligible["target_class_id"].value_counts().sort_index()
    date_values = training["target_assessment_date"].map(str)
    eligible_date_counts = date_values[eligible.index].value_counts().sort_index()
    readiness_level = "PIPELINE ONLY" if eligible.empty else "DATA AVAILABLE; REVIEW DIVERSITY"
    return {
        "students_with_evidence": students_with_evidence,
        "unique_eligible_students": int(eligible["student_id"].nunique()),
        "snapshots_per_eligible_student": {
            str(student_id): int(count)
            for student_id, count in eligible_student_counts.items()
        },
        "subjects_represented": sorted(str(value) for value in training["subject"].dropna().unique()),
        "classes_represented": sorted(int(value) for value in training["target_class_id"].dropna().unique()),
        "target_assessment_dates_represented": sorted(date_values.unique().tolist()),
        "eligible_snapshots_by_subject": {
            str(subject): int(count) for subject, count in subject_counts.items()
        },
        "eligible_snapshots_by_class": {
            str(class_id): int(count) for class_id, count in class_counts.items()
        },
        "eligible_snapshots_by_target_date": {
            str(target_date): int(count) for target_date, count in eligible_date_counts.items()
        },
        "evidence_presence_counts": {
            "quiz": int(training["has_quiz_evidence"].sum()),
            "prior_paper": int(training["has_prior_paper_evidence"].sum()),
            "attendance": int(training["has_attendance_evidence"].sum()),
        },
        "readiness_level": readiness_level,
    }


def _is_valid_target_assessment(row):
    if row is None:
        return False
    if row.get("is_absent") in (1, True, "1", "true"):
        return False
    marks = row.get("marks_obtained")
    max_marks = row.get("max_marks")
    if marks is None or max_marks in (None, 0):
        return False
    try:
        if float(marks) < 0:
            return False
        if float(max_marks) <= 0:
            return False
        if float(marks) > float(max_marks):
            return False
    except (TypeError, ValueError):
        return False
    return True


def _prior_papers_for_target(target_row, paper_rows):
    subject = str(target_row.get("subject") or "").strip()
    student_id = int(target_row["student_id"])
    class_id = int(target_row["class_id"])
    target_day = _as_date(target_row.get("assessment_date"))
    prior = []
    for row in paper_rows:
        row = _normalize_row(row)
        if int(row.get("student_id")) != student_id:
            continue
        if int(row.get("class_id")) != class_id:
            continue
        if str(row.get("subject") or "").strip() != subject:
            continue
        if int(row.get("assessment_id")) == int(target_row["assessment_id"]):
            continue
        if not _is_valid_target_assessment(row):
            continue
        if _as_date(row.get("assessment_date")) is None:
            continue
        if _as_date(row.get("assessment_date")) >= target_day:
            continue
        if not recorded_before(row, target_day):
            continue
        prior.append(row)
    return prior


def _prior_quizzes_for_target(target_row, quiz_rows):
    subject = str(target_row.get("subject") or "").strip()
    student_id = int(target_row["student_id"])
    class_id = int(target_row["class_id"])
    target_day = _as_date(target_row.get("assessment_date"))
    previous = []
    for row in quiz_rows:
        row = _normalize_row(row)
        if int(row.get("student_id")) != student_id:
            continue
        if int(row.get("class_id")) != class_id:
            continue
        if str(row.get("subject") or "").strip() != subject:
            continue
        created = _as_date(row.get("created_at"))
        if created is None:
            continue
        if created >= target_day:
            continue
        total_questions = int(row.get("total_questions") or 0)
        if total_questions <= 0:
            continue
        if row.get("score") is None:
            continue
        previous.append(row)
    return previous


def _prior_question_evidence_for_target(target_row, question_rows):
    subject = str(target_row.get("subject") or "").strip()
    student_id = int(target_row["student_id"])
    class_id = int(target_row["class_id"])
    target_day = _as_date(target_row.get("assessment_date"))
    previous = []
    for row in question_rows:
        row = _normalize_row(row)
        if int(row.get("student_id")) != student_id:
            continue
        if int(row.get("class_id")) != class_id:
            continue
        if str(row.get("subject") or "").strip() != subject:
            continue
        created = _as_date(row.get("created_at"))
        if created is None:
            continue
        if created >= target_day:
            continue
        previous.append(row)
    return previous


def _prior_attendance_for_target(target_row, attendance_rows):
    subject = str(target_row.get("subject") or "").strip()
    student_id = int(target_row["student_id"])
    class_id = int(target_row["class_id"])
    target_day = _as_date(target_row.get("assessment_date"))
    previous = []
    for row in attendance_rows:
        row = _normalize_row(row)
        if int(row.get("student_id")) != student_id:
            continue
        if int(row.get("class_id")) != class_id:
            continue
        month_start = _as_date(row.get("attendance_month"))
        if month_start is None:
            continue
        if month_start >= target_day:
            continue
        if not recorded_before(row, target_day):
            continue
        previous.append(row)
    return previous


def _build_feature_row(target_row, paper_rows, quiz_rows, question_rows, attendance_rows):
    """Build one production feature snapshot using only evidence from before T."""
    target_row = _normalize_row(target_row)
    target_student_id = int(target_row["student_id"])
    target_class_id = int(target_row["class_id"])
    target_subject = str(target_row.get("subject") or "").strip()
    target_day = _as_date(target_row.get("assessment_date"))
    target_assessment_id = int(target_row["assessment_id"])
    target_marks = _safe_float(target_row.get("marks_obtained"), 0.0)
    target_max_marks = _safe_float(target_row.get("max_marks"), 0.0)
    if target_day is None:
        return {
            "student_id": target_student_id,
            "subject": target_subject,
            "target_assessment_id": target_assessment_id,
            "target_assessment_date": target_row.get("assessment_date"),
            "target_class_id": target_class_id,
            "target_max_marks": target_max_marks,
            "target_marks_obtained": target_marks,
            "eligible_for_prediction": False,
            "ineligible_reason": "missing_target_date",
            **{col: 0.0 for col in MODEL_FEATURE_COLUMNS},
            TARGET_COLUMN: 0.0,
        }

    prior_papers = _prior_papers_for_target(target_row, paper_rows)
    prior_quizzes = _prior_quizzes_for_target(target_row, quiz_rows)
    prior_question_rows = _prior_question_evidence_for_target(target_row, question_rows)
    prior_attendance = _prior_attendance_for_target(target_row, attendance_rows)

    prior_paper_count = len(prior_papers)
    prior_paper_percentages = [
        _safe_percent(float(p["marks_obtained"]), float(p["max_marks"]))
        for p in prior_papers
    ]
    prior_paper_average_percent = (
        sum(prior_paper_percentages) / len(prior_paper_percentages)
        if prior_paper_percentages else 0.0
    )
    latest_prior_paper_percent = prior_paper_percentages[-1] if prior_paper_percentages else 0.0

    quiz_attempt_count = len(prior_quizzes)
    quiz_percentages = [
        _safe_percent(float(q["score"]), float(q["total_questions"]))
        for q in prior_quizzes
    ]
    quiz_average_percent = (
        sum(quiz_percentages) / len(quiz_percentages) if quiz_percentages else 0.0
    )
    recent_quiz_average_percent = 0.0
    if quiz_percentages:
        recent_window = quiz_percentages[-min(3, len(quiz_percentages)):]
        recent_quiz_average_percent = sum(recent_window) / len(recent_window)

    incorrect_answers = sum(
        1
        for q in prior_question_rows
        if q.get("is_correct") in (0, False, "0") or q.get("is_skipped") in (1, True, "1")
    )
    skipped_count = sum(1 for q in prior_question_rows if q.get("is_skipped") in (1, True, "1"))
    total_question_rows = len(prior_question_rows)
    skipped_answer_rate = (
        _safe_percent(skipped_count, total_question_rows) if total_question_rows else 0.0
    )

    attendance_records = prior_attendance
    total_attendance_days = sum(int(r.get("total_school_days") or 0) for r in attendance_records)
    present_days = sum(int(r.get("present_days") or 0) for r in attendance_records)
    absent_days = sum(int(r.get("absent_days") or 0) for r in attendance_records)
    attendance_percent = _safe_percent(present_days, total_attendance_days)

    days_since_last_quiz = 0.0
    if prior_quizzes:
        latest_quiz_day = max(_as_date(q.get("created_at")) for q in prior_quizzes)
        days_since_last_quiz = (target_day - latest_quiz_day).days

    recent_evidence_count = len(prior_quizzes) + prior_paper_count + len(attendance_records)
    eligible, ineligible_reason = _eligibility_for_evidence(
        target_day,
        quiz_attempt_count,
        prior_paper_count,
    )

    feature_values = {
        "quiz_attempt_count": float(quiz_attempt_count),
        "quiz_average_percent": float(quiz_average_percent),
        "recent_quiz_average_percent": float(recent_quiz_average_percent),
        "has_quiz_evidence": float(bool(prior_quizzes)),
        "incorrect_answer_count": float(incorrect_answers),
        "skipped_answer_rate": float(skipped_answer_rate),
        "prior_paper_count": float(prior_paper_count),
        "prior_paper_average_percent": float(prior_paper_average_percent),
        "latest_prior_paper_percent": float(latest_prior_paper_percent),
        "has_prior_paper_evidence": float(bool(prior_papers)),
        "attendance_percent": float(attendance_percent),
        "absent_days": float(absent_days),
        "total_attendance_days": float(total_attendance_days),
        "has_attendance_evidence": float(bool(attendance_records)),
        "days_since_last_quiz": float(days_since_last_quiz),
        "recent_evidence_count": float(recent_evidence_count),
    }

    target_percent = _safe_percent(target_marks, target_max_marks)
    return {
        "student_id": target_student_id,
        "subject": target_subject,
        "target_assessment_id": target_assessment_id,
        "target_assessment_date": target_row.get("assessment_date"),
        "target_class_id": target_class_id,
        "target_max_marks": target_max_marks,
        "target_marks_obtained": target_marks,
        "eligible_for_prediction": eligible,
        "ineligible_reason": ineligible_reason,
        **feature_values,
        TARGET_COLUMN: target_percent,
    }


def _fetch_evidence(connection):
    cursor = connection.cursor()
    question_columns = _fetch_table_columns(connection, "quiz_answer_results")
    try:
        cursor.execute(
            """
            SELECT pa.id AS assessment_id,
                   pa.class_id,
                   pa.subject,
                   pa.assessment_date,
                   pa.max_marks,
                   pa.is_published,
                   pas.student_id,
                   pas.marks_obtained,
                   pas.is_absent,
                   pas.created_at,
                   pas.updated_at
            FROM paper_assessments pa
            INNER JOIN paper_assessment_scores pas ON pas.assessment_id = pa.id
            ORDER BY pa.assessment_date, pa.id
            """
        )
        paper_rows = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT qr.id AS quiz_result_id,
                   qr.student_id,
                   qs.class_id,
                   q.subject,
                   qr.score,
                   qr.total_questions,
                   qr.created_at,
                   qr.quiz_session_id
            FROM quiz_results qr
            INNER JOIN quiz_sessions qs ON qs.id = qr.quiz_session_id
            INNER JOIN quizzes q ON q.id = qr.quiz_id
            ORDER BY qr.created_at, qr.id
            """
        )
        quiz_rows = [dict(row) for row in cursor.fetchall()]

        select_parts = [
            "qar.id AS answer_id",
            "qr.student_id",
            "qs.class_id",
            "q.subject",
            "qar.is_correct",
            "qar.is_skipped",
            "qar.created_at",
        ]
        if "question_index" in question_columns:
            select_parts.append("qar.question_index")
        if "question_text" in question_columns:
            select_parts.append("qar.question_text")
        if "topic" in question_columns:
            select_parts.append("qar.topic")
        query = (
            "SELECT " + ",\n".join(select_parts) + "\n"
            "FROM quiz_answer_results qar\n"
            "INNER JOIN quiz_results qr ON qr.id = qar.quiz_result_id\n"
            "INNER JOIN quiz_sessions qs ON qs.id = qr.quiz_session_id\n"
            "INNER JOIN quizzes q ON q.id = qr.quiz_id\n"
            "ORDER BY qar.created_at, qar.id"
        )
        cursor.execute(query)
        question_rows = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT mar.student_id,
                   mas.class_id,
                   mas.attendance_month,
                   mas.total_school_days,
                   mar.present_days,
                   (mas.total_school_days - mar.present_days) AS absent_days,
                   mas.created_at,
                   mas.updated_at,
                   mar.created_at AS record_created_at,
                   mar.updated_at AS record_updated_at
            FROM monthly_attendance_summaries mas
            INNER JOIN monthly_attendance_records mar ON mar.summary_id = mas.id
            ORDER BY mas.attendance_month, mar.student_id
            """
        )
        attendance_rows = [dict(row) for row in cursor.fetchall()]
    finally:
        cursor.close()
    return paper_rows, quiz_rows, question_rows, attendance_rows


def build_feature_row_for_target(connection, target_row):
    """Return one feature snapshot for a single target assessment row."""
    paper_rows, quiz_rows, question_rows, attendance_rows = _fetch_evidence(connection)
    return _build_feature_row(target_row, paper_rows, quiz_rows, question_rows, attendance_rows)


def build_training_dataset(connection, subject=None, include_ineligible=False):
    """Create a deterministic training feature DataFrame from real Siksha Sarathi data."""
    paper_rows, quiz_rows, question_rows, attendance_rows = _fetch_evidence(connection)
    target_rows = []
    for row in paper_rows:
        row = _normalize_row(row)
        if not _is_valid_target_assessment(row):
            continue
        if subject is not None and str(row.get("subject") or "").strip() != str(subject).strip():
            continue
        target_rows.append(row)

    rows = []
    for target_row in target_rows:
        feature_row = _build_feature_row(target_row, paper_rows, quiz_rows, question_rows, attendance_rows)
        if not include_ineligible and not feature_row["eligible_for_prediction"]:
            continue
        rows.append(feature_row)

    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        dataframe = pd.DataFrame(columns=OUTPUT_COLUMNS)
    else:
        dataframe = dataframe.reindex(columns=OUTPUT_COLUMNS)
    return dataframe


def count_feature_evidence(connection, subject=None):
    """Count dataset readiness and eligibility metrics for production ML diagnostics."""
    paper_rows, quiz_rows, question_rows, attendance_rows = _fetch_evidence(connection)
    if subject is not None:
        subject = str(subject).strip()
        paper_rows = [row for row in paper_rows if str(row.get("subject") or "").strip() == subject]
        quiz_rows = [row for row in quiz_rows if str(row.get("subject") or "").strip() == subject]
        question_rows = [row for row in question_rows if str(row.get("subject") or "").strip() == subject]
        attendance_rows = [row for row in attendance_rows if str(row.get("subject") or "") == ""]

    students = set()
    for row in paper_rows:
        students.add(int(row.get("student_id")))
    for row in quiz_rows:
        students.add(int(row.get("student_id")))
    for row in attendance_rows:
        students.add(int(row.get("student_id")))

    valid_targets = [
        row for row in paper_rows if _is_valid_target_assessment(row)
    ]
    training = build_training_dataset(connection, subject=subject, include_ineligible=True)
    eligible = int((training["eligible_for_prediction"]).fillna(False).sum()) if not training.empty else 0
    ineligible = len(training) - eligible
    if training.empty:
        reason_counts = {}
        targets_with_academic_evidence = 0
        targets_with_quiz_evidence = 0
        targets_with_prior_paper_evidence = 0
        targets_with_attendance_evidence = 0
    else:
        academic_evidence = (
            training["quiz_attempt_count"] + training["prior_paper_count"]
        ) >= 1
        targets_with_academic_evidence = int(academic_evidence.sum())
        targets_with_quiz_evidence = int((training["has_quiz_evidence"] == 1).sum())
        targets_with_prior_paper_evidence = int((training["has_prior_paper_evidence"] == 1).sum())
        targets_with_attendance_evidence = int((training["has_attendance_evidence"] == 1).sum())
        reason_counts = {
            str(reason): int(count)
            for reason, count in training["ineligible_reason"].value_counts().items()
            if reason
        }

    summary = {
        **_database_counts(connection),
        "students": len(students),
        "students_with_evidence": len(students),
        "subjects": len({str(row.get("subject") or "").strip() for row in paper_rows if str(row.get("subject") or "").strip()}),
        "paper_assessments": len({int(row.get("assessment_id")) for row in paper_rows}),
        "paper_score_rows": len(paper_rows),
        "quiz_attempts": len(quiz_rows),
        "question_answer_evidence": len(question_rows),
        "attendance_records": len(attendance_rows),
        "usable_target_rows": len(valid_targets),
        "generated_feature_snapshots": len(training),
        "targets_with_academic_evidence": targets_with_academic_evidence,
        "targets_with_quiz_evidence": targets_with_quiz_evidence,
        "targets_with_prior_paper_evidence": targets_with_prior_paper_evidence,
        "targets_with_attendance_evidence": targets_with_attendance_evidence,
        "eligible_feature_snapshots": eligible,
        "ineligible_feature_snapshots": ineligible,
        "ineligible_reason_counts": reason_counts,
    }
    summary.update(_readiness_breakdown(training))
    return summary


def generate_diagnostics(connection, subject=None):
    """Return a report with subject-level training readiness metrics."""
    dataset = build_training_dataset(connection, subject=subject, include_ineligible=True)
    summary = count_feature_evidence(connection, subject=subject)
    if not dataset.empty:
        summary["feature_columns"] = list(dataset.columns)
    else:
        summary["feature_columns"] = list(OUTPUT_COLUMNS)
    return summary
