-- Run against the existing siksha_sarathi database before starting the updated app.
-- Re-runnable. Existing quiz attempts are preserved; detailed tracking starts
-- with submissions made after this migration.
USE siksha_sarathi;

CREATE TABLE IF NOT EXISTS quiz_answer_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    quiz_result_id INT NOT NULL,
    question_index INT NOT NULL,
    question_text TEXT NOT NULL,
    topic VARCHAR(100) NOT NULL,
    difficulty VARCHAR(20) NOT NULL,
    selected_answer TEXT NULL,
    correct_answer TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL DEFAULT FALSE,
    is_skipped BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_quiz_result_question (quiz_result_id, question_index),
    CONSTRAINT fk_quiz_answer_result_attempt
        FOREIGN KEY (quiz_result_id)
        REFERENCES quiz_results(id)
        ON DELETE CASCADE
);
