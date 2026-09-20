-- Replace daily data entry with monthly totals copied from the paper register.
-- Existing daily records are summarized by calendar month before the app switches.

CREATE TABLE IF NOT EXISTS monthly_attendance_summaries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    teacher_user_id INT NOT NULL,
    class_id INT NOT NULL,
    attendance_month DATE NOT NULL,
    total_school_days INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_monthly_class_attendance (class_id, attendance_month),
    INDEX idx_monthly_attendance_class_month (class_id, attendance_month),
    CONSTRAINT fk_monthly_attendance_teacher
        FOREIGN KEY (teacher_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_monthly_attendance_class
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT chk_monthly_total_days CHECK (total_school_days BETWEEN 1 AND 31)
);

CREATE TABLE IF NOT EXISTS monthly_attendance_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    summary_id INT NOT NULL,
    student_id INT NOT NULL,
    present_days INT NOT NULL,
    note VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_monthly_attendance_student (summary_id, student_id),
    CONSTRAINT fk_monthly_attendance_summary
        FOREIGN KEY (summary_id) REFERENCES monthly_attendance_summaries(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_monthly_attendance_student
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT chk_monthly_present_days CHECK (present_days BETWEEN 0 AND 31)
);

-- Preserve daily attendance already entered. A late day counts as attended.
INSERT IGNORE INTO monthly_attendance_summaries
    (teacher_user_id, class_id, attendance_month, total_school_days)
SELECT MIN(teacher_user_id), class_id,
       DATE_SUB(MIN(attendance_date), INTERVAL DAYOFMONTH(MIN(attendance_date)) - 1 DAY),
       COUNT(DISTINCT attendance_date)
FROM attendance_sessions
GROUP BY class_id, YEAR(attendance_date), MONTH(attendance_date);

INSERT INTO monthly_attendance_records (summary_id, student_id, present_days, note)
SELECT mas.id, ar.student_id,
       SUM(CASE WHEN ar.status IN ('present', 'late') THEN 1 ELSE 0 END),
       'Converted from existing daily attendance'
FROM monthly_attendance_summaries mas
INNER JOIN attendance_sessions ats
    ON ats.class_id = mas.class_id
   AND YEAR(ats.attendance_date) = YEAR(mas.attendance_month)
   AND MONTH(ats.attendance_date) = MONTH(mas.attendance_month)
INNER JOIN attendance_records ar ON ar.attendance_session_id = ats.id
GROUP BY mas.id, ar.student_id
ON DUPLICATE KEY UPDATE present_days = VALUES(present_days);

SELECT COUNT(*) AS monthly_attendance_summaries FROM monthly_attendance_summaries;
SELECT COUNT(*) AS monthly_attendance_records FROM monthly_attendance_records;
