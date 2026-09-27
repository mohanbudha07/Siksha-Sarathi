-- Immutable audit table for production prediction requests.
-- This table records only actual request metadata and does not fabricate model health.
-- The application remains fail-closed when no production artifact exists.

USE siksha_sarathi;

DROP PROCEDURE IF EXISTS migrate_ml_prediction_monitoring;
DELIMITER //
CREATE PROCEDURE migrate_ml_prediction_monitoring()
main: BEGIN
    DECLARE table_exists INT DEFAULT 0;

    SELECT COUNT(*) INTO table_exists
    FROM information_schema.tables
    WHERE table_schema = DATABASE()
      AND table_name = 'ml_prediction_audits';

    IF table_exists = 0 THEN
        CREATE TABLE ml_prediction_audits (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            student_id INT NOT NULL,
            teacher_user_id INT NOT NULL,
            class_id INT NOT NULL,
            subject VARCHAR(100) NOT NULL,
            as_of_date DATE NOT NULL,
            prediction_status VARCHAR(40) NOT NULL DEFAULT 'model_unavailable',
            prediction_percent DECIMAL(5,2) NULL,
            fallback VARCHAR(50) NULL,
            reason VARCHAR(255) NULL,
            model_version VARCHAR(64) NOT NULL,
            model_type VARCHAR(64) NULL,
            artifact_version VARCHAR(64) NULL,
            feature_contract_version VARCHAR(32) NULL,
            validation_mae DECIMAL(10,4) NULL,
            model_training_timestamp DATETIME NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_ml_prediction_audit_identity (student_id, class_id, subject, as_of_date, model_version),
            INDEX idx_ml_prediction_audits_student_date (student_id, as_of_date),
            INDEX idx_ml_prediction_audits_status (prediction_status, as_of_date),
            INDEX idx_ml_prediction_audits_subject (subject, as_of_date),
            INDEX idx_ml_prediction_audits_model_version (model_version, model_training_timestamp),
            CONSTRAINT fk_ml_prediction_audits_student
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            CONSTRAINT fk_ml_prediction_audits_teacher
                FOREIGN KEY (teacher_user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_ml_prediction_audits_class
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        );
    ELSE
        SELECT COUNT(*) INTO table_exists
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'ml_prediction_audits'
          AND index_name = 'uq_ml_prediction_audit_identity';

        IF table_exists = 0 THEN
            ALTER TABLE ml_prediction_audits
            ADD CONSTRAINT uq_ml_prediction_audit_identity
            UNIQUE (student_id, class_id, subject, as_of_date, model_version);
        END IF;
    END IF;
    END IF;
END//
DELIMITER ;

CALL migrate_ml_prediction_monitoring();
DROP PROCEDURE migrate_ml_prediction_monitoring;

DROP TRIGGER IF EXISTS trg_ml_prediction_audits_no_update;
DROP TRIGGER IF EXISTS trg_ml_prediction_audits_no_delete;

DELIMITER //
CREATE TRIGGER trg_ml_prediction_audits_no_update
BEFORE UPDATE ON ml_prediction_audits
FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'ml_prediction_audits rows are immutable';
END//

CREATE TRIGGER trg_ml_prediction_audits_no_delete
BEFORE DELETE ON ml_prediction_audits
FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'ml_prediction_audits rows are immutable';
END//
DELIMITER ;
