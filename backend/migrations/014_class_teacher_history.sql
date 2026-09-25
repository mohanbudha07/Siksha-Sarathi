-- Preserve class-teacher responsibility history and support one active row per class.
-- Run after 013_subject_catalog.sql. Existing rows are never deleted.

USE siksha_sarathi;

DROP PROCEDURE IF EXISTS migrate_class_teacher_history;
DELIMITER //
CREATE PROCEDURE migrate_class_teacher_history()
main: BEGIN
    DECLARE table_exists INT DEFAULT 0;
    DECLARE has_academic_year INT DEFAULT 0;
    DECLARE has_started_at INT DEFAULT 0;
    DECLARE has_ended_at INT DEFAULT 0;
    DECLARE has_active_class_column INT DEFAULT 0;
    DECLARE has_active_teacher_column INT DEFAULT 0;
    DECLARE active_class_extra VARCHAR(100) DEFAULT '';
    DECLARE active_teacher_extra VARCHAR(100) DEFAULT '';
    DECLARE has_active_class_unique INT DEFAULT 0;
    DECLARE has_active_teacher_unique INT DEFAULT 0;
    DECLARE active_conflicts INT DEFAULT 0;
    DECLARE has_legacy_unique INT DEFAULT 0;
    DECLARE has_status_index INT DEFAULT 0;
    DECLARE has_teacher_index INT DEFAULT 0;

    SELECT COUNT(*) INTO table_exists
    FROM information_schema.tables
    WHERE table_schema = DATABASE()
      AND table_name = 'class_teacher_assignments';

    IF table_exists = 0 THEN
        CREATE TABLE class_teacher_assignments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            teacher_user_id INT NOT NULL,
            class_id INT NOT NULL,
            academic_year VARCHAR(20) NULL,
            started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ended_at DATETIME NULL,
            active_class_id INT GENERATED ALWAYS AS
              (CASE WHEN ended_at IS NULL THEN class_id ELSE NULL END) VIRTUAL,
            active_teacher_user_id INT GENERATED ALWAYS AS
              (CASE WHEN ended_at IS NULL THEN teacher_user_id ELSE NULL END) VIRTUAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_class_teacher_class_status (class_id, ended_at),
            INDEX idx_teacher_class_teacher_current (teacher_user_id, ended_at),
            UNIQUE KEY uq_class_teacher_active_class (active_class_id),
            UNIQUE KEY uq_class_teacher_active_teacher (active_teacher_user_id),
            CONSTRAINT fk_class_teacher_teacher
                FOREIGN KEY (teacher_user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_class_teacher_class
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        );
    ELSE
        SELECT COUNT(*) INTO has_academic_year
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'class_teacher_assignments'
          AND column_name = 'academic_year';
        IF has_academic_year = 0 THEN
            ALTER TABLE class_teacher_assignments
                ADD COLUMN academic_year VARCHAR(20) NULL AFTER class_id;
        END IF;

        SELECT COUNT(*) INTO has_started_at
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'class_teacher_assignments'
          AND column_name = 'started_at';
        IF has_started_at = 0 THEN
            ALTER TABLE class_teacher_assignments
                ADD COLUMN started_at DATETIME NULL AFTER academic_year;
        END IF;

        SELECT COUNT(*) INTO has_ended_at
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'class_teacher_assignments'
          AND column_name = 'ended_at';
        IF has_ended_at = 0 THEN
            ALTER TABLE class_teacher_assignments
                ADD COLUMN ended_at DATETIME NULL AFTER started_at;
        END IF;

        UPDATE class_teacher_assignments
        SET started_at = COALESCE(created_at, CURRENT_TIMESTAMP)
        WHERE started_at IS NULL;

        ALTER TABLE class_teacher_assignments
            MODIFY COLUMN started_at DATETIME NOT NULL;

        SELECT COUNT(*) INTO active_conflicts
        FROM (
          SELECT class_id AS conflict_key
          FROM class_teacher_assignments
          WHERE ended_at IS NULL
          GROUP BY class_id
          HAVING COUNT(*) > 1
          UNION ALL
          SELECT teacher_user_id AS conflict_key
          FROM class_teacher_assignments
          WHERE ended_at IS NULL
          GROUP BY teacher_user_id
          HAVING COUNT(*) > 1
        ) AS conflicts;
        IF active_conflicts > 0 THEN
          SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Migration 014 aborted: active class-teacher assignments violate one-to-one rules';
        END IF;

        SELECT COUNT(*) INTO has_active_class_column
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'class_teacher_assignments'
          AND column_name = 'active_class_id';
        IF has_active_class_column = 0 THEN
          ALTER TABLE class_teacher_assignments
            ADD COLUMN active_class_id INT GENERATED ALWAYS AS
              (CASE WHEN ended_at IS NULL THEN class_id ELSE NULL END) VIRTUAL
            AFTER ended_at;
        ELSE
          SELECT extra INTO active_class_extra
          FROM information_schema.columns
          WHERE table_schema = DATABASE()
            AND table_name = 'class_teacher_assignments'
            AND column_name = 'active_class_id';
          IF UPPER(active_class_extra) NOT LIKE '%VIRTUAL GENERATED%' THEN
            ALTER TABLE class_teacher_assignments
              MODIFY COLUMN active_class_id INT GENERATED ALWAYS AS
                (CASE WHEN ended_at IS NULL THEN class_id ELSE NULL END) VIRTUAL;
          END IF;
        END IF;

        SELECT COUNT(*) INTO has_active_teacher_column
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'class_teacher_assignments'
          AND column_name = 'active_teacher_user_id';
        IF has_active_teacher_column = 0 THEN
          ALTER TABLE class_teacher_assignments
            ADD COLUMN active_teacher_user_id INT GENERATED ALWAYS AS
              (CASE WHEN ended_at IS NULL THEN teacher_user_id ELSE NULL END) VIRTUAL
            AFTER active_class_id;
        ELSE
          SELECT extra INTO active_teacher_extra
          FROM information_schema.columns
          WHERE table_schema = DATABASE()
            AND table_name = 'class_teacher_assignments'
            AND column_name = 'active_teacher_user_id';
          IF UPPER(active_teacher_extra) NOT LIKE '%VIRTUAL GENERATED%' THEN
            ALTER TABLE class_teacher_assignments
              MODIFY COLUMN active_teacher_user_id INT GENERATED ALWAYS AS
                (CASE WHEN ended_at IS NULL THEN teacher_user_id ELSE NULL END) VIRTUAL;
          END IF;
        END IF;

        SELECT COUNT(*) INTO has_active_class_unique
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'class_teacher_assignments'
          AND index_name = 'uq_class_teacher_active_class';
        IF has_active_class_unique = 0 THEN
          ALTER TABLE class_teacher_assignments
            ADD UNIQUE INDEX uq_class_teacher_active_class (active_class_id);
        END IF;

        SELECT COUNT(*) INTO has_active_teacher_unique
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'class_teacher_assignments'
          AND index_name = 'uq_class_teacher_active_teacher';
        IF has_active_teacher_unique = 0 THEN
          ALTER TABLE class_teacher_assignments
            ADD UNIQUE INDEX uq_class_teacher_active_teacher (active_teacher_user_id);
        END IF;

        SELECT COUNT(*) INTO has_status_index
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'class_teacher_assignments'
          AND index_name = 'idx_class_teacher_class_status';
        IF has_status_index = 0 THEN
            ALTER TABLE class_teacher_assignments
                ADD INDEX idx_class_teacher_class_status (class_id, ended_at);
        END IF;

        SELECT COUNT(*) INTO has_legacy_unique
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'class_teacher_assignments'
          AND index_name = 'uq_class_teacher_class';
        IF has_legacy_unique > 0 THEN
            ALTER TABLE class_teacher_assignments
                DROP INDEX uq_class_teacher_class;
        END IF;

        SELECT COUNT(*) INTO has_teacher_index
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'class_teacher_assignments'
          AND index_name = 'idx_teacher_class_teacher_current';
        IF has_teacher_index = 0 THEN
            ALTER TABLE class_teacher_assignments
                ADD INDEX idx_teacher_class_teacher_current (teacher_user_id, ended_at);
        END IF;
    END IF;
END//
DELIMITER ;

CALL migrate_class_teacher_history();
DROP PROCEDURE migrate_class_teacher_history;