"""Deterministic learning next steps derived from observed school evidence."""

from __future__ import annotations

from typing import Any

LEARNING_RECOMMENDATION_VERSION = "1"

MIN_TOPIC_QUESTIONS = 3
MIN_DISTINCT_TOPIC_QUESTIONS = 2
TOPIC_REVIEW_ACCURACY_BELOW = 60.0
MAX_TOPIC_RECOMMENDATIONS = 3
MIN_SKIP_QUESTIONS = 4
HIGH_SKIP_PERCENT = 25.0
MIN_GRADED_PAPERS = 2
PAPER_REVIEW_AVERAGE_BELOW = 60.0
MIN_ATTENDANCE_DAYS = 5
MIN_ABSENCES_FOR_CATCH_UP = 2

_KIND_ORDER = {
    "topic_review": 0,
    "skipped_questions": 1,
    "paper_review": 2,
    "attendance_catch_up": 3,
}


def recommendation_source_kind(recommendation_kind: str) -> str:
    """Map recommendation kinds onto the existing persisted source contract."""
    return {
        "topic_review": "topic",
        "paper_review": "paper",
        "attendance_catch_up": "attendance",
    }.get(recommendation_kind, "manual")


def _number(value, default=0):
    try:
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return default
        return number
    except (TypeError, ValueError):
        return default


def _count(value):
    return max(0, int(_number(value)))


def _same_subject(left, right):
    return str(left or "").strip().casefold() == str(right or "").strip().casefold()


def _matching_resources(subject, topic, notes, quizzes):
    topic_key = str(topic or "").strip().casefold()
    matching_notes = [
        {
            "id": note.get("id"),
            "title": str(note.get("title") or ""),
            "chapter": str(note.get("chapter") or ""),
        }
        for note in notes
        if note.get("id") is not None
        and note.get("authorized", True) is not False
        and _same_subject(note.get("subject"), subject)
        and topic_key in str(note.get("chapter") or "").casefold()
    ]
    matching_notes.sort(key=lambda item: (item["title"].casefold(), str(item["id"])))

    matching_quizzes = []
    for quiz in quizzes:
        if (
            quiz.get("id") is None
            or quiz.get("is_published") is not True
            or quiz.get("protected") is True
            or quiz.get("authorized", True) is False
            or not _same_subject(quiz.get("subject"), subject)
        ):
            continue
        tagged_topics = quiz.get("topics")
        if not isinstance(tagged_topics, (list, tuple, set)):
            continue
        if not any(str(value or "").strip().casefold() == topic_key for value in tagged_topics):
            continue
        matching_quizzes.append({
            "id": quiz["id"],
            "title": str(quiz.get("title") or ""),
        })
    matching_quizzes.sort(key=lambda item: (item["title"].casefold(), str(item["id"])))
    return matching_notes[:2], matching_quizzes[:2]


def _topic_recommendation(scope, topic, notes, quizzes):
    subject = str(scope.get("subject") or "").strip()
    topic_name = str(topic.get("topic") or "").strip()
    total = _count(topic.get("total_questions"))
    correct = min(total, _count(topic.get("correct_answers")))
    skipped = min(total, _count(topic.get("skipped_answers")))
    distinct = _count(topic.get("distinct_questions"))
    accuracy = round(100 * correct / total, 2) if total else 0.0
    repeated = _count(topic.get("repeated_mistake_count"))
    matching_notes, matching_quizzes = _matching_resources(
        subject, topic_name, notes, quizzes
    )
    evidence = {
        "total_questions": total,
        "distinct_questions": distinct,
        "correct_answers": correct,
        "skipped_answers": skipped,
        "accuracy_percent": accuracy,
        "repeated_mistake_count": repeated,
    }
    reason = (
        f"{correct}/{total} correct across {distinct} distinct questions; "
        f"{skipped} skipped."
    )
    if repeated:
        reason += f" Recorded incorrect responses repeated {repeated} time(s)."
    return {
        "kind": "topic_review",
        "subject": subject,
        "topic": topic_name,
        "title": f"Review {topic_name}",
        "reason": reason,
        "next_step": (
            "Read an available matching note, then attempt an available "
            "matching practice quiz and review any questions that remain unclear."
        ),
        "evidence": evidence,
        "resources": {
            "notes": matching_notes,
            "quizzes": matching_quizzes,
            "note_message": None if matching_notes else "No matching note is currently available.",
        },
    }


