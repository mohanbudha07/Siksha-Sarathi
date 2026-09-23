-- Step 8: protect student identity for admin-managed enrollment.
-- Run after checking the diagnostic query returns no rows.

SELECT user_id, COUNT(*) AS profile_count
FROM students
GROUP BY user_id
HAVING COUNT(*) > 1;

ALTER TABLE students
    ADD CONSTRAINT uq_students_user UNIQUE (user_id);

SELECT COUNT(*) AS classes FROM classes;
SELECT COUNT(*) AS enrolled_students FROM student_class_enrollments;
SELECT COUNT(*) AS teacher_subject_assignments FROM teacher_class_subjects;
