"""Validation and CSV helpers for the Teacher Question Bank."""

import csv
import hashlib
import io
import re
from collections import Counter


ALLOWED_DIFFICULTIES = frozenset({"easy", "medium", "hard"})
ALLOWED_COGNITIVE_LEVELS = frozenset({
    "recall", "understanding", "application", "higher_order", "unspecified",
})
CSV_COLUMNS = (
    "question", "topic", "difficulty", "curriculum_code", "cognitive_level",
    "option_a", "option_b", "option_c", "option_d", "option_e", "option_f",
    "correct_option", "explanation",
)
MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_CSV_ROWS = 5000


class QuestionBankCsvError(ValueError):
    pass


def normalize_question_text(question_text):
    return re.sub(r"\s+", " ", str(question_text or "").strip()).casefold()


def question_text_hash(question_text):
    normalized = normalize_question_text(question_text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalized_question(data):
    question = str(data.get("question_text", data.get("question", "")) or "").strip()
    topic = re.sub(r"\s+", " ", str(data.get("topic") or "").strip())
    difficulty = str(data.get("difficulty") or "").strip().lower()
    curriculum_code = str(data.get("curriculum_code") or "unspecified").strip() or "unspecified"
    cognitive_level = str(data.get("cognitive_level") or "unspecified").strip().lower() or "unspecified"
    explanation = str(data.get("explanation") or "").strip() or None
    options = data.get("options")
    if not question:
        raise ValueError("Question text is required.")
    if not topic:
        raise ValueError("Topic is required.")
    if len(topic) > 100:
        raise ValueError("Topic must be 100 characters or fewer.")
    if difficulty not in ALLOWED_DIFFICULTIES:
        raise ValueError("Difficulty must be easy, medium, or hard.")
    if len(curriculum_code) > 50:
        raise ValueError("Curriculum code must be 50 characters or fewer.")
    if cognitive_level not in ALLOWED_COGNITIVE_LEVELS:
        raise ValueError("Cognitive level is invalid.")
    if not isinstance(options, list) or not 2 <= len(options) <= 6:
        raise ValueError("A question must have between 2 and 6 options.")
    options = [str(option or "").strip() for option in options]
    if any(not option for option in options):
        raise ValueError("Answer options must not be empty.")
    if any(len(option) > 1000 for option in options):
        raise ValueError("Answer options must be 1000 characters or fewer.")
    if len({option.casefold() for option in options}) != len(options):
        raise ValueError("Answer options must be unique.")
    correct_index = data.get("correct_option_index")
    if isinstance(correct_index, bool) or not isinstance(correct_index, int):
        raise ValueError("Select a valid correct answer.")
    if not 0 <= correct_index < len(options):
        raise ValueError("Correct answer must point to an existing option.")
    return {
        "question_text": question,
        "question_hash": question_text_hash(question),
        "topic": topic,
        "difficulty": difficulty,
        "curriculum_code": curriculum_code,
        "cognitive_level": cognitive_level,
        "options": options,
        "correct_option_index": correct_index,
        "explanation": explanation,
    }


def validate_question(data):
    if not isinstance(data, dict):
        raise ValueError("Question data is required.")
    return _normalized_question(data)


def question_snapshot(question):
    options = question["options"]
    correct_index = int(question["correct_option_index"])
    return {
        "question": question.get("question_text", question.get("question", "")),
        "topic": question["topic"],
        "difficulty": question["difficulty"],
        "curriculum_code": question.get("curriculum_code") or "unspecified",
        "cognitive_level": question.get("cognitive_level") or "unspecified",
        "options": list(options),
        "answer": options[correct_index],
        "explanation": question.get("explanation") or "",
    }


def _validate_csv_values(row_data, row_number):
    errors = []

    def error(field, message):
        errors.append({"row": row_number, "field": field, "message": message})

    question = row_data.get("question", "").strip()
    topic = re.sub(r"\s+", " ", row_data.get("topic", "").strip())
    difficulty = row_data.get("difficulty", "").strip().lower()
    curriculum_code = row_data.get("curriculum_code", "").strip() or "unspecified"
    cognitive_level = row_data.get("cognitive_level", "").strip().lower() or "unspecified"
    if not question:
        error("question", "Question text is required.")
    if not topic:
        error("topic", "Topic is required.")
    elif len(topic) > 100:
        error("topic", "Topic must be 100 characters or fewer.")
    if difficulty not in ALLOWED_DIFFICULTIES:
        error("difficulty", "Difficulty must be easy, medium, or hard.")
    if len(curriculum_code) > 50:
        error("curriculum_code", "Curriculum code must be 50 characters or fewer.")
    if cognitive_level not in ALLOWED_COGNITIVE_LEVELS:
        error("cognitive_level", "Cognitive level is invalid.")

    options = []
    saw_blank = False
    for index, letter in enumerate("abcdef"):
        option = row_data.get(f"option_{letter}", "").strip()
        if not option:
            if index < 2:
                error(f"option_{letter}", f"Option {letter.upper()} is required.")
            saw_blank = True
            continue
        if saw_blank:
            error(f"option_{letter}", "Options cannot contain gaps.")
        if len(option) > 1000:
            error(f"option_{letter}", "Options must be 1000 characters or fewer.")
        options.append(option)
    if len({option.casefold() for option in options}) != len(options):
        error("options", "Answer options must be unique.")

    correct_letter = row_data.get("correct_option", "").strip().upper()
    if correct_letter not in "ABCDEF" or len(correct_letter) != 1:
        error("correct_option", "Correct option must be a letter from A to F.")
        correct_index = -1
    else:
        correct_index = ord(correct_letter) - ord("A")
        if correct_index >= len(options) or not row_data.get(
            f"option_{correct_letter.lower()}", ""
        ).strip():
            error(
                "correct_option",
                f"Correct option {correct_letter} has no value.",
            )

    if errors:
        return None, errors
    return {
        "question_text": question,
        "question_hash": question_text_hash(question),
        "topic": topic,
        "difficulty": difficulty,
        "curriculum_code": curriculum_code,
        "cognitive_level": cognitive_level,
        "options": options,
        "correct_option_index": correct_index,
        "explanation": row_data.get("explanation", "").strip() or None,
    }, errors


def parse_question_csv(raw_bytes):
    if len(raw_bytes) > MAX_CSV_BYTES:
        raise QuestionBankCsvError("CSV file must be 5 MB or smaller.")
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise QuestionBankCsvError("CSV file must use UTF-8 encoding.") from error
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        headers = next(reader, None)
        if headers is None:
            raise QuestionBankCsvError("CSV header row is required.")
        normalized_headers = [header.strip().casefold() for header in headers]
        errors = []
        seen = set()
        for header in normalized_headers:
            if header in seen:
                errors.append({"row": 1, "field": header, "message": f"Duplicate column: {header}."})
            seen.add(header)
        for column in CSV_COLUMNS:
            if column not in normalized_headers:
                errors.append({"row": 1, "field": column, "message": f"Missing column: {column}."})
        for header in normalized_headers:
            if header not in CSV_COLUMNS:
                errors.append({"row": 1, "field": header, "message": f"Unexpected column: {header}."})
        if errors:
            total_rows = 0
            for cells in reader:
                if cells and any(cell.strip() for cell in cells):
                    total_rows += 1
                    if total_rows > MAX_CSV_ROWS:
                        raise QuestionBankCsvError(
                            "CSV file may contain at most 5000 non-empty questions."
                        )
            return [], errors, total_rows

        rows = []
        data_errors = []
        total_rows = 0
        for cells in reader:
            if not cells or not any(cell.strip() for cell in cells):
                continue
            total_rows += 1
            if total_rows > MAX_CSV_ROWS:
                raise QuestionBankCsvError("CSV file may contain at most 5000 non-empty questions.")
            row_number = total_rows + 1
            row = dict(zip(normalized_headers, cells))
            if len(cells) > len(normalized_headers):
                data_errors.append({"row": row_number, "field": "row", "message": "Row has more cells than the header."})
                continue
            for header in normalized_headers:
                row.setdefault(header, "")
            question, row_errors = _validate_csv_values(row, row_number)
            data_errors.extend(row_errors)
            if question:
                rows.append({"row": row_number, "question": question})
        hash_counts = Counter(row["question"]["question_hash"] for row in rows)
        for row in rows:
            if hash_counts[row["question"]["question_hash"]] > 1:
                data_errors.append({
                    "row": row["row"],
                    "field": "question",
                    "message": "Duplicate Question in uploaded CSV.",
                })
        return rows, data_errors, total_rows
    except csv.Error as error:
        raise QuestionBankCsvError(f"Unable to parse CSV: {error}") from error