"""Create ten clearly labeled Grade 10 demo students for local UI testing.

Run from the repository root with the project's virtual environment active:
    python backend/scripts/seed_demo_students.py

This script adds no quiz answers, exam marks, attendance or ML predictions.
"""

import getpass
import os
from pathlib import Path

import MySQLdb
import MySQLdb.cursors
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash


TEACHER_EMAIL = "mohanbudha521@gmail.com"
SUBJECT = "Science"
DEMO_DOMAIN = "example.invalid"


def main():
    repository_root = Path(__file__).resolve().parents[2]
    load_dotenv(repository_root / ".env")
    connection = MySQLdb.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER", "siksha_user"),
        passwd=os.getenv("MYSQL_PASSWORD", ""),
        db=os.getenv("MYSQL_DB", "siksha_sarathi"),
        charset="utf8mb4",
        cursorclass=MySQLdb.cursors.DictCursor,
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT DISTINCT c.id, c.name, c.grade
                   FROM users u
                   JOIN teacher_class_subjects tcs ON tcs.teacher_user_id = u.id
                   JOIN classes c ON c.id = tcs.class_id
                   WHERE u.email = %s AND u.role = 'teacher'
                     AND LOWER(tcs.subject) = LOWER(%s) AND c.grade = '10'""",
                (TEACHER_EMAIL, SUBJECT),
            )
            assigned_classes = cursor.fetchall()
            if len(assigned_classes) != 1:
                raise RuntimeError(
                    "Expected one Grade 10 Science class assigned to Mohan; "
                    f"found {len(assigned_classes)}. No records were added."
                )

            assigned_class = assigned_classes[0]
            new_students = []
            existing_students = []

            for number in range(1, 11):
                name = f"Demo Student {number:02d}"
                email = f"siksha.demo{number:02d}@{DEMO_DOMAIN}"
                cursor.execute(
                    """SELECT u.id, u.username, u.role, s.id AS student_id,
                              s.full_name, s.grade
                       FROM users u LEFT JOIN students s ON s.user_id = u.id
                       WHERE u.email = %s""",
                    (email,),
                )
                existing = cursor.fetchone()
                if existing:
                    if (existing["role"] != "student"
                            or existing["username"] != name
                            or existing["full_name"] != name
                            or existing["grade"] != assigned_class["grade"]):
                        raise RuntimeError(
                            f"{email} already belongs to another record; "
                            "no records were added."
                        )
                    existing_students.append((existing["student_id"], email))
                else:
                    new_students.append((name, email))

            if not new_students:
                print("All 10 demo students already exist; no passwords were changed.")
            else:
                password = getpass.getpass(
                    "Choose a password for the new demo accounts (at least 8 characters): "
                )
                if len(password) < 8:
                    raise ValueError("Password must have at least 8 characters; nothing was saved.")

                for name, email in new_students:
                    cursor.execute(
                        """INSERT INTO users (username, email, password, role)
                           VALUES (%s, %s, %s, 'student')""",
                        (name, email, generate_password_hash(password)),
                    )
                    user_id = cursor.lastrowid
                    cursor.execute(
                        """INSERT INTO students (user_id, full_name, grade)
                           VALUES (%s, %s, %s)""",
                        (user_id, name, assigned_class["grade"]),
                    )
                    existing_students.append((cursor.lastrowid, email))

            for student_id, _ in existing_students:
                cursor.execute(
                    """INSERT IGNORE INTO student_class_enrollments
                       (student_id, class_id) VALUES (%s, %s)""",
                    (student_id, assigned_class["id"]),
                )

            connection.commit()
            print(
                f"{len(new_students)} created; {10 - len(new_students)} already existed. "
                f"All 10 enrolled in {assigned_class['name']} (Science)."
            )
            print(f"Login emails: siksha.demo01@{DEMO_DOMAIN} through siksha.demo10@{DEMO_DOMAIN}")
            print("No demo exam marks, quiz answers or attendance were added.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
