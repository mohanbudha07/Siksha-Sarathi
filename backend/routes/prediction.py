"""Authorized Flask endpoints for the production ML runtime."""

from datetime import date, datetime, timezone
import re
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, request, session

from backend.ml_prediction_audit import normalize_audit_subject, record_prediction_audit
from ai.ml.production.feature_contract import FEATURE_CONTRACT_VERSION
from ai.ml.production.decision_support import build_teacher_decision_support
from ai.ml.production.model_monitoring import summarize_monitoring_status
from ai.ml.production.prediction_service import PredictionService

NEPAL_TIMEZONE = ZoneInfo("Asia/Kathmandu")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FALLBACK_MODE = "observed_analytics"


def nepal_today():
    return datetime.now(timezone.utc).astimezone(NEPAL_TIMEZONE).date()


def parse_as_of_date(value, today):
    if value is None:
        return today, None
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        return None, "as_of_date must use YYYY-MM-DD format"
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None, "as_of_date must be a valid calendar date"
    if parsed > today:
        return None, "as_of_date cannot be in the future"
    return parsed, None


def fetch_observed_academic_summary(cur, teacher_id, student_id, class_id, subject):
    """Read only the authorized academic summary needed for alignment."""
    cur.execute(
        """
        SELECT COUNT(qar.id) AS total_questions,
               COALESCE(SUM(qar.is_correct), 0) AS correct_answers,
               COALESCE(SUM(qar.is_skipped), 0) AS skipped_answers
        FROM quiz_results qr
        INNER JOIN quizzes q ON q.id = qr.quiz_id
        INNER JOIN quiz_sessions qs ON qs.id = qr.quiz_session_id
        LEFT JOIN quiz_answer_results qar ON qar.quiz_result_id = qr.id
        WHERE qr.student_id = %s
          AND qs.class_id = %s
          AND LOWER(TRIM(q.subject)) = LOWER(TRIM(%s))
        """,
        (student_id, class_id, subject),
    )
    quiz = cur.fetchone() or {}
    total_questions = int(quiz.get("total_questions") or 0)
    correct_answers = int(quiz.get("correct_answers") or 0)
    skipped_answers = int(quiz.get("skipped_answers") or 0)
    accuracy = round(100 * correct_answers / total_questions, 2) if total_questions else 0
    skip_percent = round(100 * skipped_answers / total_questions, 2) if total_questions else 0
    if total_questions == 0:
        quiz_status = "No activity"
    elif accuracy < 50 or skip_percent >= 25:
        quiz_status = "Needs attention"
    elif accuracy < 75:
        quiz_status = "Developing"
    else:
        quiz_status = "On track"

    cur.execute(
        """
        SELECT COUNT(CASE WHEN pas.is_absent = FALSE
                          AND pas.marks_obtained IS NOT NULL THEN 1 END)
                   AS graded_assessments,
               COALESCE(SUM(CASE WHEN pas.is_absent = FALSE
                                  AND pas.marks_obtained IS NOT NULL
                                 THEN pas.marks_obtained ELSE 0 END), 0)
                   AS marks_obtained,
               COALESCE(SUM(CASE WHEN pas.is_absent = FALSE
                                  AND pas.marks_obtained IS NOT NULL
                                 THEN pa.max_marks ELSE 0 END), 0)
                   AS maximum_marks
        FROM paper_assessments pa
        LEFT JOIN paper_assessment_scores pas
          ON pas.assessment_id = pa.id AND pas.student_id = %s
        WHERE pa.teacher_user_id = %s
          AND pa.class_id = %s
          AND LOWER(TRIM(pa.subject)) = LOWER(TRIM(%s))
          AND pa.is_published = TRUE
        """,
        (student_id, teacher_id, class_id, subject),
    )
    paper = cur.fetchone() or {}
    maximum = float(paper.get("maximum_marks") or 0)
    marks = float(paper.get("marks_obtained") or 0)
    return {
        "quiz": {
            "total_questions": total_questions,
            "accuracy_percent": accuracy,
            "skip_percent": skip_percent,
            "status": quiz_status,
        },
        "paper": {
            "graded_assessments": int(paper.get("graded_assessments") or 0),
            "average_percent": round(100 * marks / maximum, 2) if maximum else 0,
        },
    }


