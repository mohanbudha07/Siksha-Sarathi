"""Question Bank API and validation tests using the in-memory SQLite route fixture."""

import csv
import importlib
import io
import json
import sqlite3
import unittest
from pathlib import Path

from backend.question_bank import CSV_COLUMNS, MAX_CSV_ROWS, parse_question_csv

try:
    fixture = importlib.import_module("test_quiz_statistics")
except ModuleNotFoundError:
    fixture = importlib.import_module("backend.tests.test_quiz_statistics")


class BankCursor(fixture.CursorAdapter):
    def execute(self, query, args=()):
        return self.cursor.execute(
            query.replace("RAND()", "RANDOM()").replace("%s", "?"), args
        )


class BankConnection(fixture.ConnectionAdapter):
    def cursor(self):
        return BankCursor(self.connection)


class FailingOptionCursor(BankCursor):
    def execute(self, query, args=()):
        if "INSERT INTO question_bank_options" in query:
            raise RuntimeError("simulated option insert failure")
        return super().execute(query, args)


class FailingOptionConnection(BankConnection):
    def cursor(self):
        return FailingOptionCursor(self.connection)


class QuestionBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.QuizStatisticsTests.setUpClass()
        cls.backend = fixture.QuizStatisticsTests.backend

    def setUp(self):
        fixture.QuizStatisticsTests.setUp(self)
        self.backend.mysql.connection = BankConnection(self.db)
        self.db.executescript("""
            CREATE TABLE question_bank_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_by INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                question_text TEXT NOT NULL,
                question_hash TEXT NOT NULL,
                topic TEXT NOT NULL,
                difficulty TEXT NOT NULL CHECK(difficulty IN ('easy','medium','hard')),
                curriculum_code TEXT NOT NULL DEFAULT 'unspecified',
                cognitive_level TEXT NOT NULL DEFAULT 'unspecified',
                correct_option_index INTEGER NOT NULL CHECK(correct_option_index BETWEEN 0 AND 5),
                explanation TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(created_by, subject_id, question_hash)
            );
            CREATE TABLE question_bank_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                option_index INTEGER NOT NULL CHECK(option_index BETWEEN 0 AND 5),
                option_text TEXT NOT NULL,
                UNIQUE(question_id, option_index),
                FOREIGN KEY(question_id) REFERENCES question_bank_questions(id) ON DELETE CASCADE
            );
            INSERT INTO subjects VALUES(2,'Mathematics','MATH','2026-01-01');
            INSERT INTO subjects VALUES(3,'English','ENG','2026-01-01');
            INSERT INTO teacher_class_subjects VALUES(2,2,1,2,'2026-01-01');
        """)
        self.db.commit()
        self.client = self.backend.app.test_client()
        self.login("teacher")

    def login(self, role="teacher"):
        ids = {"teacher": 2, "other_teacher": 4, "admin": 3, "student": 1}
        with self.client.session_transaction() as session:
            session.clear()
            session.update(user_id=ids[role], username=role, role=role)

    def question(self, **overrides):
        result = {
            "subject_id": 1,
            "question_text": "What is force?",
            "topic": "Motion",
            "difficulty": "medium",
            "curriculum_code": "SCI-1",
            "cognitive_level": "understanding",
            "options": ["A push or pull", "A type of energy"],
            "correct_option_index": 0,
            "explanation": "Force changes motion.",
        }
        result.update(overrides)
        return result

    def create_question(self, **overrides):
        return self.client.post("/api/teacher/question-bank", json=self.question(**overrides))

    def csv_bytes(self, rows, headers=CSV_COLUMNS, bom=False):
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(headers)
        writer.writerows(rows)
        prefix = "\ufeff" if bom else ""
        return (prefix + stream.getvalue()).encode("utf-8")

    def csv_row(self, question="What is force?", **overrides):
        row = {
            "question": question,
            "topic": "Motion",
            "difficulty": "medium",
            "curriculum_code": "SCI-1",
            "cognitive_level": "understanding",
            "option_a": "A push or pull",
            "option_b": "A type of energy",
            "option_c": "",
            "option_d": "",
            "option_e": "",
            "option_f": "",
            "correct_option": "A",
            "explanation": "Force changes motion.",
        }
        row.update(overrides)
        return [row[column] for column in CSV_COLUMNS]

    def upload_csv(self, path, content):
        return self.client.post(
            path,
            data={
                "subject_id": "1",
                "file": (io.BytesIO(content), "questions.csv"),
            },
            content_type="multipart/form-data",
        )

    def count_questions(self):
        return self.db.execute("SELECT COUNT(*) FROM question_bank_questions").fetchone()[0]

    def test_schema_contract_and_migration_only_create_bank_tables(self):
        root = Path(__file__).resolve().parents[1]
        migration = (root / "migrations" / "020_question_bank.sql").read_text()
        schema = (root / "setup_db.sql").read_text()
        for source in (migration, schema):
            self.assertIn("question_bank_questions", source)
            self.assertIn("question_bank_options", source)
            self.assertIn("UNIQUE KEY uq_question_bank_owner_subject_hash", source)
            self.assertIn("ON DELETE CASCADE", source)
            self.assertIn("ON DELETE RESTRICT", source)
            self.assertIn("correct_option_index BETWEEN 0 AND 5", source)
        self.assertNotIn("ALTER TABLE quizzes", migration)
        self.assertNotIn("ALTER TABLE quiz_results", migration)
        options_table_marker = "CREATE TABLE IF NOT EXISTS question_bank_options"
        migration_options = migration.split(options_table_marker, 1)[1].strip()
        setup_options = schema.split(options_table_marker, 1)[1].split(";", 1)[0].strip() + ";"
        self.assertTrue(migration_options.endswith(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"))
        self.assertEqual(" ".join(migration_options.split()), " ".join(setup_options.split()))

    def test_subject_options_are_limited_to_current_assignments(self):
        response = self.client.get("/api/teacher/question-bank/options")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["name"] for item in response.json["subjects"]], ["Mathematics", "Science"])

    def test_unassigned_subject_is_forbidden(self):
        response = self.client.get("/api/teacher/question-bank?subject_id=999")
        self.assertEqual(response.status_code, 403)
        response = self.create_question(subject_id=999)
        self.assertEqual(response.status_code, 403)
        self.login("admin")
        self.assertEqual(self.client.get("/api/teacher/question-bank/options").status_code, 403)

    def test_create_read_update_delete_and_owner_isolation(self):
        created = self.create_question()
        self.assertEqual(created.status_code, 201)
        question_id = created.json["question"]["id"]
        self.assertEqual(created.json["question"]["correct_answer"], "A push or pull")
        self.assertEqual(self.client.get(f"/api/teacher/question-bank/{question_id}").status_code, 200)
        updated = self.client.put(
            f"/api/teacher/question-bank/{question_id}",
            json=self.question(question_text="Define force", options=["Interaction", "Mass"]),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["question"]["question"], "Define force")

        self.db.execute("INSERT INTO teacher_class_subjects VALUES(3,4,1,1,'2026-01-01')")
        self.db.commit()
        self.login("other_teacher")
        self.assertEqual(self.client.get(f"/api/teacher/question-bank/{question_id}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/teacher/question-bank/{question_id}").status_code, 404)
        self.login()
        self.assertEqual(self.client.delete(f"/api/teacher/question-bank/{question_id}").status_code, 200)
        self.assertEqual(self.count_questions(), 0)

    def test_two_and_six_options_are_valid(self):
        self.assertEqual(self.create_question().status_code, 201)
        self.assertEqual(self.create_question(
            question_text="Name a set of six.",
            options=["one", "two", "three", "four", "five", "six"],
            correct_option_index=5,
        ).status_code, 201)

    def test_invalid_answer_and_duplicate_options_are_rejected(self):
        self.assertEqual(self.create_question(correct_option_index=2).status_code, 400)
        self.assertEqual(self.create_question(options=["same", " SAME "]).status_code, 400)
        self.assertEqual(self.create_question(cognitive_level="invented").status_code, 400)

    def test_normalized_duplicate_question_is_rejected(self):
        self.assertEqual(self.create_question().status_code, 201)
        duplicate = self.create_question(question_text="  WHAT   IS FORCE? ")
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.count_questions(), 1)

    def test_pagination_search_topic_and_difficulty_filters(self):
        for index in range(12):
            response = self.create_question(
                question_text=f"Question number {index}",
                topic="Motion" if index < 6 else "Energy",
                difficulty="easy" if index % 2 == 0 else "hard",
            )
            self.assertEqual(response.status_code, 201)
        first = self.client.get("/api/teacher/question-bank?subject_id=1&page_size=10")
        self.assertEqual(first.json["pagination"]["total"], 12)
        self.assertEqual(first.json["pagination"]["total_pages"], 2)
        self.assertEqual(len(first.json["questions"]), 10)
        filtered = self.client.get(
            "/api/teacher/question-bank?subject_id=1&search=number%201&topic=Motion&difficulty=hard"
        )
        self.assertEqual(filtered.json["pagination"]["total"], 1)

    def test_template_has_exact_header_and_utf8_bom(self):
        response = self.client.get("/api/teacher/question-bank/template")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(next(csv.reader(io.StringIO(response.data.decode("utf-8-sig")))), list(CSV_COLUMNS))
        self.assertIn("question_bank_template.csv", response.headers["Content-Disposition"])

    def test_bom_csv_quoted_cells_preview_and_import_map_correct_option(self):
        row = self.csv_row(
            question='What is "force",\nin science?',
            option_a="Push, pull\nor both",
            explanation='A "force" can change motion.',
        )
        content = self.csv_bytes([row], bom=True)
        preview = self.upload_csv("/api/teacher/question-bank/import/preview", content)
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json["can_import"])
        self.assertEqual(preview.json["valid_count"], 1)
        self.assertEqual(self.count_questions(), 0)
        imported = self.upload_csv("/api/teacher/question-bank/import", content)
        self.assertEqual(imported.status_code, 201)
        stored = self.client.get("/api/teacher/question-bank?subject_id=1").json["questions"][0]
        self.assertEqual(stored["question"], 'What is "force",\nin science?')
        self.assertEqual(stored["options"][0], "Push, pull\nor both")
        self.assertEqual(stored["correct_option_index"], 0)
        self.assertEqual(stored["correct_answer"], "Push, pull\nor both")

    def test_missing_and_extra_csv_headers_are_reported(self):
        missing = self.csv_bytes([self.csv_row()], headers=CSV_COLUMNS[:-1])
        response = self.upload_csv("/api/teacher/question-bank/import/preview", missing)
        self.assertFalse(response.json["can_import"])
        self.assertTrue(any("Missing column: explanation" in item["message"] for item in response.json["errors"]))
        extra_headers = (*CSV_COLUMNS, "answer_text")
        extra = self.csv_bytes([self.csv_row() + ["wrong"]], headers=extra_headers)
        response = self.upload_csv("/api/teacher/question-bank/import/preview", extra)
        self.assertTrue(any("Unexpected column: answer_text" in item["message"] for item in response.json["errors"]))

        duplicate_headers = (*CSV_COLUMNS, " QUESTION ")
        duplicate = self.csv_bytes([self.csv_row() + ["duplicate"]], headers=duplicate_headers)
        response = self.upload_csv("/api/teacher/question-bank/import/preview", duplicate)
        self.assertTrue(any("Duplicate column: question" in item["message"] for item in response.json["errors"]))

    def test_invalid_utf8_csv_is_rejected(self):
        response = self.upload_csv("/api/teacher/question-bank/import/preview", b"\xff\xfe\xfa")
        self.assertEqual(response.status_code, 400)
        self.assertIn("UTF-8", response.json["error"])

    def test_non_csv_upload_is_rejected(self):
        response = self.client.post(
            "/api/teacher/question-bank/import/preview",
            data={"subject_id": "1", "file": (io.BytesIO(b"data"), "questions.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Only .csv", response.json["error"])

    def test_csv_invalid_values_gaps_duplicate_options_and_correct_mapping(self):
        invalid = self.csv_row(
            difficulty="normal", option_a="Newton", option_b="Newton", option_c="",
            option_d="four", correct_option="D",
        )
        response = self.upload_csv("/api/teacher/question-bank/import/preview", self.csv_bytes([invalid]))
        messages = " ".join(item["message"] for item in response.json["errors"])
        self.assertIn("Difficulty must be easy, medium, or hard", messages)
        self.assertIn("Options cannot contain gaps", messages)
        self.assertIn("Answer options must be unique", messages)
        self.assertIn("Correct option D has no value", messages)
        self.assertEqual(self.count_questions(), 0)

    def test_duplicate_csv_rows_and_existing_bank_duplicate_block_preview_and_import(self):
        repeated = self.csv_bytes([self.csv_row(), self.csv_row(question=" what   is FORCE? ")])
        preview = self.upload_csv("/api/teacher/question-bank/import/preview", repeated)
        self.assertEqual(preview.json["duplicate_count"], 1)
        self.assertFalse(preview.json["can_import"])
        self.assertEqual(self.count_questions(), 0)

        self.assertEqual(self.create_question().status_code, 201)
        preview = self.upload_csv("/api/teacher/question-bank/import/preview", self.csv_bytes([self.csv_row()]))
        self.assertEqual(preview.json["duplicate_count"], 1)
        imported = self.upload_csv("/api/teacher/question-bank/import", self.csv_bytes([self.csv_row()]))
        self.assertEqual(imported.status_code, 400)
        self.assertEqual(self.count_questions(), 1)

    def test_import_is_all_or_nothing_and_rolls_back_database_failures(self):
        invalid_csv = self.csv_bytes([self.csv_row("Good"), self.csv_row("Bad", difficulty="normal")])
        response = self.upload_csv("/api/teacher/question-bank/import", invalid_csv)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.count_questions(), 0)

        original = self.backend.mysql.connection
        self.backend.mysql.connection = FailingOptionConnection(self.db)
        try:
            response = self.upload_csv(
                "/api/teacher/question-bank/import",
                self.csv_bytes([self.csv_row("Rollback me")]),
            )
        finally:
            self.backend.mysql.connection = original
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.count_questions(), 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM question_bank_options").fetchone()[0], 0)

    def test_csv_limits_and_more_than_five_hundred_rows(self):
        rows = [self.csv_row(f"Bulk question {index}") for index in range(501)]
        preview = self.upload_csv("/api/teacher/question-bank/import/preview", self.csv_bytes(rows))
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json["valid_count"], 501)
        too_many = [self.csv_row(f"Over limit {index}") for index in range(MAX_CSV_ROWS + 1)]
        with self.assertRaisesRegex(ValueError, "5000"):
            parse_question_csv(self.csv_bytes(too_many))
        with self.assertRaisesRegex(ValueError, "5 MB"):
            parse_question_csv(b"x" * (5 * 1024 * 1024 + 1))

    def test_preview_reports_errors_truncated_after_one_hundred(self):
        rows = [self.csv_row(f"Invalid {index}", difficulty="normal") for index in range(110)]
        response = self.upload_csv("/api/teacher/question-bank/import/preview", self.csv_bytes(rows))
        self.assertEqual(response.json["error_count"], 110)
        self.assertTrue(response.json["errors_truncated"])
        self.assertEqual(len(response.json["errors"]), 100)

    def test_random_selection_filters_and_resolve_enforces_owner_and_subject(self):
        ids = []
        for index in range(3):
            response = self.create_question(question_text=f"Random {index}", topic="Motion")
            ids.append(response.json["question"]["id"])
        random_response = self.client.get("/api/teacher/question-bank/random?subject_id=1&count=2&topic=Motion&difficulty=medium")
        self.assertEqual(random_response.status_code, 200)
        self.assertEqual(len(random_response.json["questions"]), 2)
        self.assertEqual(random_response.json["questions"][0]["answer"], "A push or pull")
        too_many = self.client.get("/api/teacher/question-bank/random?subject_id=1&count=101")
        self.assertEqual(too_many.status_code, 400)
        unavailable = self.client.get("/api/teacher/question-bank/random?subject_id=1&count=4")
        self.assertEqual(unavailable.status_code, 400)
        self.assertIn("Only 3 matching questions", unavailable.json["error"])
        resolved = self.client.post("/api/teacher/question-bank/resolve", json={"subject_id": 1, "question_ids": ids[:2]})
        self.assertEqual(resolved.status_code, 200)
        wrong_subject = self.client.post("/api/teacher/question-bank/resolve", json={"subject_id": 2, "question_ids": ids[:1]})
        self.assertEqual(wrong_subject.status_code, 404)
        over_limit = self.client.post("/api/teacher/question-bank/resolve", json={"subject_id": 1, "question_ids": list(range(1, 102))})
        self.assertEqual(over_limit.status_code, 400)
        self.db.execute("INSERT INTO teacher_class_subjects VALUES(3,4,1,1,'2026-01-01')")
        self.db.commit()
        self.login("other_teacher")
        self.assertEqual(self.client.post("/api/teacher/question-bank/resolve", json={"subject_id": 1, "question_ids": ids[:1]}).status_code, 404)

    def test_npt_timestamps_and_quiz_snapshot_survive_bank_edit_and_delete(self):
        created = self.create_question()
        question_id = created.json["question"]["id"]
        self.db.execute(
            "UPDATE question_bank_questions SET created_at='2026-09-30 01:30:00', updated_at='2026-09-30 01:30:00' WHERE id=?",
            (question_id,),
        )
        self.db.commit()
        listed = self.client.get("/api/teacher/question-bank?subject_id=1").json["questions"][0]
        self.assertEqual(listed["created_at"], "Sep 30, 2026, 1:30 AM NPT")
        self.assertEqual(listed["updated_at"], "Sep 30, 2026, 1:30 AM NPT")

        snapshot = self.client.post(
            "/api/teacher/question-bank/resolve",
            json={"subject_id": 1, "question_ids": [question_id]},
        ).json["questions"][0]
        payload = {
            "title": "Snapshot quiz", "subject": "Science", "is_published": True,
            "questions": [{**snapshot, "question": snapshot["question"]}],
        }
        saved = self.client.post("/api/teacher/quizzes", json=payload)
        self.assertEqual(saved.status_code, 201)
        quiz_id = saved.json["quiz_id"]
        self.db.execute(
            "INSERT INTO quiz_results(student_id,quiz_id,score,total_questions) VALUES(1,?,1,1)",
            (quiz_id,),
        )
        self.db.commit()

        edited = self.client.put(
            f"/api/teacher/question-bank/{question_id}",
            json=self.question(question_text="Define force differently", options=["Answer B", "Other"], correct_option_index=0),
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(self.client.delete(f"/api/teacher/question-bank/{question_id}").status_code, 200)
        stored = json.loads(self.db.execute("SELECT questions FROM quizzes WHERE id=?", (quiz_id,)).fetchone()[0])
        self.assertEqual(stored[0]["question"], "What is force?")
        self.assertEqual(stored[0]["answer"], "A push or pull")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM quiz_results WHERE quiz_id=?", (quiz_id,)).fetchone()[0], 1)

        self.login("student")
        loaded = self.client.get(f"/api/student/quiz?quiz_id={quiz_id}")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json["quiz"]["questions"][0]["question"], "What is force?")
        submitted = self.client.post(
            "/api/student/quiz/submit",
            json={"quiz_id": quiz_id, "answers": {"0": "A push or pull"}},
        )
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.json["score"], 1)


if __name__ == "__main__":
    unittest.main()