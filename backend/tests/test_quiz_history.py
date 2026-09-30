"""Student and Teacher Quiz history API security and aggregation tests."""

import importlib
import json
import unittest

try:
    fixture = importlib.import_module("test_quiz_statistics")
except ModuleNotFoundError:
    fixture = importlib.import_module("backend.tests.test_quiz_statistics")


class QuizHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.QuizStatisticsTests.setUpClass()
        cls.backend = fixture.QuizStatisticsTests.backend

    def setUp(self):
        fixture.QuizStatisticsTests.setUp(self)
        self.db.execute(
            """INSERT INTO quizzes
               (id,title,subject,questions,created_by,is_published,created_at)
               VALUES(2,'Teacher Science Quiz','Science',?,2,1,'2026-09-30 01:00:00')""",
            (json.dumps(self.questions),),
        )
        self.db.execute(
            """INSERT INTO quizzes
               (id,title,subject,questions,created_by,is_published,created_at)
               VALUES(3,'Other Teacher Quiz','Science',?,4,1,'2026-09-30 01:00:00')""",
            (json.dumps(self.questions),),
        )
        self.db.execute("INSERT INTO teacher_class_subjects VALUES(2,4,1,1,'2026-01-01')")
        self.db.commit()
        self.client = self.backend.app.test_client()
        self.login("student")

    def login(self, identity):
        values = {
            "student": (1, "student"),
            "student_two": (5, "student"),
            "teacher": (2, "teacher"),
            "other_teacher": (4, "teacher"),
            "admin": (3, "admin"),
        }
        user_id, role = values[identity]
        with self.client.session_transaction() as session:
            session.clear()
            session.update(user_id=user_id, username=identity, role=role)

    def add_attempt(self, result_id, *, student_id=1, quiz_id=2, score=1, total=3,
                    session_id=None, submitted="2026-09-30 01:30:00", answers=None):
        self.db.execute(
            """INSERT INTO quiz_results
               (id,student_id,quiz_id,score,total_questions,quiz_session_id,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (result_id, student_id, quiz_id, score, total, session_id, submitted),
        )
        for row in answers or []:
            self.db.execute(
                """INSERT INTO quiz_answer_results
                   (quiz_result_id,question_index,question_text,topic,difficulty,
                    curriculum_code,cognitive_level,selected_answer,correct_answer,
                    is_correct,is_skipped)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (result_id, *row),
            )
        self.db.commit()

    @staticmethod
    def answer(index, *, selected="A", correct="A", is_correct=1, skipped=0):
        return (
            index, f"Historical question {index + 1}", "Force", "easy",
            "SCI-1", "understanding", selected, correct, is_correct, skipped,
        )

    def test_student_empty_history_and_page_size_validation(self):
        response = self.client.get("/api/student/quiz-history")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["attempts"], [])
        self.assertEqual(response.json["pagination"]["total"], 0)
        self.assertEqual(self.client.get("/api/student/quiz-history?page_size=5").status_code, 400)

    def test_student_history_pagination_counts_attempt_type_and_npt(self):
        for result_id in range(1, 12):
            self.add_attempt(
                result_id, session_id=9 if result_id == 1 else None,
                submitted=f"2026-09-{30 if result_id == 1 else 29} 01:30:00",
                answers=[self.answer(0), self.answer(1, selected="B", correct="A", is_correct=0),
                         self.answer(2, selected=None, correct="A", is_correct=0, skipped=1)],
            )
        first = self.client.get("/api/student/quiz-history?page=1&page_size=10")
        self.assertEqual(first.json["pagination"], {"page": 1, "page_size": 10, "total": 11, "total_pages": 2})
        self.assertEqual(len(first.json["attempts"]), 10)
        newest = first.json["attempts"][0]
        self.assertEqual(newest["attempt_type"], "Lab Quiz")
        self.assertEqual(newest["correct_count"], 1)
        self.assertEqual(newest["wrong_count"], 1)
        self.assertEqual(newest["skipped_count"], 1)
        self.assertEqual(newest["percentage"], 33.3)
        self.assertTrue(newest["submitted_at"].endswith("NPT"))
        self.assertEqual(first.json["attempts"][1]["attempt_type"], "Practice Quiz")
        second = self.client.get("/api/student/quiz-history?page=2&page_size=10")
        self.assertEqual(len(second.json["attempts"]), 1)

    def test_student_cannot_read_another_students_history_or_answer_key(self):
        self.add_attempt(31, answers=[self.answer(0)])
        self.add_attempt(32, student_id=2, answers=[self.answer(0)])
        owned_list = self.client.get("/api/student/quiz-history")
        self.assertEqual(owned_list.json["pagination"]["total"], 1)
        self.assertEqual([item["result_id"] for item in owned_list.json["attempts"]], [31])
        self.assertEqual(self.client.get("/api/student/quiz-history/32").status_code, 404)
        detail = self.client.get("/api/student/quiz-history/31")
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("correct_answer", detail.json["answers"][0])
        self.assertEqual(detail.json["attempt"]["correct_count"], 1)
        self.login("student_two")
        self.assertEqual(self.client.get("/api/student/quiz-history/31").status_code, 404)

    def test_student_detail_uses_historical_answer_rows_and_handles_zero_total(self):
        self.add_attempt(41, score=0, total=0, answers=[])
        detail = self.client.get("/api/student/quiz-history/41")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json["attempt"]["percentage"], 0)
        self.assertEqual(detail.json["attempt"]["wrong_count"], 0)
        self.assertEqual(detail.json["answers"], [])

    def test_teacher_zero_attempts_ownership_and_current_assignment(self):
        self.login("teacher")
        empty = self.client.get("/api/teacher/quizzes/2/attempts")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json["attempts"], [])
        self.login("other_teacher")
        self.assertEqual(self.client.get("/api/teacher/quizzes/2/attempts").status_code, 404)
        self.login("teacher")
        self.assertEqual(self.client.get("/api/teacher/quizzes/3/attempts").status_code, 404)

    def test_teacher_attempt_list_search_pagination_npt_and_counts(self):
        self.db.execute("INSERT INTO users VALUES(6,'Student Three','three@example.test','hash','student',0,'2026-01-01')")
        self.db.execute("INSERT INTO students VALUES(3,6,'Student Three','10')")
        self.db.commit()
        for result_id in range(50, 62):
            self.add_attempt(
                result_id, student_id=1 if result_id % 2 == 0 else 3,
                answers=[self.answer(0), self.answer(1, selected="B", correct="A", is_correct=0),
                         self.answer(2, selected=None, correct="A", is_correct=0, skipped=1)],
            )
        self.login("teacher")
        response = self.client.get("/api/teacher/quizzes/2/attempts?page=1&page_size=10")
        self.assertEqual(response.json["pagination"]["total"], 12)
        self.assertEqual(len(response.json["attempts"]), 10)
        self.assertTrue(response.json["attempts"][0]["submitted_at"].endswith("NPT"))
        self.assertEqual(response.json["attempts"][0]["correct_count"], 1)
        self.assertEqual(response.json["attempts"][0]["wrong_count"], 1)
        self.assertEqual(response.json["attempts"][0]["skipped_count"], 1)
        search = self.client.get("/api/teacher/quizzes/2/attempts?search=three@example.test")
        self.assertEqual(search.json["pagination"]["total"], 6)
        self.assertTrue(all(item["student_email"] == "three@example.test" for item in search.json["attempts"]))

    def test_teacher_attempt_detail_checks_quiz_result_pair_and_exposes_answer_key(self):
        self.add_attempt(
            71,
            answers=[self.answer(0), self.answer(1, selected="B", correct="A", is_correct=0)],
        )
        self.login("teacher")
        detail = self.client.get("/api/teacher/quizzes/2/attempts/71")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json["attempt"]["student_name"], "Student One")
        self.assertEqual(detail.json["answers"][0]["correct_answer"], "A")
        self.assertEqual(self.client.get("/api/teacher/quizzes/3/attempts/71").status_code, 404)
        self.login("other_teacher")
        self.assertEqual(self.client.get("/api/teacher/quizzes/2/attempts/71").status_code, 404)


if __name__ == "__main__":
    unittest.main()