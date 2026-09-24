# Quiz statistics migration

Stop the Flask backend before updating an existing database. Back up the database,
then run from the project root (use your local MySQL username):

```bash
mysqldump -u siksha_user -p siksha_sarathi > ../siksha_sarathi_before_quiz_fix.sql
mysql -u siksha_user -p siksha_sarathi < migrations/001_quiz_result_totals.sql
```

The database account needs ALTER and UPDATE permissions. Do not commit the backup.
Restart Flask only after the migration succeeds. This migration can be run again;
it does not overwrite totals already recorded.

New quiz attempts store their question count at submission. Dashboard percentages
are the mean of each attempt's percentage, so 2/2 and 5/10 average to 75%.
Older totals are inferred from the current quiz contents. If a quiz was previously
edited, verify those historical totals manually against any available records.
Attempts with missing or invalid totals remain in attempt counts but do not enter
the percentage average; if there are no usable percentages, the dashboard shows 0%.

For a new database, use the updated setup_db.sql. CREATE TABLE IF NOT EXISTS does
not update an existing table, so existing databases require the migration above.

The legacy self-reported prediction feature has been retired. Existing rows in
the `predictions` table are preserved as historical data but are not used for
student guidance or administrator statistics.

Run the regression tests with the backend environment activated:

```bash
python -m unittest discover -s backend/tests -v
```

Tests use Flask's test client with an in-memory SQLite database adapter and model
stubs. They do not connect to MySQL, load model pickle files, or change real data.
The migration itself requires verification against MySQL before merging.

## Per-question learning activity migration

Migration `002_quiz_answer_tracking.sql` creates a detail table for future quiz
submissions. Run it after migration 001 and before starting the updated backend:

```bash
mysql -u siksha_user -p siksha_sarathi < migrations/002_quiz_answer_tracking.sql
```

Each new attempt records a snapshot of every question, its topic and difficulty,
the selected and correct answers, and whether it was correct or skipped. Existing
attempt totals remain untouched because their historical selected answers cannot
be reconstructed reliably.

Quiz JSON may now include `topic` and `difficulty` (`easy`, `medium`, or `hard`)
on each question. Older quizzes remain valid: their quiz subject becomes the topic
and their difficulty is stored as `unspecified`.

## Teacher quiz ownership migration

Migration `003_teacher_quiz_ownership.sql` adds quiz ownership and publishing
status. Run it after migrations 001 and 002:

```bash
mysql -u siksha_user -p siksha_sarathi < migrations/003_teacher_quiz_ownership.sql
```

Existing quizzes remain published with no owner, so the migration never guesses
which teacher owns historical content. Newly created quizzes belong to their
teacher. Only that teacher can read, edit, publish, unpublish, or delete them.
A quiz with attempts cannot be deleted because doing so would destroy learning
history; the teacher must unpublish it instead.

## Class and subject assignment migration

Migration `004_class_subject_assignments.sql` creates classes, enrollments, and
teacher subject assignments. It also creates one `Default` class per existing
student grade and enrolls those students automatically:

```bash
mysql -u siksha_user -p siksha_sarathi < migrations/004_class_subject_assignments.sql
```

Teachers are not assigned automatically. Assignments must name the teacher,
class, and subject explicitly. Teacher learning analytics only includes a
student when that student is enrolled in the assigned class and the quiz
subject matches the teacher assignment.

## Hybrid computer-lab quiz migration

Migration 005 adds class-scoped and time-limited computer-lab quiz sessions.
Run it after migration 004 while the Flask backend is stopped:

    mysql -u siksha_user -p siksha_sarathi < migrations/005_hybrid_lab_quiz_sessions.sql

Teachers can schedule their published quizzes for assigned classes and subjects.
Students use a temporary access code during the configured time window and can
submit only once. Access codes are stored as password hashes.

Lab quizzes are removed from the ordinary practice list. Quiz questions may
include curriculum_code and cognitive_level for improved learning analytics.
Network or computer failures must not be recorded as zero marks.

A quiz is protected from ordinary practice only while it has a scheduled or
active lab session. Closing the final open session, or allowing all sessions to
end, makes the published quiz available for practice again. Closing one session
does not expose a quiz that still has another scheduled or active session.

## Paper assessment migration

Migration 006 adds teacher-managed paper assessments and student marks.

    sudo mysql siksha_sarathi < migrations/006_paper_assessments.sql

Teachers can create assessments only for assigned classes and subjects. Marks,
absence status, and teacher remarks are recorded separately for each student.
Draft results can be reviewed before being published.

## Admin school setup migration

Migration 008 prevents multiple student profiles from being attached to one
login account. It supports the admin-managed class enrollment workflow.

    sudo mysql siksha_sarathi < migrations/008_admin_school_setup.sql

The first query must return no duplicate `user_id` rows. Administrators create
all school accounts and manage class enrollment and teacher subject assignments
in the application.

## Monthly attendance migration

Migration 009 adds one paper-register summary per class and calendar month.
Teachers enter total school days and each student's present days; absences and
percentages are calculated automatically. For installations that previously
used daily attendance, this migration converts those records into monthly totals.
The application no longer exposes daily-attendance entry APIs; existing legacy
tables are left untouched so old database records are not deleted.

    sudo mysql siksha_sarathi < migrations/009_monthly_attendance_summaries.sql

## Teacher intervention migration

Migration 010 stores evidence-based support plans created by assigned teachers.
Plans have a focus area, action, success criteria, review date, progress status,
and outcome note. Students can read their plans, but only the assigned teacher
can create or update them.

    sudo mysql siksha_sarathi < migrations/010_teacher_interventions.sql

## Intervention effectiveness migration

Migration 011 adds the learning baseline captured when a teacher creates a
support plan. The application compares later quiz accuracy, published paper
marks, and attendance with that baseline. The result describes observed change
and must not be presented as proof that the intervention caused the change.

    sudo mysql siksha_sarathi < migrations/011_intervention_effectiveness.sql