def _process_scope(scope, notes, quizzes):
    if not isinstance(scope, dict):
        return [], False, False, 0
    subject = str(scope.get("subject") or "").strip()
    quiz_summary = scope.get("quiz_summary") or {}
    paper = scope.get("paper_evidence") or {}
    attendance = scope.get("attendance_evidence") or {}
    topics = scope.get("topics") or []
    recommendations = []
    has_quiz = _count(quiz_summary.get("total_questions")) > 0
    has_other_evidence = (
        _count(paper.get("graded_assessments")) > 0
        or _count(attendance.get("recorded_days")) > 0
    )

    eligible_topics = []
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        topic_name = str(topic.get("topic") or "").strip()
        total = _count(topic.get("total_questions"))
        distinct = _count(topic.get("distinct_questions"))
        correct = min(total, _count(topic.get("correct_answers")))
        accuracy = 100 * correct / total if total else 0
        if (
            not topic_name
            or topic_name.casefold() in {"unspecified", subject.casefold()}
            or total < MIN_TOPIC_QUESTIONS
            or distinct < MIN_DISTINCT_TOPIC_QUESTIONS
        ):
            continue
        eligible_topics.append((topic, accuracy))
        if accuracy < TOPIC_REVIEW_ACCURACY_BELOW:
            recommendations.append(_topic_recommendation(scope, topic, notes, quizzes))

    total_questions = _count(quiz_summary.get("total_questions"))
    correct_answers = min(total_questions, _count(quiz_summary.get("correct_answers")))
    skipped_answers = min(total_questions, _count(quiz_summary.get("skipped_answers")))
    skip_percent = round(100 * skipped_answers / total_questions, 2) if total_questions else 0.0
    if total_questions >= MIN_SKIP_QUESTIONS and skip_percent >= HIGH_SKIP_PERCENT:
        recommendations.append({
            "kind": "skipped_questions",
            "subject": subject,
            "topic": None,
            "title": "Review unanswered questions",
            "reason": (
                f"{skipped_answers}/{total_questions} recent questions were skipped "
                f"({skip_percent}%). A skipped answer does not identify why the "
                "question was unanswered."
            ),
            "next_step": "Review the unanswered questions and ask for help with any that remain unclear.",
            "evidence": {
                "total_questions": total_questions,
                "correct_answers": correct_answers,
                "skipped_answers": skipped_answers,
                "skip_percent": skip_percent,
            },
            "resources": {"notes": [], "quizzes": [], "note_message": None},
        })

    graded_papers = _count(paper.get("graded_assessments"))
    paper_average = _number(paper.get("average_percent"))
    if graded_papers >= MIN_GRADED_PAPERS and paper_average < PAPER_REVIEW_AVERAGE_BELOW:
        recommendations.append({
            "kind": "paper_review",
            "subject": subject,
            "topic": None,
            "title": "Review recent marked paper work",
            "reason": f"{paper_average}% average across {graded_papers} graded paper assessments.",
            "next_step": "Review recent marked paper work and compare it with lesson objectives.",
            "evidence": {
                "graded_assessments": graded_papers,
                "average_percent": paper_average,
                "recent_published_assessment_available": bool(paper.get("recent_published_assessment_available", graded_papers > 0)),
            },
            "resources": {"notes": [], "quizzes": [], "note_message": None},
        })

    recorded_days = _count(attendance.get("recorded_days"))
    absent_days = _count(attendance.get("absent_days"))
    if recorded_days >= MIN_ATTENDANCE_DAYS and absent_days >= MIN_ABSENCES_FOR_CATCH_UP:
        recommendations.append({
            "kind": "attendance_catch_up",
            "subject": subject or None,
            "topic": None,
            "title": "Check for lessons to catch up",
            "reason": f"{absent_days} absences across {recorded_days} recorded school days.",
            "next_step": "Check whether any lessons need catching up after recorded absences.",
            "evidence": {
                "recorded_days": recorded_days,
                "present_days": min(recorded_days, _count(attendance.get("present_days"))),
                "absent_days": absent_days,
                "attendance_percent": _number(attendance.get("attendance_percent")),
            },
            "resources": {"notes": [], "quizzes": [], "note_message": None},
        })

    has_evidence = has_quiz or has_other_evidence or any(
        _count(topic.get("total_questions")) > 0
        for topic in topics if isinstance(topic, dict)
    )
    has_topic_candidates = bool(eligible_topics)
    return recommendations, has_evidence, has_quiz, int(has_topic_candidates)


