-- Adds curriculum-aware question snapshots and class-scoped computer-lab sessions.
-- Run after migration 004 while the Flask backend is stopped.
USE siksha_sarathi;

SET @schema_name = DATABASE();

SET @sql = IF(
    EXISTS(SELECT 1 FROM information_schema.columns
           WHERE table_schema=@schema_name AND table_name='quizzes'
             AND column_name='requires_session'),
    'SELECT 1',
    'ALTER TABLE quizzes ADD COLUMN requires_session BOOLEAN NOT NULL DEFAULT FALSE AFTER is_published'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS quiz_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    quiz_id INT NOT NULL,
    class_id INT NOT NULL,
    created_by INT NOT NULL,
    access_code_hash VARCHAR(255) NOT NULL,
    starts_at DATETIME NOT NULL,
    ends_at DATETIME NOT NULL,
    is_closed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_quiz_sessions_class_time (class_id, starts_at, ends_at),
    CONSTRAINT fk_quiz_sessions_quiz
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
    CONSTRAINT fk_quiz_sessions_class
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_quiz_sessions_teacher
        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE
);

SET @sql = IF(
    EXISTS(SELECT 1 FROM information_schema.columns
           WHERE table_schema=@schema_name AND table_name='quiz_results'
             AND column_name='quiz_session_id'),
    'SELECT 1',
    'ALTER TABLE quiz_results ADD COLUMN quiz_session_id INT NULL AFTER total_questions'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(SELECT 1 FROM information_schema.key_column_usage
           WHERE table_schema=@schema_name AND table_name='quiz_results'
             AND column_name='quiz_session_id' AND referenced_table_name='quiz_sessions'),
    'SELECT 1',
    'ALTER TABLE quiz_results ADD CONSTRAINT fk_quiz_results_session FOREIGN KEY (quiz_session_id) REFERENCES quiz_sessions(id) ON DELETE SET NULL'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(SELECT 1 FROM information_schema.statistics
           WHERE table_schema=@schema_name AND table_name='quiz_results'
             AND index_name='uq_quiz_session_student_attempt'),
    'SELECT 1',
    'CREATE UNIQUE INDEX uq_quiz_session_student_attempt ON quiz_results (quiz_session_id, student_id)'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(SELECT 1 FROM information_schema.columns
           WHERE table_schema=@schema_name AND table_name='quiz_answer_results'
             AND column_name='curriculum_code'),
    'SELECT 1',
    'ALTER TABLE quiz_answer_results ADD COLUMN curriculum_code VARCHAR(50) NOT NULL DEFAULT ''unspecified'' AFTER difficulty'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(SELECT 1 FROM information_schema.columns
           WHERE table_schema=@schema_name AND table_name='quiz_answer_results'
             AND column_name='cognitive_level'),
    'SELECT 1',
    'ALTER TABLE quiz_answer_results ADD COLUMN cognitive_level VARCHAR(30) NOT NULL DEFAULT ''unspecified'' AFTER curriculum_code'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SELECT COUNT(*) AS lab_quiz_sessions FROM quiz_sessions;
