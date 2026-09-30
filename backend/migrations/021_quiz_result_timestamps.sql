-- Add the missing quiz result timestamp to existing databases.
-- Fresh databases already include this column through setup_db.sql.

USE siksha_sarathi;

DROP PROCEDURE IF EXISTS migrate_quiz_result_timestamps;

DELIMITER //

CREATE PROCEDURE migrate_quiz_result_timestamps()
BEGIN
    DECLARE column_exists INT DEFAULT 0;

    SELECT COUNT(*)
    INTO column_exists
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'quiz_results'
      AND column_name = 'created_at';

    IF column_exists = 0 THEN
        ALTER TABLE quiz_results
            ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            AFTER quiz_session_id;
    END IF;
END//

DELIMITER ;

CALL migrate_quiz_result_timestamps();

DROP PROCEDURE migrate_quiz_result_timestamps;
