import importlib
import unittest
from unittest.mock import patch
from werkzeug.security import check_password_hash


try:
    fixture = importlib.import_module('test_quiz_statistics')
except ModuleNotFoundError:
    fixture = importlib.import_module(
        'backend.tests.test_quiz_statistics'
    )


class FailingStudentInsertCursor(fixture.CursorAdapter):
    def execute(self, query, args=()):
        if 'INSERT INTO students' in query:
            raise RuntimeError('simulated student insert failure')
        return super().execute(query, args)


class FailingStudentInsertConnection(fixture.ConnectionAdapter):
    def cursor(self):
        return FailingStudentInsertCursor(self.connection)


class AuthAndCoreRouteTests(unittest.TestCase):
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

    def set_password(self, user_id, password):
        self.db.execute(
            'UPDATE users SET password=? WHERE id=?',
            (self.backend.generate_password_hash(password), user_id)
        )
        self.db.commit()

    def login_through_api(self, role, password='Password123'):
        user_ids = {'student': 1, 'teacher': 2, 'admin': 3}
        user_id = user_ids[role]
        self.set_password(user_id, password)
        row = self.db.execute(
            'SELECT email FROM users WHERE id=?', (user_id,)
        ).fetchone()
        response = self.client.post('/api/login', json={
            'email': row['email'], 'password': password
        })
        self.assertEqual(response.status_code, 200)
        return response

    def clear_session(self):
        with self.client.session_transaction() as session:
            session.clear()

    def test_successful_login_creates_expected_session(self):
        response = self.login_through_api('student')

        self.assertEqual(response.json['user'], {
            'id': 1,
            'username': 'Student',
            'email': 's@example.test',
            'role': 'student',
            'must_change_password': False,
        })
        with self.client.session_transaction() as session:
            self.assertEqual(session['user_id'], 1)
            self.assertEqual(session['username'], 'Student')
            self.assertEqual(session['role'], 'student')

    def test_failed_login_rejects_wrong_unknown_and_invalid_credentials(self):
        self.set_password(1, 'Password123')
        wrong_password = self.client.post('/api/login', json={
            'email': 's@example.test', 'password': 'wrong-password'
        })
        self.assertEqual(wrong_password.status_code, 401)

        unknown_email = self.client.post('/api/login', json={
            'email': 'unknown@example.test', 'password': 'Password123'
        })
        self.assertEqual(unknown_email.status_code, 401)

        for payload in (None, {}, {'email': 's@example.test'},
                        {'password': 'Password123'}):
            with self.subTest(payload=payload):
                response = self.client.post('/api/login', json=payload)
                self.assertEqual(response.status_code, 400)

    def test_auth_me_returns_identity_after_login_and_rejects_anonymous(self):
        self.login_through_api('teacher')
        authenticated = self.client.get('/api/auth/me')
        self.assertEqual(authenticated.status_code, 200)
        self.assertEqual(authenticated.json['user'], {
            'id': 2, 'username': 'Teacher', 'role': 'teacher',
            'must_change_password': False,
        })

        self.clear_session()
        anonymous = self.client.get('/api/auth/me')
        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(anonymous.json['error'], 'Authentication required')

    def test_logout_clears_session_and_auth_me_then_fails(self):
        self.login_through_api('admin')
        self.assertEqual(self.client.post('/api/logout').status_code, 200)

        with self.client.session_transaction() as session:
            self.assertNotIn('user_id', session)
        response = self.client.get('/api/auth/me')
        self.assertEqual(response.status_code, 401)

    def test_admin_created_accounts_require_first_login_password_change(self):
        self.login_through_api('admin')
        created_admin = self.client.post('/api/admin/admins', json={
            'username': 'Temporary Admin',
            'email': 'temporary.admin@example.test',
            'password': 'Temporary123',
        })
        created_teacher = self.client.post('/api/admin/teachers', json={
            'username': 'Temporary Teacher',
            'email': 'temporary.teacher@example.test',
            'password': 'Temporary123',
        })
        created_student = self.client.post('/api/admin/students', json={
            'full_name': 'Temporary Student',
            'email': 'temporary.student@example.test',
            'password': 'Temporary123',
            'class_id': 1,
        })
        self.assertEqual((created_admin.status_code,
                          created_teacher.status_code,
                          created_student.status_code), (201, 201, 201))
        flags = self.db.execute(
            """SELECT email, must_change_password FROM users
               WHERE email LIKE 'temporary.%@example.test'
               ORDER BY email"""
        ).fetchall()
        self.assertEqual([(row['email'], row['must_change_password']) for row in flags], [
            ('temporary.admin@example.test', 1),
            ('temporary.student@example.test', 1),
            ('temporary.teacher@example.test', 1),
        ])

    def test_login_and_auth_me_report_temporary_and_existing_password_state(self):
        self.login_through_api('student')
        self.assertFalse(self.client.get('/api/auth/me').json['user']['must_change_password'])

        self.login_through_api('admin')
        created = self.client.post('/api/admin/teachers', json={
            'username': 'Temporary Login Teacher',
            'email': 'temporary.login@example.test',
            'password': 'Temporary123',
        })
        teacher_id = created.json['teacher_id']
        self.clear_session()
        response = self.client.post('/api/login', json={
            'email': 'temporary.login@example.test',
            'password': 'Temporary123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['user']['must_change_password'])
        self.assertEqual(self.client.get('/api/auth/me').json['user']['id'], teacher_id)

    def test_change_password_validates_and_replaces_temporary_password(self):
        self.login_through_api('student')
        with self.client.session_transaction() as session:
            session['must_change_password'] = True
        self.db.execute(
            'UPDATE users SET must_change_password=1 WHERE id=1'
        )
        self.db.commit()

        self.assertEqual(self.client.post('/api/auth/change-password').status_code, 400)
        self.assertEqual(self.client.post('/api/auth/change-password', json={
            'current_password': 'wrong', 'new_password': 'NewPassword123',
            'confirm_password': 'NewPassword123',
        }).status_code, 401)
        for payload in [
            {'current_password': 'Password123', 'new_password': 'short',
             'confirm_password': 'short'},
            {'current_password': 'Password123', 'new_password': 'NewPassword123',
             'confirm_password': 'Different123'},
            {'current_password': 'Password123', 'new_password': 'Password123',
             'confirm_password': 'Password123'},
        ]:
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.client.post('/api/auth/change-password', json=payload).status_code,
                    400
                )

        changed = self.client.post('/api/auth/change-password', json={
            'current_password': 'Password123',
            'new_password': 'NewPassword123',
            'confirm_password': 'NewPassword123',
        })
        self.assertEqual(changed.status_code, 200)
        stored = self.db.execute(
            'SELECT password, must_change_password FROM users WHERE id=1'
        ).fetchone()
        self.assertFalse(stored['must_change_password'])
        self.assertTrue(check_password_hash(
            stored['password'], 'NewPassword123'
        ))
        self.assertFalse(check_password_hash(
            stored['password'], 'Password123'
        ))
        self.assertEqual(self.client.post('/api/logout').status_code, 200)
        self.assertEqual(self.client.post('/api/login', json={
            'email': 's@example.test', 'password': 'Password123'
        }).status_code, 401)
        new_login = self.client.post('/api/login', json={
            'email': 's@example.test', 'password': 'NewPassword123'
        })
        self.assertEqual(new_login.status_code, 200)
        self.assertFalse(new_login.json['user']['must_change_password'])

    def test_whitespace_only_new_password_is_rejected(self):
        self.login_through_api('student')
        response = self.client.post('/api/auth/change-password', json={
            'current_password': 'Password123',
            'new_password': '        ',
            'confirm_password': '        ',
        })
        self.assertEqual(response.status_code, 400)

    def test_temporary_password_blocks_features_but_allows_auth_lifecycle(self):
        self.login_through_api('student')
        self.db.execute(
            'UPDATE users SET must_change_password=1 WHERE id=1'
        )
        self.db.commit()
        self.assertEqual(self.client.get('/api/student/dashboard').status_code, 403)
        self.assertIn('Password change required',
                      self.client.get('/api/student/dashboard').json['error'])
        self.assertTrue(self.client.get('/api/auth/me').json['user']['must_change_password'])
        self.assertEqual(self.client.post('/api/logout').status_code, 200)

    def test_anonymous_user_cannot_change_password(self):
        self.clear_session()
        self.assertEqual(self.client.post('/api/auth/change-password', json={}).status_code, 401)

    def test_deleted_user_stale_session_is_rejected_and_cleared(self):
        self.login_through_api('student')
        self.db.execute('DELETE FROM users WHERE id=1')
        self.db.commit()
        response = self.client.get('/api/student/dashboard')
        self.assertEqual(response.status_code, 401)
        with self.client.session_transaction() as session:
            self.assertNotIn('user_id', session)
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)

    def test_changed_role_stale_session_cannot_access_admin_endpoint(self):
        self.login_through_api('admin')
        self.db.execute(
            "UPDATE users SET role='student' WHERE id=3"
        )
        self.db.commit()
        response = self.client.get('/api/admin/dashboard')
        self.assertEqual(response.status_code, 403)

    def test_temporary_teacher_cannot_use_teacher_endpoint(self):
        self.login_through_api('admin')
        created = self.client.post('/api/admin/teachers', json={
            'username': 'Blocked Teacher',
            'email': 'blocked.teacher@example.test',
            'password': 'Temporary123',
        })
        self.clear_session()
        self.client.post('/api/login', json={
            'email': 'blocked.teacher@example.test',
            'password': 'Temporary123',
        })
        self.assertEqual(self.client.get('/api/teacher/dashboard').status_code, 403)
        self.assertEqual(created.status_code, 201)

    def test_temporary_admin_cannot_use_admin_endpoint(self):
        self.login_through_api('admin')
        created = self.client.post('/api/admin/admins', json={
            'username': 'Blocked Admin',
            'email': 'blocked.admin@example.test',
            'password': 'Temporary123',
        })
        self.clear_session()
        self.client.post('/api/login', json={
            'email': 'blocked.admin@example.test',
            'password': 'Temporary123',
        })
        self.assertEqual(self.client.get('/api/admin/dashboard').status_code, 403)
        self.assertEqual(created.status_code, 201)

    def test_student_can_list_notes_with_content_and_empty_notes_are_valid(self):
        self.db.execute(
            '''INSERT INTO notes
               (id, title, subject, chapter, content, created_at, uploaded_by)
               VALUES (1, ?, ?, ?, ?, ?, ?)''',
            ('Cell lesson', 'Science', 'Cells', 'Read this lesson',
             '2026-01-02', 2)
        )
        self.db.commit()
        self.login_through_api('student')

        response = self.client.get('/api/student/notes')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['notes'][0]['title'], 'Cell lesson')
        self.assertEqual(response.json['notes'][0]['content'], 'Read this lesson')

        self.db.execute('DELETE FROM notes')
        self.db.commit()
        empty = self.client.get('/api/student/notes')
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json, {'notes': []})

    def test_student_notes_reject_teacher_admin_and_anonymous_users(self):
        for role in ('teacher', 'admin'):
            with self.subTest(role=role):
                self.login_through_api(role)
                self.assertEqual(self.client.get('/api/student/notes').status_code, 403)
        self.clear_session()
        self.assertEqual(self.client.get('/api/student/notes').status_code, 401)

    def test_teacher_can_create_and_list_own_note(self):
        self.login_through_api('teacher')
        response = self.client.post('/api/teacher/notes', json={
            'title': 'Force lesson',
            'subject': 'Science',
            'chapter': 'Force',
            'content': 'A force is a push or pull.',
        })
        self.assertEqual(response.status_code, 201)
        stored = self.db.execute(
            'SELECT title, subject, chapter, content, uploaded_by FROM notes'
        ).fetchone()
        self.assertEqual(tuple(stored), (
            'Force lesson', 'Science', 'Force',
            'A force is a push or pull.', 2
        ))

        listing = self.client.get('/api/teacher/notes')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json['notes'][0]['title'], 'Force lesson')

    def test_teacher_note_creation_validates_required_fields_and_roles(self):
        self.login_through_api('teacher')
        for payload in (None, [], {}, {
            'title': ' ', 'subject': 'Science',
            'chapter': 'Force', 'content': 'Content'
        }):
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.client.post('/api/teacher/notes', json=payload).status_code,
                    400
                )

        for role in ('student', 'admin'):
            with self.subTest(role=role):
                self.login_through_api(role)
                self.assertEqual(self.client.get('/api/teacher/notes').status_code, 403)
                self.assertEqual(self.client.post(
                    '/api/teacher/notes', json={}
                ).status_code, 403)
        self.clear_session()
        self.assertEqual(self.client.get('/api/teacher/notes').status_code, 401)
        self.assertEqual(self.client.post('/api/teacher/notes', json={}).status_code, 401)

    def test_admin_dashboard_returns_seeded_statistics(self):
        self.db.execute(
            'INSERT INTO notes (title, subject, chapter, content, uploaded_by) '
            'VALUES (?, ?, ?, ?, ?)',
            ('Dashboard note', 'Science', 'Force', 'Content', 2)
        )
        self.db.execute(
            '''INSERT INTO quiz_results
               (id, student_id, quiz_id, score, total_questions)
               VALUES (?, ?, ?, ?, ?)''', (1, 1, 1, 1, 2)
        )
        self.db.commit()
        self.login_through_api('admin')

        response = self.client.get('/api/admin/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['statistics'], {
            'total_users': 5,
            'total_students': 2,
            'total_teachers': 2,
            'total_admins': 1,
            'total_notes': 1,
            'total_quizzes': 1,
            'total_quiz_attempts': 1,
        })
        self.assertTrue(response.json['recent_users'])

    def test_admin_dashboard_rejects_student_teacher_and_anonymous_users(self):
        for role in ('student', 'teacher'):
            with self.subTest(role=role):
                self.login_through_api(role)
                self.assertEqual(self.client.get('/api/admin/dashboard').status_code, 403)
        self.clear_session()
        self.assertEqual(self.client.get('/api/admin/dashboard').status_code, 401)

    def test_admin_routes_reject_anonymous_and_wrong_roles(self):
        routes = [
            ('GET', '/api/admin/users'),
            ('GET', '/api/admin/school-setup'),
            ('POST', '/api/admin/admins'),
            ('POST', '/api/admin/students'),
        ]
        for method, url in routes:
            with self.subTest(method=method, url=url):
                self.clear_session()
                response = self.client.open(url, method=method, json={})
                self.assertEqual(response.status_code, 401)

        for role in ('student', 'teacher'):
            self.login_through_api(role)
            for method, url in routes:
                with self.subTest(role=role, method=method, url=url):
                    response = self.client.open(url, method=method, json={})
                    self.assertEqual(response.status_code, 403)

    def test_admin_student_creation_rolls_back_after_user_insert_failure(self):
        self.login_through_api('admin')
        self.backend.mysql.connection = FailingStudentInsertConnection(self.db)

        response = self.client.post('/api/admin/students', json={
            'full_name': 'Rollback Student',
            'email': 'rollback@example.test',
            'password': 'Password123',
            'class_id': 1,
        })

        self.assertEqual(response.status_code, 500)
        self.assertIsNone(self.db.execute(
            "SELECT id FROM users WHERE email='rollback@example.test'"
        ).fetchone())
        self.assertIsNone(self.db.execute(
            "SELECT id FROM students WHERE full_name='Rollback Student'"
        ).fetchone())
        self.assertEqual(
            self.db.execute(
                'SELECT COUNT(*) FROM student_class_enrollments'
            ).fetchone()[0],
            2
        )


if __name__ == '__main__':
    unittest.main()
