"""Exercise real Flask routes without a running MySQL server or ML artifacts."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import types
import unittest
from datetime import date
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
        }):
            spec.loader.exec_module(cls.backend)
        cls.backend.app.config.update(TESTING=True, SECRET_KEY='isolated-test-secret')

    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT, email TEXT,
                password TEXT, role TEXT, created_at TEXT);
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
            CREATE TABLE paper_assessments(id INTEGER PRIMARY KEY,
                teacher_user_id INTEGER, class_id INTEGER, subject TEXT,
                title TEXT, assessment_type TEXT, assessment_date TEXT,
                max_marks REAL, academic_year TEXT DEFAULT '', term TEXT DEFAULT '',
                is_published INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE paper_assessment_scores(id INTEGER PRIMARY KEY,
                assessment_id INTEGER, student_id INTEGER, marks_obtained REAL,
                is_absent INTEGER DEFAULT 0, remarks TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE class_teacher_assignments(id INTEGER PRIMARY KEY,
                teacher_user_id INTEGER, class_id INTEGER UNIQUE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE attendance_sessions(id INTEGER PRIMARY KEY,
                teacher_user_id INTEGER, class_id INTEGER,
                attendance_date TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(class_id,attendance_date));
            CREATE TABLE attendance_records(id INTEGER PRIMARY KEY,
                attendance_session_id INTEGER, student_id INTEGER, status TEXT,
                note TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(attendance_session_id,student_id));
            CREATE TABLE monthly_attendance_summaries(id INTEGER PRIMARY KEY,
                teacher_user_id INTEGER, class_id INTEGER, attendance_month TEXT,
                total_school_days INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(class_id,attendance_month));
            CREATE TABLE monthly_attendance_records(id INTEGER PRIMARY KEY,
                summary_id INTEGER, student_id INTEGER, present_days INTEGER,
                note TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(summary_id,student_id));
            CREATE TABLE teacher_interventions(id INTEGER PRIMARY KEY,
                teacher_user_id INTEGER, student_id INTEGER, subject TEXT,
                source_kind TEXT DEFAULT 'manual', focus_area TEXT,
                evidence TEXT DEFAULT '', action_plan TEXT,
                success_criteria TEXT DEFAULT '', status TEXT DEFAULT 'planned',
                review_date TEXT, outcome_note TEXT DEFAULT '', completed_at TEXT,
                baseline_quiz_accuracy REAL, baseline_quiz_questions INTEGER DEFAULT 0,
                baseline_paper_average REAL, baseline_paper_assessments INTEGER DEFAULT 0,
                baseline_attendance_percent REAL,
                baseline_attendance_days INTEGER DEFAULT 0,
                baseline_captured_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE predictions(id INTEGER PRIMARY KEY, student_id INTEGER,
                prediction TEXT, attendance REAL, assignment_score REAL,
                quiz_score REAL, study_hours REAL);
            CREATE TABLE notes(id INTEGER PRIMARY KEY, title TEXT, subject TEXT,
                chapter TEXT, content TEXT, created_at TEXT, uploaded_by INTEGER);
            INSERT INTO users VALUES(1,'Student','s@example.test','hash','student','2026-01-01');
            INSERT INTO users VALUES(2,'Teacher','t@example.test','hash','teacher','2026-01-01');
            INSERT INTO users VALUES(3,'Admin','a@example.test','hash','admin','2026-01-01');
            INSERT INTO users VALUES(4,'Other Teacher','other@example.test','hash','teacher','2026-01-01');
            INSERT INTO users VALUES(5,'Student Two','s2@example.test','hash','student','2026-01-01');
            INSERT INTO students VALUES(1,1,'Student One','10');
            INSERT INTO students VALUES(2,5,'Student Two','9');
            INSERT INTO classes VALUES(1,'Grade 10','10','Default','2026-01-01');
            INSERT INTO classes VALUES(2,'Grade 9','9','Default','2026-01-01');
            INSERT INTO student_class_enrollments VALUES(1,1,1,'2026-01-01');
            INSERT INTO student_class_enrollments VALUES(2,2,2,'2026-01-01');
            INSERT INTO teacher_class_subjects VALUES(1,2,1,'Science','2026-01-01');
            INSERT INTO class_teacher_assignments VALUES(1,2,1,'2026-01-01');
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

    def test_public_registration_is_student_only_and_enrolls_selected_class(self):
        teacher = self.client.post('/api/register', json={
            'username': 'Unapproved', 'email': 'unapproved@example.test',
            'password': 'Password123', 'role': 'teacher'
        })
        self.assertEqual(teacher.status_code, 403)
        self.assertIsNone(self.db.execute(
            "SELECT id FROM users WHERE email='unapproved@example.test'"
        ).fetchone())

        classes = self.client.get('/api/public/classes')
        self.assertEqual(classes.status_code, 200)
        self.assertEqual(classes.json['classes'][0]['name'], 'Grade 10')
        response = self.client.post('/api/register', json={
            'username': 'New Student', 'full_name': 'New Student',
            'email': 'new.student@example.test', 'password': 'Password123',
            'role': 'student', 'class_id': 1
        })
        self.assertEqual(response.status_code, 201)
        enrolled = self.db.execute(
            '''SELECT s.grade, sce.class_id FROM students s
               JOIN student_class_enrollments sce ON sce.student_id=s.id
               WHERE s.user_id=?''', (response.json['user']['id'],)
        ).fetchone()
        self.assertEqual(tuple(enrolled), ('10', 1))

    def test_admin_manages_classes_enrollment_and_teacher_assignments(self):
        self.login('admin')
        created_class = self.client.post('/api/admin/classes', json={
            'name': 'Grade 8 A', 'grade': '8', 'section': 'A'
        })
        self.assertEqual(created_class.status_code, 201)
        class_id = created_class.json['class_id']
        teacher = self.client.post('/api/admin/teachers', json={
            'username': 'Science Teacher', 'email': 'science@example.test',
            'password': 'Password123'
        })
        self.assertEqual(teacher.status_code, 201)
        teacher_id = teacher.json['teacher_id']
        self.assertEqual(self.client.put('/api/admin/students/2/class', json={
            'class_id': class_id
        }).status_code, 200)
        assignment = self.client.post('/api/admin/teacher-assignments', json={
            'teacher_user_id': teacher_id, 'class_id': class_id,
            'subject': 'Science', 'is_class_teacher': True
        })
        self.assertEqual(assignment.status_code, 201)

        setup = self.client.get('/api/admin/school-setup')
        self.assertEqual(setup.status_code, 200)
        self.assertTrue(any(item['email'] == 'science@example.test'
                            for item in setup.json['teachers']))
        self.assertTrue(any(item['student_id'] == 2 and item['class_id'] == class_id
                            for item in setup.json['students']))
        self.assertTrue(setup.json['assignments'][-1]['is_class_teacher'])
        self.assertEqual(self.client.delete(
            f"/api/admin/teacher-assignments/{assignment.json['assignment_id']}"
        ).status_code, 200)

    def test_school_setup_requires_admin_role(self):
        for role in ('student', 'teacher'):
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(
                    self.client.get('/api/admin/school-setup').status_code, 403
                )

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

    def test_student_practice_plan_requires_own_activity_and_student_role(self):
        response = self.client.get('/api/student/practice-plan')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['topics'], [])

        self.login('teacher')
        self.assertEqual(self.client.get('/api/student/practice-plan').status_code, 403)
        with self.client.session_transaction() as login_session:
            login_session.clear()
        self.assertEqual(self.client.get('/api/student/practice-plan').status_code, 401)

    def test_student_practice_plan_links_only_matching_published_resources(self):
        questions = [dict(question) for question in self.questions]
        questions[1]['topic'] = 'Force'
        self.db.execute('UPDATE quizzes SET questions=? WHERE id=1',
                        (json.dumps(questions),))
        self.db.executemany(
            '''INSERT INTO notes(id,title,subject,chapter,content,created_at,uploaded_by)
               VALUES(?,?,?,?,?,'2026-09-01',2)''',
            [(1,'Force lesson','Science','Force and motion','Content'),
             (2,'Other science lesson','Science','Electricity','Content'),
             (3,'Other subject','Math','Force','Content')]
        )
        self.db.execute(
            '''INSERT INTO quizzes(id,title,subject,questions,created_by,is_published,
               created_at,requires_session) VALUES(2,'Lab Force','Science',?,2,1,
               '2026-09-01',1)''', (json.dumps(questions),)
        )
        for _ in range(3):
            self.assertEqual(self.submit({'0': 'B', '1': 'C'}).status_code, 200)
        self.db.execute('''INSERT INTO quiz_results(id,student_id,quiz_id,score,total_questions)
                           VALUES(90,2,1,0,1)''')
        self.db.execute('''INSERT INTO quiz_answer_results(quiz_result_id,
                           question_index,question_text,topic,difficulty,is_correct,
                           is_skipped) VALUES(90,0,'Other student?','Force','easy',0,0)''')

        response = self.client.get('/api/student/practice-plan')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['topics']), 1)
        topic = response.json['topics'][0]
        self.assertEqual((topic['subject'], topic['topic']), ('Science', 'Force'))
        self.assertEqual((topic['correct_answers'],topic['total_questions']), (0,6))
        self.assertEqual([note['id'] for note in topic['notes']], [1])
        self.assertEqual([quiz['id'] for quiz in topic['quizzes']], [1])
        self.assertNotIn('correct_answer', topic)
        self.assertEqual(set(topic['quizzes'][0]), {'id', 'title'})

    def test_student_practice_plan_does_not_guess_from_one_repeated_question(self):
        for _ in range(3):
            self.assertEqual(self.submit({'0': 'B', '1': 'D'}).status_code, 200)
        response = self.client.get('/api/student/practice-plan')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['topics'], [])

    def test_legacy_student_prediction_api_is_retired(self):
        self.assertEqual(self.client.get('/api/student/prediction').status_code, 404)
        self.assertEqual(self.client.post(
            '/api/student/prediction',
            json={'attendance': 100, 'assignment_score': 100,
                  'quiz_score': 100, 'study_hours': 10}
        ).status_code, 404)

    def test_student_dashboard_does_not_return_legacy_prediction(self):
        response = self.client.get('/api/student/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('prediction', response.json)

    def test_teacher_dashboard_only_shows_assigned_students_and_quiz_evidence(self):
        self.assertEqual(self.submit({'0': 'B', '1': 'C'}).status_code, 200)
        self.db.execute('''INSERT INTO quizzes(id,title,subject,questions,is_published)
                           VALUES(2,'Math','Math','[]',1)''')
        self.db.executemany('''INSERT INTO quiz_results(id,student_id,quiz_id,score,total_questions)
                               VALUES(?,?,?,?,?)''',
                            [(50, 1, 2, 10, 10), (51, 2, 1, 10, 10)])
        self.db.execute('''INSERT INTO quiz_answer_results(quiz_result_id,
                           question_index,question_text,topic,difficulty,is_correct,is_skipped)
                           VALUES(51,0,'Other student','Force','easy',1,0)''')
        self.db.execute("INSERT INTO predictions(student_id,prediction) VALUES(2,'Needs Improvement')")
        self.db.execute("INSERT INTO classes VALUES(3,'Grade 10 B','10','B','2026-01-01')")
        self.db.execute("INSERT INTO student_class_enrollments VALUES(3,1,3,'2026-01-01')")
        self.db.execute("INSERT INTO teacher_class_subjects VALUES(2,2,3,'Science','2026-01-01')")

        self.login('teacher')
        result = self.client.get('/api/teacher/dashboard')
        self.assertEqual(result.status_code, 200)
        stats = result.json['statistics']
        self.assertEqual(stats['total_students'], 1)
        self.assertEqual(stats['total_quiz_attempts'], 1)
        self.assertEqual(stats['average_quiz_score'], 0)
        self.assertEqual(stats['students_needing_quiz_support'], 1)
        self.assertEqual(len(result.json['student_performance']), 1)
        self.assertEqual(result.json['student_performance'][0]['quiz_attempts'], 1)

        self.login('other_teacher')
        other = self.client.get('/api/teacher/dashboard')
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.json['statistics']['total_students'], 0)
        self.assertEqual(other.json['statistics']['students_needing_quiz_support'], 0)
        self.assertEqual(other.json['student_performance'], [])

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

    def test_learning_profile_keeps_school_performance_factors_separate(self):
        self.db.executemany(
            '''INSERT INTO paper_assessments
               (id,teacher_user_id,class_id,subject,title,assessment_type,
                assessment_date,max_marks,is_published)
               VALUES(?,?,?,?,?,?,?,?,?)''',
            [
                (1, 2, 1, 'Science', 'Unit Test', 'unit_test',
                 '2026-09-10', 50, 1),
                (2, 2, 1, 'Science', 'Terminal', 'terminal_exam',
                 '2026-09-15', 100, 1),
            ]
        )
        self.db.executemany(
            '''INSERT INTO paper_assessment_scores
               (id,assessment_id,student_id,marks_obtained,is_absent,remarks)
               VALUES(?,?,?,?,?,?)''',
            [
                (1, 1, 1, 40, 0, 'Good'),
                (2, 2, 1, None, 1, 'Medical leave'),
            ]
        )
        self.db.executemany(
            '''INSERT INTO attendance_sessions
               (id,teacher_user_id,class_id,attendance_date)
               VALUES(?,?,?,?)''',
            [
                (1, 2, 1, '2026-09-13'),
                (2, 2, 1, '2026-09-14'),
                (3, 2, 1, '2026-09-15'),
            ]
        )
        self.db.executemany(
            '''INSERT INTO attendance_records
               (id,attendance_session_id,student_id,status,note)
               VALUES(?,?,?,?,?)''',
            [
                (1, 1, 1, 'present', ''),
                (2, 2, 1, 'late', 'Bus delay'),
                (3, 3, 1, 'absent', 'Unwell'),
            ]
        )
        self.db.commit()
        self.login('teacher')

        overview = self.client.get('/api/teacher/learning-analytics')
        profile = overview.json['students'][0]
        self.assertEqual(profile['paper_assessments']['average_percent'], 80)
        self.assertEqual(profile['paper_assessments']['recorded_assessments'], 2)
        self.assertEqual(profile['paper_assessments']['graded_assessments'], 1)
        self.assertEqual(profile['paper_assessments']['absent_assessments'], 1)
        self.assertEqual(profile['attendance']['attendance_percent'], 66.67)
        self.assertEqual(profile['attendance']['late_days'], 1)
        self.assertEqual(profile['attendance']['absent_days'], 1)

        detail = self.client.get(
            '/api/teacher/students/1/learning-profile?subject=Science'
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json['paper_assessments']['average_percent'], 80)
        self.assertEqual(detail.json['attendance']['recorded_days'], 3)
        self.assertEqual(len(detail.json['recent_paper_assessments']), 2)
        self.assertEqual(
            detail.json['recent_paper_assessments'][1]['percentage'], 80
        )
        self.assertEqual(len(detail.json['recent_attendance']), 3)
        self.assertEqual(detail.json['recent_attendance'][0]['status'], 'absent')

    def test_ungraded_paper_marks_do_not_count_as_graded_or_trigger_action(self):
        self.db.executemany(
            '''INSERT INTO paper_assessments
               (id,teacher_user_id,class_id,subject,title,assessment_type,
                assessment_date,max_marks,is_published)
               VALUES(?,2,1,'Science',?,'unit_test','2026-09-16',100,1)''',
            [(1, 'Marked'), (2, 'Awaiting marks'), (3, 'Absent')]
        )
        self.db.executemany(
            '''INSERT INTO paper_assessment_scores
               (assessment_id,student_id,marks_obtained,is_absent)
               VALUES(?,1,?,?)''',
            [(1, 40, 0), (2, None, 0), (3, None, 1)]
        )
        self.db.commit()
        self.login('teacher')

        overview = self.client.get('/api/teacher/learning-analytics')
        self.assertEqual(overview.status_code, 200)
        paper = overview.json['students'][0]['paper_assessments']
        self.assertEqual(paper['recorded_assessments'], 3)
        self.assertEqual(paper['graded_assessments'], 1)
        self.assertEqual(paper['absent_assessments'], 1)
        self.assertEqual(paper['average_percent'], 40)

        url = '/api/teacher/students/1/learning-profile?subject=Science'
        profile = self.client.get(url)
        self.assertEqual(profile.status_code, 200)
        self.assertFalse(any(action['kind'] == 'paper'
                             for action in profile.json['teacher_actions']))

        self.db.execute(
            '''UPDATE paper_assessment_scores
               SET marks_obtained = 30 WHERE assessment_id = 2'''
        )
        self.db.commit()
        profile = self.client.get(url)
        self.assertEqual(profile.json['paper_assessments']['graded_assessments'], 2)
        self.assertTrue(any(action['kind'] == 'paper'
                            for action in profile.json['teacher_actions']))

        self.db.execute(
            '''UPDATE paper_assessment_scores SET marks_obtained = NULL
               WHERE assessment_id IN (1, 2)'''
        )
        self.db.commit()
        profile = self.client.get(url)
        self.assertEqual(profile.json['paper_assessments']['graded_assessments'], 0)
        self.assertEqual(profile.json['paper_assessments']['average_percent'], 0)
        self.assertFalse(any(action['kind'] == 'paper'
                             for action in profile.json['teacher_actions']))

    def test_teacher_topic_priorities_and_actions_use_assigned_evidence(self):
        questions = [dict(question) for question in self.questions]
        questions[1]['topic'] = 'Force'
        self.db.execute('UPDATE quizzes SET questions = ? WHERE id = 1',
                        (json.dumps(questions),))
        for _ in range(3):
            self.assertEqual(self.submit({'0': 'B', '1': 'C'}).status_code, 200)
        self.db.execute(
            '''INSERT INTO quiz_results(id,student_id,quiz_id,score,total_questions)
               VALUES(90,2,1,0,1)'''
        )
        self.db.execute(
            '''INSERT INTO quiz_answer_results
               (quiz_result_id,question_index,question_text,topic,difficulty,
                is_correct,is_skipped) VALUES(90,0,'Outside?', 'Force', 'easy',0,0)'''
        )
        self.db.executemany(
            '''INSERT INTO paper_assessments
               (id,teacher_user_id,class_id,subject,title,assessment_type,
                assessment_date,max_marks,is_published)
               VALUES(?,2,1,'Science',?,'unit_test','2026-09-16',100,1)''',
            [(1, 'Paper 1'), (2, 'Paper 2')]
        )
        self.db.executemany(
            '''INSERT INTO paper_assessment_scores
               (assessment_id,student_id,marks_obtained,is_absent)
               VALUES(?,1,40,0)''', [(1,), (2,)]
        )
        self.db.executemany(
            '''INSERT INTO attendance_sessions
               (id,teacher_user_id,class_id,attendance_date) VALUES(?,2,1,?)''',
            [(i, f'2026-09-{i + 10}') for i in range(1, 6)]
        )
        self.db.executemany(
            '''INSERT INTO attendance_records
               (attendance_session_id,student_id,status) VALUES(?,1,?)''',
            [(i, 'absent' if i <= 2 else 'present') for i in range(1, 6)]
        )
        self.db.commit()

        self.login('teacher')
        overview = self.client.get('/api/teacher/learning-analytics')
        self.assertEqual(overview.status_code, 200)
        priorities = overview.json['topic_priorities']
        self.assertEqual(len(priorities), 1)
        self.assertEqual(priorities[0]['topic'], 'Force')
        self.assertEqual(priorities[0]['total_questions'], 6)
        self.assertEqual(priorities[0]['students_to_support'][0]['student_id'], 1)

        profile = self.client.get(
            '/api/teacher/students/1/learning-profile?subject=Science'
        )
        actions = {action['kind']: action for action in profile.json['teacher_actions']}
        self.assertEqual(set(actions), {'topic', 'paper', 'attendance'})
        self.assertIn('Force', actions['topic']['title'])
        self.assertIn('2 absences', actions['attendance']['evidence'])
        self.assertIn('40.0%', actions['paper']['evidence'])

        self.login('other_teacher')
        self.assertEqual(
            self.client.get('/api/teacher/learning-analytics').json['topic_priorities'],
            []
        )
        self.assertEqual(self.client.get(
            '/api/teacher/students/1/learning-profile?subject=Science'
        ).status_code, 404)

    def test_sparse_quiz_data_does_not_create_topic_intervention(self):
        self.assertEqual(self.submit({'0': 'B', '1': 'D'}).status_code, 200)
        self.login('teacher')
        overview = self.client.get('/api/teacher/learning-analytics')
        profile = self.client.get(
            '/api/teacher/students/1/learning-profile?subject=Science'
        )
        self.assertEqual(overview.json['topic_priorities'], [])
        self.assertEqual(profile.json['teacher_actions'], [])

    def test_repeating_one_question_does_not_create_topic_intervention(self):
        for _ in range(3):
            self.assertEqual(self.submit({'0': 'B', '1': 'D'}).status_code, 200)
        self.login('teacher')
        self.assertEqual(
            self.client.get('/api/teacher/learning-analytics').json['topic_priorities'],
            []
        )
        profile = self.client.get(
            '/api/teacher/students/1/learning-profile?subject=Science'
        )
        self.assertFalse(any(action['kind'] == 'topic'
                             for action in profile.json['teacher_actions']))

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

    def paper_assessment_payload(self, **overrides):
        payload = {
            'class_id': 1,
            'subject': 'Science',
            'title': 'First Terminal Examination',
            'assessment_type': 'terminal_exam',
            'assessment_date': '2026-09-16',
            'max_marks': 50,
            'academic_year': '2083 BS',
            'term': 'First Term',
            'is_published': False,
        }
        payload.update(overrides)
        return payload

    def test_teacher_can_create_record_and_delete_paper_assessment(self):
        self.login('teacher')
        response = self.client.post(
            '/api/teacher/paper-assessments',
            json=self.paper_assessment_payload()
        )
        self.assertEqual(response.status_code, 201)
        assessment_id = response.json['assessment_id']

        detail = self.client.get(
            f'/api/teacher/paper-assessments/{assessment_id}'
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json['assessment']['class_name'], 'Grade 10')
        self.assertEqual(detail.json['students'][0]['student_id'], 1)
        self.assertIsNone(detail.json['students'][0]['marks_obtained'])

        saved = self.client.put(
            f'/api/teacher/paper-assessments/{assessment_id}/scores',
            json={'scores': [{
                'student_id': 1,
                'marks_obtained': 42,
                'is_absent': False,
                'remarks': 'Good progress',
            }]}
        )
        self.assertEqual(saved.status_code, 200)
        detail = self.client.get(
            f'/api/teacher/paper-assessments/{assessment_id}'
        )
        self.assertEqual(detail.json['students'][0]['percentage'], 84)
        self.assertEqual(detail.json['students'][0]['remarks'], 'Good progress')

        invalid_update = self.client.put(
            f'/api/teacher/paper-assessments/{assessment_id}',
            json=self.paper_assessment_payload(max_marks=40)
        )
        self.assertEqual(invalid_update.status_code, 409)

        listing = self.client.get('/api/teacher/paper-assessments')
        self.assertEqual(listing.json['assessments'][0]['recorded_students'], 1)
        self.assertEqual(
            self.client.delete(
                f'/api/teacher/paper-assessments/{assessment_id}'
            ).status_code,
            200
        )

    def test_paper_assessment_scores_validate_marks_absence_and_enrollment(self):
        self.login('teacher')
        assessment_id = self.client.post(
            '/api/teacher/paper-assessments',
            json=self.paper_assessment_payload()
        ).json['assessment_id']
        scores_url = f'/api/teacher/paper-assessments/{assessment_id}/scores'

        self.assertEqual(self.client.put(scores_url, json={'scores': [{
            'student_id': 1, 'marks_obtained': 51
        }]}).status_code, 400)
        self.assertEqual(self.client.put(scores_url, json={'scores': [{
            'student_id': 2, 'marks_obtained': 40
        }]}).status_code, 400)
        response = self.client.put(scores_url, json={'scores': [{
            'student_id': 1, 'marks_obtained': 50,
            'is_absent': True, 'remarks': 'Medical leave'
        }]})
        self.assertEqual(response.status_code, 200)
        row = self.db.execute(
            'SELECT marks_obtained,is_absent FROM paper_assessment_scores'
        ).fetchone()
        self.assertEqual(tuple(row), (None, 1))

    def test_paper_assessment_publishes_scores_together_and_rejects_over_max(self):
        self.login('teacher')
        assessment_id = self.client.post(
            '/api/teacher/paper-assessments',
            json=self.paper_assessment_payload()
        ).json['assessment_id']
        url = f'/api/teacher/paper-assessments/{assessment_id}/scores'

        invalid = self.client.put(url, json={
            'is_published': True,
            'scores': [{'student_id': 1, 'marks_obtained': 60}]
        })
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.db.execute(
            'SELECT is_published FROM paper_assessments WHERE id=?',
            (assessment_id,)
        ).fetchone()[0], 0)
        self.assertEqual(self.db.execute(
            'SELECT COUNT(*) FROM paper_assessment_scores WHERE assessment_id=?',
            (assessment_id,)
        ).fetchone()[0], 0)

        published = self.client.put(url, json={
            'is_published': True,
            'scores': [{'student_id': 1, 'marks_obtained': 45}]
        })
        self.assertEqual(published.status_code, 200)
        detail = self.client.get(f'/api/teacher/paper-assessments/{assessment_id}')
        self.assertTrue(detail.json['assessment']['is_published'])
        self.assertEqual(detail.json['students'][0]['percentage'], 90)

        self.assertEqual(self.client.put(url, json={
            'is_published': 'yes', 'scores': []
        }).status_code, 400)

    def test_paper_assessment_is_scoped_to_assigned_teacher(self):
        self.login('other_teacher')
        self.assertEqual(self.client.post(
            '/api/teacher/paper-assessments',
            json=self.paper_assessment_payload()
        ).status_code, 404)

        self.login('teacher')
        assessment_id = self.client.post(
            '/api/teacher/paper-assessments',
            json=self.paper_assessment_payload()
        ).json['assessment_id']
        self.login('other_teacher')
        self.assertEqual(self.client.get(
            f'/api/teacher/paper-assessments/{assessment_id}'
        ).status_code, 404)

    def test_paper_assessment_management_requires_teacher_role(self):
        for role in ['student', 'admin']:
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(
                    self.client.get('/api/teacher/paper-assessments').status_code,
                    403
                )

    def attendance_payload(self, **overrides):
        payload = {
            'class_id': 1,
            'attendance_date': '2026-09-16',
        }
        payload.update(overrides)
        return payload

    def test_attendance_dates_are_serialized_for_the_browser(self):
        self.assertEqual(
            self.backend.serialize_api_date(date(2026, 9, 16)),
            '2026-09-16'
        )
        self.assertEqual(
            self.backend.serialize_api_date('2026-09-16'),
            '2026-09-16'
        )

    def test_teacher_can_create_record_list_and_delete_attendance(self):
        self.login('teacher')
        created = self.client.post(
            '/api/teacher/attendance-sessions',
            json=self.attendance_payload()
        )
        self.assertEqual(created.status_code, 201)
        attendance_id = created.json['attendance_session_id']

        detail = self.client.get(
            f'/api/teacher/attendance-sessions/{attendance_id}'
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json['session']['class_name'], 'Grade 10')
        self.assertEqual(detail.json['students'][0]['student_id'], 1)
        self.assertIsNone(detail.json['students'][0]['status'])

        saved = self.client.put(
            f'/api/teacher/attendance-sessions/{attendance_id}/records',
            json={'records': [{
                'student_id': 1,
                'status': 'present',
                'note': 'On time',
            }]}
        )
        self.assertEqual(saved.status_code, 200)
        detail = self.client.get(
            f'/api/teacher/attendance-sessions/{attendance_id}'
        )
        self.assertEqual(detail.json['students'][0]['status'], 'present')
        self.assertEqual(detail.json['students'][0]['note'], 'On time')

        listing = self.client.get('/api/teacher/attendance-sessions')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(
            listing.json['assigned_classes'][0]['class_name'],
            'Grade 10'
        )
        self.assertEqual(listing.json['sessions'][0]['recorded_students'], 1)
        self.assertEqual(listing.json['sessions'][0]['present_count'], 1)
        self.assertEqual(
            self.client.delete(
                f'/api/teacher/attendance-sessions/{attendance_id}'
            ).status_code,
            200
        )

    def test_attendance_requires_valid_status_and_complete_class_roster(self):
        self.login('teacher')
        attendance_id = self.client.post(
            '/api/teacher/attendance-sessions',
            json=self.attendance_payload()
        ).json['attendance_session_id']
        records_url = (
            f'/api/teacher/attendance-sessions/{attendance_id}/records'
        )
        self.assertEqual(self.client.put(records_url, json={'records': [{
            'student_id': 1, 'status': 'missing'
        }]}).status_code, 400)
        self.assertEqual(self.client.put(records_url, json={'records': [{
            'student_id': 2, 'status': 'present'
        }]}).status_code, 400)
        self.assertEqual(
            self.client.put(records_url, json={'records': []}).status_code,
            400
        )

    def test_duplicate_attendance_session_is_rejected(self):
        self.login('teacher')
        first = self.client.post(
            '/api/teacher/attendance-sessions',
            json=self.attendance_payload()
        )
        self.assertEqual(first.status_code, 201)
        duplicate = self.client.post(
            '/api/teacher/attendance-sessions',
            json=self.attendance_payload()
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_attendance_is_teacher_scoped_and_requires_teacher_role(self):
        self.login('other_teacher')
        self.assertEqual(self.client.post(
            '/api/teacher/attendance-sessions',
            json=self.attendance_payload()
        ).status_code, 404)

        self.login('teacher')
        attendance_id = self.client.post(
            '/api/teacher/attendance-sessions',
            json=self.attendance_payload()
        ).json['attendance_session_id']
        self.login('other_teacher')
        self.assertEqual(self.client.get(
            f'/api/teacher/attendance-sessions/{attendance_id}'
        ).status_code, 404)

        for role in ['student', 'admin']:
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(
                    self.client.get(
                        '/api/teacher/attendance-sessions'
                    ).status_code,
                    403
                )

    def monthly_attendance_payload(self, **overrides):
        payload = {
            'class_id': 1,
            'attendance_month': '2026-09',
            'total_school_days': 20,
        }
        payload.update(overrides)
        return payload

    def test_teacher_can_manage_monthly_paper_register_totals(self):
        self.login('teacher')
        created = self.client.post(
            '/api/teacher/monthly-attendance',
            json=self.monthly_attendance_payload()
        )
        self.assertEqual(created.status_code, 201)
        summary_id = created.json['attendance_summary_id']

        detail_url = f'/api/teacher/monthly-attendance/{summary_id}'
        detail = self.client.get(detail_url)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json['summary']['total_school_days'], 20)
        self.assertEqual(detail.json['students'][0]['student_id'], 1)

        saved = self.client.put(f'{detail_url}/records', json={'records': [{
            'student_id': 1,
            'present_days': 18,
            'note': 'Two days absent',
        }]})
        self.assertEqual(saved.status_code, 200)

        listing = self.client.get('/api/teacher/monthly-attendance')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json['summaries'][0]['present_days'], 18)
        self.assertEqual(listing.json['summaries'][0]['absent_days'], 2)

        analytics = self.client.get('/api/teacher/learning-analytics')
        attendance = analytics.json['students'][0]['attendance']
        self.assertEqual(attendance['recorded_months'], 1)
        self.assertEqual(attendance['recorded_days'], 20)
        self.assertEqual(attendance['attendance_percent'], 90)
        self.assertEqual(self.client.put(detail_url, json={
            'total_school_days': 17
        }).status_code, 400)
        updated = self.client.put(detail_url, json={'total_school_days': 22})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json['total_school_days'], 22)
        self.assertEqual(self.client.delete(detail_url).status_code, 200)

    def test_monthly_attendance_rejects_impossible_or_incomplete_totals(self):
        self.login('teacher')
        for total_days in (0, 32, 'many'):
            with self.subTest(total_days=total_days):
                response = self.client.post(
                    '/api/teacher/monthly-attendance',
                    json=self.monthly_attendance_payload(
                        total_school_days=total_days
                    )
                )
                self.assertEqual(response.status_code, 400)

        summary_id = self.client.post(
            '/api/teacher/monthly-attendance',
            json=self.monthly_attendance_payload()
        ).json['attendance_summary_id']
        records_url = f'/api/teacher/monthly-attendance/{summary_id}/records'
        self.assertEqual(self.client.put(records_url, json={'records': [{
            'student_id': 1, 'present_days': 21
        }]}).status_code, 400)
        self.assertEqual(
            self.client.put(records_url, json={'records': []}).status_code,
            400
        )

    def test_monthly_attendance_is_unique_and_teacher_scoped(self):
        self.login('teacher')
        first = self.client.post(
            '/api/teacher/monthly-attendance',
            json=self.monthly_attendance_payload()
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(self.client.post(
            '/api/teacher/monthly-attendance',
            json=self.monthly_attendance_payload()
        ).status_code, 409)

        summary_id = first.json['attendance_summary_id']
        self.login('other_teacher')
        self.assertEqual(self.client.get(
            f'/api/teacher/monthly-attendance/{summary_id}'
        ).status_code, 404)

        for role in ['student', 'admin']:
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(self.client.get(
                    '/api/teacher/monthly-attendance'
                ).status_code, 403)

    def intervention_payload(self, **overrides):
        payload = {
            'subject': 'Science',
            'source_kind': 'topic',
            'focus_area': 'Force concepts',
            'evidence': 'Two repeated incorrect answers about force.',
            'action_plan': 'Review force examples and complete one guided quiz.',
            'success_criteria': 'Score at least 70% on the review quiz.',
            'status': 'planned',
            'review_date': '2026-09-30',
            'outcome_note': '',
        }
        payload.update(overrides)
        return payload

    def test_teacher_tracks_support_plan_and_student_can_read_it(self):
        self.assertEqual(self.submit({'0': 'A', '1': 'D'}).status_code, 200)
        self.db.execute(
            '''INSERT INTO paper_assessments
               (id,teacher_user_id,class_id,subject,title,assessment_type,
                assessment_date,max_marks,is_published)
               VALUES(1,2,1,'Science','Baseline','unit_test','2026-09-01',100,1)'''
        )
        self.db.execute(
            '''INSERT INTO paper_assessment_scores
               (assessment_id,student_id,marks_obtained,is_absent)
               VALUES(1,1,40,0)'''
        )
        self.db.execute(
            '''INSERT INTO monthly_attendance_summaries
               (id,teacher_user_id,class_id,attendance_month,total_school_days)
               VALUES(1,2,1,'2026-09-01',20)'''
        )
        self.db.execute(
            '''INSERT INTO monthly_attendance_records
               (summary_id,student_id,present_days) VALUES(1,1,16)'''
        )
        self.db.commit()
        self.login('teacher')
        created = self.client.post(
            '/api/teacher/students/1/interventions',
            json=self.intervention_payload()
        )
        self.assertEqual(created.status_code, 201)
        intervention_id = created.json['intervention_id']

        listing = self.client.get(
            '/api/teacher/students/1/interventions?subject=Science'
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json['interventions'][0]['focus_area'],
                         'Force concepts')
        effectiveness = listing.json['interventions'][0]['effectiveness']
        self.assertTrue(effectiveness['available'])
        self.assertEqual(effectiveness['baseline']['quiz_accuracy'], 100)
        self.assertEqual(effectiveness['baseline']['paper_average'], 40)
        self.assertEqual(effectiveness['baseline']['attendance_percent'], 80)

        self.login('student')
        self.assertEqual(self.submit({'0': 'B', '1': 'C'}).status_code, 200)
        self.db.execute(
            '''INSERT INTO paper_assessments
               (id,teacher_user_id,class_id,subject,title,assessment_type,
                assessment_date,max_marks,is_published)
               VALUES(2,2,1,'Science','Follow-up','unit_test','2026-09-20',100,1)'''
        )
        self.db.execute(
            '''INSERT INTO paper_assessment_scores
               (assessment_id,student_id,marks_obtained,is_absent)
               VALUES(2,1,80,0)'''
        )
        self.db.execute(
            '''UPDATE monthly_attendance_records SET present_days=18
               WHERE summary_id=1 AND student_id=1'''
        )
        self.db.commit()
        self.login('teacher')
        listing = self.client.get(
            '/api/teacher/students/1/interventions?subject=Science'
        )
        change = listing.json['interventions'][0]['effectiveness']['delta']
        self.assertEqual(change['quiz_accuracy'], -50)
        self.assertEqual(change['paper_average'], 20)
        self.assertEqual(change['attendance_percent'], 10)

        self.assertEqual(self.client.put(
            f'/api/teacher/interventions/{intervention_id}',
            json={'status': 'completed'}
        ).status_code, 400)
        completed = self.client.put(
            f'/api/teacher/interventions/{intervention_id}',
            json={
                'status': 'completed',
                'outcome_note': 'Student scored 80% after guided review.'
            }
        )
        self.assertEqual(completed.status_code, 200)

        self.login('student')
        student_view = self.client.get('/api/student/interventions')
        self.assertEqual(student_view.status_code, 200)
        plan = student_view.json['interventions'][0]
        self.assertEqual(plan['status'], 'completed')
        self.assertEqual(plan['teacher_name'], 'Teacher')
        self.assertIn('80%', plan['outcome_note'])

    def test_interventions_are_assignment_scoped_and_role_protected(self):
        self.login('other_teacher')
        self.assertEqual(self.client.post(
            '/api/teacher/students/1/interventions',
            json=self.intervention_payload()
        ).status_code, 404)

        self.login('teacher')
        intervention_id = self.client.post(
            '/api/teacher/students/1/interventions',
            json=self.intervention_payload()
        ).json['intervention_id']
        self.login('other_teacher')
        self.assertEqual(self.client.put(
            f'/api/teacher/interventions/{intervention_id}',
            json={'status': 'in_progress'}
        ).status_code, 404)
        self.assertEqual(self.client.delete(
            f'/api/teacher/interventions/{intervention_id}'
        ).status_code, 404)

        for role in ['student', 'admin']:
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(self.client.get(
                    '/api/teacher/students/1/interventions?subject=Science'
                ).status_code, 403)

    def test_intervention_validation_rejects_unsupported_or_invalid_plans(self):
        self.login('teacher')
        invalid_payloads = [
            self.intervention_payload(action_plan='short'),
            self.intervention_payload(source_kind='prediction'),
            self.intervention_payload(status='done'),
            self.intervention_payload(focus_area=''),
            self.intervention_payload(review_date='tomorrow'),
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(
                    '/api/teacher/students/1/interventions', json=payload
                ).status_code, 400)

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
