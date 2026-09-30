-- Teacher-owned reusable Question Bank. Quiz JSON remains an independent snapshot.
-- This migration creates new structures only; it does not alter Quiz or attempt data.

USE siksha_sarathi;

CREATE TABLE IF NOT EXISTS question_bank_questions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    created_by INT NOT NULL,
    subject_id INT NOT NULL,
    question_text TEXT NOT NULL,
    question_hash CHAR(64) NOT NULL,
    topic VARCHAR(100) NOT NULL,
    difficulty VARCHAR(20) NOT NULL,
    curriculum_code VARCHAR(50) NOT NULL DEFAULT 'unspecified',
    cognitive_level VARCHAR(30) NOT NULL DEFAULT 'unspecified',
    correct_option_index TINYINT UNSIGNED NOT NULL,
    explanation TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_question_bank_owner_subject_hash (created_by, subject_id, question_hash),
    INDEX idx_question_bank_owner_subject (created_by, subject_id),
    INDEX idx_question_bank_subject_topic_difficulty (subject_id, topic, difficulty),
    INDEX idx_question_bank_updated_at (updated_at),
    CONSTRAINT fk_question_bank_creator
        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_question_bank_subject
        FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE RESTRICT,
    CONSTRAINT chk_question_bank_difficulty
        CHECK (difficulty IN ('easy', 'medium', 'hard')),
    CONSTRAINT chk_question_bank_cognitive_level
        CHECK (cognitive_level IN ('recall', 'understanding', 'application', 'higher_order', 'unspecified')),
    CONSTRAINT chk_question_bank_correct_option
        CHECK (correct_option_index BETWEEN 0 AND 5)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS question_bank_options (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    question_id BIGINT NOT NULL,
    option_index TINYINT UNSIGNED NOT NULL,
    option_text VARCHAR(1000) NOT NULL,
    UNIQUE KEY uq_question_bank_option_index (question_id, option_index),
    CONSTRAINT fk_question_bank_options_question
        FOREIGN KEY (question_id) REFERENCES question_bank_questions(id) ON DELETE CASCADE,
    CONSTRAINT chk_question_bank_option_index
        CHECK (option_index BETWEEN 0 AND 5)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;