"""Teacher-owned Question Bank API."""

import csv
import io
import math

from flask import Blueprint, Response, request, session

from backend.question_bank import (
    CSV_COLUMNS,
    MAX_CSV_BYTES,
    MAX_CSV_ROWS,
    QuestionBankCsvError,
    parse_question_csv,
    question_snapshot,
    validate_question,
)
from backend.time_utils import serialize_nepal_datetime


PAGE_SIZES = frozenset({10, 25, 50, 100})


def _is_duplicate_key_error(error):
    return (
        getattr(error, "errno", None) == 1062
        or bool(error.args and error.args[0] == 1062)
        or "UNIQUE constraint failed" in str(error)
    )


def _positive_int(value, label):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a positive integer.") from None
    if number < 1:
        raise ValueError(f"{label} must be a positive integer.")
    return number


def _assignment_exists(cur, teacher_id, subject_id):
    cur.execute(
        """SELECT 1 FROM teacher_class_subjects
           WHERE teacher_user_id = %s AND subject_id = %s LIMIT 1""",
        (teacher_id, subject_id),
    )
    return cur.fetchone() is not None


def _subject_id(cur, teacher_id, raw_subject_id):
    subject_id = _positive_int(raw_subject_id, "Subject")
    if not _assignment_exists(cur, teacher_id, subject_id):
        raise PermissionError("You are not currently assigned to this subject.")
    return subject_id


def _question_rows(cur, question_ids):
    if not question_ids:
        return {}
    placeholders = ",".join(["%s"] * len(question_ids))
    cur.execute(
        f"""SELECT q.id, q.created_by, q.subject_id, s.name AS subject_name,
                   q.question_text, q.topic, q.difficulty, q.curriculum_code,
                   q.cognitive_level, q.correct_option_index, q.explanation,
                   q.created_at, q.updated_at
            FROM question_bank_questions q
            INNER JOIN subjects s ON s.id = q.subject_id
            WHERE q.id IN ({placeholders})""",
        tuple(question_ids),
    )
    rows = {row["id"]: row for row in cur.fetchall()}
    cur.execute(
        f"""SELECT question_id, option_index, option_text
            FROM question_bank_options
            WHERE question_id IN ({placeholders})
            ORDER BY question_id, option_index""",
        tuple(question_ids),
    )
    options = {question_id: [] for question_id in question_ids}
    for option in cur.fetchall():
        options[option["question_id"]].append(option["option_text"])
    for question_id, row in rows.items():
        row["options"] = options.get(question_id, [])
        row["created_at"] = serialize_nepal_datetime(row["created_at"])
        row["updated_at"] = serialize_nepal_datetime(row["updated_at"])
        row["correct_answer"] = (
            row["options"][row["correct_option_index"]]
            if row["correct_option_index"] < len(row["options"])
            else None
        )
    return rows


