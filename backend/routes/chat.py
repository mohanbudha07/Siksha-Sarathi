"""Current-membership room chat over authenticated REST endpoints."""

from flask import Blueprint, request, session
from flask_limiter.util import get_remote_address


MAX_MESSAGE_LENGTH = 2000
DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 100


def fetch_chat_user(cur, user_id):
    cur.execute(
        "SELECT id, role, must_change_password FROM users WHERE id = %s",
        (user_id,)
    )
    return cur.fetchone()


def room_lookup(cur, room_type, class_id=None, subject_id=None):
    if room_type == "staff":
        cur.execute("SELECT id FROM chat_rooms WHERE room_type = 'staff'")
    elif room_type == "class":
        cur.execute(
            "SELECT id FROM chat_rooms WHERE room_type = 'class' AND class_id = %s",
            (class_id,)
        )
    else:
        cur.execute(
            """SELECT id FROM chat_rooms
               WHERE room_type = 'subject' AND class_id = %s AND subject_id = %s""",
            (class_id, subject_id)
        )
    return cur.fetchone()


def ensure_room(cur, room_type, class_id=None, subject_id=None):
    existing = room_lookup(cur, room_type, class_id, subject_id)
    if existing:
        return int(existing["id"])
    try:
        cur.execute(
            """INSERT INTO chat_rooms (room_type, class_id, subject_id)
               VALUES (%s, %s, %s)""",
            (room_type, class_id, subject_id)
        )
        return int(cur.lastrowid)
    except Exception:
        existing = room_lookup(cur, room_type, class_id, subject_id)
        if existing:
            return int(existing["id"])
        raise


def authorized_room_specs(cur, role, user_id):
    specs = set()
    if role == "student":
        cur.execute(
            """SELECT sce.class_id
               FROM students s
               INNER JOIN student_class_enrollments sce
                 ON sce.student_id = s.id AND sce.ended_at IS NULL
               WHERE s.user_id = %s""",
            (user_id,)
        )
        class_ids = {int(row["class_id"]) for row in cur.fetchall()}
        for class_id in class_ids:
            specs.add(("class", class_id, None))
            cur.execute(
                """SELECT subject_id FROM chat_rooms
                   WHERE room_type = 'subject' AND class_id = %s
                   UNION
                   SELECT subject_id FROM teacher_class_subjects
                   WHERE class_id = %s""",
                (class_id, class_id)
            )
            specs.update(
                ("subject", class_id, int(row["subject_id"]))
                for row in cur.fetchall()
            )
    elif role == "teacher":
        cur.execute(
            """SELECT class_id FROM class_teacher_assignments
               WHERE teacher_user_id = %s AND ended_at IS NULL""",
            (user_id,)
        )
        specs.update(("class", int(row["class_id"]), None) for row in cur.fetchall())
        cur.execute(
            """SELECT class_id, subject_id FROM teacher_class_subjects
               WHERE teacher_user_id = %s""",
            (user_id,)
        )
        specs.update(
            ("subject", int(row["class_id"]), int(row["subject_id"]))
            for row in cur.fetchall()
        )
        specs.add(("staff", None, None))
    elif role == "admin":
        cur.execute("SELECT id FROM classes")
        specs.update(("class", int(row["id"]), None) for row in cur.fetchall())
        cur.execute("SELECT class_id, subject_id FROM teacher_class_subjects")
        specs.update(
            ("subject", int(row["class_id"]), int(row["subject_id"]))
            for row in cur.fetchall()
        )
        cur.execute(
            "SELECT room_type, class_id, subject_id FROM chat_rooms "
            "WHERE room_type = 'subject'"
        )
        specs.update(
            ("subject", int(row["class_id"]), int(row["subject_id"]))
            for row in cur.fetchall()
        )
        specs.add(("staff", None, None))
    return specs


