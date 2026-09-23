-- Step 4F: teacher-entered daily class attendance.
-- Run after 006_paper_assessments.sql while the Flask backend is stopped.

CREATE TABLE IF NOT EXISTS class_teacher_assignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    teacher_user_id INT NOT NULL,
    class_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_class_teacher_class (class_id),
    CONSTRAINT fk_class_teacher_teacher
        FOREIGN KEY (teacher_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_class_teacher_class
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attendance_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    teacher_user_id INT NOT NULL,
    class_id INT NOT NULL,
    attendance_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_daily_class_attendance (class_id, attendance_date),
    INDEX idx_attendance_class_date (class_id, attendance_date),
    CONSTRAINT fk_attendance_sessions_teacher
        FOREIGN KEY (teacher_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_attendance_sessions_class
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attendance_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    attendance_session_id INT NOT NULL,
    student_id INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    note VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_attendance_session_student
        (attendance_session_id, student_id),
    CONSTRAINT fk_attendance_records_session
        FOREIGN KEY (attendance_session_id)
        REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_attendance_records_student
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

SELECT COUNT(*) AS class_teacher_assignments FROM class_teacher_assignments;
SELECT COUNT(*) AS attendance_sessions FROM attendance_sessions;
SELECT COUNT(*) AS attendance_records FROM attendance_records;
