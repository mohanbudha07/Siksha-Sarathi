"""Student-scoped tutoring context build for the student AI assistant."""

from __future__ import annotations

from typing import Any

from ai.grounded_tutor import (
    GROUNDED_TUTOR_VERSION,
    MAX_GROUNDING_CONTEXT_CHARS,
    MAX_GROUNDING_NOTES,
    MAX_NOTE_EXCERPT_CHARS,
    MAX_RECOMMENDATIONS,
    MAX_SUPPORT_PLANS,
    normalize_grounding,
)
from ai.ml.production.learning_recommendations import build_learning_recommendations
from backend.student_access import fetch_student_context


def _subject_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def _sanitize_excerpt(content: Any, limit: int = MAX_NOTE_EXCERPT_CHARS) -> str:
    text = str(content or "").replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def _authorized_subjects(context: dict[str, Any]) -> set[str]:
    if not isinstance(context, dict):
        return set()
    return {
        _subject_key(subject.get("name"))
        for subject in (context.get("subjects") or [])
        if isinstance(subject, dict) and str(subject.get("name") or "").strip()
    }


def get_student_ai_context_options(cur, user_id: int) -> dict[str, Any]:
    """Return only the student's authorized subjects for safe frontend selection."""
    context = fetch_student_context(cur, user_id)
    if not context:
        return {"subjects": []}
    subjects = []
    for subject in context.get("subjects") or []:
        name = str(subject.get("name") or "").strip()
        if name:
            subjects.append(name)
    return {"subjects": subjects}


def _collect_recent_student_recommendations(cur, student_id: int, subject_names: set[str]):
    if not subject_names:
        return []

    cur.execute(
        """
        SELECT q.subject, qar.topic,
               COUNT(*) AS total_questions,
               COUNT(DISTINCT qar.question_text) AS distinct_questions,
               COALESCE(SUM(qar.is_correct), 0) AS correct_answers,
               COALESCE(SUM(qar.is_skipped), 0) AS skipped_answers
        FROM (
            SELECT id FROM quiz_results
            WHERE student_id = %s
            ORDER BY id DESC LIMIT 10
        ) recent
        INNER JOIN quiz_answer_results qar
            ON qar.quiz_result_id = recent.id
        INNER JOIN quiz_results qr ON qr.id = recent.id
        INNER JOIN quizzes q ON q.id = qr.quiz_id
        WHERE LOWER(TRIM(q.subject)) IN (%s)
        GROUP BY q.subject, qar.topic
        """,
        (student_id, ", ".join(["%s"] * len(subject_names)))
    )

    # The above placeholder query is intentionally replaced below with a
    # deterministic subject-aware loop using the student's current records.
    return []


