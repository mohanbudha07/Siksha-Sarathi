-- Replace free-text teacher assignment subjects with a school subject catalog.
-- Existing assignment values are preserved by the backfill before the old
-- column is removed.
USE siksha_sarathi;

DROP PROCEDURE IF EXISTS migrate_subject_catalog;
DELIMITER //
CREATE PROCEDURE migrate_subject_catalog()
main: BEGIN
    DECLARE has_subject_text INT DEFAULT 0;
    DECLARE has_subject_id INT DEFAULT 0;
    DECLARE has_subject_fk INT DEFAULT 0;
    DECLARE has_old_unique INT DEFAULT 0;
    DECLARE has_new_unique INT DEFAULT 0;
    DECLARE invalid_count INT DEFAULT 0;
    DECLARE missing_count INT DEFAULT 0;
    DECLARE duplicate_count INT DEFAULT 0;
    DECLARE subject_id_nullable VARCHAR(3) DEFAULT 'NO';

    SELECT COUNT(*) INTO has_subject_text
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'teacher_class_subjects'
      AND column_name = 'subject';

    SELECT COUNT(*) INTO has_subject_id
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'teacher_class_subjects'
      AND column_name = 'subject_id';

    -- This runs before any legacy index or column can be removed.
    IF has_subject_text = 1 THEN
        SELECT COUNT(*) INTO invalid_count
        FROM teacher_class_subjects
        WHERE subject IS NULL OR TRIM(subject) = '';
        IF invalid_count > 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Migration 013 aborted: teacher assignments contain NULL or blank subjects';
        END IF;

        SELECT COUNT(*) INTO duplicate_count
        FROM (
            SELECT teacher_user_id, class_id, TRIM(subject) AS normalized_subject
            FROM teacher_class_subjects
            GROUP BY teacher_user_id, class_id, TRIM(subject)
            HAVING COUNT(*) > 1
        ) AS duplicate_assignments;
        IF duplicate_count > 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Migration 013 aborted: normalized duplicate teacher/class/subject assignments exist';
        END IF;
    END IF;

    CREATE TABLE IF NOT EXISTS subjects (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        code VARCHAR(30) NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_subject_name (name),
        UNIQUE KEY uq_subject_code (code)
    );

    IF has_subject_id = 0 THEN
        ALTER TABLE teacher_class_subjects
            ADD COLUMN subject_id INT NULL AFTER class_id;
    END IF;

    IF has_subject_text = 1 THEN
        INSERT INTO subjects (name)
        SELECT DISTINCT TRIM(tcs.subject)
        FROM teacher_class_subjects tcs
        WHERE tcs.subject IS NOT NULL AND TRIM(tcs.subject) <> ''
        ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(subjects.id);

        UPDATE teacher_class_subjects tcs
        INNER JOIN subjects s ON s.name = TRIM(tcs.subject)
        SET tcs.subject_id = s.id
        WHERE tcs.subject_id IS NULL;
    END IF;

    SELECT COUNT(*) INTO missing_count
    FROM teacher_class_subjects
    WHERE subject_id IS NULL;
    IF missing_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Migration 013 aborted: one or more teacher assignments were not backfilled';
    END IF;

    SELECT COUNT(*) INTO duplicate_count
    FROM (
        SELECT teacher_user_id, class_id, subject_id
        FROM teacher_class_subjects
        GROUP BY teacher_user_id, class_id, subject_id
        HAVING COUNT(*) > 1
    ) AS duplicate_assignments;
    IF duplicate_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Migration 013 aborted: structured duplicate teacher assignments exist';
    END IF;

    SELECT COUNT(*) INTO has_subject_fk
    FROM information_schema.key_column_usage
    WHERE table_schema = DATABASE()
      AND table_name = 'teacher_class_subjects'
      AND column_name = 'subject_id'
      AND referenced_table_name = 'subjects';
    IF has_subject_fk = 0 THEN
        ALTER TABLE teacher_class_subjects
            ADD CONSTRAINT fk_teacher_assignment_subject
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE;
    END IF;

    SELECT COUNT(*) INTO has_new_unique
    FROM (
        SELECT index_name
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'teacher_class_subjects'
          AND index_name = 'uq_teacher_class_subject_id'
          AND non_unique = 0
        GROUP BY index_name
        HAVING COUNT(*) = 3
           AND GROUP_CONCAT(
               column_name ORDER BY seq_in_index SEPARATOR ','
           ) = 'teacher_user_id,class_id,subject_id'
    ) AS structured_indexes;
    IF has_new_unique = 0 THEN
        ALTER TABLE teacher_class_subjects
            ADD UNIQUE KEY uq_teacher_class_subject_id
                (teacher_user_id, class_id, subject_id);
    END IF;

    SELECT COUNT(*) INTO has_old_unique
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'teacher_class_subjects'
      AND index_name = 'uq_teacher_class_subject'
      AND column_name = 'subject';
    IF has_old_unique = 1 THEN
        ALTER TABLE teacher_class_subjects
            DROP INDEX uq_teacher_class_subject;
    END IF;

    IF has_subject_text = 1 THEN
        ALTER TABLE teacher_class_subjects DROP COLUMN subject;
    END IF;

    SELECT IS_NULLABLE INTO subject_id_nullable
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'teacher_class_subjects'
      AND column_name = 'subject_id';
    IF subject_id_nullable = 'YES' THEN
        ALTER TABLE teacher_class_subjects
            MODIFY COLUMN subject_id INT NOT NULL;
    END IF;
END//
DELIMITER ;

CALL migrate_subject_catalog();
DROP PROCEDURE migrate_subject_catalog;
