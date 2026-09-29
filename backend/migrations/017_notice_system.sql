-- Official one-way notices with publication-time recipient snapshots.
-- Apply after migration 016 while the backend is stopped and after a backup.

USE siksha_sarathi;

CREATE TABLE IF NOT EXISTS notices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    created_by_user_id INT NOT NULL,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    visibility VARCHAR(20) NOT NULL DEFAULT 'internal',
    audience_type VARCHAR(20) NOT NULL,
    target_class_id INT NULL,
    target_subject_id INT NULL,
    target_user_id INT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_notices_visibility_created (visibility, created_at),
    INDEX idx_notices_creator_created (created_by_user_id, created_at),
    CONSTRAINT fk_notices_creator
        FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_notices_target_class
        FOREIGN KEY (target_class_id) REFERENCES classes(id) ON DELETE RESTRICT,
    CONSTRAINT fk_notices_target_subject
        FOREIGN KEY (target_subject_id) REFERENCES subjects(id) ON DELETE RESTRICT,
    CONSTRAINT fk_notices_target_user
        FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT chk_notices_visibility
        CHECK (visibility IN ('internal', 'public')),
    CONSTRAINT chk_notices_audience
        CHECK (audience_type IN ('all', 'students', 'teachers', 'class', 'subject', 'student', 'teacher')),
    CONSTRAINT chk_notices_public_scope
        CHECK (visibility <> 'public' OR audience_type = 'all'),
    CONSTRAINT chk_notices_target_scope
        CHECK (
            (audience_type IN ('all', 'students', 'teachers')
                AND target_class_id IS NULL AND target_subject_id IS NULL
                AND target_user_id IS NULL)
            OR (audience_type = 'class'
                AND target_class_id IS NOT NULL AND target_subject_id IS NULL
                AND target_user_id IS NULL)
            OR (audience_type = 'subject'
                AND target_class_id IS NOT NULL AND target_subject_id IS NOT NULL
                AND target_user_id IS NULL)
            OR (audience_type IN ('student', 'teacher')
                AND target_class_id IS NULL AND target_subject_id IS NULL
                AND target_user_id IS NOT NULL)
        )
);

CREATE TABLE IF NOT EXISTS notice_recipients (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    notice_id INT NOT NULL,
    user_id INT NOT NULL,
    delivered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP NULL,
    UNIQUE KEY uq_notice_recipient (notice_id, user_id),
    INDEX idx_notice_recipients_user_read (user_id, read_at),
    INDEX idx_notice_recipients_notice (notice_id),
    CONSTRAINT fk_notice_recipients_notice
        FOREIGN KEY (notice_id) REFERENCES notices(id) ON DELETE CASCADE,
    CONSTRAINT fk_notice_recipients_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);