def _build_phase10_recommendations(cur, student_id: int, subject_names: set[str]):
    """Reuse the canonical Phase 10 recommendation engine against the student's own recent evidence."""
    if not subject_names:
        return []

    cur.execute(
        """
        SELECT q.subject, qar.topic,
               COUNT(*) AS total_questions,
               COUNT(DISTINCT qar.question_text) AS distinct_questions,
               COALESCE(SUM(qar.is_correct), 0) AS correct_answers,
               COALESCE(SUM(qar.is_skipped), 0) AS skipped_answers
        FROM (
            SELECT id FROM quiz_results
            WHERE student_id = %s
            ORDER BY id DESC LIMIT 10
        ) recent
        INNER JOIN quiz_answer_results qar
            ON qar.quiz_result_id = recent.id
        INNER JOIN quiz_results qr ON qr.id = recent.id
        INNER JOIN quizzes q ON q.id = qr.quiz_id
        GROUP BY q.subject, qar.topic
        """,
        (student_id,),
    )
    topic_rows = cur.fetchall()
    topics_by_subject = {subject_name.casefold(): [] for subject_name in subject_names}
    for row in topic_rows:
        subject_key = _subject_key(row.get("subject"))
        if subject_key not in topics_by_subject:
            continue
        topics_by_subject[subject_key].append({
            "topic": row.get("topic") or "Unspecified",
            "total_questions": int(row.get("total_questions") or 0),
            "distinct_questions": int(row.get("distinct_questions") or 0),
            "correct_answers": int(row.get("correct_answers") or 0),
            "skipped_answers": int(row.get("skipped_answers") or 0),
        })

    cur.execute(
        """
        SELECT q.subject, COUNT(qar.id) AS total_questions,
               COALESCE(SUM(qar.is_correct), 0) AS correct_answers,
               COALESCE(SUM(qar.is_skipped), 0) AS skipped_answers
        FROM (
            SELECT id FROM quiz_results WHERE student_id = %s ORDER BY id DESC LIMIT 10
        ) recent
        INNER JOIN quiz_results qr ON qr.id = recent.id
        INNER JOIN quizzes q ON q.id = qr.quiz_id
        LEFT JOIN quiz_answer_results qar ON qar.quiz_result_id = qr.id
        GROUP BY q.subject
        """,
        (student_id,),
    )
    quiz_summary_by_subject = {}
    for row in cur.fetchall():
        subject_key = _subject_key(row.get("subject"))
        if subject_key in topics_by_subject:
            quiz_summary_by_subject[subject_key] = {
                "total_questions": int(row.get("total_questions") or 0),
                "correct_answers": int(row.get("correct_answers") or 0),
                "skipped_answers": int(row.get("skipped_answers") or 0),
            }

    subject_evidence = []
    for subject_name in sorted(subject_names, key=lambda value: value.casefold()):
        subject_key = subject_name.casefold()
        subject_evidence.append({
            "subject": subject_name,
            "topics": topics_by_subject.get(subject_key, []),
            "quiz_summary": quiz_summary_by_subject.get(subject_key, {}),
            "paper_evidence": {},
            "attendance_evidence": {},
        })

    result = build_learning_recommendations({"subject_evidence": subject_evidence}, notes=(), quizzes=())
    recommendations = result.get("recommendations") or []
    cleaned = []
    for item in recommendations[:MAX_RECOMMENDATIONS]:
        cleaned.append({
            "subject": str(item.get("subject") or "").strip() or "General",
            "title": str(item.get("title") or "").strip() or "Review topic",
            "reason": str(item.get("reason") or "").strip(),
            "next_step": str(item.get("next_step") or "").strip(),
        })
    return cleaned


