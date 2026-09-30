-- Add reversible account status without deleting or rewriting any users.
-- Existing users remain active because the new column defaults to TRUE.

USE siksha_sarathi;

DROP PROCEDURE IF EXISTS migrate_user_account_status;
DELIMITER //
CREATE PROCEDURE migrate_user_account_status()
BEGIN
    DECLARE column_exists INT DEFAULT 0;
    DECLARE index_exists INT DEFAULT 0;

    SELECT COUNT(*) INTO column_exists
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'users'
      AND column_name = 'is_active';
    IF column_exists = 0 THEN
        ALTER TABLE users
            ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE
            AFTER must_change_password;
    END IF;

    SELECT COUNT(*) INTO column_exists
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'users'
      AND column_name = 'deactivated_at';
    IF column_exists = 0 THEN
        ALTER TABLE users
            ADD COLUMN deactivated_at DATETIME NULL
            AFTER is_active;
    END IF;

    SELECT COUNT(*) INTO index_exists
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'users'
      AND index_name = 'idx_users_role_active';
    IF index_exists = 0 THEN
        ALTER TABLE users
            ADD INDEX idx_users_role_active (role, is_active);
    END IF;
END//
DELIMITER ;

CALL migrate_user_account_status();
DROP PROCEDURE migrate_user_account_status;