def has_room_access(cur, user, room):
    role = user["role"]
    if role == "admin":
        return True
    if room["room_type"] == "staff":
        return role == "teacher"
    if role == "student":
        cur.execute(
            """SELECT 1 AS allowed
               FROM students s
               INNER JOIN student_class_enrollments sce
                 ON sce.student_id = s.id AND sce.ended_at IS NULL
               WHERE s.user_id = %s AND sce.class_id = %s
               LIMIT 1""",
            (user["id"], room["class_id"])
        )
        return cur.fetchone() is not None
    if role != "teacher":
        return False
    if room["room_type"] == "class":
        cur.execute(
            """SELECT 1 AS allowed FROM class_teacher_assignments
               WHERE teacher_user_id = %s AND class_id = %s AND ended_at IS NULL
               LIMIT 1""",
            (user["id"], room["class_id"])
        )
    else:
        cur.execute(
            """SELECT 1 AS allowed FROM teacher_class_subjects
               WHERE teacher_user_id = %s AND class_id = %s AND subject_id = %s
               LIMIT 1""",
            (user["id"], room["class_id"], room["subject_id"])
        )
    return cur.fetchone() is not None


def serialize_room(row):
    if row["room_type"] == "staff":
        name = "Staff Room"
        class_name = None
        subject_name = None
    else:
        class_name = f'{row["class_name"]} - Section {row["section"]}'
        subject_name = row.get("subject_name")
        name = class_name if row["room_type"] == "class" else f"{class_name} • {subject_name}"
    return {
        "id": int(row["id"]),
        "room_type": row["room_type"],
        "name": name,
        "class_id": row["class_id"],
        "class_name": class_name,
        "subject_id": row["subject_id"],
        "subject_name": subject_name,
    }


def serialize_message(row):
    return {
        "id": int(row["id"]),
        "message": row["message"],
        "created_at": row["created_at"],
        "sender": {
            "id": int(row["sender_id"]),
            "display_name": row["display_name"],
            "role": row["sender_role"],
        },
    }


