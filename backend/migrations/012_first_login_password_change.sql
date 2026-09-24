-- Require school-issued accounts to choose a personal password on first login.
-- Existing accounts remain usable because the default is FALSE.
USE siksha_sarathi;

SET @has_must_change_password = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'users'
      AND column_name = 'must_change_password'
);
SET @migration_sql = IF(
    @has_must_change_password = 0,
    'ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT FALSE AFTER role',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;