import unittest

from ai.ml.production.learning_recommendations import (
    LEARNING_RECOMMENDATION_VERSION,
    build_learning_recommendations,
    recommendation_source_kind,
)


def _topic(
    name="Force",
    total=6,
    distinct=3,
    correct=2,
    skipped=1,
    repeated=0,
):
    return {
        "topic": name,
        "total_questions": total,
        "distinct_questions": distinct,
        "correct_answers": correct,
        "skipped_answers": skipped,
        "repeated_mistake_count": repeated,
    }


def _scope(**overrides):
    scope = {
        "subject": "Science",
        "topics": [_topic()],
        "quiz_summary": {"total_questions": 6, "correct_answers": 2, "skipped_answers": 1},
        "paper_evidence": {"graded_assessments": 0, "average_percent": 0},
        "attendance_evidence": {"recorded_days": 0, "present_days": 0, "absent_days": 0},
    }
    scope.update(overrides)
    return scope


class LearningRecommendationTests(unittest.TestCase):
    def test_no_evidence_returns_useful_no_evidence_state(self):
        result = build_learning_recommendations(_scope(
            topics=[],
            quiz_summary={"total_questions": 0, "correct_answers": 0, "skipped_answers": 0},
        ))
        self.assertEqual(result["version"], LEARNING_RECOMMENDATION_VERSION)
        self.assertEqual(result["status"], "no_evidence")
        self.assertEqual(result["provenance"], "observed_academic_evidence")
        self.assertIn("Take a practice quiz", result["message"])
        self.assertEqual(result["recommendations"], [])

    def test_fewer_than_three_topic_observations_is_insufficient(self):
        result = build_learning_recommendations(_scope(topics=[_topic(total=2, correct=0)]))
        self.assertEqual(result["status"], "insufficient_topic_evidence")
        self.assertEqual(result["recommendations"], [])

    def test_fewer_than_two_distinct_questions_is_insufficient(self):
        result = build_learning_recommendations(_scope(topics=[_topic(distinct=1)]))
        self.assertEqual(result["status"], "insufficient_topic_evidence")
        self.assertEqual(result["recommendations"], [])

    def test_topic_accuracy_at_60_percent_does_not_trigger_review(self):
        result = build_learning_recommendations(_scope(topics=[_topic(total=5, correct=3, skipped=0)]))
        self.assertEqual(result["status"], "no_current_review_priority")
        self.assertEqual(result["recommendations"], [])

    def test_topic_below_60_percent_triggers_observed_review(self):
        result = build_learning_recommendations(_scope())
        item = result["recommendations"][0]
        self.assertEqual(item["kind"], "topic_review")
        self.assertEqual(item["reason"], "2/6 correct across 3 distinct questions; 1 skipped.")
        self.assertEqual(item["evidence"]["accuracy_percent"], 33.33)
        self.assertIn("Read an available matching note", item["next_step"])

    def test_multiple_topics_sort_by_accuracy_volume_then_stable_names(self):
        result = build_learning_recommendations(_scope(
            topics=[
                _topic("Zebra", total=8, distinct=4, correct=3, skipped=0),
                _topic("Alpha", total=6, distinct=3, correct=2, skipped=0),
                _topic("Beta", total=8, distinct=4, correct=4, skipped=0),
                _topic("Alpha", total=5, distinct=3, correct=1, skipped=0),
            ],
            quiz_summary={"total_questions": 27, "correct_answers": 10, "skipped_answers": 0},
        ))
        topics = [item["topic"] for item in result["recommendations"]]
        self.assertEqual(topics, ["Alpha", "Zebra", "Beta"])
        self.assertEqual(
            build_learning_recommendations(_scope(
                topics=[_topic("Zebra", 8, 4, 3, 0), _topic("Alpha", 6, 3, 2, 0)],
                quiz_summary={"total_questions": 14, "correct_answers": 5, "skipped_answers": 0},
            )),
            build_learning_recommendations(_scope(
                topics=[_topic("Zebra", 8, 4, 3, 0), _topic("Alpha", 6, 3, 2, 0)],
                quiz_summary={"total_questions": 14, "correct_answers": 5, "skipped_answers": 0},
            )),
        )

    def test_topic_review_attaches_matching_note_and_quiz(self):
        result = build_learning_recommendations(
            _scope(),
            notes=[{"id": 1, "title": "Force notes", "subject": "Science", "chapter": "Force and Motion"}],
            quizzes=[{"id": 2, "title": "Force Practice", "subject": "Science", "topics": ["Force"], "is_published": True, "protected": False}],
        )
        resources = result["recommendations"][0]["resources"]
        self.assertEqual([note["id"] for note in resources["notes"]], [1])
        self.assertEqual([quiz["id"] for quiz in resources["quizzes"]], [2])

    def test_wrong_subject_note_is_not_attached(self):
        result = build_learning_recommendations(
            _scope(),
            notes=[{"id": 1, "title": "Force notes", "subject": "History", "chapter": "Force"}],
        )
        resources = result["recommendations"][0]["resources"]
        self.assertEqual(resources["notes"], [])
        self.assertEqual(resources["note_message"], "No matching note is currently available.")

    def test_wrong_topic_unpublished_and_protected_quizzes_are_not_attached(self):
        quizzes = [
            {"id": 1, "title": "Other Topic", "subject": "Science", "topics": ["Energy"], "is_published": True, "protected": False},
            {"id": 2, "title": "Unpublished", "subject": "Science", "topics": ["Force"], "is_published": False, "protected": False},
            {"id": 3, "title": "Active Lab", "subject": "Science", "topics": ["Force"], "is_published": True, "protected": True},
            {"id": 4, "title": "Unauthorized", "subject": "Science", "topics": ["Force"], "is_published": True, "protected": False, "authorized": False},
        ]
        result = build_learning_recommendations(_scope(), quizzes=quizzes)
        self.assertEqual(result["recommendations"][0]["resources"]["quizzes"], [])

    def test_invalid_quiz_descriptor_is_ignored_safely(self):
        result = build_learning_recommendations(
            _scope(),
            quizzes=[{"id": 1, "title": "Bad", "subject": "Science", "topics": "invalid", "is_published": True}],
        )
        self.assertEqual(result["recommendations"][0]["resources"]["quizzes"], [])

    def test_skip_rule_and_required_caveat(self):
        result = build_learning_recommendations(_scope(
            topics=[],
            quiz_summary={"total_questions": 4, "correct_answers": 2, "skipped_answers": 1},
        ))
        item = result["recommendations"][0]
        self.assertEqual(item["kind"], "skipped_questions")
        self.assertIn("A skipped answer does not identify why", item["reason"])

    def test_paper_review_rule_uses_two_graded_assessments(self):
        result = build_learning_recommendations(_scope(
            topics=[],
            quiz_summary={"total_questions": 0},
            paper_evidence={"graded_assessments": 2, "average_percent": 59.9},
        ))
        item = result["recommendations"][0]
        self.assertEqual(item["kind"], "paper_review")
        self.assertEqual(item["next_step"], "Review recent marked paper work and compare it with lesson objectives.")

    def test_paper_average_at_60_percent_does_not_trigger_review(self):
        result = build_learning_recommendations(_scope(
            topics=[],
            quiz_summary={"total_questions": 0},
            paper_evidence={"graded_assessments": 2, "average_percent": 60.0},
        ))
        self.assertEqual(result["recommendations"], [])

    def test_skip_threshold_requires_four_questions_and_25_percent(self):
        too_few = build_learning_recommendations(_scope(
            topics=[], quiz_summary={"total_questions": 3, "skipped_answers": 3},
        ))
        below_rate = build_learning_recommendations(_scope(
            topics=[], quiz_summary={"total_questions": 4, "skipped_answers": 0},
        ))
        self.assertEqual(too_few["recommendations"], [])
        self.assertEqual(below_rate["recommendations"], [])

    def test_attendance_is_context_only_and_attendance_alone_is_not_topic_weakness(self):
        result = build_learning_recommendations(_scope(
            topics=[],
            quiz_summary={"total_questions": 0},
            attendance_evidence={"recorded_days": 10, "present_days": 7, "absent_days": 3, "attendance_percent": 70},
        ))
        item = result["recommendations"][0]
        self.assertEqual(item["kind"], "attendance_catch_up")
        self.assertEqual(item["next_step"], "Check whether any lessons need catching up after recorded absences.")
        self.assertNotIn("weak", item["title"].casefold())
        self.assertNotIn("caused", item["reason"].casefold())

    def test_global_attendance_recommendation_is_not_duplicated_per_subject(self):
        result = build_learning_recommendations({
            "subject_evidence": [
                _scope(subject="Science", topics=[], quiz_summary={"total_questions": 0}),
                _scope(subject="Math", topics=[], quiz_summary={"total_questions": 0}),
            ],
            "attendance_evidence": {
                "recorded_days": 10,
                "present_days": 7,
                "absent_days": 3,
                "attendance_percent": 70,
            },
        })
        attendance_recommendations = [
            item for item in result["recommendations"]
            if item["kind"] == "attendance_catch_up"
        ]
        self.assertEqual(len(attendance_recommendations), 1)
        self.assertIsNone(attendance_recommendations[0]["subject"])

    def test_repeated_mistakes_only_strengthen_qualifying_topic_reason(self):
        result = build_learning_recommendations(_scope(topics=[_topic(repeated=3)]))
        self.assertIn("repeated 3 time(s)", result["recommendations"][0]["reason"])
        no_eligible = build_learning_recommendations(_scope(topics=[_topic(total=2, repeated=3)]))
        self.assertEqual(no_eligible["recommendations"], [])

    def test_duplicate_topic_recommendations_are_deduplicated(self):
        result = build_learning_recommendations(_scope(topics=[_topic(), _topic()]))
        self.assertEqual(len(result["recommendations"]), 1)

    def test_topic_recommendations_are_capped_at_three_best_priorities(self):
        result = build_learning_recommendations(_scope(
            topics=[
                _topic("Four", total=10, distinct=5, correct=5, skipped=0),
                _topic("Three", total=10, distinct=5, correct=4, skipped=0),
                _topic("Two", total=10, distinct=5, correct=3, skipped=0),
                _topic("One", total=10, distinct=5, correct=1, skipped=0),
            ],
            quiz_summary={"total_questions": 40, "correct_answers": 13, "skipped_answers": 0},
        ))
        self.assertEqual(
            [item["topic"] for item in result["recommendations"]],
            ["One", "Two", "Three"],
        )

    def test_output_is_stable_for_repeated_input(self):
        evidence = _scope(topics=[_topic("Force", repeated=2)])
        self.assertEqual(build_learning_recommendations(evidence), build_learning_recommendations(evidence))

    def test_recommendation_kinds_map_to_existing_intervention_sources(self):
        self.assertEqual(recommendation_source_kind("topic_review"), "topic")
        self.assertEqual(recommendation_source_kind("paper_review"), "paper")
        self.assertEqual(recommendation_source_kind("attendance_catch_up"), "attendance")
        self.assertEqual(recommendation_source_kind("skipped_questions"), "manual")
        self.assertEqual(recommendation_source_kind("unknown"), "manual")


if __name__ == "__main__":
    unittest.main()