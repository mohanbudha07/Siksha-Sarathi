"""Admin-only CSV preview, import, export, and template endpoints."""

import csv
import io
import re

from flask import Blueprint, Response, request
from werkzeug.security import generate_password_hash


MAX_FILE_BYTES = 1_048_576
MAX_DATA_ROWS = 1000
EMAIL_PATTERN = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")

STUDENT_HEADERS = (
    "full_name", "email", "temporary_password", "grade", "section",
    "academic_year",
)
TEACHER_HEADERS = ("full_name", "email", "temporary_password")
ASSIGNMENT_HEADERS = ("teacher_email", "grade", "section", "subject_code")


class CSVInputError(ValueError):
    pass


def safe_csv_cell(value):
    text = "" if value is None else str(value)
    stripped = text.lstrip()
    if text.startswith(("\t", "\r")) or (stripped and stripped[0] in "=+-@"):
        return "'" + text
    return text


def csv_response(headers, rows, filename):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([safe_csv_cell(value) for value in row])
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


def read_csv_upload(upload, required_headers, allowed_headers):
    if upload is None or not upload.filename:
        raise CSVInputError("Choose a CSV file")
    if not upload.filename.lower().endswith(".csv"):
        raise CSVInputError("Only .csv files are accepted")
    raw = upload.stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise CSVInputError("CSV file must be 1 MB or smaller")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CSVInputError("CSV file must use UTF-8 encoding") from error
    if not text.strip():
        raise CSVInputError("CSV file is empty")

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        raw_headers = next(reader)
    except StopIteration as error:
        raise CSVInputError("CSV file has no header row") from error
    except csv.Error as error:
        raise CSVInputError("CSV header is malformed") from error

    headers = [header.strip().lower() for header in raw_headers]
    if not any(headers):
        raise CSVInputError("CSV file has no header row")
    if len(set(headers)) != len(headers):
        raise CSVInputError("CSV contains duplicate headers")
    missing = [header for header in required_headers if header not in headers]
    if missing:
        raise CSVInputError("Missing required header(s): " + ", ".join(missing))
    unknown = [header for header in headers if header not in allowed_headers]
    if unknown:
        raise CSVInputError("Unknown header(s): " + ", ".join(unknown))

    rows = []
    try:
        for values in reader:
            row_number = reader.line_num
            if not any(value.strip() for value in values):
                continue
            if len(rows) >= MAX_DATA_ROWS:
                raise CSVInputError("CSV file cannot contain more than 1000 data rows")
            errors = []
            if len(values) != len(headers):
                errors.append({
                    "field": "_row",
                    "message": f"Expected {len(headers)} columns but found {len(values)}"
                })
            normalized_values = values[:len(headers)] + [""] * max(
                0, len(headers) - len(values)
            )
            data = {
                header: value.strip()
                for header, value in zip(headers, normalized_values)
            }
            rows.append({"row_number": row_number, "data": data, "errors": errors})
    except csv.Error as error:
        raise CSVInputError(
            f"Malformed CSV near row {reader.line_num}: {error}"
        ) from error
    if not rows:
        raise CSVInputError("CSV file contains no data rows")
    return rows


def add_error(row, field, message):
    row["errors"].append({"field": field, "message": message})


def email_is_valid(email):
    return bool(EMAIL_PATTERN.fullmatch(email))


