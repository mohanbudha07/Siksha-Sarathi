-- Run against the existing siksha_sarathi database before starting the updated app.
-- Re-runnable. Existing quizzes remain published and retain NULL ownership.
USE siksha_sarathi;

SET @has_created_by = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'quizzes'
      AND column_name = 'created_by'
);
SET @migration_sql = IF(
    @has_created_by = 0,
    'ALTER TABLE quizzes ADD COLUMN created_by INT NULL AFTER questions',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_is_published = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'quizzes'
      AND column_name = 'is_published'
);
SET @migration_sql = IF(
    @has_is_published = 0,
    'ALTER TABLE quizzes ADD COLUMN is_published BOOLEAN NOT NULL DEFAULT TRUE AFTER created_by',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_created_by_index = (
    SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'quizzes'
      AND index_name = 'idx_quizzes_created_by'
);
SET @migration_sql = IF(
    @has_created_by_index = 0,
    'CREATE INDEX idx_quizzes_created_by ON quizzes(created_by)',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_created_by_fk = (
    SELECT COUNT(*) FROM information_schema.key_column_usage
    WHERE table_schema = DATABASE()
      AND table_name = 'quizzes'
      AND column_name = 'created_by'
      AND referenced_table_name = 'users'
);
SET @migration_sql = IF(
    @has_created_by_fk = 0,
    'ALTER TABLE quizzes ADD CONSTRAINT fk_quizzes_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SELECT COUNT(*) AS legacy_quizzes_without_owner
FROM quizzes
WHERE created_by IS NULL;
