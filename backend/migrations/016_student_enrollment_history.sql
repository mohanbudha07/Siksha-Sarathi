-- Student enrollment history migration
-- Preserve historical class memberships while enforcing one active enrollment per student.
-- Run after 015_ml_prediction_monitoring.sql and before using the app's current-class auth rules.

USE siksha_sarathi;

DROP PROCEDURE IF EXISTS migrate_student_enrollment_history;
DELIMITER //
CREATE PROCEDURE migrate_student_enrollment_history()
main: BEGIN
    DECLARE table_exists INT DEFAULT 0;
    DECLARE has_academic_year INT DEFAULT 0;
    DECLARE has_started_at INT DEFAULT 0;
    DECLARE has_ended_at INT DEFAULT 0;
    DECLARE has_transfer_note INT DEFAULT 0;
    DECLARE has_active_student_column INT DEFAULT 0;
    DECLARE has_legacy_unique INT DEFAULT 0;
    DECLARE has_active_unique INT DEFAULT 0;
    DECLARE has_status_index INT DEFAULT 0;

    SELECT COUNT(*) INTO table_exists
    FROM information_schema.tables
    WHERE table_schema = DATABASE()
      AND table_name = 'student_class_enrollments';

    IF table_exists = 0 THEN
        CREATE TABLE student_class_enrollments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT NOT NULL,
            class_id INT NOT NULL,
            academic_year VARCHAR(20) NULL,
            started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ended_at DATETIME NULL,
            transfer_note VARCHAR(255) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active_student_id INT GENERATED ALWAYS AS
                (CASE WHEN ended_at IS NULL THEN student_id ELSE NULL END) VIRTUAL,
            INDEX idx_student_enrollment_status (student_id, ended_at),
            INDEX idx_enrollment_class_status (class_id, ended_at),
            UNIQUE KEY uq_student_active_enrollment (active_student_id),
            CONSTRAINT fk_student_enrollment_student
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            CONSTRAINT fk_student_enrollment_class
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        );
    ELSE
        SELECT COUNT(*) INTO has_academic_year
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'student_class_enrollments'
          AND column_name = 'academic_year';
        IF has_academic_year = 0 THEN
            ALTER TABLE student_class_enrollments
                ADD COLUMN academic_year VARCHAR(20) NULL AFTER class_id;
        END IF;

        SELECT COUNT(*) INTO has_started_at
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'student_class_enrollments'
          AND column_name = 'started_at';
        IF has_started_at = 0 THEN
            ALTER TABLE student_class_enrollments
                ADD COLUMN started_at DATETIME NULL AFTER academic_year;
        END IF;

        SELECT COUNT(*) INTO has_ended_at
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'student_class_enrollments'
          AND column_name = 'ended_at';
        IF has_ended_at = 0 THEN
            ALTER TABLE student_class_enrollments
                ADD COLUMN ended_at DATETIME NULL AFTER started_at;
        END IF;

        SELECT COUNT(*) INTO has_transfer_note
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'student_class_enrollments'
          AND column_name = 'transfer_note';
        IF has_transfer_note = 0 THEN
            ALTER TABLE student_class_enrollments
                ADD COLUMN transfer_note VARCHAR(255) NULL AFTER ended_at;
        END IF;

        UPDATE student_class_enrollments
        SET started_at = COALESCE(started_at, created_at, CURRENT_TIMESTAMP)
        WHERE started_at IS NULL;

        ALTER TABLE student_class_enrollments
            MODIFY COLUMN started_at DATETIME NOT NULL;

        SELECT COUNT(*) INTO has_active_student_column
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'student_class_enrollments'
          AND column_name = 'active_student_id';
        IF has_active_student_column = 0 THEN
            ALTER TABLE student_class_enrollments
                ADD COLUMN active_student_id INT GENERATED ALWAYS AS
                    (CASE WHEN ended_at IS NULL THEN student_id ELSE NULL END) VIRTUAL
                AFTER transfer_note;
        END IF;

        SELECT COUNT(*) INTO has_status_index
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'student_class_enrollments'
          AND index_name = 'idx_student_enrollment_status';
        IF has_status_index = 0 THEN
            ALTER TABLE student_class_enrollments
                ADD INDEX idx_student_enrollment_status (student_id, ended_at);
        END IF;

        SELECT COUNT(*) INTO has_legacy_unique
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'student_class_enrollments'
          AND index_name = 'uq_student_class';
        IF has_legacy_unique > 0 THEN
            ALTER TABLE student_class_enrollments
                DROP INDEX uq_student_class;
        END IF;

        -- Legacy rows have no end date. Keep the latest active row per student
        -- and close older active rows at the next period's start time.
        DROP TEMPORARY TABLE IF EXISTS student_enrollment_backfill_ends;
        CREATE TEMPORARY TABLE student_enrollment_backfill_ends AS
            SELECT previous.id, MIN(next.started_at) AS ended_at
            FROM student_class_enrollments previous
            INNER JOIN student_class_enrollments next
                ON next.student_id = previous.student_id
               AND (
                    next.started_at > previous.started_at
                    OR (next.started_at = previous.started_at AND next.id > previous.id)
               )
               AND next.ended_at IS NULL
            WHERE previous.ended_at IS NULL
            GROUP BY previous.id;

          UPDATE student_class_enrollments older
          INNER JOIN student_enrollment_backfill_ends historical
            ON historical.id = older.id
          SET older.ended_at = historical.ended_at;
          DROP TEMPORARY TABLE student_enrollment_backfill_ends;

        SELECT COUNT(*) INTO has_active_unique
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'student_class_enrollments'
          AND index_name = 'uq_student_active_enrollment';
        IF has_active_unique = 0 THEN
            ALTER TABLE student_class_enrollments
                ADD UNIQUE INDEX uq_student_active_enrollment (active_student_id);
        END IF;
    END IF;
END//
DELIMITER ;

CALL migrate_student_enrollment_history();
DROP PROCEDURE migrate_student_enrollment_history;

-- Active enrollment now means: ended_at IS NULL.
-- Historical periods are preserved; only one row is active per student at any time.