def build_student_tutoring_context(cur, user_id: int, selected_subject: str | None = None, question: str | None = None):
    """Build the minimal, authorized grounding payload for the logged-in student."""
    context = fetch_student_context(cur, user_id)
    if not context or not context.get("current_class"):
        return {
            "version": GROUNDED_TUTOR_VERSION,
            "subject": None,
            "status": "general_only",
            "recommendations": [],
            "notes": [],
            "support_plans": [],
            "evidence_summary": {
                "recommendation_count": 0,
                "note_count": 0,
                "support_plan_count": 0,
                "subject_count": 0,
            },
            "subjects": [],
        }

    subject_names = set(_authorized_subjects(context))
    subject_label = str(selected_subject or "").strip()
    if subject_label and _subject_key(subject_label) not in subject_names:
        raise ValueError("Selected subject is not currently authorized for this student")

    current_subject = subject_label if subject_label else None
    current_class_id = context["current_class"]["id"]

    # Notes are restricted to this class's current subjects and capped to a small set.
    cur.execute(
        """
        SELECT n.id, n.title, n.subject, n.chapter, n.content
        FROM notes n
        WHERE EXISTS (
            SELECT 1
            FROM teacher_class_subjects tcs
            INNER JOIN subjects sub ON sub.id = tcs.subject_id
            WHERE tcs.class_id = %s
              AND LOWER(TRIM(sub.name)) = LOWER(TRIM(n.subject))
        )
        ORDER BY n.created_at DESC
        """,
        (current_class_id,),
    )
    notes = []
    for row in cur.fetchall():
        note_subject = str(row.get("subject") or "").strip()
        if _subject_key(note_subject) not in subject_names:
            continue
        if current_subject and _subject_key(note_subject) != _subject_key(current_subject):
            continue
        notes.append({
            "id": row.get("id"),
            "title": str(row.get("title") or "").strip(),
            "subject": note_subject,
            "chapter": str(row.get("chapter") or "").strip(),
            "excerpt": _sanitize_excerpt(row.get("content")),
        })

    if question:
        q_tokens = {
            token for token in str(question).lower().replace("?", " ").split()
            if len(token) > 3
        }
        notes.sort(key=lambda item: (
            0 if _subject_key(item["subject"]) == _subject_key(current_subject) else 1,
            -sum(1 for token in q_tokens if token in (str(item.get("title") or "").lower() + " " + str(item.get("chapter") or "").lower() + " " + str(item.get("excerpt") or "").lower())),
            str(item.get("title") or "").casefold(),
            int(item.get("id") or 0),
        ))
    else:
        notes.sort(key=lambda item: (str(item.get("title") or "").casefold(), int(item.get("id") or 0)))
    notes = notes[:MAX_GROUNDING_NOTES]

    cur.execute(
        """
        SELECT id, subject, focus_area, action_plan, success_criteria, status
        FROM teacher_interventions
        WHERE student_id = %s
          AND status IN ('planned', 'in_progress')
        ORDER BY
          CASE status WHEN 'in_progress' THEN 1 WHEN 'planned' THEN 2 ELSE 3 END,
          id DESC
        LIMIT %s
        """,
        (context["student_id"], MAX_SUPPORT_PLANS),
    )
    support_plans = []
    for row in cur.fetchall():
        plan_subject = str(row.get("subject") or "").strip()
        if _subject_key(plan_subject) not in subject_names:
            continue
        if current_subject and _subject_key(plan_subject) != _subject_key(current_subject):
            continue
        support_plans.append({
            "subject": plan_subject,
            "focus_area": str(row.get("focus_area") or "").strip(),
            "teacher_action": str(row.get("action_plan") or "").strip(),
            "success_criteria": str(row.get("success_criteria") or "").strip(),
        })

    recommendations = _build_phase10_recommendations(cur, context["student_id"], subject_names)
    if current_subject:
        recommendations = [
            item for item in recommendations
            if _subject_key(item.get("subject")) == _subject_key(current_subject)
        ][:MAX_RECOMMENDATIONS]

    context_payload = {
        "version": GROUNDED_TUTOR_VERSION,
        "subject": current_subject,
        "recommendations": recommendations,
        "notes": notes,
        "support_plans": support_plans[:MAX_SUPPORT_PLANS],
        "evidence_summary": {
            "recommendation_count": len(recommendations),
            "note_count": len(notes),
            "support_plan_count": len(support_plans[:MAX_SUPPORT_PLANS]),
            "subject_count": len(subject_names),
        },
        "subjects": sorted(subject_names, key=lambda value: value.casefold()),
    }
    if not any((recommendations, notes, support_plans)):
        context_payload["status"] = "general_only"
    elif recommendations and not notes and not support_plans:
        context_payload["status"] = "partial_grounding"
    else:
        context_payload["status"] = "grounded"

    if MAX_GROUNDING_CONTEXT_CHARS:
        payload_text = str(context_payload).encode("utf-8")
        if len(payload_text) > MAX_GROUNDING_CONTEXT_CHARS:
            context_payload["notes"] = context_payload["notes"][:1]
            context_payload["support_plans"] = context_payload["support_plans"][:1]
            context_payload["recommendations"] = context_payload["recommendations"][:1]

    return normalize_grounding(context_payload)
