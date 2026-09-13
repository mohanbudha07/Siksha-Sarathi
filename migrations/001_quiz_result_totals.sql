-- Run against the existing siksha_sarathi database before starting the updated app.
-- Re-runnable. Existing scores and attempts are preserved.
USE siksha_sarathi;

SET @has_total_questions = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'quiz_results'
      AND column_name = 'total_questions'
);
SET @migration_sql = IF(
    @has_total_questions = 0,
    'ALTER TABLE quiz_results ADD COLUMN total_questions INT NULL AFTER score',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- Historical totals are inferred from CURRENT quiz questions. If a quiz has
-- already changed, the original total cannot be reconstructed from this schema.
-- Invalid JSON, non-arrays, empty quizzes, and impossible scores stay NULL.
UPDATE quiz_results qr
INNER JOIN quizzes q ON q.id = qr.quiz_id
SET qr.total_questions = JSON_LENGTH(
    CASE WHEN JSON_VALID(q.questions) THEN q.questions ELSE 'null' END
)
WHERE qr.total_questions IS NULL
  AND JSON_TYPE(
      CASE WHEN JSON_VALID(q.questions) THEN q.questions ELSE 'null' END
  ) = 'ARRAY'
  AND JSON_LENGTH(
      CASE WHEN JSON_VALID(q.questions) THEN q.questions ELSE 'null' END
  ) > 0
  AND qr.score BETWEEN 0 AND JSON_LENGTH(
      CASE WHEN JSON_VALID(q.questions) THEN q.questions ELSE 'null' END
  );

-- These attempts still count as attempts, but are excluded from score averages.
SELECT COUNT(*) AS attempts_without_recoverable_total
FROM quiz_results
WHERE total_questions IS NULL;