def build_learning_recommendations(
    evidence: dict[str, Any],
    *,
    notes=(),
    quizzes=(),
) -> dict[str, Any]:
    """Build deterministic observed-evidence next steps from normalized data.

    ``evidence`` may describe one subject or provide a ``subject_evidence``
    list. Resources must already be limited to those available to the caller.
    Quiz descriptors must be parsed/validated by the application adapter.
    """
    evidence = evidence if isinstance(evidence, dict) else {}
    scopes = evidence.get("subject_evidence")
    if not isinstance(scopes, list):
        scopes = [evidence]
    all_recommendations = []
    has_evidence = False
    has_quiz = False
    has_topic_candidates = False
    for scope in scopes:
        scope_recommendations, scope_evidence, scope_quiz, topic_candidates = _process_scope(
            scope, notes, quizzes
        )
        all_recommendations.extend(scope_recommendations)
        has_evidence = has_evidence or scope_evidence
        has_quiz = has_quiz or scope_quiz
        has_topic_candidates = has_topic_candidates or bool(topic_candidates)

    global_attendance = evidence.get("attendance_evidence")
    if isinstance(global_attendance, dict):
        attendance_scope = {
            "subject": None,
            "topics": [],
            "quiz_summary": {},
            "paper_evidence": {},
            "attendance_evidence": global_attendance,
        }
        attendance_recommendations, attendance_has_evidence, _has_quiz, _topic_candidates = _process_scope(
            attendance_scope, notes, quizzes
        )
        all_recommendations.extend(attendance_recommendations)
        has_evidence = has_evidence or attendance_has_evidence

    deduplicated = {}
    for recommendation in all_recommendations:
        key = (
            recommendation["kind"],
            str(recommendation.get("subject") or "").casefold(),
            str(recommendation.get("topic") or "").casefold(),
        )
        deduplicated.setdefault(key, recommendation)
    recommendations = list(deduplicated.values())
    topic_recommendations = [
        item for item in recommendations if item["kind"] == "topic_review"
    ]
    topic_recommendations.sort(key=lambda item: (
        _number(item.get("evidence", {}).get("accuracy_percent"), 100),
        -_count(item.get("evidence", {}).get("total_questions")),
        str(item.get("subject") or "").casefold(),
        str(item.get("topic") or "").casefold(),
    ))
    recommendations = [
        item for item in recommendations if item["kind"] != "topic_review"
    ] + topic_recommendations[:MAX_TOPIC_RECOMMENDATIONS]
    recommendations.sort(key=lambda item: (
        _KIND_ORDER.get(item["kind"], 99),
        _number(item.get("evidence", {}).get("accuracy_percent"), 100),
        -_count(item.get("evidence", {}).get("total_questions")),
        str(item.get("subject") or "").casefold(),
        str(item.get("topic") or "").casefold(),
    ))

    if recommendations:
        status = "recommendations_available"
        message = "Choose one observed-evidence next step and check your progress afterward."
    elif not has_evidence:
        status = "no_evidence"
        message = "Take a practice quiz to start building personalized recommendations."
    elif has_quiz and not has_topic_candidates:
        status = "insufficient_topic_evidence"
        message = "Keep practising across different tagged questions to build enough topic evidence."
    else:
        status = "no_current_review_priority"
        message = "No current review priority was identified from the available evidence. Keep learning and check back after more activity."

    return {
        "version": LEARNING_RECOMMENDATION_VERSION,
        "recommendation_version": LEARNING_RECOMMENDATION_VERSION,
        "provenance": "observed_academic_evidence",
        "evidence_state": "observed_evidence" if has_evidence else "no_evidence",
        "status": status,
        "message": message,
        "recommendations": recommendations,
    }