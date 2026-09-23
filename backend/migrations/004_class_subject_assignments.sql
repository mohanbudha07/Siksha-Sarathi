-- Run against the existing siksha_sarathi database before starting the updated app.
-- Re-runnable. Students are enrolled into grade-based default classes. Teachers
-- are deliberately not auto-assigned because subject responsibility must be explicit.
USE siksha_sarathi;

CREATE TABLE IF NOT EXISTS classes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    grade VARCHAR(20) NOT NULL,
    section VARCHAR(50) NOT NULL DEFAULT 'Default',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_class_grade_section (grade, section)
);

CREATE TABLE IF NOT EXISTS student_class_enrollments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    class_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_student_class (student_id, class_id),
    CONSTRAINT fk_enrollment_student
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_enrollment_class
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS teacher_class_subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    teacher_user_id INT NOT NULL,
    class_id INT NOT NULL,
    subject VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_teacher_class_subject (teacher_user_id, class_id, subject),
    CONSTRAINT fk_teacher_assignment_user
        FOREIGN KEY (teacher_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_teacher_assignment_class
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
);

INSERT INTO classes (name, grade, section)
SELECT DISTINCT
    CONCAT('Grade ', TRIM(grade)),
    TRIM(grade),
    'Default'
FROM students
WHERE grade IS NOT NULL
  AND TRIM(grade) <> ''
ON DUPLICATE KEY UPDATE name = VALUES(name);

INSERT IGNORE INTO student_class_enrollments (student_id, class_id)
SELECT s.id, c.id
FROM students s
INNER JOIN classes c
    ON c.grade = TRIM(s.grade)
   AND c.section = 'Default'
WHERE s.grade IS NOT NULL
  AND TRIM(s.grade) <> '';

SELECT id, name, grade, section
FROM classes
ORDER BY grade, section;

SELECT COUNT(*) AS enrolled_students
FROM student_class_enrollments;

SELECT COUNT(*) AS teacher_subject_assignments
FROM teacher_class_subjects;
