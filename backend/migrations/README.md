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

## Subject catalog migration

Migration 013 creates the school subject catalog and backfills every distinct
legacy `teacher_class_subjects.subject` value into `subjects`. Assignments are
then linked through `subject_id`, the structured unique constraint and foreign
key are added, and the old free-text assignment column is removed. Run this
only after backing up the database; it preserves existing assignments but
normalizes their subject source. The migration validates legacy assignments
first and refuses NULL/blank subjects or normalized duplicate assignments. It
does not silently discard assignment rows. The final structured index is named
`uq_teacher_class_subject_id`; rerunning a completed migration leaves it in
place and skips the already-NOT-NULL column alteration. The migration sequence
runs inside one stored procedure so a validation or backfill `SIGNAL` prevents
later legacy index/column cleanup even when a SQL client continues after an
error.

    sudo mysql siksha_sarathi < migrations/013_subject_catalog.sql

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

## First-login password migration

Migration 012 adds `users.must_change_password`. Existing accounts remain
usable with the default `FALSE`; administrator-created accounts explicitly set
it to `TRUE` and must choose a new password after signing in.

    sudo mysql siksha_sarathi < migrations/012_first_login_password_change.sql

## Class-teacher history migration

Migration 014 separates class-teacher responsibility from subject assignments.
It adds nullable `academic_year`, `started_at`, and `ended_at` to
`class_teacher_assignments`, backfills legacy `started_at` values from
`created_at`, and removes the old one-row-per-class unique index. Existing
rows remain intact; their academic year is left NULL because it cannot be
reliably inferred. New responsibility changes close the active row and insert
a new row, so only the current assignment has a NULL `ended_at`. MySQL also
enforces one active class per teacher and one active teacher per class through
generated active-key columns and unique indexes; historical rows produce NULL
keys and remain unrestricted. The migration checks for active conflicts and
aborts with a useful error instead of deleting or changing conflicting rows.
Stored timestamps are left unchanged; admin and teacher APIs convert
class-teacher datetimes to readable `Asia/Kathmandu` (NPT, UTC+05:45) values
at the response boundary without rewriting historical records.

Run it after migration 013:

    sudo mysql siksha_sarathi < migrations/014_class_teacher_history.sql

The migration uses `INFORMATION_SCHEMA` guards and may be rerun after a
successful run. It does not delete class-teacher or attendance history.

## ML prediction monitoring audit migration

Migration 015 creates `ml_prediction_audits`, which is a write-once audit table
for production forecast requests. It stores actual teacher, student, class,
subject, and result metadata without writing any fabricated monitoring
signals. Historical model identity is preserved with `model_version`,
`model_type`, `artifact_version`, `validation_mae`, and
`model_training_timestamp`; these values let future monitoring compare the
served model version against the original validation baseline even after the
active artifact is replaced. The table intentionally does not store
`evidence_json` because that payload can include raw feature vectors, quiz
answers, or other sensitive values and is not required for model-version
monitoring.

## Student enrollment history migration

Migration 016 upgrades `student_class_enrollments` from a simple one-row-per-class
record to a temporal history table. Each enrollment period stores its class,
academic year, start and end timestamps, transfer note, and an explicit
`ended_at` flag for the current record. MySQL enforces one active enrollment per
student with a generated `active_student_id` column and a unique index,
`uq_student_active_enrollment`, while the legacy `uq_student_class` uniqueness is
removed because historical repeats of the same class are valid over different
periods. Existing records are backfilled by preserving all rows, using
`created_at` for missing `started_at` values, and selecting the latest undated
enrollment per student by `started_at` then `id`. Older undated rows remain in
place and receive an `ended_at` value at the next enrollment start. The active
enrollment unique index is added after this deterministic backfill. All current
authorization rules treat membership as current only when `ended_at IS NULL`.

Run it after migration 015:

    sudo mysql siksha_sarathi < migrations/016_student_enrollment_history.sql

The migration is safe to rerun after it has succeeded; existing ended periods
are left unchanged and no enrollment rows are deleted.

## Official notice system migration

Migration 017 adds immutable one-way notices and a recipient snapshot for each
published notice. Admins can publish institution, role, class, and individual
notices, including public institution-wide notices. Teachers can publish only
internal notices within their active class-teacher or assigned subject scope.
Recipients are resolved from current enrollment and assignments at publication
time; later class transfers do not change prior deliveries. Inbox read state is
per recipient. The public feed returns only public institution-wide notices;
Chat remains a separate feature.