def create_prediction_blueprint(
    mysql,
    login_required,
    role_required,
    teacher_role,
    admin_role,
    prediction_service=None,
    today_provider=None,
):
    prediction = Blueprint("prediction", __name__)
    default_service = prediction_service or PredictionService()
    default_today_provider = today_provider or nepal_today

    def get_service():
        return current_app.extensions.get("prediction_service", default_service)

    def get_today():
        provider = current_app.extensions.get(
            "prediction_today_provider", default_today_provider
        )
        return provider()

    @prediction.get("/api/teacher/students/<int:student_id>/prediction")
    @login_required
    @role_required(teacher_role)
    def teacher_student_prediction_api(student_id):
        if "class_id" in request.args:
            return {"error": "class_id is derived from the teacher assignment"}, 400

        subject_query = str(request.args.get("subject") or "").strip()
        if not subject_query:
            return {"error": "Subject is required"}, 400

        cutoff, date_error = parse_as_of_date(
            request.args.get("as_of_date"), get_today()
        )
        if date_error:
            return {"error": date_error}, 400

        cur = mysql.connection.cursor()
        try:
            cur.execute(
                """
                SELECT s.id AS student_id,
                       sce.class_id,
                       sub.name AS subject
                FROM teacher_class_subjects tcs
                INNER JOIN subjects sub ON sub.id = tcs.subject_id
                INNER JOIN student_class_enrollments sce
                    ON sce.class_id = tcs.class_id
                   AND sce.student_id = %s
                   AND sce.id = (
                       SELECT latest.id
                       FROM student_class_enrollments latest
                       WHERE latest.student_id = sce.student_id
                       ORDER BY latest.created_at DESC, latest.id DESC
                       LIMIT 1
                   )
                INNER JOIN students s ON s.id = sce.student_id
                WHERE tcs.teacher_user_id = %s
                  AND LOWER(TRIM(sub.name)) = LOWER(TRIM(%s))
                LIMIT 1
                """,
                (student_id, session["user_id"], subject_query),
            )
            scope = cur.fetchone()
        except Exception:
            return {"error": "Unable to resolve prediction access"}, 500
        finally:
            cur.close()

        if not scope:
            return {"error": "Student prediction scope not found"}, 404

        try:
            result = get_service().predict(
                mysql.connection,
                student_id=int(scope["student_id"]),
                class_id=int(scope["class_id"]),
                subject=str(scope["subject"]).strip(),
                as_of_date=cutoff.isoformat(),
            )
        except Exception:
            return {"error": "Prediction service is unavailable"}, 500

        observed_cur = mysql.connection.cursor()
        try:
            observed = fetch_observed_academic_summary(
                observed_cur,
                session["user_id"],
                int(scope["student_id"]),
                int(scope["class_id"]),
                str(scope["subject"]).strip(),
            )
        except Exception:
            return {"error": "Unable to read observed learning evidence"}, 500
        finally:
            observed_cur.close()

        decision_support = build_teacher_decision_support(
            result.get("status"),
            result.get("prediction_percent"),
            observed,
        )

        prediction_result = {
            "status": result.get("status", "model_unavailable"),
            "prediction_percent": result.get("prediction_percent"),
            "fallback": result.get("fallback"),
            "reason": result.get("reason"),
        }
        for optional_field in ("model_version", "model_type"):
            if result.get(optional_field) is not None:
                prediction_result[optional_field] = result[optional_field]
        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            evidence = {}
        safe_evidence = {
            key: evidence[key]
            for key in (
                "academic_evidence_count",
                "quiz_attempt_count",
                "prior_paper_count",
                "has_quiz_evidence",
                "has_prior_paper_evidence",
                "has_attendance_evidence",
                "recent_evidence_count",
            )
            if key in evidence
        }

        if prediction_result.get("status") == "prediction_available":
            manifest = None
            try:
                loaded = get_service().loader.load()
                manifest = getattr(loaded, "manifest", None)
            except Exception:
                manifest = None
            if isinstance(manifest, dict):
                try:
                    record_prediction_audit(
                        mysql.connection,
                        teacher_user_id=session["user_id"],
                        student_id=int(scope["student_id"]),
                        class_id=int(scope["class_id"]),
                        subject=str(scope["subject"]).strip(),
                        as_of_date=cutoff.isoformat(),
                        prediction_result=prediction_result,
                        validated_manifest=manifest,
                        model_version=result.get("model_version") or manifest.get("artifact_version"),
                    )
                except Exception:
                    print("Prediction monitoring audit could not be recorded")

        return {
            "student": {
                "id": int(scope["student_id"]),
                "subject": str(scope["subject"]).strip(),
                "class_id": int(scope["class_id"]),
            },
            "as_of_date": cutoff.isoformat(),
            "prediction": prediction_result,
            "decision_support": decision_support,
            "evidence": safe_evidence,
        }, 200

    @prediction.get("/api/admin/ml/runtime-status")
    @login_required
    @role_required(admin_role)
    def admin_ml_runtime_status_api():
        service = get_service()
        try:
            load_result = service.loader.load()
        except Exception:
            load_result = None

        available = bool(load_result and load_result.available)
        response = {
            "status": "prediction_available" if available else "model_unavailable",
            "model_loaded": available,
            "feature_contract_version": FEATURE_CONTRACT_VERSION,
            "fallback": None if available else FALLBACK_MODE,
        }
        if available and load_result.manifest:
            for output_key, manifest_key in (
                ("model_version", "artifact_version"),
                ("model_type", "model_type"),
                ("target_name", "target_name"),
            ):
                value = load_result.manifest.get(manifest_key)
                if value is not None:
                    response[output_key] = value
        else:
            response["reason"] = "no validated production artifact is available"
        return response, 200

    @prediction.get("/api/admin/ml/monitoring-status")
    @login_required
    @role_required(admin_role)
    def admin_ml_monitoring_status_api():
        service = get_service()
        try:
            load_result = service.loader.load()
        except Exception:
            load_result = None

        report = summarize_monitoring_status(load_result)
        return report, 200

    return prediction
