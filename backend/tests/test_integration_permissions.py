"""Cross-feature permission scenarios for Phase 8 integration hardening."""

import importlib
import unittest
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash


try:
    fixture = importlib.import_module("test_quiz_statistics")
except ModuleNotFoundError:
    fixture = importlib.import_module("backend.tests.test_quiz_statistics")


class IntegrationPermissionTests(unittest.TestCase):
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
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE chat_messages(
                id INTEGER PRIMARY KEY,
                room_id INTEGER NOT NULL,
                sender_user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE notices(
                id INTEGER PRIMARY KEY,
                created_by_user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                visibility TEXT NOT NULL,
                audience_type TEXT NOT NULL,
                target_class_id INTEGER,
                target_subject_id INTEGER,
                target_user_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE notice_recipients(
                id INTEGER PRIMARY KEY,
                notice_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                delivered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                read_at TEXT,
                UNIQUE(notice_id,user_id)
            );
        ''')
        self.db.commit()

    def tearDown(self):
        fixture.QuizStatisticsTests.tearDown(self)

    def login(self, role):
        fixture.QuizStatisticsTests.login(self, role)

    def login_api(self, role, password="Password123"):
        ids = {"student": 1, "teacher": 2, "admin": 3}
        user_id = ids[role]
        self.db.execute(
            "UPDATE users SET password=? WHERE id=?",
            (generate_password_hash(password), user_id)
        )
        self.db.commit()
        email = self.db.execute(
            "SELECT email FROM users WHERE id=?", (user_id,)
        ).fetchone()[0]
        endpoint = "/api/admin/login" if role == "admin" else "/api/login"
        payload = {"email": email, "password": password}
        if role != "admin":
            payload["role"] = role
        response = self.client.post(endpoint, json=payload)
        self.assertEqual(response.status_code, 200)
        return response

    def current_room(self, room_type, class_id=1):
        self.login("student")
        response = self.client.get("/api/chat/rooms")
        self.assertEqual(response.status_code, 200)
        return next(
            room for room in response.json["rooms"]
            if room["room_type"] == room_type and room["class_id"] == class_id
        )

    def test_student_transfer_integrates_chat_attendance_notices_and_teacher_scope(self):
        self.login("admin")
        old_notice = self.client.post("/api/admin/notices", json={
            "title": "Class A notice", "body": "Delivered before transfer",
            "visibility": "internal", "audience_type": "class", "class_id": 1,
        })
        self.assertEqual(old_notice.status_code, 201)

        self.db.execute(
            "INSERT INTO classes VALUES(3,'Grade 10 Section B','10','B','2026-01-01')"
        )
        self.db.execute(
            "INSERT INTO teacher_class_subjects VALUES(2,4,3,1,'2026-01-01')"
        )
        self.db.execute(
            """INSERT INTO class_teacher_assignments
               (id,teacher_user_id,class_id,academic_year,started_at,created_at)
               VALUES(2,4,3,'2084/85','2026-01-01','2026-01-01')"""
        )
        self.db.execute(
            """INSERT INTO monthly_attendance_summaries
               (id,teacher_user_id,class_id,attendance_month,total_school_days)
               VALUES(1,2,1,'2026-09-01',20)"""
        )
        self.db.execute(
            """INSERT INTO monthly_attendance_records
               (id,summary_id,student_id,present_days,note)
               VALUES(1,1,1,18,'Before transfer')"""
        )
        self.db.commit()

        old_room = self.current_room("class")
        self.assertEqual(self.client.post(
            f"/api/chat/rooms/{old_room['id']}/messages",
            json={"message": "Class A history"}
        ).status_code, 201)

        self.login("admin")
        transfer = self.client.put("/api/admin/students/1/class", json={
            "class_id": 3, "academic_year": "2084/85",
            "transfer_note": "Integration test transfer",
        })
        self.assertEqual(transfer.status_code, 200)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM student_class_enrollments "
            "WHERE student_id=1 AND ended_at IS NOT NULL"
        ).fetchone()[0], 1)
        self.assertEqual(self.db.execute(
            "SELECT class_id FROM student_class_enrollments "
            "WHERE student_id=1 AND ended_at IS NULL"
        ).fetchone()[0], 3)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE room_id=?",
            (old_room["id"],)
        ).fetchone()[0], 1)

        self.login("student")
        self.assertEqual(self.client.get(
            f"/api/chat/rooms/{old_room['id']}/messages"
        ).status_code, 403)
        new_rooms = self.client.get("/api/chat/rooms").json["rooms"]
        self.assertTrue(any(
            room["room_type"] == "class" and room["class_id"] == 3
            for room in new_rooms
        ))
        self.assertTrue(any(
            room["room_type"] == "subject" and room["class_id"] == 3
            and room["subject_id"] == 1
            for room in new_rooms
        ))
        self.assertEqual(
            self.client.get("/api/student/attendance").json["records"][0]["present_days"],
            18
        )
        inbox = self.client.get("/api/notices")
        self.assertEqual(
            [notice["id"] for notice in inbox.json["notices"]],
            [old_notice.json["notice_id"]]
        )

        self.login("admin")
        self.assertEqual(self.client.post("/api/admin/notices", json={
            "title": "Future Class A", "body": "No transferred student",
            "visibility": "internal", "audience_type": "class", "class_id": 1,
        }).status_code, 400)
        new_notice = self.client.post("/api/admin/notices", json={
            "title": "Class B notice", "body": "Current membership",
            "visibility": "internal", "audience_type": "class", "class_id": 3,
        })
        self.assertEqual(new_notice.status_code, 201)
        self.assertEqual(self.db.execute(
            "SELECT user_id FROM notice_recipients WHERE notice_id=?",
            (new_notice.json["notice_id"],)
        ).fetchall()[0]["user_id"], 1)

        self.login("teacher")
        self.assertEqual(self.client.get(
            "/api/teacher/students/1/learning-profile?subject=Science"
        ).status_code, 404)
        future_attendance = self.client.post("/api/teacher/monthly-attendance", json={
            "class_id": 1, "attendance_month": "2026-10", "total_school_days": 20,
        })
        self.assertEqual(future_attendance.status_code, 201)
        roster = self.client.get(
            f"/api/teacher/monthly-attendance/{future_attendance.json['attendance_summary_id']}"
        )
        self.assertEqual(roster.status_code, 200)
        self.assertNotIn(1, [student["student_id"] for student in roster.json["students"]])

    def test_class_teacher_replacement_integrates_attendance_notices_and_chat(self):
        self.login("teacher")
        attendance = self.client.post("/api/teacher/monthly-attendance", json={
            "class_id": 1, "attendance_month": "2026-09", "total_school_days": 20,
        })
        self.assertEqual(attendance.status_code, 201)
        summary_id = attendance.json["attendance_summary_id"]
        self.assertEqual(self.client.put(
            f"/api/teacher/monthly-attendance/{summary_id}/records",
            json={"records": [{"student_id": 1, "present_days": 18}]}
        ).status_code, 200)
        prior_notice = self.client.post("/api/teacher/notices", json={
            "title": "Before replacement", "body": "Historical delivery",
            "visibility": "internal", "audience_type": "class", "class_id": 1,
        })
        self.assertEqual(prior_notice.status_code, 201)
        old_room = self.current_room("class")
        self.login("teacher")
        self.assertEqual(self.client.post(
            f"/api/chat/rooms/{old_room['id']}/messages",
            json={"message": "Before teacher change"}
        ).status_code, 201)

        self.login("admin")
        changed = self.client.post("/api/admin/class-teacher-assignments", json={
            "teacher_user_id": 4, "class_id": 1, "academic_year": "2084/85",
        })
        self.assertEqual(changed.status_code, 201)

        self.login("teacher")
        self.assertEqual(self.client.post("/api/teacher/monthly-attendance", json={
            "class_id": 1, "attendance_month": "2026-10", "total_school_days": 20,
        }).status_code, 404)
        self.assertEqual(self.client.put(
            f"/api/teacher/monthly-attendance/{summary_id}/records",
            json={"records": [{"student_id": 1, "present_days": 19}]}
        ).status_code, 403)
        self.assertEqual(self.client.get(
            f"/api/teacher/monthly-attendance/{summary_id}"
        ).status_code, 200)
        self.assertEqual(self.client.post("/api/teacher/notices", json={
            "title": "Former teacher", "body": "Must be denied",
            "visibility": "internal", "audience_type": "class", "class_id": 1,
        }).status_code, 403)
        self.assertEqual(self.client.get(
            f"/api/chat/rooms/{old_room['id']}/messages"
        ).status_code, 403)

        self.login("other_teacher")
        self.assertEqual(self.client.post("/api/teacher/monthly-attendance", json={
            "class_id": 1, "attendance_month": "2026-10", "total_school_days": 20,
        }).status_code, 201)
        replacement_notice = self.client.post("/api/teacher/notices", json={
            "title": "After replacement", "body": "Current teacher",
            "visibility": "internal", "audience_type": "class", "class_id": 1,
        })
        self.assertEqual(replacement_notice.status_code, 201)
        self.assertEqual(self.client.get(
            f"/api/chat/rooms/{old_room['id']}/messages"
        ).status_code, 200)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE room_id=?", (old_room["id"],)
        ).fetchone()[0], 1)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM notice_recipients WHERE notice_id=?",
            (prior_notice.json["notice_id"],)
        ).fetchone()[0], 1)

    def test_subject_assignments_bound_note_quiz_lab_and_assessment_operations(self):
        self.db.execute("INSERT INTO subjects VALUES(2,'Mathematics','MATH','2026-01-01')")
        self.db.execute(
            "INSERT INTO teacher_class_subjects VALUES(2,4,1,2,'2026-01-01')"
        )
        self.db.commit()
        note_payload = {
            "title": "Scoped note", "subject": "Mathematics",
            "chapter": "Algebra", "content": "Text", "class_id": 1,
        }
        self.login("teacher")
        unassigned_note = self.client.post("/api/teacher/notes", json=note_payload)
        self.assertEqual(unassigned_note.status_code, 403)
        own_note = self.client.post("/api/teacher/notes", json={
            **note_payload, "subject": "Science",
        })
        self.assertEqual(own_note.status_code, 201)
        note_id = self.db.execute(
            "SELECT id FROM notes WHERE uploaded_by=2 ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        self.assertEqual(self.client.put(f"/api/teacher/notes/{note_id}", json={
            **note_payload, "subject": "Mathematics",
        }).status_code, 403)

        science_quiz = {
            "title": "Scoped quiz", "subject": "Science", "is_published": True,
            "questions": [{
                "question": "Question?", "options": ["A", "B"], "answer": "A",
                "topic": "Topic", "difficulty": "easy",
            }],
        }
        math_quiz = {**science_quiz, "subject": "Mathematics"}
        self.assertEqual(self.client.post("/api/teacher/quizzes", json=math_quiz).status_code, 403)
        science_quiz_response = self.client.post(
            "/api/teacher/quizzes", json=science_quiz
        )
        self.assertEqual(science_quiz_response.status_code, 201)
        science_quiz_id = science_quiz_response.json["quiz_id"]
        self.assertEqual(self.client.put(
            f"/api/teacher/quizzes/{science_quiz_id}", json=math_quiz
        ).status_code, 403)

        self.login("other_teacher")
        math_note = self.client.post("/api/teacher/notes", json={
            **note_payload, "subject": "Mathematics",
        })
        self.assertEqual(math_note.status_code, 201)
        self.assertEqual(self.client.post(
            "/api/teacher/quizzes", json=math_quiz
        ).status_code, 201)
        self.assertEqual(self.client.post("/api/teacher/notes", json={
            **note_payload, "subject": "Science",
        }).status_code, 403)
        self.assertEqual(self.client.post("/api/teacher/quizzes", json=science_quiz).status_code, 403)
        self.assertEqual(self.client.get(
            f"/api/teacher/notes/{note_id}"
        ).status_code, 404)
        self.assertEqual(self.client.put(
            f"/api/teacher/notes/{note_id}", json=note_payload
        ).status_code, 404)
        self.assertEqual(self.client.delete(
            f"/api/teacher/notes/{note_id}"
        ).status_code, 404)
        self.assertEqual(self.client.post("/api/teacher/paper-assessments", json={
            "class_id": 1, "subject": "Science", "title": "Math teacher cannot",
            "assessment_type": "class_test", "assessment_date": "2026-09-29",
            "max_marks": 20,
        }).status_code, 404)

        self.db.execute(
            """INSERT INTO quizzes
               (id,title,subject,questions,created_by,is_published,created_at)
                    VALUES(4,'Foreign Science','Science','[]',4,1,'2026-01-01')"""
        )
        self.db.commit()
        now = datetime.now(timezone.utc)
        session_payload = {
            "quiz_id": 4, "class_id": 1, "access_code": "ABCD",
            "starts_at": (now - timedelta(minutes=1)).isoformat(),
            "ends_at": (now + timedelta(minutes=30)).isoformat(),
        }
        self.assertEqual(self.client.post(
            "/api/teacher/quiz-sessions", json=session_payload
        ).status_code, 404)

    def test_scored_assessment_is_preserved_and_former_assignment_loses_access(self):
        self.login("teacher")
        payload = {
            "class_id": 1, "subject": "Science", "title": "Preserved marks",
            "assessment_type": "class_test", "assessment_date": "2026-09-29",
            "max_marks": 20,
        }
        created = self.client.post("/api/teacher/paper-assessments", json=payload)
        self.assertEqual(created.status_code, 201)
        assessment_id = created.json["assessment_id"]
        score_url = f"/api/teacher/paper-assessments/{assessment_id}/scores"
        self.assertEqual(self.client.put(score_url, json={
            "scores": [{"student_id": 1, "marks_obtained": 15}],
        }).status_code, 200)
        delete = self.client.delete(f"/api/teacher/paper-assessments/{assessment_id}")
        self.assertEqual(delete.status_code, 409)
        self.assertEqual(self.db.execute(
            "SELECT marks_obtained FROM paper_assessment_scores WHERE assessment_id=?",
            (assessment_id,)
        ).fetchone()[0], 15)

        self.db.execute("DELETE FROM teacher_class_subjects WHERE teacher_user_id=2 AND class_id=1 AND subject_id=1")
        self.db.commit()
        self.assertEqual(self.client.get(
            f"/api/teacher/paper-assessments/{assessment_id}"
        ).status_code, 404)
        self.assertEqual(self.client.put(score_url, json={"scores": []}).status_code, 404)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM paper_assessment_scores WHERE assessment_id=?",
            (assessment_id,)
        ).fetchone()[0], 1)

    def test_transfer_roster_save_preserves_historical_assessment_score(self):
        self.login("teacher")
        assessment = self.client.post("/api/teacher/paper-assessments", json={
            "class_id": 1, "subject": "Science", "title": "Transfer evidence",
            "assessment_type": "class_test", "assessment_date": "2026-09-29",
            "max_marks": 20,
        })
        self.assertEqual(assessment.status_code, 201)
        assessment_id = assessment.json["assessment_id"]
        scores_url = f"/api/teacher/paper-assessments/{assessment_id}/scores"
        self.assertEqual(self.client.put(scores_url, json={
            "scores": [{"student_id": 1, "marks_obtained": 16}],
        }).status_code, 200)

        self.login("admin")
        self.assertEqual(self.client.put("/api/admin/students/1/class", json={
            "class_id": 2, "academic_year": "2084/85",
        }).status_code, 200)

        self.login("teacher")
        self.assertEqual(self.client.put(scores_url, json={"scores": []}).status_code, 200)
        score = self.db.execute(
            "SELECT student_id, marks_obtained FROM paper_assessment_scores "
            "WHERE assessment_id=?", (assessment_id,)
        ).fetchone()
        self.assertEqual((score["student_id"], score["marks_obtained"]), (1, 16))

    def test_must_change_password_blocks_shared_notice_apis_but_allows_password_lifecycle(self):
        self.login_api("student")
        self.db.execute("UPDATE users SET must_change_password=1 WHERE id=1")
        self.db.commit()
        for response in (
            self.client.get("/api/notices"),
            self.client.get("/api/notices/unread-count"),
            self.client.patch("/api/notices/1/read"),
        ):
            self.assertEqual(response.status_code, 403)
            self.assertIn("Password change required", response.json["error"])
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        changed = self.client.post("/api/auth/change-password", json={
            "current_password": "Password123", "new_password": "NewPassword123",
            "confirm_password": "NewPassword123",
        })
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.client.get("/api/notices").status_code, 200)

    def test_malformed_login_clears_existing_authenticated_session(self):
        self.login_api("admin")
        failed = self.client.post("/api/login", json={
            "email": "a@example.test", "password": "Password123",
        })
        self.assertEqual(failed.status_code, 400)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_cross_role_endpoint_attacks_are_denied_without_writes(self):
        self.login("student")
        self.assertEqual(self.client.get("/api/teacher/monthly-attendance").status_code, 403)
        self.assertEqual(self.client.get("/api/admin/users").status_code, 403)
        self.login("teacher")
        self.assertEqual(self.client.get("/api/admin/users").status_code, 403)
        self.assertEqual(self.client.get("/api/student/attendance").status_code, 403)
        self.login("admin")
        self.assertEqual(self.client.post("/api/teacher/monthly-attendance", json={
            "class_id": 1, "attendance_month": "2026-10", "total_school_days": 20,
        }).status_code, 403)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM monthly_attendance_summaries"
        ).fetchone()[0], 0)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get("/api/admin/users").status_code, 401)


if __name__ == "__main__":
    unittest.main()
