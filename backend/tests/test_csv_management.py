"""Admin CSV bulk-management validation and transaction regressions."""

import csv
import importlib
import io
import unittest
from werkzeug.security import check_password_hash


try:
    fixture = importlib.import_module("test_quiz_statistics")
except ModuleNotFoundError:
    fixture = importlib.import_module("backend.tests.test_quiz_statistics")


class CSVManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.QuizStatisticsTests.setUpClass()
        cls.backend = fixture.QuizStatisticsTests.backend

    def setUp(self):
        fixture.QuizStatisticsTests.setUp(self)

    def tearDown(self):
        fixture.QuizStatisticsTests.tearDown(self)

    def login(self, role):
        fixture.QuizStatisticsTests.login(self, role)

    def upload(self, endpoint, content, filename="import.csv"):
        if isinstance(content, str):
            content = content.encode("utf-8")
        stream = io.BytesIO(content)
        response = self.client.post(
            endpoint,
            data={"file": (stream, filename)},
            content_type="multipart/form-data"
        )
        stream.close()
        return response

    @staticmethod
    def student_csv(*rows):
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow((
            "full_name", "email", "temporary_password", "grade", "section",
            "academic_year",
        ))
        writer.writerows(rows)
        return output.getvalue()

    @staticmethod
    def teacher_csv(*rows):
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(("full_name", "email", "temporary_password"))
        writer.writerows(rows)
        return output.getvalue()

    @staticmethod
    def assignment_csv(*rows):
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(("teacher_email", "grade", "section", "subject_code"))
        writer.writerows(rows)
        return output.getvalue()

    def test_student_csv_preview_is_valid_and_performs_no_writes(self):
        self.login("admin")
        before = self.db.total_changes
        response = self.upload(
            "/api/admin/csv/students/preview",
            self.student_csv(("New Student", " NEW@EXAMPLE.TEST ", "SecretTemp123", "10", "Default", "2083/84"))
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["valid"])
        self.assertEqual(response.json["total_rows"], 1)
        self.assertEqual(response.json["rows"][0]["row_number"], 2)
        self.assertEqual(response.json["rows"][0]["email"], "new@example.test")
        self.assertEqual(response.json["rows"][0]["class_name"], "Grade 10")
        self.assertNotIn("temporary_password", response.json["rows"][0])
        self.assertNotIn("SecretTemp123", response.get_data(as_text=True))
        self.assertEqual(self.db.total_changes, before)

    def test_student_preview_rejects_missing_and_unknown_headers(self):
        self.login("admin")
        missing = self.upload(
            "/api/admin/csv/students/preview",
            "full_name,email,temporary_password,grade\nPerson,p@example.test,TempPass123,10\n"
        )
        unknown = self.upload(
            "/api/admin/csv/students/preview",
            "full_name,email,temporary_password,grade,section,secret\nPerson,p@example.test,TempPass123,10,A,x\n"
        )
        duplicate_headers = self.upload(
            "/api/admin/csv/students/preview",
            "full_name,email,temporary_password,grade,section, email\n"
        )
        self.assertEqual(missing.status_code, 400)
        self.assertIn("section", missing.json["error"] or "")
        self.assertEqual(unknown.status_code, 400)
        self.assertIn("Unknown header", unknown.json["error"])
        self.assertEqual(duplicate_headers.status_code, 400)
        self.assertIn("duplicate headers", duplicate_headers.json["error"])

    def test_student_preview_reports_email_class_and_duplicate_errors_by_row(self):
        self.login("admin")
        content = self.student_csv(
            ("First", "dup@example.test", "TempPass123", "10", "Default", ""),
            ("Second", "DUP@example.test", "TempPass123", "10", "Default", ""),
            ("Missing class", "missing@example.test", "TempPass123", "10", "C", ""),
            ("Existing email", "s@example.test", "TempPass123", "10", "Default", ""),
        )
        response = self.upload("/api/admin/csv/students/preview", content)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["valid"])
        self.assertEqual(response.json["invalid_rows"], 3)
        self.assertEqual(response.json["rows"][1]["row_number"], 3)
        self.assertIn("Duplicate email", response.json["rows"][1]["errors"][0]["message"])
        self.assertTrue(any("does not exist" in error["message"]
                            for error in response.json["rows"][2]["errors"]))
        self.assertTrue(any("already exists" in error["message"]
                            for error in response.json["rows"][3]["errors"]))

    def test_csv_parser_accepts_utf8_bom_and_ignores_blank_rows(self):
        self.login("admin")
        content = "\ufeff" + self.student_csv(
            ("Élodie Student", "elodie@example.test", "TempPass123", "10", "Default", ""),
            ("", "", "", "", "", ""),
        )
        response = self.upload("/api/admin/csv/students/preview", content.encode("utf-8"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["total_rows"], 1)
        self.assertEqual(response.json["rows"][0]["full_name"], "Élodie Student")

    def test_csv_parser_rejects_empty_malformed_invalid_utf8_and_non_csv_files(self):
        self.login("admin")
        endpoint = "/api/admin/csv/students/preview"
        self.assertEqual(self.upload(endpoint, b"", "empty.csv").status_code, 400)
        self.assertEqual(self.upload(endpoint, b"\xff\xfe", "bad.csv").status_code, 400)
        malformed = self.upload(endpoint, b'full_name,email,temporary_password,grade,section\n"broken', "bad.csv")
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(self.upload(endpoint, "whatever", "users.xlsx").status_code, 400)

    def test_csv_parser_rejects_more_than_5000_rows_and_files_over_5mb(self):
        self.login("admin")
        endpoint = "/api/admin/csv/students/preview"
        many_rows = self.student_csv(*[
            (f"Student {index}", f"student{index}@example.test", "TempPass123", "10", "Default", "")
            for index in range(5001)
        ])
        too_many = self.upload(endpoint, many_rows)
        too_large = self.upload(endpoint, b"x" * (5 * 1024 * 1024 + 1), "big.csv")
        self.assertEqual(too_many.status_code, 400)
        self.assertIn("5000", too_many.json["error"])
        self.assertEqual(too_large.status_code, 400)
        self.assertIn("5 MB", too_large.json["error"])

    def test_csv_parser_accepts_5000_rows_and_bounds_password_safe_preview(self):
        self.login("admin")
        content = self.student_csv(*[
            (f"Student {index}", f"student{index}@example.test", "TempPass123", "10", "Default", "")
            for index in range(5000)
        ])
        response = self.upload("/api/admin/csv/students/preview", content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["total_rows"], 5000)
        self.assertEqual(response.json["valid_rows"], 5000)
        self.assertEqual(len(response.json["rows"]), 50)
        self.assertNotIn("TempPass123", response.get_data(as_text=True))
        self.assertNotIn("temporary_password", response.get_data(as_text=True))

    def test_invalid_preview_keeps_full_counts_and_caps_returned_error_details(self):
        self.login("admin")
        content = self.student_csv(*[
            (f"Student {index}", f"student{index}@example.test", "short", "10", "Default", "")
            for index in range(120)
        ])
        response = self.upload("/api/admin/csv/students/preview", content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["total_rows"], 120)
        self.assertEqual(response.json["invalid_rows"], 120)
        self.assertEqual(response.json["error_count"], 120)
        self.assertTrue(response.json["errors_truncated"])
        self.assertEqual(len(response.json["rows"]), 100)
        self.assertEqual(response.json["problem_summary"][0]["type"], "short_password")
        self.assertEqual(response.json["problem_summary"][0]["count"], 120)

    def test_class_and_subject_reference_downloads_are_admin_only(self):
        self.login("admin")
        classes = self.client.get("/api/admin/csv/references/classes")
        self.assertEqual(classes.status_code, 200)
        class_rows = list(csv.DictReader(io.StringIO(classes.get_data(as_text=True))))
        self.assertEqual(class_rows[0], {
            "class_id": "1", "class_name": "Grade 10", "grade": "10", "section": "Default",
        })
        subjects = self.client.get("/api/admin/csv/references/subjects")
        self.assertEqual(subjects.status_code, 200)
        subject_rows = list(csv.DictReader(io.StringIO(subjects.get_data(as_text=True))))
        self.assertEqual(subject_rows[0], {
            "subject_id": "1", "subject_name": "Science", "subject_code": "SCI",
        })
        for role in ("student", "teacher"):
            self.login(role)
            self.assertEqual(self.client.get("/api/admin/csv/references/classes").status_code, 403)
            self.assertEqual(self.client.get("/api/admin/csv/references/subjects").status_code, 403)

    def test_assignment_import_rolls_back_all_new_rows_on_database_failure(self):
        self.db.execute("INSERT INTO subjects VALUES(2,'Mathematics','MATH','2026-01-01')")
        self.db.executescript('''CREATE TRIGGER fail_assignment
            BEFORE INSERT ON teacher_class_subjects WHEN NEW.subject_id = 2
            BEGIN SELECT RAISE(ABORT, 'insert failed'); END;''')
        self.db.commit()
        self.login("admin")
        before = self.db.execute("SELECT COUNT(*) FROM teacher_class_subjects").fetchone()[0]
        response = self.upload(
            "/api/admin/csv/teacher-assignments/import",
            self.assignment_csv(
                ("t@example.test", "9", "Default", "SCI"),
                ("t@example.test", "10", "Default", "MATH"),
            ),
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM teacher_class_subjects").fetchone()[0], before)

    def test_student_bulk_import_creates_hashed_accounts_and_active_enrollments(self):
        self.login("admin")
        content = self.student_csv(
            ("Bulk Student", "bulk@example.test", "PrivateTemp456", "10", "Default", "2083/84"),
            ("Second Student", "second@example.test", "AnotherTemp456", "9", "Default", ""),
        )
        response = self.upload("/api/admin/csv/students/import", content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["imported_students"], 2)
        account = self.db.execute(
            "SELECT id,username,email,password,role,must_change_password FROM users WHERE email='bulk@example.test'"
        ).fetchone()
        self.assertEqual(account["role"], "student")
        self.assertEqual(account["must_change_password"], 1)
        self.assertTrue(check_password_hash(account["password"], "PrivateTemp456"))
        self.assertNotEqual(account["password"], "PrivateTemp456")
        student = self.db.execute(
            "SELECT id,grade FROM students WHERE user_id=?", (account["id"],)
        ).fetchone()
        self.assertEqual(student["grade"], "10")
        enrollment = self.db.execute(
            "SELECT class_id,academic_year,started_at,ended_at FROM student_class_enrollments WHERE student_id=?",
            (student["id"],)
        ).fetchone()
        self.assertEqual(enrollment["class_id"], 1)
        self.assertEqual(enrollment["academic_year"], "2083/84")
        self.assertIsNotNone(enrollment["started_at"])
        self.assertIsNone(enrollment["ended_at"])
        self.assertNotIn("PrivateTemp456", response.get_data(as_text=True))

    def test_student_import_is_all_or_nothing_on_database_failure(self):
        self.db.executescript('''CREATE TRIGGER fail_second_student
            BEFORE INSERT ON students WHEN NEW.full_name = 'Fail Student'
            BEGIN SELECT RAISE(ABORT, 'insert failed'); END;''')
        self.db.commit()
        self.login("admin")
        before_users = self.db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        before_students = self.db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        response = self.upload(
            "/api/admin/csv/students/import",
            self.student_csv(
                ("Good Student", "good@example.test", "TempPass123", "10", "Default", ""),
                ("Fail Student", "fail@example.test", "TempPass456", "10", "Default", ""),
            )
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["errors"][0]["row_number"], 3)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM users").fetchone()[0], before_users)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM students").fetchone()[0], before_students)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM student_class_enrollments").fetchone()[0], 2)

    def test_student_import_revalidates_email_after_preview(self):
        self.login("admin")
        content = self.student_csv(
            ("New Student", "race@example.test", "TempPass123", "10", "Default", "")
        )
        preview = self.upload("/api/admin/csv/students/preview", content)
        self.assertTrue(preview.json["valid"])
        self.db.execute(
            "INSERT INTO users(username,email,password,role) VALUES('Created concurrently','race@example.test','hash','teacher')"
        )
        self.db.commit()
        imported = self.upload("/api/admin/csv/students/import", content)
        self.assertEqual(imported.status_code, 400)
        self.assertEqual(imported.json["rows"][0]["errors"][0]["message"], "Email already exists")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM students").fetchone()[0], 2)

    def test_teacher_preview_and_import_hash_passwords_and_reject_duplicates(self):
        self.login("admin")
        content = self.teacher_csv(
            ("New Teacher", " NEW.TEACHER@example.test ", "TeacherTemp789")
        )
        preview = self.upload("/api/admin/csv/teachers/preview", content)
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json["valid"])
        self.assertNotIn("TeacherTemp789", preview.get_data(as_text=True))
        self.assertNotIn("temporary_password", preview.json["rows"][0])
        imported = self.upload("/api/admin/csv/teachers/import", content)
        self.assertEqual(imported.status_code, 200)
        self.assertEqual(imported.json["imported_teachers"], 1)
        teacher = self.db.execute(
            "SELECT password,role,must_change_password FROM users WHERE email='new.teacher@example.test'"
        ).fetchone()
        self.assertEqual(teacher["role"], "teacher")
        self.assertEqual(teacher["must_change_password"], 1)
        self.assertTrue(check_password_hash(teacher["password"], "TeacherTemp789"))
        duplicate = self.upload("/api/admin/csv/teachers/import", content)
        self.assertEqual(duplicate.status_code, 400)

    def test_teacher_preview_rejects_existing_and_duplicate_emails_in_same_csv(self):
        self.login("admin")
        response = self.upload(
            "/api/admin/csv/teachers/preview",
            self.teacher_csv(
                ("First Teacher", "repeat@example.test", "TempPass123"),
                ("Second Teacher", "REPEAT@example.test", "TempPass456"),
                ("Existing Teacher", "t@example.test", "TempPass789"),
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["valid"])
        self.assertTrue(any(
            "Duplicate email within this CSV" in error["message"]
            for error in response.json["rows"][1]["errors"]
        ))
        self.assertTrue(any(
            "Email already exists" in error["message"]
            for error in response.json["rows"][2]["errors"]
        ))
        self.assertNotIn("TempPass123", response.get_data(as_text=True))
        self.assertNotIn("temporary_password", response.get_data(as_text=True))

    def test_teacher_import_rolls_back_all_rows_on_failure(self):
        self.db.executescript('''CREATE TRIGGER fail_teacher
            BEFORE INSERT ON users WHEN NEW.email = 'fail.teacher@example.test'
            BEGIN SELECT RAISE(ABORT, 'insert failed'); END;''')
        self.db.commit()
        self.login("admin")
        before = self.db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        response = self.upload(
            "/api/admin/csv/teachers/import",
            self.teacher_csv(
                ("Good Teacher", "good.teacher@example.test", "TempPass123"),
                ("Fail Teacher", "fail.teacher@example.test", "TempPass456"),
            )
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["errors"][0]["row_number"], 3)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM users").fetchone()[0], before)

    def test_assignment_preview_resolves_normalized_teacher_class_and_subject(self):
        self.login("admin")
        response = self.upload(
            "/api/admin/csv/teacher-assignments/preview",
            self.assignment_csv((" T@EXAMPLE.TEST ", "10", "Default", "sci"))
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["valid"])
        row = response.json["rows"][0]
        self.assertEqual(row["teacher_email"], "t@example.test")
        self.assertEqual(row["class_name"], "Grade 10")
        self.assertEqual(row["subject_name"], "Science")
        self.assertEqual(row["status"], "Already exists")

    def test_assignment_preview_rejects_invalid_references_and_duplicate_rows(self):
        self.db.execute("INSERT INTO subjects VALUES(2,'Mathematics','MATH','2026-01-01')")
        self.db.commit()
        self.login("admin")
        response = self.upload(
            "/api/admin/csv/teacher-assignments/preview",
            self.assignment_csv(
                ("s@example.test", "10", "Default", "SCI"),
                ("t@example.test", "99", "Missing", "SCI"),
                ("t@example.test", "10", "Default", "MISSING"),
                ("t@example.test", "10", "Default", "MATH"),
                ("T@EXAMPLE.TEST", "10", "Default", "math"),
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["valid"])
        rows = response.json["rows"]
        self.assertEqual(rows[0]["row_number"], 2)
        self.assertIn("Teacher account not found", rows[0]["errors"][0]["message"])
        self.assertTrue(any("does not exist" in error["message"] for error in rows[1]["errors"]))
        self.assertIn("Subject code not found", rows[2]["errors"][0]["message"])
        self.assertEqual(rows[4]["row_number"], 6)
        self.assertIn("Duplicate assignment", rows[4]["errors"][0]["message"])

    def test_assignment_import_skips_existing_and_adds_new(self):
        self.db.execute("INSERT INTO subjects VALUES(2,'Mathematics','MATH','2026-01-01')")
        self.db.commit()
        self.login("admin")
        content = self.assignment_csv(
            ("t@example.test", "10", "Default", "SCI"),
            ("t@example.test", "10", "Default", "MATH"),
        )
        response = self.upload("/api/admin/csv/teacher-assignments/import", content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["imported_assignments"], 1)
        self.assertEqual(response.json["skipped_existing"], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM teacher_class_subjects").fetchone()[0], 2)

    def test_invalid_assignment_row_prevents_partial_import(self):
        self.db.execute("INSERT INTO subjects VALUES(2,'Mathematics','MATH','2026-01-01')")
        self.db.commit()
        self.login("admin")
        before = self.db.execute("SELECT COUNT(*) FROM teacher_class_subjects").fetchone()[0]
        response = self.upload(
            "/api/admin/csv/teacher-assignments/import",
            self.assignment_csv(
                ("t@example.test", "10", "Default", "MATH"),
                ("t@example.test", "10", "Default", "MISSING"),
            )
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM teacher_class_subjects").fetchone()[0], before)

    def test_student_teacher_and_admin_csv_endpoints_are_admin_only(self):
        self.login("student")
        student_denied = self.client.get("/api/admin/csv/templates/students")
        self.assertEqual(student_denied.status_code, 403)
        self.login("teacher")
        teacher_denied = self.client.get("/api/admin/csv/teachers/export")
        self.assertEqual(teacher_denied.status_code, 403)

    def test_templates_have_exact_headers(self):
        self.login("admin")
        cases = [
            ("students", ["full_name", "email", "temporary_password", "grade", "section", "academic_year"]),
            ("teachers", ["full_name", "email", "temporary_password"]),
            ("teacher-assignments", ["teacher_email", "grade", "section", "subject_code"]),
        ]
        for name, expected in cases:
            with self.subTest(name=name):
                response = self.client.get(f"/api/admin/csv/templates/{name}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(next(csv.reader(io.StringIO(response.get_data(as_text=True)))), expected)
                self.assertIn("attachment; filename=", response.headers["Content-Disposition"])

    def test_exports_are_current_only_and_exclude_password_fields(self):
        self.db.execute("UPDATE student_class_enrollments SET ended_at='2026-09-01' WHERE id=1")
        self.db.execute('''INSERT INTO student_class_enrollments
            (id,student_id,class_id,academic_year,started_at,created_at)
            VALUES(3,1,2,'2083/84','2026-09-02','2026-09-02')''')
        self.db.commit()
        self.login("admin")
        students = list(csv.DictReader(io.StringIO(
            self.client.get("/api/admin/csv/students/export").get_data(as_text=True)
        )))
        self.assertEqual(len([row for row in students if row["email"] == "s@example.test"]), 1)
        self.assertEqual(next(row for row in students if row["email"] == "s@example.test")["class_name"], "Grade 9")
        teacher_data = self.client.get("/api/admin/csv/teachers/export").get_data(as_text=True)
        self.assertNotIn("password", teacher_data.lower())
        self.assertNotIn("must_change_password", teacher_data.lower())
        teacher_rows = list(csv.DictReader(io.StringIO(teacher_data)))
        self.assertTrue(next(row for row in teacher_rows if row["email"] == "t@example.test")["created_at"].endswith("NPT"))
        assignments = list(csv.DictReader(io.StringIO(
            self.client.get("/api/admin/csv/teacher-assignments/export").get_data(as_text=True)
        )))
        self.assertEqual(assignments, [{
            "teacher_name": "Teacher", "teacher_email": "t@example.test",
            "grade": "10", "section": "Default", "class_name": "Grade 10",
            "subject_name": "Science", "subject_code": "SCI",
        }])

    def test_csv_exports_neutralize_formula_like_user_text(self):
        for index, name in enumerate(("=2+3", "+2+3", "-2+3", "@SUM(A1:A2)")):
            self.db.execute(
                "INSERT INTO users(username,email,password,role) VALUES(?,?,?,'teacher')",
                (name, f"formula{index}@example.test", "hash")
            )
        self.db.commit()
        self.login("admin")
        rows = list(csv.DictReader(io.StringIO(
            self.client.get("/api/admin/csv/teachers/export").get_data(as_text=True)
        )))
        for index, name in enumerate(("=2+3", "+2+3", "-2+3", "@SUM(A1:A2)")):
            row = next(item for item in rows if item["email"] == f"formula{index}@example.test")
            self.assertEqual(row["full_name"], "'" + name)
            self.assertEqual(row["email"], f"formula{index}@example.test")
        ordinary = next(item for item in rows if item["email"] == "t@example.test")
        self.assertEqual(ordinary["email"], "t@example.test")

    def test_student_and_teacher_cannot_access_csv_exports(self):
        for role in ("student", "teacher"):
            with self.subTest(role=role):
                self.login(role)
                response = self.client.get("/api/admin/csv/students/export")
                self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()