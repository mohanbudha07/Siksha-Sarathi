-- Add evidence snapshots used to compare student progress after a support plan.
-- Deltas describe change over time; they do not prove the plan caused the change.

ALTER TABLE teacher_interventions
    ADD COLUMN baseline_quiz_accuracy DECIMAL(6,2) NULL AFTER outcome_note,
    ADD COLUMN baseline_quiz_questions INT NOT NULL DEFAULT 0
        AFTER baseline_quiz_accuracy,
    ADD COLUMN baseline_paper_average DECIMAL(6,2) NULL
        AFTER baseline_quiz_questions,
    ADD COLUMN baseline_paper_assessments INT NOT NULL DEFAULT 0
        AFTER baseline_paper_average,
    ADD COLUMN baseline_attendance_percent DECIMAL(6,2) NULL
        AFTER baseline_paper_assessments,
    ADD COLUMN baseline_attendance_days INT NOT NULL DEFAULT 0
        AFTER baseline_attendance_percent,
    ADD COLUMN baseline_captured_at TIMESTAMP NULL
        AFTER baseline_attendance_days;

SELECT COUNT(*) AS plans_with_baseline
FROM teacher_interventions
WHERE baseline_captured_at IS NOT NULL;
