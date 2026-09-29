"""Institutional room chat authorization and history tests."""

import importlib
from pathlib import Path
import unittest
from unittest.mock import patch


try:
    fixture = importlib.import_module("test_quiz_statistics")
except ModuleNotFoundError:
    fixture = importlib.import_module("backend.tests.test_quiz_statistics")


ROOT = Path(__file__).resolve().parents[2]


class ChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.QuizStatisticsTests.setUpClass()
        cls.backend = fixture.QuizStatisticsTests.backend

    def setUp(self):
        fixture.QuizStatisticsTests.setUp(self)
        self.db.executescript('''
            CREATE TABLE chat_rooms(
                id INTEGER PRIMARY KEY,
                room_type TEXT NOT NULL,
                class_id INTEGER,
                subject_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                CHECK (
                    (room_type='class' AND class_id IS NOT NULL AND subject_id IS NULL)
                    OR (room_type='subject' AND class_id IS NOT NULL AND subject_id IS NOT NULL)
                    OR (room_type='staff' AND class_id IS NULL AND subject_id IS NULL)
                )
            );
            CREATE UNIQUE INDEX uq_chat_class_room
                ON chat_rooms(class_id) WHERE room_type='class';
            CREATE UNIQUE INDEX uq_chat_subject_room
                ON chat_rooms(class_id,subject_id) WHERE room_type='subject';
            CREATE UNIQUE INDEX uq_chat_staff_room
                ON chat_rooms(room_type) WHERE room_type='staff';
            CREATE TABLE chat_messages(
                id INTEGER PRIMARY KEY,
                room_id INTEGER NOT NULL,
                sender_user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        self.db.execute("INSERT INTO subjects VALUES(2,'Mathematics','MATH','2026-01-01')")
        self.db.commit()

    def tearDown(self):
        fixture.QuizStatisticsTests.tearDown(self)

    def login(self, role):
        fixture.QuizStatisticsTests.login(self, role)

    def room(self, room_type, class_id=None, subject_id=None):
        if room_type == "staff":
            self.db.execute(
                "INSERT INTO chat_rooms(room_type) VALUES('staff')"
            )
        else:
            self.db.execute(
                "INSERT INTO chat_rooms(room_type,class_id,subject_id) VALUES(?,?,?)",
                (room_type, class_id, subject_id)
            )
        self.db.commit()
        return self.db.execute("SELECT last_insert_rowid()").fetchone()[0]

    def rooms(self):
        response = self.client.get("/api/chat/rooms")
        self.assertEqual(response.status_code, 200)
        return response.json["rooms"]

    def send(self, room_id, payload):
        return self.client.post(
            f"/api/chat/rooms/{room_id}/messages", json=payload
        )

    def transfer_student_one_to_class_two(self):
        self.db.execute(
            "UPDATE student_class_enrollments SET ended_at='2026-09-29' "
            "WHERE student_id=1 AND ended_at IS NULL"
        )
        self.db.execute(
            """INSERT INTO student_class_enrollments
               (id,student_id,class_id,academic_year,started_at,ended_at,created_at)
               VALUES(3,1,2,'2084/85','2026-09-29',NULL,'2026-09-29')"""
        )
        self.db.commit()

    def test_student_can_list_current_class_and_subject_rooms(self):
        self.login("student")
        rooms = self.rooms()
        self.assertEqual({row["room_type"] for row in rooms}, {"class", "subject"})
        self.assertEqual({row["class_id"] for row in rooms}, {1})
        self.assertEqual({row["subject_name"] for row in rooms if row["room_type"] == "subject"}, {"Science"})
        self.assertTrue(any(row["name"] == "Staff Room" for row in rooms) is False)

    def test_student_cannot_access_old_class_room_after_transfer(self):
        self.login("student")
        old_room = next(room for room in self.rooms() if room["room_type"] == "class")
        self.transfer_student_one_to_class_two()
        response = self.client.get(f"/api/chat/rooms/{old_room['id']}/messages")
        self.assertEqual(response.status_code, 403)
        new_rooms = self.rooms()
        self.assertTrue(any(room["class_id"] == 2 for room in new_rooms))

    def test_transfer_preserves_old_messages_but_revokes_room_access(self):
        self.login("student")
        old_room = next(room for room in self.rooms() if room["room_type"] == "class")
        sent = self.send(old_room["id"], {"message": "Before transfer"})
        self.assertEqual(sent.status_code, 201)
        self.transfer_student_one_to_class_two()
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM chat_messages WHERE room_id=?", (old_room["id"],)).fetchone()[0],
            1
        )
        self.assertEqual(self.client.get(f"/api/chat/rooms/{old_room['id']}/messages").status_code, 403)

    def test_active_class_teacher_can_access_class_room(self):
        self.login("teacher")
        class_room = next(room for room in self.rooms() if room["room_type"] == "class")
        self.assertEqual(
            self.client.get(f"/api/chat/rooms/{class_room['id']}/messages").status_code,
            200
        )

    def test_former_class_teacher_loses_class_room_access(self):
        self.login("teacher")
        class_room = next(room for room in self.rooms() if room["room_type"] == "class")
        self.db.execute(
            "UPDATE class_teacher_assignments SET ended_at='2026-09-29' WHERE id=1"
        )
        self.db.execute(
            """INSERT INTO class_teacher_assignments
               (id,teacher_user_id,class_id,academic_year,started_at,created_at)
               VALUES(2,4,1,'2084/85','2026-09-29','2026-09-29')"""
        )
        self.db.commit()
        self.assertEqual(self.client.get(f"/api/chat/rooms/{class_room['id']}/messages").status_code, 403)
        self.login("other_teacher")
        self.assertEqual(self.client.get(f"/api/chat/rooms/{class_room['id']}/messages").status_code, 200)

    def test_subject_teacher_can_access_assigned_subject_room(self):
        self.db.execute(
            "INSERT INTO teacher_class_subjects VALUES(2,4,1,2,'2026-01-01')"
        )
        self.db.commit()
        subject_room = self.room("subject", 1, 2)
        self.login("other_teacher")
        self.assertEqual(self.client.get(f"/api/chat/rooms/{subject_room}/messages").status_code, 200)

    def test_subject_teacher_cannot_access_unassigned_subject_room(self):
        math_room = self.room("subject", 1, 2)
        self.login("teacher")
        self.assertEqual(self.client.get(f"/api/chat/rooms/{math_room}/messages").status_code, 403)

    def test_subject_teacher_does_not_gain_class_room_access(self):
        self.db.execute(
            "INSERT INTO teacher_class_subjects VALUES(2,4,2,1,'2026-01-01')"
        )
        self.db.commit()
        class_room = self.room("class", 2)
        self.login("other_teacher")
        self.assertEqual(self.client.get(f"/api/chat/rooms/{class_room}/messages").status_code, 403)

    def test_teacher_can_access_staff_room(self):
        self.login("teacher")
        staff_room = next(room for room in self.rooms() if room["room_type"] == "staff")
        self.assertEqual(self.client.get(f"/api/chat/rooms/{staff_room['id']}/messages").status_code, 200)

    def test_student_cannot_access_staff_room(self):
        staff_room = self.room("staff")
        self.login("student")
        self.assertEqual(self.client.get(f"/api/chat/rooms/{staff_room}/messages").status_code, 403)

    def test_admin_can_access_staff_room(self):
        self.login("admin")
        staff_room = next(room for room in self.rooms() if room["room_type"] == "staff")
        self.assertEqual(self.client.get(f"/api/chat/rooms/{staff_room['id']}/messages").status_code, 200)

    def test_admin_can_access_school_rooms_for_oversight(self):
        self.login("admin")
        rooms = self.rooms()
        self.assertEqual({room["room_type"] for room in rooms}, {"class", "subject", "staff"})
        self.assertEqual({room["class_id"] for room in rooms if room["class_id"] is not None}, {1, 2})
        for room in rooms:
            self.assertEqual(self.client.get(f"/api/chat/rooms/{room['id']}/messages").status_code, 200)

    def test_unauthenticated_user_cannot_access_chat(self):
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get("/api/chat/rooms").status_code, 401)
        self.assertEqual(self.client.get("/api/chat/rooms/1/messages").status_code, 401)
        self.assertEqual(self.client.post("/api/chat/rooms/1/messages", json={"message": "Hello"}).status_code, 401)

    def test_authorized_user_can_send_message(self):
        self.login("student")
        class_room = next(room for room in self.rooms() if room["room_type"] == "class")
        response = self.send(class_room["id"], {"message": "  Hello class  "})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["message"]["message"], "Hello class")
        self.assertEqual(response.json["message"]["sender"]["display_name"], "Student One")
        self.assertEqual(response.json["message"]["sender"]["role"], "student")

    def test_sender_identity_is_derived_from_session(self):
        self.login("student")
        class_room = next(room for room in self.rooms() if room["room_type"] == "class")
        for field in ("sender_id", "sender_user_id"):
            response = self.send(class_room["id"], {"message": "Session sender", field: 3})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0], 0)
        accepted = self.send(class_room["id"], {"message": "Session sender"})
        self.assertEqual(accepted.json["message"]["sender"]["id"], 1)

    def test_chat_responses_exclude_private_account_fields(self):
        self.login("student")
        rooms = self.rooms()
        class_room = next(room for room in rooms if room["room_type"] == "class")
        sent = self.send(class_room["id"], {"message": "Safe identity"})
        payload = str({"rooms": rooms, "message": sent.json["message"]}).lower()
        self.assertNotIn("email", payload)
        self.assertNotIn("password", payload)
        self.assertEqual(
            set(sent.json["message"]["sender"]),
            {"id", "display_name", "role"}
        )

    def test_unauthorized_user_cannot_send_message(self):
        class_room = self.room("class", 2)
        self.login("student")
        response = self.send(class_room, {"message": "Private class"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0], 0)

    def test_student_cannot_access_another_class_room(self):
        other_class_room = self.room("class", 2)
        self.login("student")
        response = self.client.get(f"/api/chat/rooms/{other_class_room}/messages")
        self.assertEqual(response.status_code, 403)

    def test_message_insert_failure_rolls_back(self):
        self.db.executescript('''CREATE TRIGGER fail_chat_message
            BEFORE INSERT ON chat_messages
            BEGIN SELECT RAISE(ABORT, 'simulated message failure'); END;''')
        self.db.commit()
        self.login("student")
        class_room = next(room for room in self.rooms() if room["room_type"] == "class")
        response = self.send(class_room["id"], {"message": "Will roll back"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0], 0)

    def test_message_send_is_rate_limited_per_user(self):
        self.login("student")
        class_room = next(room for room in self.rooms() if room["room_type"] == "class")
        responses = [
            self.send(class_room["id"], {"message": f"Rate test {index}"})
            for index in range(31)
        ]
        self.assertEqual(responses[-1].status_code, 429)
        self.assertIn("Too many chat messages", responses[-1].json["error"])

    def test_blank_message_rejected(self):
        self.login("student")
        class_room = next(room for room in self.rooms() if room["room_type"] == "class")
        for value in ("", "  \n\t"):
            response = self.send(class_room["id"], {"message": value})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0], 0)

    def test_oversized_message_rejected(self):
        self.login("student")
        class_room = next(room for room in self.rooms() if room["room_type"] == "class")
        response = self.send(class_room["id"], {"message": "x" * 2001})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0], 0)

    def test_message_history_requires_current_access(self):
        self.login("student")
        class_room = next(room for room in self.rooms() if room["room_type"] == "class")
        self.send(class_room["id"], {"message": "History"})
        self.transfer_student_one_to_class_two()
        response = self.client.get(f"/api/chat/rooms/{class_room['id']}/messages")
        self.assertEqual(response.status_code, 403)

    def test_message_history_is_paginated(self):
        self.login("student")
        class_room = next(room for room in self.rooms() if room["room_type"] == "class")
        for index in range(1, 6):
            self.assertEqual(self.send(class_room["id"], {"message": f"Message {index}"}).status_code, 201)
        latest = self.client.get(f"/api/chat/rooms/{class_room['id']}/messages?limit=2")
        self.assertEqual([row["message"] for row in latest.json["messages"]], ["Message 4", "Message 5"])
        self.assertTrue(latest.json["has_more"])
        before_id = latest.json["next_before_id"]
        older = self.client.get(f"/api/chat/rooms/{class_room['id']}/messages?limit=2&before_id={before_id}")
        self.assertEqual([row["message"] for row in older.json["messages"]], ["Message 2", "Message 3"])

    def test_message_history_supports_tuple_fetchall(self):
        self.login("student")
        class_room = next(room for room in self.rooms() if room["room_type"] == "class")
        for index in range(1, 6):
            self.assertEqual(
                self.send(class_room["id"], {"message": f"Tuple page {index}"}).status_code,
                201
            )

        connection = self.backend.mysql.connection
        original_cursor = connection.cursor

        class TupleFetchallCursor:
            def __init__(self, cursor):
                self.cursor = cursor

            def fetchall(self):
                return tuple(self.cursor.fetchall())

            def __getattr__(self, name):
                return getattr(self.cursor, name)

        with patch.object(
            connection,
            "cursor",
            side_effect=lambda: TupleFetchallCursor(original_cursor())
        ):
            latest = self.client.get(
                f"/api/chat/rooms/{class_room['id']}/messages?limit=2"
            )
            self.assertEqual(latest.status_code, 200)
            self.assertEqual(
                [row["message"] for row in latest.json["messages"]],
                ["Tuple page 4", "Tuple page 5"]
            )
            self.assertTrue(latest.json["has_more"])
            self.assertEqual(latest.json["next_before_id"], latest.json["messages"][0]["id"])

            before_id = latest.json["next_before_id"]
            older = self.client.get(
                f"/api/chat/rooms/{class_room['id']}/messages?limit=2&before_id={before_id}"
            )
            self.assertEqual(older.status_code, 200)
            self.assertEqual(
                [row["message"] for row in older.json["messages"]],
                ["Tuple page 2", "Tuple page 3"]
            )
            self.assertTrue(older.json["has_more"])

            oldest = self.client.get(
                f"/api/chat/rooms/{class_room['id']}/messages?limit=2&before_id="
                f"{older.json['next_before_id']}"
            )
            self.assertEqual(oldest.status_code, 200)
            self.assertEqual(
                [row["message"] for row in oldest.json["messages"]],
                ["Tuple page 1"]
            )
            self.assertFalse(oldest.json["has_more"])
            self.assertIsNone(oldest.json["next_before_id"])

    def test_old_messages_remain_after_membership_changes(self):
        self.login("teacher")
        class_room = next(room for room in self.rooms() if room["room_type"] == "class")
        sent = self.send(class_room["id"], {"message": "Teacher history"})
        self.assertEqual(sent.status_code, 201)
        self.db.execute(
            "UPDATE class_teacher_assignments SET ended_at='2026-09-29' WHERE id=1"
        )
        self.db.commit()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM chat_messages WHERE room_id=?", (class_room["id"],)).fetchone()[0], 1)

    def test_chat_schema_contract(self):
        migration = (ROOT / "backend/migrations/018_chat_system.sql").read_text()
        setup_schema = (ROOT / "backend/setup_db.sql").read_text()
        for sql in (migration, setup_schema):
            self.assertIn("CREATE TABLE IF NOT EXISTS chat_rooms", sql)
            self.assertIn("CREATE TABLE IF NOT EXISTS chat_messages", sql)
            self.assertIn("room_type ENUM('class', 'subject', 'staff')", sql)
            self.assertIn("subject_room_class_key", sql)
            self.assertIn("staff_room_key", sql)
            self.assertIn("message VARCHAR(2000)", sql)
            self.assertIn("fk_chat_messages_sender", sql)
        self.assertIn("UNIQUE KEY uq_chat_class_room", migration)
        self.assertIn("UNIQUE KEY uq_chat_subject_room", migration)
        self.assertIn("UNIQUE KEY uq_chat_staff_room", migration)


if __name__ == "__main__":
    unittest.main()