def _question_payload(row):
    return {
        "id": row["id"],
        "subject_id": row["subject_id"],
        "subject_name": row["subject_name"],
        "question": row["question_text"],
        "topic": row["topic"],
        "difficulty": row["difficulty"],
        "curriculum_code": row["curriculum_code"],
        "cognitive_level": row["cognitive_level"],
        "options": row["options"],
        "correct_option_index": row["correct_option_index"],
        "correct_answer": row["correct_answer"],
        "explanation": row["explanation"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _bank_duplicate_hashes(cur, teacher_id, subject_id, hashes):
    if not hashes:
        return set()
    placeholders = ",".join(["%s"] * len(hashes))
    cur.execute(
        f"""SELECT question_hash FROM question_bank_questions
            WHERE created_by = %s AND subject_id = %s
              AND question_hash IN ({placeholders})""",
        (teacher_id, subject_id, *hashes),
    )
    return {row["question_hash"] for row in cur.fetchall()}


def _csv_upload():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise ValueError("Choose a CSV file.")
    if upload.filename.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[-1].lower() != "csv":
        raise ValueError("Only .csv files are supported.")
    raw_bytes = upload.stream.read(MAX_CSV_BYTES + 1)
    if len(raw_bytes) > MAX_CSV_BYTES:
        raise QuestionBankCsvError("CSV file must be 5 MB or smaller.")
    return raw_bytes


def _validate_csv_for_teacher(cur, teacher_id, subject_id, raw_bytes):
    rows, errors, total_rows = parse_question_csv(raw_bytes)
    csv_hashes = [row["question"]["question_hash"] for row in rows]
    existing_hashes = _bank_duplicate_hashes(
        cur, teacher_id, subject_id, set(csv_hashes)
    )
    duplicate_hashes = set()
    seen = set()
    for row in rows:
        question = row["question"]
        digest = question["question_hash"]
        if digest in existing_hashes:
            errors.append({
                "row": row["row"], "field": "question",
                "message": "Question already exists in your bank for this subject.",
            })
            duplicate_hashes.add(digest)
        if digest in seen:
            duplicate_hashes.add(digest)
        seen.add(digest)
    duplicate_row_numbers = {
        error["row"] for error in errors
        if error["message"].startswith("Duplicate Question")
        or error["message"].startswith("Question already exists")
    }
    invalid_row_numbers = {
        error["row"] for error in errors if error["row"] > 1
    }
    valid_rows = [
        row for row in rows
        if row["row"] not in invalid_row_numbers
    ]
    return {
        "rows": valid_rows,
        "total_rows": total_rows,
        "valid_count": len(valid_rows),
        "invalid_count": len(invalid_row_numbers),
        "duplicate_count": len(duplicate_hashes),
        "errors": errors,
    }


def create_question_bank_blueprint(mysql, login_required, role_required, teacher_role):
    bank = Blueprint("question_bank", __name__)

    @bank.get("/api/teacher/question-bank/options")
    @login_required
    @role_required(teacher_role)
    def question_bank_options_api():
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT DISTINCT s.id, s.name, s.code
                   FROM teacher_class_subjects tcs
                   INNER JOIN subjects s ON s.id = tcs.subject_id
                   WHERE tcs.teacher_user_id = %s
                   ORDER BY s.name""",
                (session["user_id"],),
            )
            return {"subjects": cur.fetchall()}, 200
        finally:
            cur.close()

    @bank.get("/api/teacher/question-bank/template")
    @login_required
    @role_required(teacher_role)
    def question_bank_template_api():
        output = io.StringIO(newline="")
        csv.writer(output, lineterminator="\r\n").writerow(CSV_COLUMNS)
        response = Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8")
        response.headers["Content-Disposition"] = "attachment; filename=question_bank_template.csv"
        return response

    @bank.post("/api/teacher/question-bank/import/preview")
    @login_required
    @role_required(teacher_role)
    def question_bank_import_preview_api():
        cur = mysql.connection.cursor()
        try:
            try:
                subject_id = _subject_id(cur, session["user_id"], request.form.get("subject_id"))
                result = _validate_csv_for_teacher(
                    cur, session["user_id"], subject_id, _csv_upload()
                )
            except PermissionError as error:
                return {"error": str(error)}, 403
            except (ValueError, QuestionBankCsvError) as error:
                return {"error": str(error)}, 400
            errors = result["errors"]
            return {
                "total_rows": result["total_rows"],
                "valid_count": result["valid_count"],
                "invalid_count": result["invalid_count"],
                "duplicate_count": result["duplicate_count"],
                "can_import": not errors and result["total_rows"] > 0,
                "error_count": len(errors),
                "errors_truncated": len(errors) > 100,
                "errors": errors[:100],
                "row_numbering": "Header is row 1; data rows are numbered by CSV record, starting at row 2.",
                "valid_preview": [
                    {**row["question"], "question": row["question"]["question_text"]}
                    for row in result["rows"][:20]
                ],
                "max_rows": MAX_CSV_ROWS,
            }, 200
        finally:
            cur.close()

    @bank.post("/api/teacher/question-bank/import")
    @login_required
    @role_required(teacher_role)
    def question_bank_import_api():
        cur = mysql.connection.cursor()
        try:
            try:
                subject_id = _subject_id(cur, session["user_id"], request.form.get("subject_id"))
                result = _validate_csv_for_teacher(
                    cur, session["user_id"], subject_id, _csv_upload()
                )
            except PermissionError as error:
                return {"error": str(error)}, 403
            except (ValueError, QuestionBankCsvError) as error:
                return {"error": str(error)}, 400
            if result["errors"] or result["total_rows"] == 0:
                return {
                    "error": "CSV contains invalid or duplicate questions.",
                    "errors": result["errors"][:100],
                    "error_count": len(result["errors"]),
                    "errors_truncated": len(result["errors"]) > 100,
                }, 400
            for row in result["rows"]:
                question = row["question"]
                cur.execute(
                    """INSERT INTO question_bank_questions
                       (created_by, subject_id, question_text, question_hash,
                        topic, difficulty, curriculum_code, cognitive_level,
                        correct_option_index, explanation)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        session["user_id"], subject_id, question["question_text"],
                        question["question_hash"], question["topic"],
                        question["difficulty"], question["curriculum_code"],
                        question["cognitive_level"], question["correct_option_index"],
                        question["explanation"],
                    ),
                )
                question_id = cur.lastrowid
                for option_index, option_text in enumerate(question["options"]):
                    cur.execute(
                        """INSERT INTO question_bank_options
                           (question_id, option_index, option_text)
                           VALUES (%s, %s, %s)""",
                        (question_id, option_index, option_text),
                    )
            mysql.connection.commit()
            return {"imported_count": len(result["rows"])}, 201
        except Exception as error:
            mysql.connection.rollback()
            if _is_duplicate_key_error(error):
                return {"error": "A duplicate question was added by another request. Preview and retry."}, 409
            return {"error": "Unable to import Question Bank CSV."}, 500
        finally:
            cur.close()

    @bank.get("/api/teacher/question-bank/random")
    @login_required
    @role_required(teacher_role)
    def question_bank_random_api():
        cur = mysql.connection.cursor()
        try:
            try:
                subject_id = _subject_id(cur, session["user_id"], request.args.get("subject_id"))
                count = _positive_int(request.args.get("count"), "Count")
                if count > 100:
                    raise ValueError("Count must be between 1 and 100.")
                difficulty = request.args.get("difficulty", "").strip().lower()
                if difficulty and difficulty not in {"easy", "medium", "hard"}:
                    raise ValueError("Difficulty must be easy, medium, or hard.")
            except PermissionError as error:
                return {"error": str(error)}, 403
            except ValueError as error:
                return {"error": str(error)}, 400
            topic = request.args.get("topic", "").strip()
            query = """SELECT id FROM question_bank_questions
                       WHERE created_by = %s AND subject_id = %s"""
            args = [session["user_id"], subject_id]
            if topic:
                query += " AND LOWER(TRIM(topic)) = LOWER(TRIM(%s))"
                args.append(topic)
            if difficulty:
                query += " AND difficulty = %s"
                args.append(difficulty)
            query += " ORDER BY RAND() LIMIT %s"
            args.append(count)
            cur.execute(query, tuple(args))
            ids = [row["id"] for row in cur.fetchall()]
            if len(ids) < count:
                return {"error": f"Only {len(ids)} matching questions are available."}, 400
            rows = _question_rows(cur, ids)
            return {"questions": [question_snapshot(rows[item_id]) for item_id in ids]}, 200
        finally:
            cur.close()

    @bank.post("/api/teacher/question-bank/resolve")
    @login_required
    @role_required(teacher_role)
    def question_bank_resolve_api():
        cur = mysql.connection.cursor()
        try:
            data = request.get_json(silent=True)
            if not isinstance(data, dict) or not isinstance(data.get("question_ids"), list):
                return {"error": "Subject and question IDs are required."}, 400
            question_ids = data["question_ids"]
            if not 1 <= len(question_ids) <= 100 or any(
                isinstance(item, bool) or not isinstance(item, int) or item < 1
                for item in question_ids
            ) or len(set(question_ids)) != len(question_ids):
                return {"error": "Choose between 1 and 100 unique question IDs."}, 400
            try:
                subject_id = _subject_id(cur, session["user_id"], data.get("subject_id"))
            except PermissionError as error:
                return {"error": str(error)}, 403
            except ValueError as error:
                return {"error": str(error)}, 400
            rows = _question_rows(cur, question_ids)
            if len(rows) != len(question_ids) or any(
                row["created_by"] != session["user_id"]
                or row["subject_id"] != subject_id
                for row in rows.values()
            ):
                return {"error": "One or more questions are unavailable for this subject."}, 404
            return {
                "questions": [question_snapshot(rows[item_id]) for item_id in question_ids]
            }, 200
        finally:
            cur.close()

    @bank.route("/api/teacher/question-bank", methods=["GET", "POST"])
    @login_required
    @role_required(teacher_role)
    def question_bank_collection_api():
        cur = mysql.connection.cursor()
        if request.method == "POST":
            try:
                data = request.get_json(silent=True)
                question = validate_question(data)
                subject_id = _subject_id(cur, session["user_id"], (data or {}).get("subject_id"))
            except PermissionError as error:
                cur.close()
                return {"error": str(error)}, 403
            except ValueError as error:
                cur.close()
                return {"error": str(error)}, 400
            try:
                if _bank_duplicate_hashes(
                    cur, session["user_id"], subject_id, {question["question_hash"]}
                ):
                    return {"error": "This question already exists in your bank for this subject."}, 409
                cur.execute(
                    """INSERT INTO question_bank_questions
                       (created_by, subject_id, question_text, question_hash,
                        topic, difficulty, curriculum_code, cognitive_level,
                        correct_option_index, explanation)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        session["user_id"], subject_id, question["question_text"],
                        question["question_hash"], question["topic"], question["difficulty"],
                        question["curriculum_code"], question["cognitive_level"],
                        question["correct_option_index"], question["explanation"],
                    ),
                )
                question_id = cur.lastrowid
                for option_index, option_text in enumerate(question["options"]):
                    cur.execute(
                        """INSERT INTO question_bank_options
                           (question_id, option_index, option_text)
                           VALUES (%s, %s, %s)""",
                        (question_id, option_index, option_text),
                    )
                mysql.connection.commit()
                rows = _question_rows(cur, [question_id])
                return {"question": _question_payload(rows[question_id])}, 201
            except Exception as error:
                mysql.connection.rollback()
                if _is_duplicate_key_error(error):
                    return {"error": "This question already exists in your bank for this subject."}, 409
                return {"error": "Unable to create Question Bank question."}, 500
            finally:
                cur.close()

        try:
            try:
                subject_id = _subject_id(cur, session["user_id"], request.args.get("subject_id"))
                page = _positive_int(request.args.get("page", 1), "Page")
                page_size = int(request.args.get("page_size", 25))
                if page_size not in PAGE_SIZES:
                    raise ValueError("Page size must be 10, 25, 50, or 100.")
                difficulty = request.args.get("difficulty", "").strip().lower()
                if difficulty and difficulty not in {"easy", "medium", "hard"}:
                    raise ValueError("Difficulty must be easy, medium, or hard.")
            except PermissionError as error:
                return {"error": str(error)}, 403
            except ValueError as error:
                return {"error": str(error)}, 400
            search = request.args.get("search", "").strip()
            topic = request.args.get("topic", "").strip()
            where = "q.created_by = %s AND q.subject_id = %s"
            args = [session["user_id"], subject_id]
            if search:
                where += " AND (q.question_text LIKE %s OR q.topic LIKE %s)"
                args.extend([f"%{search}%", f"%{search}%"])
            if topic:
                where += " AND LOWER(TRIM(q.topic)) = LOWER(TRIM(%s))"
                args.append(topic)
            if difficulty:
                where += " AND q.difficulty = %s"
                args.append(difficulty)
            cur.execute(f"SELECT COUNT(*) AS total FROM question_bank_questions q WHERE {where}", tuple(args))
            total = int(cur.fetchone()["total"] or 0)
            cur.execute(
                f"""SELECT q.id FROM question_bank_questions q
                    WHERE {where} ORDER BY q.updated_at DESC, q.id DESC
                    LIMIT %s OFFSET %s""",
                (*args, page_size, (page - 1) * page_size),
            )
            ids = [row["id"] for row in cur.fetchall()]
            rows = _question_rows(cur, ids)
            cur.execute(
                """SELECT DISTINCT topic FROM question_bank_questions
                   WHERE created_by = %s AND subject_id = %s ORDER BY topic""",
                (session["user_id"], subject_id),
            )
            topics = [row["topic"] for row in cur.fetchall()]
            return {
                "questions": [_question_payload(rows[item_id]) for item_id in ids],
                "topics": topics,
                "pagination": {
                    "page": page, "page_size": page_size, "total": total,
                    "total_pages": math.ceil(total / page_size) if total else 0,
                },
            }, 200
        finally:
            cur.close()

    @bank.route("/api/teacher/question-bank/<int:question_id>", methods=["GET", "PUT", "DELETE"])
    @login_required
    @role_required(teacher_role)
    def question_bank_item_api(question_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """SELECT id, created_by, subject_id FROM question_bank_questions
                   WHERE id = %s""",
                (question_id,),
            )
            existing = cur.fetchone()
            if not existing or existing["created_by"] != session["user_id"]:
                return {"error": "Question not found."}, 404
            if not _assignment_exists(cur, session["user_id"], existing["subject_id"]):
                return {"error": "You are not currently assigned to this subject."}, 403
            if request.method == "GET":
                rows = _question_rows(cur, [question_id])
                return {"question": _question_payload(rows[question_id])}, 200
            if request.method == "DELETE":
                cur.execute("DELETE FROM question_bank_questions WHERE id = %s", (question_id,))
                mysql.connection.commit()
                return {"message": "Question deleted."}, 200

            data = request.get_json(silent=True)
            try:
                question = validate_question(data)
                subject_id = _subject_id(
                    cur, session["user_id"], (data or {}).get("subject_id", existing["subject_id"])
                )
            except PermissionError as error:
                return {"error": str(error)}, 403
            except ValueError as error:
                return {"error": str(error)}, 400
            cur.execute(
                """SELECT id FROM question_bank_questions
                   WHERE created_by = %s AND subject_id = %s
                     AND question_hash = %s AND id <> %s""",
                (session["user_id"], subject_id, question["question_hash"], question_id),
            )
            if cur.fetchone():
                return {"error": "This question already exists in your bank for this subject."}, 409
            cur.execute(
                """UPDATE question_bank_questions
                   SET subject_id = %s, question_text = %s, question_hash = %s,
                       topic = %s, difficulty = %s, curriculum_code = %s,
                       cognitive_level = %s, correct_option_index = %s, explanation = %s
                   WHERE id = %s AND created_by = %s""",
                (
                    subject_id, question["question_text"], question["question_hash"],
                    question["topic"], question["difficulty"], question["curriculum_code"],
                    question["cognitive_level"], question["correct_option_index"],
                    question["explanation"], question_id, session["user_id"],
                ),
            )
            cur.execute("DELETE FROM question_bank_options WHERE question_id = %s", (question_id,))
            for option_index, option_text in enumerate(question["options"]):
                cur.execute(
                    """INSERT INTO question_bank_options
                       (question_id, option_index, option_text)
                       VALUES (%s, %s, %s)""",
                    (question_id, option_index, option_text),
                )
            mysql.connection.commit()
            rows = _question_rows(cur, [question_id])
            return {"question": _question_payload(rows[question_id])}, 200
        except Exception as error:
            mysql.connection.rollback()
            if _is_duplicate_key_error(error):
                return {"error": "This question already exists in your bank for this subject."}, 409
            return {"error": "Unable to update Question Bank question."}, 500
        finally:
            cur.close()

    return bank