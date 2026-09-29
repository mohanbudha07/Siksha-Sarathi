-- Private Learning Material targeting and attachment metadata.
-- Existing Notes remain unscoped (NULL) and are not deleted or reclassified.

USE siksha_sarathi;

CREATE TABLE IF NOT EXISTS note_attachments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    note_id INT NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(64) NOT NULL,
    mime_type VARCHAR(255) NOT NULL,
    size_bytes BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_note_attachments_stored_filename (stored_filename),
    INDEX idx_note_attachments_note_id (note_id),
    CONSTRAINT fk_note_attachments_note
        FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

DROP PROCEDURE IF EXISTS add_learning_material_targeting;
DELIMITER $$
CREATE PROCEDURE add_learning_material_targeting()
BEGIN
    DECLARE object_exists INT DEFAULT 0;

    SELECT COUNT(*) INTO object_exists
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'notes'
      AND column_name = 'target_class_id';
    IF object_exists = 0 THEN
        ALTER TABLE notes ADD COLUMN target_class_id INT NULL AFTER chapter;
    END IF;

    SELECT COUNT(*) INTO object_exists
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'notes'
      AND column_name = 'target_student_id';
    IF object_exists = 0 THEN
        ALTER TABLE notes ADD COLUMN target_student_id INT NULL AFTER target_class_id;
    END IF;

    SELECT COUNT(*) INTO object_exists
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'notes'
      AND index_name = 'idx_notes_target_class';
    IF object_exists = 0 THEN
        ALTER TABLE notes ADD INDEX idx_notes_target_class (target_class_id);
    END IF;

    SELECT COUNT(*) INTO object_exists
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'notes'
      AND index_name = 'idx_notes_target_student';
    IF object_exists = 0 THEN
        ALTER TABLE notes ADD INDEX idx_notes_target_student (target_student_id);
    END IF;

    SELECT COUNT(*) INTO object_exists
    FROM information_schema.referential_constraints
    WHERE constraint_schema = DATABASE()
      AND table_name = 'notes'
      AND constraint_name = 'fk_notes_target_class';
    IF object_exists = 0 THEN
        ALTER TABLE notes
            ADD CONSTRAINT fk_notes_target_class
            FOREIGN KEY (target_class_id) REFERENCES classes(id) ON DELETE RESTRICT;
    END IF;

    SELECT COUNT(*) INTO object_exists
    FROM information_schema.referential_constraints
    WHERE constraint_schema = DATABASE()
      AND table_name = 'notes'
      AND constraint_name = 'fk_notes_target_student';
    IF object_exists = 0 THEN
        ALTER TABLE notes
            ADD CONSTRAINT fk_notes_target_student
            FOREIGN KEY (target_student_id) REFERENCES students(id) ON DELETE RESTRICT;
    END IF;

    SELECT COUNT(*) INTO object_exists
    FROM information_schema.table_constraints
    WHERE constraint_schema = DATABASE()
      AND table_name = 'notes'
      AND constraint_name = 'chk_notes_student_requires_class'
      AND constraint_type = 'CHECK';
    IF object_exists = 0 THEN
      ALTER TABLE notes
        ADD CONSTRAINT chk_notes_student_requires_class
        CHECK (target_student_id IS NULL OR target_class_id IS NOT NULL);
    END IF;
END$$
DELIMITER ;

CALL add_learning_material_targeting();
DROP PROCEDURE add_learning_material_targeting;