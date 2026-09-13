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

Both teacher and admin warning counts now use the latest prediction per student.
A student whose latest result is Good is not counted because of an older warning.

Run the regression tests with the backend environment activated:

```bash
python -m unittest discover -s tests -v
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
