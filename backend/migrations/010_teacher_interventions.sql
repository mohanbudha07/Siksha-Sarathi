-- Track the support actions teachers take after reviewing learning evidence.

CREATE TABLE IF NOT EXISTS teacher_interventions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    teacher_user_id INT NOT NULL,
    student_id INT NOT NULL,
    subject VARCHAR(100) NOT NULL,
    source_kind VARCHAR(30) NOT NULL DEFAULT 'manual',
    focus_area VARCHAR(150) NOT NULL,
    evidence VARCHAR(500) NOT NULL DEFAULT '',
    action_plan TEXT NOT NULL,
    success_criteria VARCHAR(500) NOT NULL DEFAULT '',
    status VARCHAR(30) NOT NULL DEFAULT 'planned',
    review_date DATE NULL,
    outcome_note VARCHAR(1000) NOT NULL DEFAULT '',
    completed_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_intervention_teacher_student
        (teacher_user_id, student_id, subject, status),
    INDEX idx_intervention_student_status (student_id, status),
    CONSTRAINT fk_intervention_teacher
        FOREIGN KEY (teacher_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_intervention_student
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT chk_intervention_source
        CHECK (source_kind IN ('topic', 'paper', 'attendance', 'manual')),
    CONSTRAINT chk_intervention_status
        CHECK (status IN ('planned', 'in_progress', 'completed', 'cancelled'))
);

SELECT COUNT(*) AS teacher_interventions FROM teacher_interventions;
