import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from ai.ml.production.artifact_loader import (
    ARTIFACT_CORRUPT,
    ARTIFACT_INCOMPATIBLE,
    ProductionArtifactLoader,
)
from ai.ml.production.feature_contract import (
    FEATURE_CONTRACT_VERSION,
    MODEL_FEATURE_COLUMNS,
    TARGET_COLUMN,
)
from ai.ml.production.model_training import (
    MIN_MAE_IMPROVEMENT_VS_DUMMY,
    MODEL_APPROVAL_POLICY_VERSION,
    MODEL_TRAINING_VERSION,
    assess_candidate_approval,
    package_approved_candidate,
    promote_candidate,
    run_training_pipeline,
)
from ai.ml.production.training_readiness import _candidate_models, _temporal_split


def _ready_dataset():
    target_dates = ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"]
    rows = []
    for date_index, target_date in enumerate(target_dates):
        for student_id in range(1, 31):
            ordinal = date_index * 30 + student_id
            row = {
                "student_id": student_id,
                "subject": "Mathematics",
                "target_assessment_id": 1000 + ordinal,
                "target_assessment_date": target_date,
                "target_class_id": 7,
                "target_max_marks": 100.0,
                "target_marks_obtained": 48.0 + date_index * 4 + student_id % 40,
                "eligible_for_prediction": True,
                "ineligible_reason": "",
                TARGET_COLUMN: 48.0 + date_index * 4 + student_id % 40,
            }
            row.update({
                column: float((student_id * 7 + date_index * 11 + index) % 97)
                for index, column in enumerate(MODEL_FEATURE_COLUMNS)
            })
            rows.append(row)
    return pd.DataFrame(rows)


def _evaluation(dummy_mae=10.0, candidate_mae=8.0, *, r2=0.5):
    return {
        "status": "evaluated",
        "models": [
            {"model_name": "DummyRegressor", "mae": dummy_mae, "rmse": 12.0, "r2": 0.0},
            {"model_name": "Ridge", "mae": candidate_mae, "rmse": 10.0, "r2": r2},
            {"model_name": "RandomForestRegressor", "mae": candidate_mae + 1, "rmse": 11.0, "r2": 0.4},
            {"model_name": "GradientBoostingRegressor", "mae": candidate_mae + 2, "rmse": 12.0, "r2": 0.3},
        ],
    }


def _approved_ridge():
    decision = assess_candidate_approval(_evaluation())
    if decision["status"] != "candidate_approval_eligible":
        raise AssertionError("test candidate must satisfy the explicit approval policy")
    return decision


def _evaluate_models_for_test(split):
    from ai.ml.production.training_readiness import _evaluate_models

    return _evaluate_models(split["train"], split["validation"])


def _package_ridge(directory, *, output_name="staging"):
    from sklearn.linear_model import Ridge

    dataset = _ready_dataset()
    model = Ridge(alpha=10.0).fit(
        dataset[MODEL_FEATURE_COLUMNS],
        dataset[TARGET_COLUMN],
    )
    output_dir = Path(directory) / output_name
    result = package_approved_candidate(
        model=model,
        model_name="Ridge",
        eligible_dataset=dataset,
        evaluation_report={
            "training_row_count": len(dataset),
            "candidate_evaluation": _evaluation(),
            "feature_names": list(MODEL_FEATURE_COLUMNS),
            "student_id": 11,
            "email": "student@example.test",
            "raw_rows": [{"feature_vector": [1.0, 2.0]}],
            "absolute_path": str(Path(directory).resolve()),
            "database_password": "must-not-be-packaged",
        },
        approval=_approved_ridge(),
        output_dir=output_dir,
    )
    if result["status"] != "candidate_packaged":
        raise AssertionError(f"test candidate package failed: {result}")
    return output_dir, result


class RecordingEstimator:
    def __init__(self):
        self.fit_columns = None
        self.fit_index = None
        self.fit_rows = None

    def fit(self, features, target):
        self.fit_columns = list(features.columns)
        self.fit_index = features.index.tolist()
        self.fit_rows = len(features)
        return self

    def predict(self, features):
        return [65.0] * len(features)


class InvalidSmokeEstimator:
    def predict(self, features):
        return [101.0] * len(features)


