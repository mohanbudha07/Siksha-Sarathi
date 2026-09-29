"""Notice delivery, authorization, and schema contract regressions."""

import importlib
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch


try:
    fixture = importlib.import_module("test_quiz_statistics")
except ModuleNotFoundError:
    fixture = importlib.import_module("backend.tests.test_quiz_statistics")


ROOT = Path(__file__).resolve().parents[1]


class NoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.QuizStatisticsTests.setUpClass()
        cls.backend = fixture.QuizStatisticsTests.backend

    def setUp(self):
        fixture.QuizStatisticsTests.setUp(self)
        self.db.executescript('''
            CREATE TABLE notices(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_by_user_id INTEGER NOT NULL,
                title TEXT NOT NULL CHECK(length(title) <= 200),
                body TEXT NOT NULL CHECK(length(body) <= 5000),
                visibility TEXT NOT NULL DEFAULT 'internal'
                    CHECK(visibility IN ('internal','public')),
                audience_type TEXT NOT NULL CHECK(audience_type IN
                    ('all','students','teachers','class','subject','student','teacher')),
                target_class_id INTEGER,
                target_subject_id INTEGER,
                target_user_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK(visibility != 'public' OR audience_type = 'all'),
                FOREIGN KEY(created_by_user_id) REFERENCES users(id),
                FOREIGN KEY(target_class_id) REFERENCES classes(id),
                FOREIGN KEY(target_subject_id) REFERENCES subjects(id),
                FOREIGN KEY(target_user_id) REFERENCES users(id)
            );
            CREATE TABLE notice_recipients(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notice_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                delivered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                read_at TEXT,
                UNIQUE(notice_id,user_id),
                FOREIGN KEY(notice_id) REFERENCES notices(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        ''')
        self.db.commit()

    def tearDown(self):
        fixture.QuizStatisticsTests.tearDown(self)

    def login(self, role):
        fixture.QuizStatisticsTests.login(self, role)

    def publish_admin(self, **overrides):
        payload = {
            "title": "School notice",
            "body": "Please read the official update.",
            "visibility": "internal",
            "audience_type": "all",
        }
        payload.update(overrides)
        return self.client.post("/api/admin/notices", json=payload)

    def publish_teacher(self, **overrides):
        payload = {
            "title": "Class notice",
            "body": "Please check the schedule.",
            "visibility": "internal",
            "audience_type": "class",
            "class_id": 1,
        }
        payload.update(overrides)
        return self.client.post("/api/teacher/notices", json=payload)

    def recipients(self, notice_id):
        return {
            row[0] for row in self.db.execute(
                "SELECT user_id FROM notice_recipients WHERE notice_id=?",
                (notice_id,)
            ).fetchall()
        }

    def test_admin_can_publish_notice_to_entire_institution(self):
        self.login("admin")
        response = self.publish_admin()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.recipients(response.json["notice_id"]), {1, 2, 3, 4, 5})

    def test_admin_can_publish_notice_to_all_students(self):
        self.login("admin")
        response = self.publish_admin(audience_type="students")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.recipients(response.json["notice_id"]), {1, 5})

    def test_admin_can_publish_notice_to_all_teachers(self):
        self.login("admin")
        response = self.publish_admin(audience_type="teachers")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.recipients(response.json["notice_id"]), {2, 4})

    def test_admin_can_publish_notice_to_specific_class(self):
        self.login("admin")
        response = self.publish_admin(audience_type="class", class_id=1)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.recipients(response.json["notice_id"]), {1})

    def test_admin_can_publish_notice_to_specific_student(self):
        self.login("admin")
        response = self.publish_admin(audience_type="student", student_id=2)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.recipients(response.json["notice_id"]), {5})

    def test_admin_can_publish_notice_to_specific_teacher(self):
        self.login("admin")
        response = self.publish_admin(audience_type="teacher", teacher_user_id=4)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.recipients(response.json["notice_id"]), {4})

    def test_public_notice_requires_admin_and_institution_scope(self):
        self.login("admin")
        response = self.publish_admin(visibility="public", audience_type="class", class_id=1)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notices").fetchone()[0], 0)

    def test_teacher_cannot_publish_public_notice(self):
        self.login("teacher")
        response = self.publish_teacher(visibility="public")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notices").fetchone()[0], 0)

    def test_active_class_teacher_can_publish_to_own_class(self):
        self.login("teacher")
        response = self.publish_teacher()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.recipients(response.json["notice_id"]), {1})

    def test_former_class_teacher_cannot_publish_to_old_class(self):
        self.db.execute(
            "UPDATE class_teacher_assignments SET ended_at='2026-09-01' WHERE id=1"
        )
        self.db.commit()
        self.login("teacher")
        response = self.publish_teacher()
        self.assertEqual(response.status_code, 403)

    def test_replacement_class_teacher_can_publish_while_former_notice_delivery_survives(self):
        self.login("teacher")
        first = self.publish_teacher()
        self.assertEqual(first.status_code, 201)
        first_notice_id = first.json["notice_id"]
        self.db.execute(
            "UPDATE class_teacher_assignments SET ended_at='2026-09-15' WHERE id=1"
        )
        self.db.execute('''INSERT INTO class_teacher_assignments
            (id,teacher_user_id,class_id,academic_year,started_at,created_at)
            VALUES(2,4,1,'2084/85','2026-09-16','2026-09-16')''')
        self.db.commit()

        self.login("teacher")
        self.assertEqual(self.publish_teacher().status_code, 403)
        self.login("other_teacher")
        second = self.publish_teacher()
        self.assertEqual(second.status_code, 201)
        self.assertEqual(self.recipients(first_notice_id), {1})
        self.assertEqual(self.recipients(second.json["notice_id"]), {1})
        self.login("student")
        inbox = self.client.get("/api/notices")
        self.assertEqual({item["id"] for item in inbox.json["notices"]}, {
            first_notice_id, second.json["notice_id"]
        })

    def test_subject_teacher_can_publish_to_assigned_class_subject(self):
        self.db.execute(
            "UPDATE class_teacher_assignments SET ended_at='2026-09-01' WHERE id=1"
        )
        self.db.commit()
        self.login("teacher")
        response = self.publish_teacher(
            audience_type="subject", subject_id=1
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.recipients(response.json["notice_id"]), {1})

    def test_subject_teacher_cannot_publish_class_wide_without_class_teacher_role(self):
        self.db.execute(
            "UPDATE class_teacher_assignments SET ended_at='2026-09-01' WHERE id=1"
        )
        self.db.commit()
        self.login("teacher")
        response = self.publish_teacher(audience_type="class")
        self.assertEqual(response.status_code, 403)

    def test_subject_teacher_cannot_publish_to_unassigned_scope(self):
        self.login("teacher")
        wrong_class = self.publish_teacher(
            audience_type="subject", class_id=2, subject_id=1
        )
        self.assertEqual(wrong_class.status_code, 403)
        self.db.execute("INSERT INTO subjects VALUES(2,'Mathematics','MATH','2026-01-01')")
        self.db.commit()
        wrong_subject = self.publish_teacher(
            audience_type="subject", subject_id=2
        )
        self.assertEqual(wrong_subject.status_code, 403)

    def test_teacher_can_target_student_they_teach(self):
        self.login("teacher")
        response = self.publish_teacher(audience_type="student", student_id=1)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.recipients(response.json["notice_id"]), {1})

    def test_teacher_cannot_target_unrelated_student(self):
        self.login("teacher")
        response = self.publish_teacher(audience_type="student", student_id=2)
        self.assertEqual(response.status_code, 403)

    def test_notice_recipients_are_snapshotted_at_publish_time(self):
        self.login("admin")
        created = self.publish_admin(audience_type="class", class_id=1)
        notice_id = created.json["notice_id"]
        self.assertEqual(self.recipients(notice_id), {1})
        self.db.execute(
            "UPDATE student_class_enrollments SET ended_at='2026-09-15' WHERE id=1"
        )
        self.db.execute('''INSERT INTO student_class_enrollments
            (id,student_id,class_id,started_at,created_at)
            VALUES(3,1,2,'2026-09-16','2026-09-16')''')
        self.db.commit()
        self.assertEqual(self.recipients(notice_id), {1})

    def test_transfer_does_not_remove_already_delivered_notice(self):
        self.login("admin")
        old_notice = self.publish_admin(audience_type="class", class_id=1).json["notice_id"]
        self.db.execute(
            "UPDATE student_class_enrollments SET ended_at='2026-09-15' WHERE id=1"
        )
        self.db.execute('''INSERT INTO student_class_enrollments
            (id,student_id,class_id,started_at,created_at)
            VALUES(3,1,2,'2026-09-16','2026-09-16')''')
        self.db.commit()
        self.login("student")
        inbox = self.client.get("/api/notices")
        self.assertEqual([item["id"] for item in inbox.json["notices"]], [old_notice])

    def test_transferred_student_does_not_receive_new_old_class_notice(self):
        self.db.execute(
            "UPDATE student_class_enrollments SET ended_at='2026-09-15' WHERE id=1"
        )
        self.db.execute('''INSERT INTO student_class_enrollments
            (id,student_id,class_id,started_at,created_at)
            VALUES(3,1,2,'2026-09-16','2026-09-16')''')
        self.db.commit()
        self.login("admin")
        old_class = self.publish_admin(audience_type="class", class_id=1)
        new_class = self.publish_admin(audience_type="class", class_id=2)
        self.assertEqual(old_class.status_code, 400)
        self.assertEqual(new_class.status_code, 201)
        self.assertEqual(self.recipients(new_class.json["notice_id"]), {1, 5})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notices").fetchone()[0], 1)

    def test_recipient_inbox_returns_only_own_notices(self):
        self.login("admin")
        created = self.publish_admin(audience_type="all")
        notice_id = created.json["notice_id"]
        self.login("student")
        inbox = self.client.get("/api/notices")
        self.assertEqual(inbox.status_code, 200)
        self.assertEqual([item["id"] for item in inbox.json["notices"]], [notice_id])
        self.assertNotIn("recipients", inbox.json["notices"][0])
        self.assertNotIn("user_id", inbox.json["notices"][0])

    def test_notice_read_state_is_per_recipient(self):
        self.login("admin")
        notice_id = self.publish_admin(audience_type="all").json["notice_id"]
        self.login("student")
        self.assertEqual(self.client.patch(f"/api/notices/{notice_id}/read").status_code, 200)
        self.login("other_teacher")
        inbox = self.client.get("/api/notices")
        self.assertFalse(inbox.json["notices"][0]["is_read"])
        self.assertIsNone(inbox.json["notices"][0]["read_at"])

    def test_mark_notice_read_is_idempotent(self):
        self.login("admin")
        notice_id = self.publish_admin(audience_type="student", student_id=1).json["notice_id"]
        self.login("student")
        first = self.client.patch(f"/api/notices/{notice_id}/read")
        read_at = self.db.execute(
            "SELECT read_at FROM notice_recipients WHERE notice_id=? AND user_id=1",
            (notice_id,)
        ).fetchone()[0]
        second = self.client.patch(f"/api/notices/{notice_id}/read")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.db.execute(
            "SELECT read_at FROM notice_recipients WHERE notice_id=? AND user_id=1",
            (notice_id,)
        ).fetchone()[0], read_at)

    def test_non_recipient_cannot_mark_notice_read(self):
        self.login("admin")
        notice_id = self.publish_admin(audience_type="student", student_id=1).json["notice_id"]
        self.login("other_teacher")
        self.assertEqual(self.client.patch(f"/api/notices/{notice_id}/read").status_code, 404)

    def test_unread_count_is_user_specific(self):
        self.login("admin")
        notice_id = self.publish_admin(audience_type="all").json["notice_id"]
        self.login("student")
        self.client.patch(f"/api/notices/{notice_id}/read")
        self.assertEqual(self.client.get("/api/notices/unread-count").json["unread_count"], 0)
        self.login("other_teacher")
        self.assertEqual(self.client.get("/api/notices/unread-count").json["unread_count"], 1)

    def test_public_notices_endpoint_exposes_only_public_notices(self):
        self.login("admin")
        public = self.publish_admin(visibility="public", audience_type="all")
        internal = self.publish_admin(visibility="internal", audience_type="all")
        response = self.client.get("/api/public/notices")
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json["notices"]]
        self.assertIn(public.json["notice_id"], ids)
        self.assertNotIn(internal.json["notice_id"], ids)
        self.assertNotIn("read_at", response.json["notices"][0])
        self.assertNotIn("target_class_id", response.json["notices"][0])

    def test_internal_notice_never_appears_publicly(self):
        self.login("admin")
        internal = self.publish_admin(audience_type="all")
        response = self.client.get("/api/public/notices")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            internal.json["notice_id"],
            [item["id"] for item in response.json["notices"]]
        )

    def test_duplicate_notice_recipient_is_prevented(self):
        self.login("admin")
        notice_id = self.publish_admin(audience_type="student", student_id=1).json["notice_id"]
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO notice_recipients(notice_id,user_id) VALUES(?,?)",
                (notice_id, 1)
            )

    def test_admin_notice_publish_rolls_back_when_delivery_insert_fails(self):
        self.db.executescript('''CREATE TRIGGER fail_notice_delivery
            BEFORE INSERT ON notice_recipients
            BEGIN SELECT RAISE(ABORT, 'delivery insert failed'); END;''')
        self.db.commit()
        self.login("admin")
        response = self.publish_admin(audience_type="all")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notices").fetchone()[0], 0)

    def test_admin_teacher_and_student_notice_route_security(self):
        self.login("student")
        self.assertEqual(self.publish_admin().status_code, 403)
        self.assertEqual(self.publish_teacher().status_code, 403)
        self.login("teacher")
        self.assertEqual(self.publish_admin().status_code, 403)
        self.login("admin")
        self.assertEqual(self.publish_teacher().status_code, 403)

    def test_unauthenticated_user_cannot_access_internal_inbox_but_can_read_public_feed(self):
        self.login("admin")
        self.publish_admin(visibility="public", audience_type="all")
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get("/api/notices").status_code, 401)
        self.assertEqual(self.client.get("/api/notices/unread-count").status_code, 401)
        self.assertEqual(self.client.get("/api/public/notices").status_code, 200)

    def test_teacher_options_only_include_assigned_scopes_and_students(self):
        self.db.execute(
            "INSERT INTO classes VALUES(3,'Grade 8','8','A','2026-01-01')"
        )
        self.db.execute(
            "UPDATE student_class_enrollments SET class_id=3 WHERE student_id=2"
        )
        self.db.execute(
            "INSERT INTO student_class_enrollments"
            "(id, student_id, class_id, academic_year, started_at, ended_at, transfer_note, created_at)"
            " VALUES(3,1,3,NULL,'2025-01-01','2025-12-31',NULL,'2025-01-01')"
        )
        self.db.execute(
            "INSERT INTO teacher_class_subjects VALUES(2,2,3,1,'2026-01-01')"
        )
        self.db.execute(
            "INSERT INTO class_teacher_assignments"
            "(id, teacher_user_id, class_id, academic_year, started_at, ended_at, created_at)"
            " VALUES(2,2,2,'2025/26','2025-01-01','2025-12-31','2025-01-01')"
        )
        self.db.commit()
        self.login("teacher")
        response = self.client.get("/api/teacher/notices/options")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["class_id"] for item in response.json["class_teacher_classes"]], [1])
        self.assertEqual(
            {(item["class_id"], item["subject_id"])
             for item in response.json["subject_assignments"]},
            {(1, 1), (3, 1)}
        )
        students = response.json["students"]
        self.assertEqual(
            {(item["student_id"], item["class_id"]) for item in students},
            {(1, 1), (2, 3)}
        )
        for student in students:
            self.assertEqual(set(student), {
                "student_id", "full_name", "class_id", "class_name"
            })

    def test_teacher_options_database_failure_returns_generic_json(self):
        self.login("teacher")
        connection = self.backend.mysql.connection
        original_cursor = connection.cursor
        with patch.object(
            connection,
            "cursor",
            side_effect=[original_cursor(), RuntimeError("private SQL details")]
        ):
            response = self.client.get("/api/teacher/notices/options")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json, {"error": "Unable to load notice options"})
        self.assertNotIn("private SQL details", response.get_data(as_text=True))

    def test_admin_notice_options_exclude_sensitive_account_fields(self):
        self.login("admin")
        response = self.client.get("/api/admin/notices/options")
        self.assertEqual(response.status_code, 200)
        self.assertIn("classes", response.json)
        self.assertEqual(set(response.json["students"][0]), {
            "student_id", "full_name", "class_name"
        })
        self.assertEqual(set(response.json["teachers"][0]), {
            "teacher_user_id", "username"
        })

    def test_notice_requires_nonempty_eligible_audience_and_valid_content(self):
        self.db.execute("INSERT INTO classes VALUES(3,'Empty Class','8','A','2026-01-01')")
        self.db.commit()
        self.login("admin")
        empty = self.publish_admin(audience_type="class", class_id=3)
        invalid_title = self.publish_admin(title="x" * 201)
        invalid_body = self.publish_admin(body=" ")
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(invalid_title.status_code, 400)
        self.assertEqual(invalid_body.status_code, 400)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notices").fetchone()[0], 0)

    def test_sent_notices_are_creator_scoped_and_include_delivery_counts(self):
        self.login("admin")
        own_notice = self.publish_admin(audience_type="all").json["notice_id"]
        self.login("teacher")
        teacher_notice = self.publish_teacher().json["notice_id"]
        self.login("student")
        self.assertEqual(self.client.patch(
            f"/api/notices/{teacher_notice}/read"
        ).status_code, 200)
        self.login("teacher")
        sent_teacher = self.client.get("/api/notices/sent")
        self.assertEqual([item["id"] for item in sent_teacher.json["notices"]], [teacher_notice])
        self.assertEqual(sent_teacher.json["notices"][0]["delivered_count"], 1)
        self.assertEqual(sent_teacher.json["notices"][0]["read_count"], 1)
        self.login("admin")
        sent_admin = self.client.get("/api/notices/sent")
        self.assertEqual([item["id"] for item in sent_admin.json["notices"]], [own_notice])

    def test_notice_schema_contract_in_migration_and_canonical_schema(self):
        migration = (ROOT / "migrations/017_notice_system.sql").read_text()
        schema = (ROOT / "setup_db.sql").read_text()
        for source in (migration, schema):
            self.assertIn("CREATE TABLE IF NOT EXISTS notices", source)
            self.assertIn("CREATE TABLE IF NOT EXISTS notice_recipients", source)
            self.assertIn("uq_notice_recipient (notice_id, user_id)", source)
            self.assertIn("idx_notice_recipients_user_read (user_id, read_at)", source)
            self.assertIn("read_at TIMESTAMP NULL", source)
        self.assertIn("fk_notice_recipients_notice", migration)
        self.assertIn("fk_notice_recipients_user", migration)


if __name__ == "__main__":
    unittest.main()