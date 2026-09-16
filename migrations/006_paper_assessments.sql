-- Adds teacher-managed paper assessments and per-student marks.
-- Run after migration 005 while the Flask backend is stopped.
USE siksha_sarathi;

CREATE TABLE IF NOT EXISTS paper_assessments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    teacher_user_id INT NOT NULL,
    class_id INT NOT NULL,
    subject VARCHAR(100) NOT NULL,
    title VARCHAR(150) NOT NULL,
    assessment_type VARCHAR(30) NOT NULL,
    assessment_date DATE NOT NULL,
    max_marks DECIMAL(7,2) NOT NULL,
    academic_year VARCHAR(20) NOT NULL DEFAULT '',
    term VARCHAR(50) NOT NULL DEFAULT '',
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_paper_assessments_class_subject
        (class_id, subject, assessment_date),
    CONSTRAINT fk_paper_assessments_teacher
        FOREIGN KEY (teacher_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_paper_assessments_class
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS paper_assessment_scores (
    id INT AUTO_INCREMENT PRIMARY KEY,
    assessment_id INT NOT NULL,
    student_id INT NOT NULL,
    marks_obtained DECIMAL(7,2) NULL,
    is_absent BOOLEAN NOT NULL DEFAULT FALSE,
    remarks VARCHAR(500) NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_paper_assessment_student (assessment_id, student_id),
    CONSTRAINT fk_paper_scores_assessment
        FOREIGN KEY (assessment_id) REFERENCES paper_assessments(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_paper_scores_student
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

SELECT COUNT(*) AS paper_assessments FROM paper_assessments;
SELECT COUNT(*) AS paper_assessment_scores FROM paper_assessment_scores;
