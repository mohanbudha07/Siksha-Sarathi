"""Exercise real Flask routes without a running MySQL server or ML artifacts."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
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

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

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
            CREATE TABLE classes(id INTEGER PRIMARY KEY, name TEXT, grade TEXT,
                section TEXT, created_at TEXT);
            CREATE TABLE student_class_enrollments(id INTEGER PRIMARY KEY,
                student_id INTEGER, class_id INTEGER, created_at TEXT);
            CREATE TABLE teacher_class_subjects(id INTEGER PRIMARY KEY,
                teacher_user_id INTEGER, class_id INTEGER, subject TEXT,
                created_at TEXT);
            CREATE TABLE quizzes(id INTEGER PRIMARY KEY, title TEXT, subject TEXT,
                questions TEXT, created_by INTEGER, is_published INTEGER,
                created_at TEXT, requires_session INTEGER DEFAULT 0);
            CREATE TABLE quiz_results(id INTEGER PRIMARY KEY, student_id INTEGER,
                quiz_id INTEGER, score INTEGER, total_questions INTEGER,
                quiz_session_id INTEGER);
            CREATE TABLE quiz_answer_results(id INTEGER PRIMARY KEY,
                quiz_result_id INTEGER, question_index INTEGER, question_text TEXT,
                topic TEXT, difficulty TEXT, curriculum_code TEXT DEFAULT 'unspecified',
                cognitive_level TEXT DEFAULT 'unspecified', selected_answer TEXT,
                correct_answer TEXT, is_correct INTEGER, is_skipped INTEGER);
            CREATE TABLE quiz_sessions(id INTEGER PRIMARY KEY, quiz_id INTEGER,
                class_id INTEGER, created_by INTEGER, access_code_hash TEXT,
                starts_at TEXT, ends_at TEXT, is_closed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE predictions(id INTEGER PRIMARY KEY, student_id INTEGER,
                prediction TEXT, attendance REAL, assignment_score REAL,
                quiz_score REAL, study_hours REAL);
            CREATE TABLE notes(id INTEGER PRIMARY KEY, title TEXT, subject TEXT,
                chapter TEXT, content TEXT, created_at TEXT, uploaded_by INTEGER);
            INSERT INTO users VALUES(1,'Student','s@example.test','student','2026-01-01');
            INSERT INTO users VALUES(2,'Teacher','t@example.test','teacher','2026-01-01');
            INSERT INTO users VALUES(3,'Admin','a@example.test','admin','2026-01-01');
            INSERT INTO users VALUES(4,'Other Teacher','other@example.test','teacher','2026-01-01');
            INSERT INTO users VALUES(5,'Student Two','s2@example.test','student','2026-01-01');
            INSERT INTO students VALUES(1,1,'Student One','10');
            INSERT INTO students VALUES(2,5,'Student Two','9');
            INSERT INTO classes VALUES(1,'Grade 10','10','Default','2026-01-01');
            INSERT INTO classes VALUES(2,'Grade 9','9','Default','2026-01-01');
            INSERT INTO student_class_enrollments VALUES(1,1,1,'2026-01-01');
            INSERT INTO student_class_enrollments VALUES(2,2,2,'2026-01-01');
            INSERT INTO teacher_class_subjects VALUES(1,2,1,'Science','2026-01-01');
        ''')
        self.questions = [
            {'question': 'First?', 'options': ['A', 'B'], 'answer': 'A',
             'explanation': 'The correct answer is A', 'topic': 'Force',
             'difficulty': 'Easy'},
            {'question': 'Second?', 'options': ['C', 'D'], 'answer': 'D'},
        ]
        self.db.execute(
            '''INSERT INTO quizzes(id,title,subject,questions,is_published,created_at)
               VALUES(1,?,?,?,?,?)''',
            ('Science Quiz', 'Science', json.dumps(self.questions), 1, '2026-01-01')
        )
        self.db.commit()
        self.backend.mysql.connection = ConnectionAdapter(self.db)
        self.client = self.backend.app.test_client()
        self.login('student')

    def tearDown(self):
        self.db.close()

    def login(self, role):
        user_ids = {'student': 1, 'teacher': 2, 'admin': 3, 'other_teacher': 4}
        with self.client.session_transaction() as session:
            session.clear()
            session.update(
                user_id=user_ids[role],
                username=role,
                role='teacher' if role == 'other_teacher' else role
            )

    def submit(self, answers):
        return self.client.post('/api/student/quiz/submit',
                                json={'quiz_id': 1, 'answers': answers})

    def quiz_payload(self, **overrides):
        payload = {
            'title': 'Force Practice',
            'subject': 'Science',
            'is_published': True,
            'questions': [{
                'question': 'What is force?',
                'topic': 'Force',
                'difficulty': 'Easy',
                'options': ['A push or pull', 'Energy'],
                'answer': 'A push or pull',
                'explanation': 'Force is a push or pull.',
            }],
        }
        payload.update(overrides)
        return payload

    def test_quiz_response_contains_only_public_fields(self):
        response = self.client.get('/api/student/quiz')
        self.assertEqual(response.status_code, 200)
        questions = response.json['quiz']['questions']
        for question in questions:
            self.assertEqual(
                set(question),
                {'question', 'options', 'topic', 'difficulty',
                 'curriculum_code', 'cognitive_level'}
            )
            self.assertNotIn('answer', question)
            self.assertNotIn('explanation', question)
        self.assertEqual((questions[0]['topic'], questions[0]['difficulty']),
                         ('Force', 'easy'))
        self.assertEqual((questions[1]['topic'], questions[1]['difficulty']),
                         ('Science', 'unspecified'))

    def test_submission_grades_on_server_and_snapshots_total(self):
        response = self.submit({'0': 'A', '1': 'C'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json['score'], response.json['total']), (1, 2))
        row = self.db.execute('SELECT score, total_questions FROM quiz_results').fetchone()
        self.assertEqual(tuple(row), (1, 2))
        details = self.db.execute(
            '''SELECT question_index, topic, difficulty, selected_answer,
                      correct_answer, is_correct, is_skipped
               FROM quiz_answer_results ORDER BY question_index'''
        ).fetchall()
        self.assertEqual(tuple(details[0]), (0, 'Force', 'easy', 'A', 'A', 1, 0))
        self.assertEqual(tuple(details[1]),
                         (1, 'Science', 'unspecified', 'C', 'D', 0, 0))

    def test_incomplete_answers_are_recorded_as_skipped(self):
        response = self.submit({'0': 'A'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (response.json['score'], response.json['total'], response.json['skipped']),
            (1, 2, 1)
        )
        detail = self.db.execute(
            '''SELECT selected_answer, is_correct, is_skipped
               FROM quiz_answer_results WHERE question_index=1'''
        ).fetchone()
        self.assertEqual(tuple(detail), (None, 0, 1))

    def test_extra_and_invalid_answers_are_rejected(self):
        for answers in [{'0': 'A', '1': 'D', '2': 'E'},
                        {'0': 'unknown', '1': 'D'}, {'0': None, '1': 'D'}, []]:
            with self.subTest(answers=answers):
                self.assertEqual(self.submit(answers).status_code, 400)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM quiz_results').fetchone()[0], 0)

    def test_empty_answer_object_records_every_question_as_skipped(self):
        response = self.submit({})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json['score'], response.json['skipped']), (0, 2))
        rows = self.db.execute(
            'SELECT is_correct, is_skipped FROM quiz_answer_results'
        ).fetchall()
        self.assertEqual([tuple(row) for row in rows], [(0, 1), (0, 1)])

    def test_non_object_payload_is_rejected(self):
        response = self.client.post('/api/student/quiz/submit', json=['invalid'])
        self.assertEqual(response.status_code, 400)

    def test_malformed_stored_quizzes_cannot_be_served_or_graded(self):
        for raw in ['invalid json', '[]', '{}', '[null]',
                    json.dumps([{'question': 'Q?', 'options': ['A', 'B']}]),
                    json.dumps([{'question': 'Q?', 'options': ['A', 'A'], 'answer': 'A'}]),
                    json.dumps([{'question': 'Q?', 'options': ['A', 'B'],
                                 'answer': 'A', 'topic': ''}]),
                    json.dumps([{'question': 'Q?', 'options': ['A', 'B'],
                                 'answer': 'A', 'difficulty': 'impossible'}])]:
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
        self.db.executemany('''INSERT INTO quiz_results
            (id,student_id,quiz_id,score,total_questions) VALUES(?,?,?,?,?)''',
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
        self.db.executemany('''INSERT INTO quiz_results
            (id,student_id,quiz_id,score,total_questions) VALUES(?,?,?,?,?)''',
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

    def test_teacher_learning_overview_is_scoped_to_assigned_class_and_subject(self):
        self.assertEqual(self.submit({'0': 'A', '1': 'C'}).status_code, 200)
        self.login('teacher')

        response = self.client.get('/api/teacher/learning-analytics')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['assignments']), 1)
        self.assertEqual(response.json['assignments'][0]['subject'], 'Science')
        self.assertEqual(response.json['statistics'], {
            'assigned_students': 1,
            'student_subject_profiles': 1,
            'students_with_activity': 1,
            'profiles_needing_attention': 0,
        })

        profiles = response.json['students']
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]['student_id'], 1)
        self.assertEqual(profiles[0]['class_name'], 'Grade 10')
        self.assertEqual(profiles[0]['subject'], 'Science')
        self.assertEqual(profiles[0]['attempts'], 1)
        self.assertEqual(profiles[0]['accuracy_percent'], 50)
        self.assertEqual(profiles[0]['status'], 'Developing')

    def test_teacher_learning_profile_shows_topics_difficulty_trends_and_mistakes(self):
        self.assertEqual(self.submit({'0': 'A', '1': 'C'}).status_code, 200)
        self.assertEqual(self.submit({}).status_code, 200)
        self.login('teacher')

        response = self.client.get(
            '/api/teacher/students/1/learning-profile?subject=science'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertEqual(data['student']['full_name'], 'Student One')
        self.assertEqual(data['summary']['attempts'], 2)
        self.assertEqual(data['summary']['total_questions'], 4)
        self.assertEqual(data['summary']['correct_answers'], 1)
        self.assertEqual(data['summary']['skipped_answers'], 2)
        self.assertEqual(data['summary']['accuracy_percent'], 25)
        self.assertEqual(data['summary']['skip_percent'], 50)
        self.assertEqual(data['summary']['status'], 'Needs attention')

        topics = {topic['topic']: topic for topic in data['topics']}
        self.assertEqual(topics['Force']['accuracy_percent'], 50)
        self.assertEqual(topics['Force']['skipped_answers'], 1)
        self.assertEqual(topics['Science']['accuracy_percent'], 0)
        self.assertEqual(topics['Science']['skipped_answers'], 1)

        difficulties = {
            item['difficulty']: item for item in data['difficulties']
        }
        self.assertEqual(difficulties['easy']['total_questions'], 2)
        self.assertEqual(difficulties['unspecified']['total_questions'], 2)
        self.assertEqual(
            [attempt['attempt_id'] for attempt in data['recent_attempts']],
            [2, 1]
        )
        self.assertEqual(len(data['common_mistakes']), 1)
        self.assertEqual(data['common_mistakes'][0]['question_text'], 'Second?')
        self.assertEqual(data['common_mistakes'][0]['correct_answer'], 'D')

    def test_unassigned_teacher_cannot_access_student_learning_profile(self):
        self.login('other_teacher')
        overview = self.client.get('/api/teacher/learning-analytics')
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.json['assignments'], [])
        self.assertEqual(overview.json['students'], [])
        self.assertEqual(
            self.client.get(
                '/api/teacher/students/1/learning-profile?subject=Science'
            ).status_code,
            404
        )

    def test_teacher_learning_profile_requires_subject_and_teacher_role(self):
        self.login('teacher')
        self.assertEqual(
            self.client.get('/api/teacher/students/1/learning-profile').status_code,
            400
        )

        for role in ['student', 'admin']:
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(
                    self.client.get('/api/teacher/learning-analytics').status_code,
                    403
                )

        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(
            self.client.get('/api/teacher/learning-analytics').status_code,
            401
        )

    def test_teacher_can_create_list_read_update_and_delete_own_quiz(self):
        self.login('teacher')
        response = self.client.post('/api/teacher/quizzes', json=self.quiz_payload())
        self.assertEqual(response.status_code, 201)
        quiz_id = response.json['quiz_id']

        row = self.db.execute(
            'SELECT title, subject, questions, created_by, is_published FROM quizzes WHERE id=?',
            (quiz_id,)
        ).fetchone()
        stored_questions = json.loads(row['questions'])
        self.assertEqual((row['created_by'], row['is_published']), (2, 1))
        self.assertEqual(stored_questions[0]['difficulty'], 'easy')

        response = self.client.get('/api/teacher/quizzes')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['quizzes']), 1)
        self.assertEqual(response.json['quizzes'][0]['question_count'], 1)
        self.assertEqual(response.json['quizzes'][0]['attempt_count'], 0)

        response = self.client.get(f'/api/teacher/quizzes/{quiz_id}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json['quiz']['questions'][0]['answer'],
            'A push or pull'
        )

        updated = self.quiz_payload(title='Updated Quiz', is_published=False)
        response = self.client.put(f'/api/teacher/quizzes/{quiz_id}', json=updated)
        self.assertEqual(response.status_code, 200)
        row = self.db.execute(
            'SELECT title, is_published FROM quizzes WHERE id=?', (quiz_id,)
        ).fetchone()
        self.assertEqual(tuple(row), ('Updated Quiz', 0))

        self.assertEqual(
            self.client.delete(f'/api/teacher/quizzes/{quiz_id}').status_code,
            200
        )
        self.assertIsNone(
            self.db.execute('SELECT id FROM quizzes WHERE id=?', (quiz_id,)).fetchone()
        )

    def test_teacher_cannot_manage_legacy_or_another_teachers_quiz(self):
        self.db.execute(
            '''INSERT INTO quizzes
               (id,title,subject,questions,created_by,is_published,created_at)
               VALUES(2,?,?,?,?,?,?)''',
            ('Other Quiz', 'Science', json.dumps(self.questions), 4, 1, '2026-01-01')
        )
        self.db.commit()
        self.login('teacher')

        self.assertEqual(self.client.get('/api/teacher/quizzes').json['quizzes'], [])
        for quiz_id in [1, 2]:
            with self.subTest(quiz_id=quiz_id):
                self.assertEqual(
                    self.client.get(f'/api/teacher/quizzes/{quiz_id}').status_code,
                    404
                )
                self.assertEqual(
                    self.client.put(
                        f'/api/teacher/quizzes/{quiz_id}', json=self.quiz_payload()
                    ).status_code,
                    404
                )
                self.assertEqual(
                    self.client.delete(f'/api/teacher/quizzes/{quiz_id}').status_code,
                    404
                )

    def test_teacher_quiz_validation_rejects_invalid_payloads(self):
        self.login('teacher')
        invalid_payloads = [
            None,
            [],
            {},
            self.quiz_payload(title=' '),
            self.quiz_payload(is_published='yes'),
            self.quiz_payload(questions=[]),
            self.quiz_payload(questions=[{
                'question': 'Q?', 'topic': '', 'difficulty': 'easy',
                'options': ['A', 'B'], 'answer': 'A'
            }]),
            self.quiz_payload(questions=[{
                'question': 'Q?', 'topic': 'Force', 'difficulty': 'unknown',
                'options': ['A', 'B'], 'answer': 'A'
            }]),
            self.quiz_payload(questions=[{
                'question': 'Q?', 'topic': 'Force', 'difficulty': 'hard',
                'options': ['A', 'A'], 'answer': 'A'
            }]),
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.client.post('/api/teacher/quizzes', json=payload).status_code,
                    400
                )
        self.assertEqual(
            self.db.execute('SELECT COUNT(*) FROM quizzes WHERE created_by=2').fetchone()[0],
            0
        )

    def test_quiz_with_attempts_cannot_be_deleted_but_can_be_unpublished(self):
        self.login('teacher')
        response = self.client.post('/api/teacher/quizzes', json=self.quiz_payload())
        quiz_id = response.json['quiz_id']
        self.db.execute(
            '''INSERT INTO quiz_results
               (id,student_id,quiz_id,score,total_questions) VALUES(?,?,?,?,?)''',
            (10, 1, quiz_id, 1, 1)
        )
        self.db.commit()

        response = self.client.delete(f'/api/teacher/quizzes/{quiz_id}')
        self.assertEqual(response.status_code, 409)
        self.assertIn('unpublish', response.json['error'].lower())

        response = self.client.put(
            f'/api/teacher/quizzes/{quiz_id}',
            json=self.quiz_payload(is_published=False)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.db.execute('SELECT is_published FROM quizzes WHERE id=?', (quiz_id,)).fetchone()[0],
            0
        )

    def test_unpublished_quiz_cannot_be_served_or_submitted(self):
        self.db.execute('UPDATE quizzes SET is_published=0 WHERE id=1')
        self.db.commit()
        self.assertEqual(self.client.get('/api/student/quiz').status_code, 404)
        self.assertEqual(self.submit({'0': 'A', '1': 'D'}).status_code, 404)

    def test_student_can_list_and_select_published_quizzes(self):
        self.db.execute(
            '''INSERT INTO quizzes
               (id,title,subject,questions,created_by,is_published,created_at)
               VALUES(2,?,?,?,?,?,?)''',
            ('Teacher Quiz', 'Science', json.dumps(self.questions), 2, 1, '2026-01-02')
        )
        self.db.execute(
            '''INSERT INTO quizzes
               (id,title,subject,questions,created_by,is_published,created_at)
               VALUES(3,?,?,?,?,?,?)''',
            ('Draft Quiz', 'Math', json.dumps(self.questions), 2, 0, '2026-01-03')
        )
        self.db.commit()

        response = self.client.get('/api/student/quizzes')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(quiz['id'], quiz['title'], quiz['question_count'])
             for quiz in response.json['quizzes']],
            [(1, 'Science Quiz', 2), (2, 'Teacher Quiz', 2)]
        )

        response = self.client.get('/api/student/quiz?quiz_id=2')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['quiz']['title'], 'Teacher Quiz')
        self.assertEqual(self.client.get('/api/student/quiz?quiz_id=3').status_code, 404)
        self.assertEqual(
            self.client.get('/api/student/quiz?quiz_id=invalid').status_code,
            400
        )

    def test_student_quiz_list_ignores_malformed_published_quizzes(self):
        self.db.execute(
            '''INSERT INTO quizzes
               (id,title,subject,questions,created_by,is_published,created_at)
               VALUES(2,?,?,?,?,?,?)''',
            ('Broken Quiz', 'Science', 'invalid', 2, 1, '2026-01-02')
        )
        self.db.commit()
        response = self.client.get('/api/student/quizzes')
        self.assertEqual([quiz['id'] for quiz in response.json['quizzes']], [1])

    def test_teacher_quiz_management_requires_teacher_role(self):
        for role in ['student', 'admin']:
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(self.client.get('/api/teacher/quizzes').status_code, 403)
                self.assertEqual(
                    self.client.post('/api/teacher/quizzes', json=self.quiz_payload()).status_code,
                    403
                )

        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get('/api/teacher/quizzes').status_code, 401)

    def lab_session_payload(self, quiz_id, **overrides):
        now = datetime.now(timezone.utc)
        payload = {
            'quiz_id': quiz_id,
            'class_id': 1,
            'access_code': 'LAB-2048',
            'starts_at': (now - timedelta(minutes=5)).isoformat(),
            'ends_at': (now + timedelta(minutes=30)).isoformat(),
        }
        payload.update(overrides)
        return payload

    def test_teacher_can_run_class_scoped_lab_quiz(self):
        self.login('teacher')
        quiz_payload = self.quiz_payload()
        quiz_payload['questions'][0].update({
            'curriculum_code': 'G10-SCI-FORCE-01',
            'cognitive_level': 'application',
        })
        created = self.client.post('/api/teacher/quizzes', json=quiz_payload)
        self.assertEqual(created.status_code, 201)
        quiz_id = created.json['quiz_id']

        response = self.client.post(
            '/api/teacher/quiz-sessions',
            json=self.lab_session_payload(quiz_id)
        )
        self.assertEqual(response.status_code, 201)
        lab_session_id = response.json['session_id']
        self.assertEqual(response.json['access_code'], 'LAB-2048')
        stored = self.db.execute(
            'SELECT access_code_hash FROM quiz_sessions WHERE id=?',
            (lab_session_id,)
        ).fetchone()['access_code_hash']
        self.assertNotEqual(stored, 'LAB-2048')
        self.assertEqual(
            self.db.execute('SELECT requires_session FROM quizzes WHERE id=?',
                            (quiz_id,)).fetchone()[0],
            1
        )

        self.login('student')
        available = self.client.get('/api/student/quiz-sessions')
        self.assertEqual(available.status_code, 200)
        self.assertEqual(available.json['sessions'][0]['state'], 'active')
        self.assertNotIn(
            quiz_id,
            [quiz['id'] for quiz in self.client.get('/api/student/quizzes').json['quizzes']]
        )
        self.assertEqual(
            self.client.get(f'/api/student/quiz?quiz_id={quiz_id}').status_code,
            404
        )
        self.assertEqual(
            self.client.post(
                f'/api/student/quiz-sessions/{lab_session_id}/start',
                json={'access_code': 'wrong'}
            ).status_code,
            403
        )
        started = self.client.post(
            f'/api/student/quiz-sessions/{lab_session_id}/start',
            json={'access_code': 'LAB-2048'}
        )
        self.assertEqual(started.status_code, 200)
        question = started.json['quiz']['questions'][0]
        self.assertEqual(question['curriculum_code'], 'G10-SCI-FORCE-01')
        self.assertEqual(question['cognitive_level'], 'application')
        self.assertNotIn('answer', question)

        self.assertEqual(
            self.client.post('/api/student/quiz/submit', json={
                'quiz_id': quiz_id,
                'answers': {'0': 'A push or pull'}
            }).status_code,
            403
        )
        submitted = self.client.post('/api/student/quiz/submit', json={
            'quiz_id': quiz_id,
            'quiz_session_id': lab_session_id,
            'answers': {'0': 'A push or pull'}
        })
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(
            self.db.execute('SELECT quiz_session_id FROM quiz_results').fetchone()[0],
            lab_session_id
        )
        self.assertEqual(
            self.client.post(
                f'/api/student/quiz-sessions/{lab_session_id}/start',
                json={'access_code': 'LAB-2048'}
            ).status_code,
            409
        )

    def test_lab_quiz_rejects_unassigned_teacher_and_closed_session(self):
        self.login('teacher')
        created = self.client.post('/api/teacher/quizzes', json=self.quiz_payload())
        quiz_id = created.json['quiz_id']
        self.login('other_teacher')
        self.assertEqual(
            self.client.post('/api/teacher/quiz-sessions',
                             json=self.lab_session_payload(quiz_id)).status_code,
            404
        )

        self.login('teacher')
        created_session = self.client.post(
            '/api/teacher/quiz-sessions', json=self.lab_session_payload(quiz_id)
        )
        lab_session_id = created_session.json['session_id']
        self.assertEqual(
            self.client.post(
                f'/api/teacher/quiz-sessions/{lab_session_id}/close'
            ).status_code,
            200
        )
        self.login('student')
        self.assertEqual(
            self.client.post(
                f'/api/student/quiz-sessions/{lab_session_id}/start',
                json={'access_code': 'LAB-2048'}
            ).status_code,
            409
        )

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