def validate_students(cur, rows):
    cur.execute("SELECT LOWER(email) AS email FROM users")
    existing_emails = {str(row["email"]).strip().lower() for row in cur.fetchall()}
    seen_emails = set()
    class_cache = {}

    for row in rows:
        data = row["data"]
        name = data.get("full_name", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("temporary_password", "")
        grade = data.get("grade", "").strip()
        section = data.get("section", "").strip()
        academic_year = data.get("academic_year", "").strip()
        row.update({"full_name": name, "email": email, "grade": grade,
                    "section": section})

        if not name:
            add_error(row, "full_name", "Full name is required")
        elif len(name) > 100:
            add_error(row, "full_name", "Full name must be at most 100 characters")
        if not email or not email_is_valid(email):
            add_error(row, "email", "Enter a valid email address")
        elif email in seen_emails:
            add_error(row, "email", "Duplicate email within this CSV")
        elif email in existing_emails:
            add_error(row, "email", "Email already exists")
        if email:
            seen_emails.add(email)
        if len(password) < 8:
            add_error(row, "temporary_password", "Password must contain at least 8 characters")
        if not grade:
            add_error(row, "grade", "Grade is required")
        elif len(grade) > 20:
            add_error(row, "grade", "Grade must be at most 20 characters")
        if not section:
            add_error(row, "section", "Section is required")
        elif len(section) > 50:
            add_error(row, "section", "Section must be at most 50 characters")
        if len(academic_year) > 20:
            add_error(row, "academic_year", "Academic year must be at most 20 characters")

        key = (grade, section)
        if grade and section and len(grade) <= 20 and len(section) <= 50:
            if key not in class_cache:
                cur.execute(
                    "SELECT id, name, grade FROM classes WHERE grade = %s AND section = %s",
                    key
                )
                class_cache[key] = cur.fetchone()
            class_row = class_cache[key]
            if not class_row:
                add_error(row, "section", f"Class Grade {grade} / Section {section} does not exist")
            else:
                row["_class_id"] = class_row["id"]
                row["_class_grade"] = class_row["grade"]
                row["class_name"] = class_row["name"]
        else:
            row["class_name"] = ""
        row["valid"] = not row["errors"]
    return rows


def validate_teachers(cur, rows):
    cur.execute("SELECT LOWER(email) AS email FROM users")
    existing_emails = {str(row["email"]).strip().lower() for row in cur.fetchall()}
    seen_emails = set()
    for row in rows:
        data = row["data"]
        name = data.get("full_name", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("temporary_password", "")
        row.update({"full_name": name, "email": email})
        if not name:
            add_error(row, "full_name", "Full name is required")
        elif len(name) > 100:
            add_error(row, "full_name", "Full name must be at most 100 characters")
        if not email or not email_is_valid(email):
            add_error(row, "email", "Enter a valid email address")
        elif email in seen_emails:
            add_error(row, "email", "Duplicate email within this CSV")
        elif email in existing_emails:
            add_error(row, "email", "Email already exists")
        if email:
            seen_emails.add(email)
        if len(password) < 8:
            add_error(row, "temporary_password", "Password must contain at least 8 characters")
        row["valid"] = not row["errors"]
    return rows


def validate_assignments(cur, rows):
    teacher_cache = {}
    class_cache = {}
    subject_cache = {}
    cur.execute("SELECT teacher_user_id, class_id, subject_id FROM teacher_class_subjects")
    existing_assignments = {
        (int(row["teacher_user_id"]), int(row["class_id"]), int(row["subject_id"]))
        for row in cur.fetchall()
    }
    seen_assignments = set()

    for row in rows:
        data = row["data"]
        email = data.get("teacher_email", "").strip().lower()
        grade = data.get("grade", "").strip()
        section = data.get("section", "").strip()
        code = data.get("subject_code", "").strip().upper()
        row.update({"teacher_email": email, "grade": grade,
                    "section": section, "subject_code": code})

        teacher_id = None
        if not email or not email_is_valid(email):
            add_error(row, "teacher_email", "Enter a valid teacher email")
        elif email not in teacher_cache:
            cur.execute(
                "SELECT id FROM users WHERE LOWER(email) = %s AND role = 'teacher'",
                (email,)
            )
            teacher_cache[email] = cur.fetchone()
        if email in teacher_cache and teacher_cache[email]:
            teacher_id = int(teacher_cache[email]["id"])
        elif email and email_is_valid(email):
            add_error(row, "teacher_email", "Teacher account not found")

        class_id = None
        class_key = (grade, section)
        if not grade:
            add_error(row, "grade", "Grade is required")
        if not section:
            add_error(row, "section", "Section is required")
        if grade and section:
            if class_key not in class_cache:
                cur.execute(
                    "SELECT id, name FROM classes WHERE grade = %s AND section = %s",
                    class_key
                )
                class_cache[class_key] = cur.fetchone()
            if not class_cache[class_key]:
                add_error(row, "section", f"Class Grade {grade} / Section {section} does not exist")
            else:
                class_id = int(class_cache[class_key]["id"])
                row["class_name"] = class_cache[class_key]["name"]

        subject_id = None
        if not code:
            add_error(row, "subject_code", "Subject code is required")
        elif code not in subject_cache:
            cur.execute("SELECT id, name FROM subjects WHERE UPPER(code) = %s", (code,))
            subject_cache[code] = cur.fetchone()
        if code in subject_cache and subject_cache[code]:
            subject_id = int(subject_cache[code]["id"])
            row["subject_name"] = subject_cache[code]["name"]
        elif code:
            add_error(row, "subject_code", "Subject code not found")

        if teacher_id and class_id and subject_id:
            assignment_key = (teacher_id, class_id, subject_id)
            if assignment_key in seen_assignments:
                add_error(row, "teacher_email", "Duplicate assignment within this CSV")
            elif assignment_key in existing_assignments:
                row["status"] = "Already exists"
            else:
                row["status"] = "Valid"
                row["_teacher_user_id"] = teacher_id
                row["_class_id"] = class_id
                row["_subject_id"] = subject_id
            seen_assignments.add(assignment_key)
        row["valid"] = not row["errors"]
        if row["errors"]:
            row["status"] = "Invalid"
    return rows


def preview_payload(rows):
    safe_rows = []
    for row in rows:
        safe_rows.append({
            key: value for key, value in row.items()
            if not key.startswith("_") and key != "data"
        })
    invalid_rows = sum(not row["valid"] for row in rows)
    return {
        "valid": invalid_rows == 0,
        "total_rows": len(rows),
        "valid_rows": len(rows) - invalid_rows,
        "invalid_rows": invalid_rows,
        "rows": safe_rows,
    }


def csv_input_error_response(error):
    return {"error": str(error), "errors": []}, 400


def create_csv_management_blueprint(mysql, login_required, role_required, admin_role):
    csv_management = Blueprint("csv_management", __name__)

    def load_rows(required_headers, allowed_headers):
        try:
            return read_csv_upload(
                request.files.get("file"), required_headers, allowed_headers
            ), None
        except CSVInputError as error:
            return None, error

    def run_preview(validator, required_headers, allowed_headers):
        rows, error = load_rows(required_headers, allowed_headers)
        if error:
            return csv_input_error_response(error)
        cur = mysql.connection.cursor()
        try:
            return preview_payload(validator(cur, rows)), 200
        except Exception as error:
            print("CSV preview error:", type(error).__name__)
            return {"error": "Unable to validate CSV data", "errors": []}, 500
        finally:
            cur.close()

    def run_import(validator, required_headers, allowed_headers, insert_rows,
                   count_key):
        rows, error = load_rows(required_headers, allowed_headers)
        if error:
            return csv_input_error_response(error)
        cur = mysql.connection.cursor()
        try:
            if hasattr(mysql.connection, "begin"):
                mysql.connection.begin()
            validated = validator(cur, rows)
            preview = preview_payload(validated)
            if not preview["valid"]:
                mysql.connection.rollback()
                return {"error": "CSV contains invalid rows", **preview}, 400
            count = insert_rows(cur, validated)
            mysql.connection.commit()
            return {count_key: count}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("CSV import failed; transaction rolled back:", type(error).__name__)
            return {
                "error": "Import failed; no rows were imported",
                "errors": [{
                    "row_number": getattr(error, "csv_row_number", None),
                    "field": "_row",
                    "message": "Database rejected this row; no rows were imported",
                }],
            }, 409
        finally:
            cur.close()

    @csv_management.get("/api/admin/csv/templates/students")
    @login_required
    @role_required(admin_role)
    def student_template_api():
        return csv_response(STUDENT_HEADERS, [], "student_template.csv")

    @csv_management.get("/api/admin/csv/templates/teachers")
    @login_required
    @role_required(admin_role)
    def teacher_template_api():
        return csv_response(TEACHER_HEADERS, [], "teacher_template.csv")

    @csv_management.get("/api/admin/csv/templates/teacher-assignments")
    @login_required
    @role_required(admin_role)
    def assignment_template_api():
        return csv_response(ASSIGNMENT_HEADERS, [], "teacher_assignment_template.csv")

    @csv_management.post("/api/admin/csv/students/preview")
    @login_required
    @role_required(admin_role)
    def preview_students_api():
        return run_preview(validate_students, STUDENT_HEADERS[:5], STUDENT_HEADERS)

    @csv_management.post("/api/admin/csv/students/import")
    @login_required
    @role_required(admin_role)
    def import_students_api():
        def insert(cur, rows):
            imported = 0
            for row in rows:
                try:
                    cur.execute(
                        """INSERT INTO users
                           (username, email, password, role, must_change_password)
                           VALUES (%s, %s, %s, 'student', TRUE)""",
                        (row["full_name"], row["email"],
                         generate_password_hash(row["data"]["temporary_password"]))
                    )
                    user_id = cur.lastrowid
                    cur.execute(
                        "INSERT INTO students (user_id, full_name, grade) VALUES (%s, %s, %s)",
                        (user_id, row["full_name"], row["_class_grade"])
                    )
                    student_id = cur.lastrowid
                    cur.execute(
                        """INSERT INTO student_class_enrollments
                           (student_id, class_id, academic_year, started_at)
                           VALUES (%s, %s, %s, CURRENT_TIMESTAMP)""",
                        (student_id, row["_class_id"],
                         row["data"].get("academic_year") or None)
                    )
                    imported += 1
                except Exception as error:
                    error.csv_row_number = row["row_number"]
                    raise
            return imported
        return run_import(
            validate_students, STUDENT_HEADERS[:5], STUDENT_HEADERS,
            insert, "imported_students"
        )

    @csv_management.get("/api/admin/csv/students/export")
    @login_required
    @role_required(admin_role)
    def export_students_api():
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT s.full_name, u.email, c.grade, c.section,
                          c.name AS class_name, sce.academic_year
                   FROM students s
                   INNER JOIN users u ON u.id = s.user_id
                   LEFT JOIN student_class_enrollments sce
                     ON sce.student_id = s.id AND sce.ended_at IS NULL
                   LEFT JOIN classes c ON c.id = sce.class_id
                   ORDER BY s.full_name, s.id"""
            )
            headers = ("full_name", "email", "grade", "section", "class_name", "academic_year")
            return csv_response(
                headers,
                [[row.get(key) or "" for key in headers] for row in cur.fetchall()],
                "students.csv"
            )
        finally:
            cur.close()

    @csv_management.post("/api/admin/csv/teachers/preview")
    @login_required
    @role_required(admin_role)
    def preview_teachers_api():
        return run_preview(validate_teachers, TEACHER_HEADERS, TEACHER_HEADERS)

    @csv_management.post("/api/admin/csv/teachers/import")
    @login_required
    @role_required(admin_role)
    def import_teachers_api():
        def insert(cur, rows):
            imported = 0
            for row in rows:
                try:
                    cur.execute(
                        """INSERT INTO users
                           (username, email, password, role, must_change_password)
                           VALUES (%s, %s, %s, 'teacher', TRUE)""",
                        (row["full_name"], row["email"],
                         generate_password_hash(row["data"]["temporary_password"]))
                    )
                    imported += 1
                except Exception as error:
                    error.csv_row_number = row["row_number"]
                    raise
            return imported
        return run_import(
            validate_teachers, TEACHER_HEADERS, TEACHER_HEADERS,
            insert, "imported_teachers"
        )

    @csv_management.get("/api/admin/csv/teachers/export")
    @login_required
    @role_required(admin_role)
    def export_teachers_api():
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT username AS full_name, email, created_at
                   FROM users WHERE role = 'teacher' ORDER BY username, id"""
            )
            headers = ("full_name", "email", "created_at")
            return csv_response(
                headers,
                [[row.get(key) or "" for key in headers] for row in cur.fetchall()],
                "teachers.csv"
            )
        finally:
            cur.close()

    @csv_management.post("/api/admin/csv/teacher-assignments/preview")
    @login_required
    @role_required(admin_role)
    def preview_assignments_api():
        return run_preview(validate_assignments, ASSIGNMENT_HEADERS, ASSIGNMENT_HEADERS)

    @csv_management.post("/api/admin/csv/teacher-assignments/import")
    @login_required
    @role_required(admin_role)
    def import_assignments_api():
        rows, error = load_rows(ASSIGNMENT_HEADERS, ASSIGNMENT_HEADERS)
        if error:
            return csv_input_error_response(error)
        cur = mysql.connection.cursor()
        try:
            if hasattr(mysql.connection, "begin"):
                mysql.connection.begin()
            validated = validate_assignments(cur, rows)
            preview = preview_payload(validated)
            if not preview["valid"]:
                mysql.connection.rollback()
                return {"error": "CSV contains invalid rows", **preview}, 400
            imported = 0
            skipped = 0
            for row in validated:
                if row.get("status") == "Already exists":
                    skipped += 1
                    continue
                try:
                    cur.execute(
                        """INSERT INTO teacher_class_subjects
                           (teacher_user_id, class_id, subject_id)
                           VALUES (%s, %s, %s)""",
                        (row["_teacher_user_id"], row["_class_id"], row["_subject_id"])
                    )
                    imported += 1
                except Exception as error:
                    error.csv_row_number = row["row_number"]
                    raise
            mysql.connection.commit()
            return {"imported_assignments": imported, "skipped_existing": skipped}, 200
        except Exception as error:
            mysql.connection.rollback()
            print("CSV assignment import failed; transaction rolled back:", type(error).__name__)
            return {
                "error": "Import failed; no assignments were imported",
                "errors": [{
                    "row_number": getattr(error, "csv_row_number", None),
                    "field": "_row",
                    "message": "Database rejected this row; no assignments were imported",
                }],
            }, 409
        finally:
            cur.close()

    @csv_management.get("/api/admin/csv/teacher-assignments/export")
    @login_required
    @role_required(admin_role)
    def export_assignments_api():
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT u.username AS teacher_name, u.email AS teacher_email,
                          c.grade, c.section, c.name AS class_name,
                          sub.name AS subject_name, sub.code AS subject_code
                   FROM teacher_class_subjects tcs
                   INNER JOIN users u ON u.id = tcs.teacher_user_id
                   INNER JOIN classes c ON c.id = tcs.class_id
                   INNER JOIN subjects sub ON sub.id = tcs.subject_id
                   ORDER BY c.grade, c.section, u.username, sub.name"""
            )
            headers = (
                "teacher_name", "teacher_email", "grade", "section",
                "class_name", "subject_name", "subject_code",
            )
            return csv_response(
                headers,
                [[row.get(key) or "" for key in headers] for row in cur.fetchall()],
                "teacher_assignments.csv"
            )
        finally:
            cur.close()

    return csv_management