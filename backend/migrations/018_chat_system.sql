-- Current-membership room chat. Apply after migration 017 and a verified backup.
-- No existing enrollment, assignment, notice, or AI chat rows are modified.

USE siksha_sarathi;

CREATE TABLE IF NOT EXISTS chat_rooms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    room_type ENUM('class', 'subject', 'staff') NOT NULL,
    class_id INT NULL,
    subject_id INT NULL,
    class_room_key INT GENERATED ALWAYS AS
        (CASE WHEN room_type = 'class' THEN class_id ELSE NULL END) VIRTUAL,
    subject_room_class_key INT GENERATED ALWAYS AS
        (CASE WHEN room_type = 'subject' THEN class_id ELSE NULL END) VIRTUAL,
    subject_room_subject_key INT GENERATED ALWAYS AS
        (CASE WHEN room_type = 'subject' THEN subject_id ELSE NULL END) VIRTUAL,
    staff_room_key TINYINT GENERATED ALWAYS AS
        (CASE WHEN room_type = 'staff' THEN 1 ELSE NULL END) VIRTUAL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_chat_class_room (class_room_key),
    UNIQUE KEY uq_chat_subject_room (subject_room_class_key, subject_room_subject_key),
    UNIQUE KEY uq_chat_staff_room (staff_room_key),
    INDEX idx_chat_rooms_class_subject (class_id, subject_id),
    CONSTRAINT chk_chat_room_scope CHECK (
        (room_type = 'class' AND class_id IS NOT NULL AND subject_id IS NULL)
        OR (room_type = 'subject' AND class_id IS NOT NULL AND subject_id IS NOT NULL)
        OR (room_type = 'staff' AND class_id IS NULL AND subject_id IS NULL)
    ),
    CONSTRAINT fk_chat_rooms_class
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE RESTRICT,
    CONSTRAINT fk_chat_rooms_subject
        FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    room_id INT NOT NULL,
    sender_user_id INT NOT NULL,
    message VARCHAR(2000) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_chat_messages_room_page (room_id, id),
    INDEX idx_chat_messages_sender (sender_user_id, id),
    CONSTRAINT fk_chat_messages_room
        FOREIGN KEY (room_id) REFERENCES chat_rooms(id) ON DELETE RESTRICT,
    CONSTRAINT fk_chat_messages_sender
        FOREIGN KEY (sender_user_id) REFERENCES users(id) ON DELETE RESTRICT
);