Back up the database, stop the backend, then run:

    mysqldump -u siksha_user -p siksha_sarathi > ../siksha_sarathi_before_notice_system.sql
    mysql -u siksha_user -p siksha_sarathi < migrations/017_notice_system.sql

For a new database, `backend/setup_db.sql` includes both notice tables.

Run it after migration 014:

    sudo mysql siksha_sarathi < migrations/015_ml_prediction_monitoring.sql

The table keeps request metadata only. When no production artifact exists, the
system returns a no-model state and leaves any monitoring or retraining claim
empty; it does not create synthetic model health data.

## Room chat migration

Migration 018 adds normalized `chat_rooms` and `chat_messages` tables. Rooms
are created lazily from current class enrollments and teacher assignments;
membership is never copied into a manually managed member list. Class and
subject room access is rechecked for every list, history, and send request, so
transfers and teacher changes revoke access while preserving old messages.
Admins may inspect all school rooms. The single Staff Room is available only to
Admins and Teachers. Chat messages are immutable plain text, and the REST API
returns paginated history. The frontend polls only the active room every four
seconds. This is conversational Chat, separate from both Notices and the AI
assistant's `chat_history`.

Back up the database, stop the backend, and then apply migration 018:

    sudo mysqldump siksha_sarathi > ../siksha_sarathi_before_chat_system.sql
    sudo mysql siksha_sarathi < migrations/018_chat_system.sql

For new databases, `backend/setup_db.sql` includes both Chat tables. The
migration only creates Chat structures; it does not modify enrollment,
teacher-assignment, Attendance, Notice, or AI chat-history data.

## Learning Material attachment migration

Migration 019 adds nullable class and Student targeting to `notes` and creates
`note_attachments`. Existing Notes remain unchanged with NULL targets; the
migration does not infer historical classes or remove content. Target foreign
keys use `ON DELETE RESTRICT` so removing a class or Student cannot silently
widen a material's audience. Attachment metadata cascades when its Note is
deleted; file bytes remain in the private backend upload directory and are
removed by the application.

The default private file root is the ignored repository-level
`uploads/learning_materials` directory. Set `LEARNING_MATERIAL_UPLOAD_DIR` to
an absolute path or a path relative to the repository root to choose another
private location. Flask does not serve this directory as static content; file
downloads always go through authenticated, object-authorized API routes.

After migration 018, back up the database, stop the backend, then apply
migration 019 manually from the repository root:

    sudo mysqldump siksha_sarathi > backups/siksha_sarathi_before_019_$(date +%Y%m%d_%H%M%S).sql
    sudo mysql siksha_sarathi < backend/migrations/019_learning_material_attachments.sql

Do not run the migration automatically from the application or unit tests. For
new databases, `backend/setup_db.sql` includes the target columns and attachment
table.

## Teacher Question Bank migration

Migration 020 creates normalized `question_bank_questions` and
`question_bank_options` tables for reusable Teacher-owned questions. It adds no
foreign key from Quizzes to the bank: adding a bank question to a Quiz copies a
snapshot into the existing Quiz JSON, so later bank edits or deletion do not
change saved Quizzes or attempt history. Teacher access is limited to currently
assigned Subjects. The unique Teacher/Subject/question-hash key prevents
normalized duplicate questions.

After reviewing and backing up the database, stop the backend before applying
migration 020:

    sudo mysqldump siksha_sarathi > backups/siksha_sarathi_before_020_$(date +%Y%m%d_%H%M%S).sql
    sudo mysql siksha_sarathi < backend/migrations/020_question_bank.sql

Do not apply this migration from the application or unit tests. For new
databases, `backend/setup_db.sql` includes both Question Bank tables.

## Quiz Result Timestamp Migration

Migration 021 adds `quiz_results.created_at` only when it is missing. Fresh
databases already contain this field in `backend/setup_db.sql`. It is safe to
run against older databases because it checks `information_schema` before
`ALTER TABLE`.

    sudo mysql siksha_sarathi < backend/migrations/021_quiz_result_timestamps.sql

## User Account Status Migration

Migration 022 adds `users.is_active` with a default of TRUE and nullable
`users.deactivated_at`. Existing accounts stay active; no user or historical
school data is deleted or rewritten. The migration checks `INFORMATION_SCHEMA`
before adding either column or the `(role, is_active)` index, so it is safe to
rerun after success. New databases include these fields and index in
`backend/setup_db.sql`.

After backing up the database and stopping the backend, apply manually:

    sudo mysql siksha_sarathi < backend/migrations/022_user_account_status.sql
