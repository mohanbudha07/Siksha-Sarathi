"""Exercise real Flask routes without a running MySQL server or ML artifacts."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class CursorAdapter:
    def __init__(self, connection):
        self.cursor = connection.cursor()

    def execute(self, query, args=()):
        return self.cursor.execute(query.replace('%s', '?'), args)

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]

    def close(self):
        self.cursor.close()


class ConnectionAdapter:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return CursorAdapter(self.connection)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()


class QuizStatisticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mysql_module = types.ModuleType('flask_mysqldb')
        mysql_module.MySQL = lambda app: types.SimpleNamespace(connection=None)
        dotenv_module = types.ModuleType('dotenv')
        dotenv_module.load_dotenv = lambda: None
        spec = importlib.util.spec_from_file_location('siksha_test_app', ROOT / 'app.py')
        cls.backend = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {
            'flask_mysqldb': mysql_module, 'dotenv': dotenv_module
        }), patch('joblib.load'):
            spec.loader.exec_module(cls.backend)
        cls.backend.app.config.update(TESTING=True, SECRET_KEY='isolated-test-secret')

    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT, email TEXT,
                role TEXT, created_at TEXT);
            CREATE TABLE students(id INTEGER PRIMARY KEY, user_id INTEGER,
                full_name TEXT, grade TEXT);
            CREATE TABLE quizzes(id INTEGER PRIMARY KEY, title TEXT, subject TEXT,
                questions TEXT);
            CREATE TABLE quiz_results(id INTEGER PRIMARY KEY, student_id INTEGER,
                quiz_id INTEGER, score INTEGER, total_questions INTEGER);
            CREATE TABLE predictions(id INTEGER PRIMARY KEY, student_id INTEGER,
                prediction TEXT, attendance REAL, assignment_score REAL,
                quiz_score REAL, study_hours REAL);
            CREATE TABLE notes(id INTEGER PRIMARY KEY, title TEXT, subject TEXT,
                chapter TEXT, content TEXT, created_at TEXT, uploaded_by INTEGER);
            INSERT INTO users VALUES(1,'Student','s@example.test','student','2026-01-01');
            INSERT INTO users VALUES(2,'Teacher','t@example.test','teacher','2026-01-01');
            INSERT INTO users VALUES(3,'Admin','a@example.test','admin','2026-01-01');
            INSERT INTO users VALUES(4,'Other Teacher','other@example.test','teacher','2026-01-01');
            INSERT INTO students VALUES(1,1,'Student One','10');
            INSERT INTO students VALUES(2,4,'Student Two','10');
        ''')
        self.questions = [
            {'question': 'First?', 'options': ['A', 'B'], 'answer': 'A',
             'explanation': 'The correct answer is A'},
            {'question': 'Second?', 'options': ['C', 'D'], 'answer': 'D'},
        ]
        self.db.execute('INSERT INTO quizzes VALUES(1,?,?,?)',
                        ('Science Quiz', 'Science', json.dumps(self.questions)))
        self.db.commit()
        self.backend.mysql.connection = ConnectionAdapter(self.db)
        self.client = self.backend.app.test_client()
        self.login('student')

    def tearDown(self):
        self.db.close()

    def login(self, role):
        with self.client.session_transaction() as session:
            session.clear()
            session.update(user_id={'student': 1, 'teacher': 2, 'admin': 3}[role],
                           username=role, role=role)

    def submit(self, answers):
        return self.client.post('/api/student/quiz/submit',
                                json={'quiz_id': 1, 'answers': answers})

    def test_quiz_response_contains_only_public_fields(self):
        response = self.client.get('/api/student/quiz')
        self.assertEqual(response.status_code, 200)
        for question in response.json['quiz']['questions']:
            self.assertEqual(set(question), {'question', 'options'})

    def test_submission_grades_on_server_and_snapshots_total(self):
        response = self.submit({'0': 'A', '1': 'C'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json['score'], response.json['total']), (1, 2))
        row = self.db.execute('SELECT score, total_questions FROM quiz_results').fetchone()
        self.assertEqual(tuple(row), (1, 2))

    def test_incomplete_extra_and_invalid_answers_are_rejected(self):
        for answers in [{}, {'0': 'A'}, {'0': 'A', '1': 'D', '2': 'E'},
                        {'0': 'unknown', '1': 'D'}, {'0': None, '1': 'D'}, []]:
            with self.subTest(answers=answers):
                self.assertEqual(self.submit(answers).status_code, 400)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM quiz_results').fetchone()[0], 0)

    def test_non_object_payload_is_rejected(self):
        response = self.client.post('/api/student/quiz/submit', json=['invalid'])
        self.assertEqual(response.status_code, 400)

    def test_malformed_stored_quizzes_cannot_be_served_or_graded(self):
        for raw in ['invalid json', '[]', '{}', '[null]',
                    json.dumps([{'question': 'Q?', 'options': ['A', 'B']}]),
                    json.dumps([{'question': 'Q?', 'options': ['A', 'A'], 'answer': 'A'}])]:
            with self.subTest(raw=raw):
                self.db.execute('UPDATE quizzes SET questions=?', (raw,))
                self.assertEqual(self.client.get('/api/student/quiz').status_code, 500)
                self.assertEqual(self.submit({'0': 'A'}).status_code, 500)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM quiz_results').fetchone()[0], 0)

    def test_missing_quiz_returns_404(self):
        self.db.execute('DELETE FROM quizzes')
        self.assertEqual(self.client.get('/api/student/quiz').status_code, 404)
        self.assertEqual(self.submit({'0': 'A'}).status_code, 404)

    def test_perfect_two_question_attempt_displays_100_percent(self):
        self.assertEqual(self.submit({'0': 'A', '1': 'D'}).status_code, 200)
        response = self.client.get('/api/student/dashboard')
        self.assertEqual(response.json['stats']['average_quiz_score'], 100)

    def test_percentages_use_attempt_totals_even_after_quiz_changes(self):
        self.db.executemany('INSERT INTO quiz_results VALUES(?,?,?,?,?)',
                            [(1, 1, 1, 2, 2), (2, 1, 1, 5, 10),
                             (3, 1, 1, 99, None), (4, 1, 1, 0, 0)])
        self.db.execute('UPDATE quizzes SET questions=?', ('[]',))
        student = self.client.get('/api/student/dashboard').json['stats']
        self.assertEqual(student['average_quiz_score'], 75)
        self.assertEqual(student['completed_quizzes'], 4)
        self.login('teacher')
        teacher = self.client.get('/api/teacher/dashboard').json
        self.assertEqual(teacher['statistics']['average_quiz_score'], 75)
        self.assertEqual(teacher['student_performance'][0]['average_quiz_score'], 75)

    def test_zero_score_counts_in_average(self):
        self.db.executemany('INSERT INTO quiz_results VALUES(?,?,?,?,?)',
                            [(1, 1, 1, 2, 2), (2, 1, 1, 0, 2)])
        response = self.client.get('/api/student/dashboard')
        self.assertEqual(response.json['stats']['average_quiz_score'], 50)

    def test_empty_statistics_are_zero(self):
        response = self.client.get('/api/student/dashboard')
        self.assertEqual(response.json['stats']['average_quiz_score'], 0)
        self.login('teacher')
        response = self.client.get('/api/teacher/dashboard')
        self.assertEqual(response.json['statistics']['average_quiz_score'], 0)

    def test_risk_counts_match_latest_prediction(self):
        self.db.executemany('INSERT INTO predictions(id,student_id,prediction) VALUES(?,?,?)',
                            [(1, 1, 'Needs Improvement'), (2, 1, 'Good'),
                             (3, 2, 'Good'), (4, 2, 'Needs Improvement')])
        for role in ['teacher', 'admin']:
            with self.subTest(role=role):
                self.login(role)
                response = self.client.get('/api/' + role + '/dashboard')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json['statistics']['students_needing_improvement'], 1)
                self.db.execute("UPDATE predictions SET prediction='Good' WHERE id=4")
                response = self.client.get('/api/' + role + '/dashboard')
                self.assertEqual(response.json['statistics']['students_needing_improvement'], 0)
                self.db.execute("UPDATE predictions SET prediction='Needs Improvement' WHERE id=4")

    def test_quiz_routes_still_require_student_role(self):
        self.login('teacher')
        self.assertEqual(self.client.get('/api/student/quiz').status_code, 403)
        self.assertEqual(self.submit({'0': 'A', '1': 'D'}).status_code, 403)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get('/api/student/quiz').status_code, 401)
        self.assertEqual(self.submit({'0': 'A', '1': 'D'}).status_code, 401)

    def test_teacher_can_read_update_and_delete_own_note(self):
        self.db.execute(
            'INSERT INTO notes VALUES(1,?,?,?,?,?,?)',
            ('Original', 'Science', '1', 'Original content', '2026-01-01', 2)
        )
        self.db.commit()
        self.login('teacher')

        response = self.client.get('/api/teacher/notes/1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['note']['content'], 'Original content')

        response = self.client.put('/api/teacher/notes/1', json={
            'title': '  Updated title  ',
            'subject': ' Science ',
            'chapter': ' 2 ',
            'content': ' Updated content ',
        })
        self.assertEqual(response.status_code, 200)
        row = self.db.execute(
            'SELECT title, subject, chapter, content FROM notes WHERE id=1'
        ).fetchone()
        self.assertEqual(tuple(row), ('Updated title', 'Science', '2', 'Updated content'))

        response = self.client.delete('/api/teacher/notes/1')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.db.execute('SELECT id FROM notes WHERE id=1').fetchone())

    def test_teacher_cannot_manage_another_teachers_note(self):
        self.db.execute(
            'INSERT INTO notes VALUES(1,?,?,?,?,?,?)',
            ('Private', 'Science', '1', 'Other teacher content', '2026-01-01', 4)
        )
        self.db.commit()
        self.login('teacher')

        self.assertEqual(self.client.get('/api/teacher/notes/1').status_code, 404)
        self.assertEqual(self.client.put('/api/teacher/notes/1', json={
            'title': 'Changed', 'subject': 'Science',
            'chapter': '1', 'content': 'Changed',
        }).status_code, 404)
        self.assertEqual(self.client.delete('/api/teacher/notes/1').status_code, 404)
        row = self.db.execute('SELECT title, content FROM notes WHERE id=1').fetchone()
        self.assertEqual(tuple(row), ('Private', 'Other teacher content'))

    def test_note_update_rejects_invalid_data(self):
        self.db.execute(
            'INSERT INTO notes VALUES(1,?,?,?,?,?,?)',
            ('Original', 'Science', '1', 'Content', '2026-01-01', 2)
        )
        self.db.commit()
        self.login('teacher')

        for payload in [None, [], {}, {
            'title': ' ', 'subject': 'Science', 'chapter': '1', 'content': 'Content'
        }]:
            with self.subTest(payload=payload):
                response = self.client.put('/api/teacher/notes/1', json=payload)
                self.assertEqual(response.status_code, 400)

    def test_note_management_requires_teacher_role(self):
        for role, expected_status in [('student', 403), ('admin', 403)]:
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(
                    self.client.get('/api/teacher/notes/1').status_code,
                    expected_status,
                )

        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get('/api/teacher/notes/1').status_code, 401)


if __name__ == '__main__':
    unittest.main()
