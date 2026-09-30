"""Account lifecycle schema and Admin workflow regressions."""

from pathlib import Path
import unittest
import importlib

from werkzeug.security import check_password_hash, generate_password_hash

try:
    fixture = importlib.import_module("test_quiz_statistics")
except ModuleNotFoundError:
    fixture = importlib.import_module("backend.tests.test_quiz_statistics")


class AccountLifecycleSchemaTests(unittest.TestCase):
    def test_fresh_schema_and_migration_add_default_active_status(self):
        backend_root = Path(__file__).resolve().parents[1]
        schema = (backend_root / "setup_db.sql").read_text()
        migration = (backend_root / "migrations" / "022_user_account_status.sql").read_text()
        normalized_schema = " ".join(schema.split()).lower()
        normalized_migration = " ".join(migration.split()).lower()
        for normalized in (normalized_schema, normalized_migration):
            self.assertIn("is_active boolean not null default true", normalized)
            self.assertIn("deactivated_at datetime null", normalized)
            self.assertIn("idx_users_role_active", normalized)
        self.assertIn(
            "add column is_active boolean not null default true after must_change_password",
            normalized_migration,
        )
        self.assertNotIn("defaulttrue", normalized_migration)
        self.assertIn("information_schema.columns", migration.lower())
        self.assertIn("information_schema.statistics", migration.lower())
        self.assertIn("if column_exists = 0 then", normalized_migration)
        self.assertIn("if index_exists = 0 then", normalized_migration)
        self.assertIn("drop procedure if exists migrate_user_account_status", normalized_migration)
        self.assertLess(
            normalized_migration.index("call migrate_user_account_status();"),
            normalized_migration.index("drop procedure migrate_user_account_status;"),
        )
        self.assertNotIn("delete from users", migration.lower())


class AccountLifecycleApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.QuizStatisticsTests.setUpClass()
        cls.backend = fixture.QuizStatisticsTests.backend

    def setUp(self):
        fixture.QuizStatisticsTests.setUp(self)
        self.client = self.backend.app.test_client()
        self.db.execute(
            "UPDATE users SET password = ? WHERE id IN (1, 2, 3, 4, 5)",
            (generate_password_hash("ExistingPass123"),),
        )
        self.db.commit()

    def tearDown(self):
        fixture.QuizStatisticsTests.tearDown(self)

    def login(self, role="admin"):
        user_id = {"student": 1, "teacher": 2, "admin": 3, "other_teacher": 4}[role]
        actual_role = "teacher" if role == "other_teacher" else role
        with self.client.session_transaction() as session:
            session.clear()
            session.update(user_id=user_id, username=role, role=actual_role)

    def test_existing_users_default_active_and_migration_contract(self):
        rows = self.db.execute("SELECT is_active, deactivated_at FROM users").fetchall()
        self.assertTrue(all(row["is_active"] == 1 and row["deactivated_at"] is None for row in rows))
        setup_schema = (Path(__file__).resolve().parents[1] / "setup_db.sql").read_text().lower()
        migration = (Path(__file__).resolve().parents[1] / "migrations" / "022_user_account_status.sql").read_text().lower()
        self.assertIn("is_active boolean not null default true", setup_schema)
        self.assertIn("deactivated_at datetime null", setup_schema)
        self.assertIn("information_schema.columns", migration)

    def test_admin_user_list_paginates_searches_and_filters_status(self):
        for user_id in range(10, 36):
            self.db.execute(
                "INSERT INTO users(id,username,email,password,role,must_change_password,created_at) VALUES(?,?,?,?,?,0,'2026-01-01')",
                (user_id, f"Student {user_id}", f"student{user_id}@example.test", "hash", "student"),
            )
            self.db.execute(
                "INSERT INTO students(id,user_id,full_name,grade) VALUES(?,?,?,?)",
                (user_id, user_id, f"Student {user_id}", "10"),
            )
        self.db.execute("UPDATE users SET is_active=0,deactivated_at='2026-09-30 01:00:00' WHERE id=10")
        self.db.commit()
        self.login()
        first = self.client.get("/api/admin/accounts?role=student&status=all&page=1&page_size=10")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json["total"], 28)
        self.assertEqual(len(first.json["items"]), 10)
        self.assertEqual(first.json["total_pages"], 3)
        inactive = self.client.get("/api/admin/accounts?role=student&status=inactive")
        self.assertEqual(inactive.json["total"], 1)
        self.assertEqual(inactive.json["items"][0]["student_id"], 10)
        self.assertTrue(inactive.json["items"][0]["deactivated_at"].endswith("NPT"))
        active = self.client.get("/api/admin/accounts?role=student&status=active&search=STUDENT11")
        self.assertEqual(active.json["total"], 1)
        self.assertEqual(active.json["items"][0]["email"], "student11@example.test")
        email_search = self.client.get("/api/admin/accounts?role=student&status=all&search=student10@")
        self.assertEqual(email_search.json["total"], 1)
        invalid_size = self.client.get("/api/admin/accounts?role=student&page_size=5")
        self.assertEqual(invalid_size.status_code, 400)
        self.assertNotIn("password", str(first.json).lower())

    def test_student_and_teacher_edits_normalize_email_and_reject_duplicates(self):
        self.login()
        student = self.client.put("/api/admin/students/1", json={
            "full_name": "  Updated Student ", "email": " UPDATED@EXAMPLE.TEST ",
            "role": "admin", "class_id": 2,
        })
        self.assertEqual(student.status_code, 200)
        account = self.db.execute("SELECT username,email,role FROM users WHERE id=1").fetchone()
        profile = self.db.execute("SELECT full_name,grade FROM students WHERE id=1").fetchone()
        enrollment = self.db.execute("SELECT class_id FROM student_class_enrollments WHERE student_id=1 AND ended_at IS NULL").fetchone()
        self.assertEqual((account["username"], account["email"], account["role"]), ("Updated Student", "updated@example.test", "student"))
        self.assertEqual((profile["full_name"], profile["grade"]), ("Updated Student", "10"))
        self.assertEqual(enrollment["class_id"], 1)
        duplicate_student = self.client.put("/api/admin/students/1", json={"full_name": "Updated", "email": "t@example.test"})
        self.assertEqual(duplicate_student.status_code, 409)
        teacher = self.client.put("/api/admin/teachers/2", json={
            "username": " Updated Teacher ", "email": " UPDATED.T@EXAMPLE.TEST ", "role": "admin",
        })
        self.assertEqual(teacher.status_code, 200)
        teacher_row = self.db.execute("SELECT username,email,role FROM users WHERE id=2").fetchone()
        self.assertEqual((teacher_row["username"], teacher_row["email"], teacher_row["role"]), ("Updated Teacher", "updated.t@example.test", "teacher"))
        duplicate_teacher = self.client.put("/api/admin/teachers/2", json={"username": "Teacher", "email": "s2@example.test"})
        self.assertEqual(duplicate_teacher.status_code, 409)

    def test_teacher_list_search_pagination_and_status_filters(self):
        for user_id in range(10, 36):
            self.db.execute(
                "INSERT INTO users(id,username,email,password,role,must_change_password,created_at) VALUES(?,?,?,?,?,0,'2026-01-01')",
                (user_id, f"Teacher {user_id}", f"teacher{user_id}@example.test", "hash", "teacher"),
            )
        self.db.execute("UPDATE users SET is_active=0,deactivated_at='2026-09-30 01:00:00' WHERE id=10")
        self.db.commit()
        self.login()
        first = self.client.get("/api/admin/accounts?role=teacher&status=all&page=1&page_size=10")
        self.assertEqual(first.json["total"], 28)
        self.assertEqual(len(first.json["items"]), 10)
        self.assertEqual(first.json["total_pages"], 3)
        searched = self.client.get("/api/admin/accounts?role=teacher&status=active&search=TEACHER11")
        self.assertEqual(searched.json["total"], 1)
        self.assertEqual(searched.json["items"][0]["email"], "teacher11@example.test")
        inactive = self.client.get("/api/admin/accounts?role=teacher&status=inactive")
        self.assertEqual(inactive.json["total"], 1)

    def test_reset_password_hashes_and_requires_first_login_change(self):
        self.login()
        response = self.client.post("/api/admin/users/1/reset-password", json={"temporary_password": " NewTempPass123 "})
        self.assertEqual(response.status_code, 200)
        user = self.db.execute("SELECT password,must_change_password FROM users WHERE id=1").fetchone()
        self.assertTrue(check_password_hash(user["password"], " NewTempPass123 "))
        self.assertEqual(user["must_change_password"], 1)
        self.assertNotIn("NewTempPass123", response.get_data(as_text=True))
        self.assertEqual(self.client.post("/api/admin/users/1/reset-password", json={"temporary_password": "        "}).status_code, 400)
        self.assertEqual(self.client.post("/api/admin/users/3/reset-password", json={"temporary_password": "LongEnough123"}).status_code, 404)

    def test_deactivate_reactivate_preserves_student_and_teacher_history(self):
        self.login()
        before_enrollment = self.db.execute("SELECT COUNT(*) FROM student_class_enrollments WHERE student_id=1").fetchone()[0]
        before_assignment = self.db.execute("SELECT COUNT(*) FROM teacher_class_subjects WHERE teacher_user_id=2").fetchone()[0]
        student = self.client.post("/api/admin/users/1/deactivate")
        self.assertEqual(student.status_code, 200)
        self.assertEqual(self.db.execute("SELECT is_active FROM users WHERE id=1").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM student_class_enrollments WHERE student_id=1").fetchone()[0], before_enrollment)
        self.assertEqual(self.client.get("/api/admin/students/1/enrollment-history").json["history"][0]["class_id"], 1)
        self.assertEqual(self.client.post("/api/admin/users/1/deactivate").status_code, 200)
        self.assertEqual(self.client.post("/api/admin/users/1/reactivate").status_code, 200)
        self.assertEqual(self.db.execute("SELECT is_active,deactivated_at FROM users WHERE id=1").fetchone()["is_active"], 1)

        self.assertEqual(self.client.post("/api/admin/users/2/deactivate").status_code, 200)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM teacher_class_subjects WHERE teacher_user_id=2").fetchone()[0], before_assignment)
        setup = self.client.get("/api/admin/school-setup")
        self.assertNotIn(2, {teacher["id"] for teacher in setup.json["teachers"]})
        self.assertTrue(any(item["teacher_user_id"] == 2 for item in setup.json["assignments"]))
        self.assertEqual(self.client.post("/api/admin/teacher-assignments", json={
            "teacher_user_id": 2, "class_id": 2, "subject_id": 1,
        }).status_code, 404)
        self.assertEqual(self.client.post("/api/admin/users/2/reactivate").status_code, 200)

    def test_inactive_login_auth_me_and_existing_session_are_rejected(self):
        for user_id, role in ((1, "student"), (2, "teacher")):
            self.db.execute("UPDATE users SET is_active=0 WHERE id=?", (user_id,))
            self.db.commit()
            login = self.client.post("/api/login", json={"email": "s@example.test" if user_id == 1 else "t@example.test", "password": "ExistingPass123", "role": role})
            self.assertEqual(login.status_code, 403)
            self.assertIn("deactivated", login.json["error"])
            self.login("student" if user_id == 1 else "teacher")
            self.assertEqual(self.client.post("/api/auth/change-password", json={
                "current_password": "ExistingPass123",
                "new_password": "NewPassword456",
                "confirm_password": "NewPassword456",
            }).status_code, 403)
            self.login("student" if user_id == 1 else "teacher")
            me = self.client.get("/api/auth/me")
            self.assertEqual(me.status_code, 403)
            self.login("student" if user_id == 1 else "teacher")
            self.assertEqual(self.client.get("/api/student/quizzes" if user_id == 1 else "/api/teacher/question-bank/options").status_code, 403)
            self.db.execute("UPDATE users SET is_active=1 WHERE id=?", (user_id,))
            self.db.commit()
        for role, email in (("student", "s@example.test"), ("teacher", "t@example.test")):
            response = self.client.post("/api/login", json={"email": email, "password": "ExistingPass123", "role": role})
            self.assertEqual(response.status_code, 200)

    def test_admin_cannot_deactivate_admin_and_lifecycle_routes_are_admin_only(self):
        self.login()
        self.assertEqual(self.client.post("/api/admin/users/3/deactivate").status_code, 404)
        for role in ("student", "teacher"):
            self.login(role)
            self.assertEqual(self.client.get("/api/admin/accounts?role=student").status_code, 403)
            self.assertEqual(self.client.post("/api/admin/users/1/reactivate").status_code, 403)

    def test_dashboard_omits_expensive_recent_and_class_lists(self):
        for class_id in range(20, 27):
            self.db.execute(
                "INSERT INTO classes(id,name,grade,section,created_at) VALUES(?,?,?,?,?)",
                (class_id, f"Grade {class_id}", str(class_id), "A", "2026-01-01"),
            )
        for user_id in range(10, 22):
            self.db.execute(
                "INSERT INTO users(id,username,email,password,role,must_change_password,created_at) VALUES(?,?,?,?,?,0,'2026-09-30 03:00:00')",
                (user_id, f"Recent Admin {user_id}", f"recent{user_id}@example.test", "hash", "admin"),
            )
        self.db.execute("UPDATE users SET is_active=0,deactivated_at='2026-09-30 04:00:00' WHERE id=21")
        self.db.commit()
        self.login()
        response = self.client.get("/api/admin/dashboard")
        self.assertEqual(set(response.json["statistics"]), {"total_students", "total_teachers", "total_classes", "total_subjects"})
        self.assertNotIn("recent_users", response.json)
        self.assertNotIn("class_overview", response.json)
        self.assertEqual(response.json["statistics"]["total_classes"], 9)
        recent = response.json["recent_accounts"]
        self.assertEqual(len(recent), 10)
        self.assertEqual(recent[0]["user_id"], 21)
        self.assertFalse(recent[0]["is_active"])
        self.assertTrue(recent[0]["created_at"].endswith("NPT"))
        self.assertTrue(all("password" not in item and "hash" not in item for item in recent))
        self.assertLessEqual(len(response.json["school_snapshot"]), 6)
        science_class = next(item for item in response.json["school_snapshot"] if item["id"] == 1)
        self.assertEqual(science_class["student_count"], 1)
        self.assertEqual(science_class["subject_count"], 1)
        self.assertEqual(science_class["assigned_teacher_count"], 1)
        self.assertEqual(science_class["class_teacher_name"], "Teacher")


if __name__ == "__main__":
    unittest.main()