def create_chat_blueprint(mysql, login_required, limiter):
    chat = Blueprint("chat", __name__)

    def get_user_or_response(cur):
        user = fetch_chat_user(cur, session["user_id"])
        if not user:
            session.clear()
            return None, ({"error": "Authentication required"}, 401)
        if bool(user["must_change_password"]):
            return None, ({"error": "Password change required before using this feature"}, 403)
        return user, None

    def user_rate_key():
        user_id = session.get("user_id")
        return f"chat-user:{user_id}" if user_id is not None else get_remote_address()

    @chat.get("/api/chat/rooms")
    @login_required
    def chat_rooms_api():
        cur = mysql.connection.cursor()
        try:
            user, error = get_user_or_response(cur)
            if error:
                return error
            specs = authorized_room_specs(cur, user["role"], int(user["id"]))
            for room_type, class_id, subject_id in specs:
                ensure_room(cur, room_type, class_id, subject_id)
            mysql.connection.commit()
            cur.execute(
                """SELECT cr.id, cr.room_type, cr.class_id, cr.subject_id,
                          c.name AS class_name, c.section, sub.name AS subject_name
                   FROM chat_rooms cr
                   LEFT JOIN classes c ON c.id = cr.class_id
                   LEFT JOIN subjects sub ON sub.id = cr.subject_id
                   ORDER BY CASE cr.room_type
                              WHEN 'class' THEN 1 WHEN 'subject' THEN 2 ELSE 3 END,
                            c.grade, c.section, sub.name"""
            )
            rooms = [
                serialize_room(row) for row in cur.fetchall()
                if has_room_access(cur, user, row)
            ]
            rooms.sort(key=lambda room: (
                {"class": 0, "subject": 1, "staff": 2}[room["room_type"]],
                room["name"].casefold()
            ))
            return {"rooms": rooms}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("Chat room list failed:", type(error).__name__)
            return {"error": "Unable to load chat rooms"}, 500
        finally:
            cur.close()

    @chat.get("/api/chat/rooms/<int:room_id>/messages")
    @login_required
    def chat_messages_api(room_id):
        try:
            limit = int(request.args.get("limit", DEFAULT_HISTORY_LIMIT))
            if limit < 1 or limit > MAX_HISTORY_LIMIT:
                raise ValueError
            before_id = request.args.get("before_id")
            if before_id is not None:
                before_id = int(before_id)
                if before_id < 1:
                    raise ValueError
        except (TypeError, ValueError):
            return {"error": "limit must be 1-100 and before_id must be positive"}, 400

        cur = mysql.connection.cursor()
        try:
            user, error = get_user_or_response(cur)
            if error:
                return error
            cur.execute(
                "SELECT id, room_type, class_id, subject_id FROM chat_rooms WHERE id = %s",
                (room_id,)
            )
            room = cur.fetchone()
            if not room or not has_room_access(cur, user, room):
                return {"error": "You do not have access to this room"}, 403

            if before_id is None:
                cur.execute(
                    """SELECT cm.id, cm.message, cm.created_at,
                              u.id AS sender_id, u.role AS sender_role,
                              COALESCE(NULLIF(s.full_name, ''), u.username) AS display_name
                       FROM chat_messages cm
                       INNER JOIN users u ON u.id = cm.sender_user_id
                       LEFT JOIN students s ON s.user_id = u.id
                       WHERE cm.room_id = %s
                       ORDER BY cm.id DESC LIMIT %s""",
                    (room_id, limit + 1)
                )
            else:
                cur.execute(
                    """SELECT cm.id, cm.message, cm.created_at,
                              u.id AS sender_id, u.role AS sender_role,
                              COALESCE(NULLIF(s.full_name, ''), u.username) AS display_name
                       FROM chat_messages cm
                       INNER JOIN users u ON u.id = cm.sender_user_id
                       LEFT JOIN students s ON s.user_id = u.id
                       WHERE cm.room_id = %s AND cm.id < %s
                       ORDER BY cm.id DESC LIMIT %s""",
                    (room_id, before_id, limit + 1)
                )
            rows = list(cur.fetchall())
            has_more = len(rows) > limit
            rows = list(reversed(rows[:limit]))
            messages = [serialize_message(row) for row in rows]
            return {
                "messages": messages,
                "limit": limit,
                "has_more": has_more,
                "next_before_id": messages[0]["id"] if has_more and messages else None,
            }, 200
        finally:
            cur.close()

    @chat.post("/api/chat/rooms/<int:room_id>/messages")
    @login_required
    @limiter.limit("30 per minute", key_func=user_rate_key)
    def send_chat_message_api(room_id):
        cur = mysql.connection.cursor()
        try:
            user, error = get_user_or_response(cur)
            if error:
                return error
            cur.execute(
                "SELECT id, room_type, class_id, subject_id FROM chat_rooms WHERE id = %s",
                (room_id,)
            )
            room = cur.fetchone()
            if not room or not has_room_access(cur, user, room):
                return {"error": "You do not have access to this room"}, 403

            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return {"error": "Message data is required"}, 400
            if "sender_id" in data or "sender_user_id" in data:
                return {"error": "Sender identity is derived from your session"}, 400
            message = data.get("message")
            if not isinstance(message, str) or not message.strip():
                return {"error": "Message cannot be blank"}, 400
            if len(message) > MAX_MESSAGE_LENGTH:
                return {"error": "Message must be at most 2000 characters"}, 400

            cur.execute(
                "INSERT INTO chat_messages (room_id, sender_user_id, message) "
                "VALUES (%s, %s, %s)",
                (room_id, user["id"], message.strip())
            )
            message_id = int(cur.lastrowid)
            cur.execute(
                """SELECT cm.id, cm.message, cm.created_at,
                          u.id AS sender_id, u.role AS sender_role,
                          COALESCE(NULLIF(s.full_name, ''), u.username) AS display_name
                   FROM chat_messages cm
                   INNER JOIN users u ON u.id = cm.sender_user_id
                   LEFT JOIN students s ON s.user_id = u.id
                   WHERE cm.id = %s""",
                (message_id,)
            )
            message_row = cur.fetchone()
            mysql.connection.commit()
            return {"message": serialize_message(message_row)}, 201
        except Exception as error:
            mysql.connection.rollback()
            print("Chat message send failed:", type(error).__name__)
            return {"error": "Unable to send message"}, 500
        finally:
            cur.close()

    return chat