class ModelTrainingTests(unittest.TestCase):
    def _assert_refused_without_side_effects(self, dataset, directory):
        destination = Path(directory) / "candidate"
        with patch("ai.ml.production.model_training._evaluate_models") as evaluate:
            with patch("ai.ml.production.model_training._candidate_models") as candidates:
                result = run_training_pipeline(dataset, output_dir=destination)
        self.assertEqual(result["status"], "training_refused")
        self.assertFalse(destination.exists())
        self.assertFalse(result["files_created"])
        self.assertFalse(result["estimator_fit_called"])
        evaluate.assert_not_called()
        candidates.assert_not_called()

    def test_empty_dataset_refuses_training_without_fit_or_files(self):
        with tempfile.TemporaryDirectory() as directory:
            self._assert_refused_without_side_effects(pd.DataFrame(), directory)

    def test_insufficient_rows_refuse_training_without_fit_or_files(self):
        dataset = _ready_dataset().iloc[:-24].copy()
        with tempfile.TemporaryDirectory() as directory:
            self._assert_refused_without_side_effects(dataset, directory)

    def test_insufficient_students_refuse_training_without_fit_or_files(self):
        dataset = _ready_dataset()
        dataset = dataset[dataset["student_id"] <= 25].copy()
        with tempfile.TemporaryDirectory() as directory:
            self._assert_refused_without_side_effects(dataset, directory)

    def test_insufficient_target_dates_refuse_training_without_fit_or_files(self):
        dataset = _ready_dataset()
        dataset.loc[dataset["target_assessment_date"] == "2024-04-01", "target_assessment_date"] = "2024-03-01"
        with tempfile.TemporaryDirectory() as directory:
            self._assert_refused_without_side_effects(dataset, directory)

    def test_invalid_structural_data_refuses_training_without_fit_or_files(self):
        dataset = _ready_dataset()
        dataset.loc[0, TARGET_COLUMN] = 101.0
        with tempfile.TemporaryDirectory() as directory:
            self._assert_refused_without_side_effects(dataset, directory)

    def test_missing_feature_column_refuses_training(self):
        dataset = _ready_dataset().drop(columns=[MODEL_FEATURE_COLUMNS[0]])
        with tempfile.TemporaryDirectory() as directory:
            self._assert_refused_without_side_effects(dataset, directory)

    def test_insufficient_temporal_validation_refuses_training(self):
        rows = []
        for assessment_index in range(70):
            student_id = assessment_index % 30 + 1
            rows.append({
                "student_id": student_id,
                "subject": "Mathematics",
                "target_assessment_id": 1000 + assessment_index,
                "target_assessment_date": "2024-01-01",
                "target_class_id": 7,
                "target_max_marks": 100.0,
                "target_marks_obtained": 60.0,
                "eligible_for_prediction": True,
                "ineligible_reason": "",
                TARGET_COLUMN: 60.0,
                **{column: float(student_id + index) for index, column in enumerate(MODEL_FEATURE_COLUMNS)},
            })
        for date_index, target_date in enumerate(("2024-02-01", "2024-03-01", "2024-04-01")):
            for row_index in range(10):
                student_id = row_index % 9 + 1
                rows.append({
                    "student_id": student_id,
                    "subject": "Mathematics",
                    "target_assessment_id": 2000 + date_index * 10 + row_index,
                    "target_assessment_date": target_date,
                    "target_class_id": 7,
                    "target_max_marks": 100.0,
                    "target_marks_obtained": 61.0 + date_index,
                    "eligible_for_prediction": True,
                    "ineligible_reason": "",
                    TARGET_COLUMN: 61.0 + date_index,
                    **{column: float(student_id + date_index + index) for index, column in enumerate(MODEL_FEATURE_COLUMNS)},
                })
        with tempfile.TemporaryDirectory() as directory:
            self._assert_refused_without_side_effects(pd.DataFrame(rows), directory)

    def test_dummy_best_or_tied_is_rejected(self):
        result = assess_candidate_approval(_evaluation(dummy_mae=8.0, candidate_mae=8.0))
        self.assertEqual(result["status"], "candidate_rejected")
        self.assertEqual(result["reason"], "dummy_best_or_tied")
        self.assertEqual(result["model_name"], "DummyRegressor")

    def test_improvement_below_ten_percent_is_rejected(self):
        result = assess_candidate_approval(_evaluation(dummy_mae=10.0, candidate_mae=9.01))
        self.assertEqual(result["status"], "candidate_rejected")
        self.assertLess(result["relative_mae_improvement"], MIN_MAE_IMPROVEMENT_VS_DUMMY)

    def test_improvement_exactly_ten_percent_is_eligible(self):
        result = assess_candidate_approval(_evaluation(dummy_mae=10.0, candidate_mae=9.0))
        self.assertEqual(result["status"], "candidate_approval_eligible")
        self.assertEqual(result["relative_mae_improvement"], MIN_MAE_IMPROVEMENT_VS_DUMMY)

    def test_improvement_above_ten_percent_is_eligible(self):
        result = assess_candidate_approval(_evaluation(dummy_mae=10.0, candidate_mae=8.9))
        self.assertEqual(result["status"], "candidate_approval_eligible")
        self.assertGreater(result["relative_mae_improvement"], MIN_MAE_IMPROVEMENT_VS_DUMMY)

    def test_non_finite_candidate_metric_is_rejected(self):
        evaluation = _evaluation()
        for candidate in evaluation["models"][1:]:
            candidate["r2"] = math.nan
        result = assess_candidate_approval(evaluation)
        self.assertEqual(result["status"], "candidate_rejected")
        self.assertEqual(result["reason"], "no_valid_non_dummy_candidate")

    def test_undefined_r2_is_allowed_when_other_metrics_are_finite(self):
        result = assess_candidate_approval(_evaluation(r2=None))
        self.assertEqual(result["status"], "candidate_approval_eligible")

    def test_dummy_is_never_packaged_as_a_production_candidate(self):
        decision = assess_candidate_approval(_evaluation(dummy_mae=10.0, candidate_mae=12.0))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate"
            result = package_approved_candidate(
                model=object(),
                model_name="DummyRegressor",
                eligible_dataset=_ready_dataset(),
                evaluation_report={},
                approval=decision,
                output_dir=output,
            )
        self.assertEqual(result["status"], "candidate_rejected")
        self.assertFalse(output.exists())

    def test_package_recomputes_approval_instead_of_trusting_status_flag(self):
        decision = _approved_ridge()
        decision["candidate_metrics"]["mae"] = 9.9
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate"
            result = package_approved_candidate(
                model=object(),
                model_name="Ridge",
                eligible_dataset=_ready_dataset(),
                evaluation_report={},
                approval=decision,
                output_dir=output,
            )
        self.assertEqual(result["status"], "candidate_rejected")
        self.assertFalse(output.exists())

    def test_staging_path_cannot_be_active_production_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            active_artifacts = Path(directory) / "artifacts"
            with patch("ai.ml.production.model_training.DEFAULT_ARTIFACT_DIR", active_artifacts):
                with patch("ai.ml.production.model_training._evaluate_models", return_value=_evaluation()):
                    result = run_training_pipeline(
                        _ready_dataset(),
                        output_dir=active_artifacts,
                    )
        self.assertEqual(result["status"], "candidate_rejected")
        self.assertEqual(result["reason"], "staging_must_be_outside_active_artifacts")
        self.assertFalse(active_artifacts.exists())

    def test_invalid_smoke_inference_discards_temporary_package(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate"
            result = package_approved_candidate(
                model=InvalidSmokeEstimator(),
                model_name="Ridge",
                eligible_dataset=_ready_dataset(),
                evaluation_report={},
                approval=_approved_ridge(),
                output_dir=output,
            )
        self.assertEqual(result["status"], "package_validation_failed")
        self.assertFalse(output.exists())

    def test_candidate_ranking_uses_temporal_mae_and_is_deterministic(self):
        first = assess_candidate_approval(_evaluation())
        second = assess_candidate_approval(_evaluation())
        self.assertEqual(first["model_name"], "Ridge")
        self.assertEqual(first, second)

    def test_repeated_real_temporal_evaluation_selects_the_same_candidate(self):
        split = _temporal_split(_ready_dataset())
        first = assess_candidate_approval(_evaluate_models_for_test(split))
        second = assess_candidate_approval(_evaluate_models_for_test(split))
        self.assertEqual(first["status"], second["status"])
        self.assertEqual(first.get("model_name"), second.get("model_name"))
        self.assertEqual(first.get("candidate_metrics"), second.get("candidate_metrics"))

    def test_dry_run_can_approve_without_final_fit_or_files(self):
        constructed = []

        def capture_candidates():
            candidates = _candidate_models()
            constructed.extend(candidates)
            return candidates

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "candidate"
            with patch("ai.ml.production.model_training._evaluate_models", return_value=_evaluation()):
                with patch("ai.ml.production.model_training._candidate_models", side_effect=capture_candidates) as factory:
                    result = run_training_pipeline(_ready_dataset(), dry_run=True)
            self.assertEqual(result["status"], "candidate_approval_eligible")
            self.assertFalse(destination.exists())
            self.assertFalse(result["files_created"])
            self.assertEqual(factory.call_count, 1)
            for _name, estimator, _params in constructed:
                self.assertFalse(hasattr(estimator, "n_features_in_"))

    def test_candidate_factory_retains_fixed_phase7_parameters(self):
        candidates = {name: (estimator, params) for name, estimator, params in _candidate_models()}
        self.assertEqual(candidates["DummyRegressor"][1], {"strategy": "mean"})
        self.assertEqual(candidates["Ridge"][1], {"alpha": 10.0})
        self.assertEqual(candidates["RandomForestRegressor"][1], {
            "n_estimators": 200,
            "random_state": 42,
            "max_depth": 8,
            "min_samples_leaf": 2,
        })
        self.assertEqual(candidates["GradientBoostingRegressor"][1], {
            "random_state": 42,
            "n_estimators": 200,
            "max_depth": 2,
            "learning_rate": 0.05,
            "subsample": 0.8,
        })

    def test_training_evaluator_receives_the_single_phase7_temporal_split(self):
        dataset = _ready_dataset()
        split = _temporal_split(dataset)
        evaluator = Mock(return_value=_evaluation())
        with patch("ai.ml.production.model_training._evaluate_models", evaluator):
            result = run_training_pipeline(dataset)
        self.assertEqual(result["status"], "candidate_approval_eligible")
        evaluator.assert_called_once()
        train_arg, validation_arg = evaluator.call_args.args
        self.assertEqual(train_arg.index.tolist(), split["train"].index.tolist())
        self.assertEqual(validation_arg.index.tolist(), split["validation"].index.tolist())
        self.assertEqual(list(train_arg[MODEL_FEATURE_COLUMNS].columns), MODEL_FEATURE_COLUMNS)
        self.assertEqual(list(validation_arg[MODEL_FEATURE_COLUMNS].columns), MODEL_FEATURE_COLUMNS)

    def test_fresh_full_data_fit_uses_exact_production_feature_order(self):
        dataset = _ready_dataset()
        estimator = RecordingEstimator()
        candidates = [
            ("DummyRegressor", RecordingEstimator(), {}),
            ("Ridge", estimator, {"alpha": 10.0}),
        ]
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "candidate"
            with patch("ai.ml.production.model_training._evaluate_models", return_value=_evaluation()):
                with patch("ai.ml.production.model_training._candidate_models", return_value=candidates):
                    with patch(
                        "ai.ml.production.model_training.package_approved_candidate",
                        return_value={"status": "candidate_packaged", "files_created": False},
                    ):
                        result = run_training_pipeline(dataset, output_dir=output_dir)
        self.assertEqual(result["status"], "candidate_packaged")
        self.assertEqual(estimator.fit_columns, MODEL_FEATURE_COLUMNS)
        self.assertEqual(estimator.fit_rows, len(dataset))
        self.assertEqual(estimator.fit_index, dataset.index.tolist())

    def test_rejected_candidate_never_gets_final_full_data_fit(self):
        estimators = [RecordingEstimator(), RecordingEstimator()]
        candidates = [
            ("DummyRegressor", estimators[0], {}),
            ("Ridge", estimators[1], {"alpha": 10.0}),
        ]
        rejected_evaluation = _evaluation(dummy_mae=8.0, candidate_mae=8.5)
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "candidate"
            with patch("ai.ml.production.model_training._evaluate_models", return_value=rejected_evaluation):
                with patch("ai.ml.production.model_training._candidate_models", return_value=candidates):
                    result = run_training_pipeline(_ready_dataset(), output_dir=output_dir)
        self.assertEqual(result["status"], "candidate_rejected")
        self.assertFalse(output_dir.exists())
        self.assertTrue(all(estimator.fit_rows is None for estimator in estimators))

    def test_staging_manifest_loader_checksum_and_privacy_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            staging, result = _package_ridge(directory)
            manifest = json.loads((staging / "manifest.json").read_text())
            report = json.loads((staging / "evaluation_report.json").read_text())
            loaded = ProductionArtifactLoader(staging).load()

            self.assertEqual(result["status"], "candidate_packaged")
            self.assertTrue(loaded.available)
            self.assertTrue(callable(loaded.model.predict))
            required = {
                "artifact_version", "model_type", "feature_contract_version",
                "feature_names", "target_name", "target_unit", "training_timestamp",
                "training_data_source", "training_row_count", "unique_student_count",
                "validation_strategy", "primary_metric", "validation_metrics",
                "model_file", "checksum_sha256",
            }
            self.assertTrue(required.issubset(manifest))
            self.assertEqual(manifest["feature_contract_version"], FEATURE_CONTRACT_VERSION)
            self.assertEqual(manifest["feature_names"], MODEL_FEATURE_COLUMNS)
            self.assertEqual(manifest["target_name"], TARGET_COLUMN)
            self.assertEqual(manifest["target_unit"], "percentage / 0-100 paper-assessment score")
            self.assertEqual(manifest["model_file"], "model.joblib")
            self.assertFalse(Path(manifest["model_file"]).is_absolute())
            self.assertEqual(
                manifest["checksum_sha256"],
                hashlib.sha256((staging / "model.joblib").read_bytes()).hexdigest(),
            )
            self.assertTrue(manifest["approved_for_promotion"])
            self.assertTrue(manifest["smoke_test_passed"])
            self.assertEqual(manifest["training_data_source"], "local_siksha_sarathi_mysql")
            self.assertEqual(manifest["training_version"], MODEL_TRAINING_VERSION)
            self.assertEqual(manifest["approval_policy_version"], MODEL_APPROVAL_POLICY_VERSION)
            self.assertEqual(report["feature_names"], MODEL_FEATURE_COLUMNS)

            forbidden_keys = {
                "student_id", "user_id", "teacher_user_id", "full_name", "username",
                "email", "marks_obtained", "raw_rows", "feature_vector", "database_password",
            }
            self.assertTrue(forbidden_keys.isdisjoint(manifest))
            self.assertTrue(forbidden_keys.isdisjoint(report))
            serialized = (staging / "manifest.json").read_text() + (staging / "evaluation_report.json").read_text()
            self.assertNotIn(str(Path(__file__).resolve().parents[2]), serialized)
            self.assertNotIn("/home/", serialized)
            self.assertNotIn("MYSQL_PASSWORD", serialized)
            self.assertNotIn("student@example.test", serialized)
            self.assertNotIn("must-not-be-packaged", serialized)
            self.assertNotIn("feature_vector", serialized)
            self.assertNotIn("absolute_path", serialized)

    def test_tampered_staging_model_fails_existing_checksum_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            staging, _result = _package_ridge(directory)
            with (staging / "model.joblib").open("ab") as model_file:
                model_file.write(b"tampered")
            loaded = ProductionArtifactLoader(staging).load()
            self.assertFalse(loaded.available)
            self.assertEqual(loaded.status, ARTIFACT_CORRUPT)
            result = promote_candidate(staging, production_dir=Path(directory) / "active")
            self.assertEqual(result["status"], "promotion_refused")
            self.assertFalse((Path(directory) / "active").exists())

    def test_unapproved_candidate_cannot_promote(self):
        with tempfile.TemporaryDirectory() as directory:
            staging, _result = _package_ridge(directory)
            manifest_path = staging / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["approved_for_promotion"] = False
            manifest_path.write_text(json.dumps(manifest))
            active = Path(directory) / "active"
            result = promote_candidate(staging, production_dir=active)
            self.assertEqual(result["status"], "promotion_refused")
            self.assertFalse(active.exists())

    def test_loader_invalid_candidate_cannot_promote(self):
        with tempfile.TemporaryDirectory() as directory:
            staging, _result = _package_ridge(directory)
            manifest_path = staging / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["feature_names"] = list(reversed(MODEL_FEATURE_COLUMNS))
            manifest_path.write_text(json.dumps(manifest))
            active = Path(directory) / "active"
            result = promote_candidate(staging, production_dir=active)
            self.assertEqual(result["status"], "promotion_refused")
            self.assertFalse(active.exists())
            self.assertEqual(ProductionArtifactLoader(staging).load().status, ARTIFACT_INCOMPATIBLE)

    def test_report_with_raw_identity_cannot_promote(self):
        with tempfile.TemporaryDirectory() as directory:
            staging, _result = _package_ridge(directory)
            report_path = staging / "evaluation_report.json"
            report = json.loads(report_path.read_text())
            report["student_id"] = 11
            report_path.write_text(json.dumps(report))
            active = Path(directory) / "active"
            result = promote_candidate(staging, production_dir=active)
            self.assertEqual(result["status"], "promotion_refused")
            self.assertEqual(result["reason"], "staged_evaluation_report_invalid")
            self.assertFalse(active.exists())

    def test_valid_approved_candidate_promotes_only_on_explicit_call(self):
        with tempfile.TemporaryDirectory() as directory:
            staging, _result = _package_ridge(directory)
            active = Path(directory) / "active-artifacts"
            self.assertFalse(active.exists())
            result = promote_candidate(staging, production_dir=active)
            self.assertEqual(result["status"], "artifact_promoted")
            self.assertTrue(ProductionArtifactLoader(active).load().available)

    def test_replacement_requires_opt_in_and_preserves_old_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            active, _ = _package_ridge(directory, output_name="active")
            staged, _ = _package_ridge(directory, output_name="new-candidate")
            old_checksum = json.loads((active / "manifest.json").read_text())["checksum_sha256"]
            result = promote_candidate(staged, production_dir=active)
            self.assertEqual(result["status"], "promotion_refused")
            self.assertEqual(
                json.loads((active / "manifest.json").read_text())["checksum_sha256"],
                old_checksum,
            )

            result = promote_candidate(staged, production_dir=active, replace_existing=True)
            self.assertEqual(result["status"], "artifact_promoted")
            self.assertTrue(result["backup_retained"])
            self.assertTrue(ProductionArtifactLoader(active).load().available)
            backups = list(Path(directory).glob("active.backup-*"))
            self.assertEqual(len(backups), 1)
            self.assertTrue(ProductionArtifactLoader(backups[0]).load().available)

    def test_failed_replacement_restores_previous_valid_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            active, _ = _package_ridge(directory, output_name="active")
            staged, _ = _package_ridge(directory, output_name="new-candidate")
            old_checksum = json.loads((active / "manifest.json").read_text())["checksum_sha256"]
            real_replace = os.replace
            calls = 0

            def fail_candidate_install(source, target):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated atomic install failure")
                return real_replace(source, target)

            with patch("ai.ml.production.model_training.os.replace", side_effect=fail_candidate_install):
                result = promote_candidate(staged, production_dir=active, replace_existing=True)

            self.assertEqual(result["status"], "promotion_refused")
            self.assertTrue(ProductionArtifactLoader(active).load().available)
            self.assertEqual(
                json.loads((active / "manifest.json").read_text())["checksum_sha256"],
                old_checksum,
            )

    def test_phase9_reports_contain_only_aggregate_evaluation_metadata(self):
        dataset = _ready_dataset()
        with patch("ai.ml.production.model_training._evaluate_models", return_value=_evaluation()):
            report = run_training_pipeline(dataset, dry_run=True)
        serialized = json.dumps(report, allow_nan=False)
        self.assertNotIn('"student_id"', serialized)
        self.assertNotIn('"student_name"', serialized)
        self.assertNotIn('"email"', serialized)
        self.assertNotIn('"feature_vector"', serialized)
        self.assertNotIn("MYSQL_PASSWORD", serialized)
        self.assertNotIn(str(Path(__file__).resolve().parents[2]), serialized)

    def test_loader_tamper_status_is_checksum_protected_before_deserialization(self):
        with tempfile.TemporaryDirectory() as directory:
            staging, _result = _package_ridge(directory)
            with (staging / "model.joblib").open("ab") as model_file:
                model_file.write(b"tamper")
            with patch("ai.ml.production.artifact_loader.joblib.load") as load:
                result = ProductionArtifactLoader(staging).load()
            self.assertEqual(result.status, ARTIFACT_CORRUPT)
            load.assert_not_called()


if __name__ == "__main__":
    unittest.main()