import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from ai.ml.evaluate_uci_research import (
    ID_FIELDS,
    SCENARIOS,
    TARGET,
    aggregate_metric_values,
    build_manifest,
    build_model,
    build_research_splits,
    compare_mae_to_baseline,
    evaluate_scenario,
    identity_group_summary,
    write_results,
)


class UCIResearchEvaluationTests(unittest.TestCase):
    @staticmethod
    def _records():
        return pd.DataFrame(
            {
                "G1": [10, 11, 12, 13, 14, 15, 16, 17],
                "failures": [0, 0, 1, 0, 1, 0, 0, 1],
                "studytime": [2, 2, 3, 2, 3, 4, 2, 3],
                "absences": [2, 3, 4, 1, 5, 2, 0, 6],
                "subject": ["Mathematics", "Portuguese"] * 4,
                "G3": [11, 12, 13, 14, 15, 16, 17, 18],
            }
        )

    def test_identity_groups_never_cross_research_split(self):
        records = self._records()
        groups = [0, 0, 1, 1, 2, 2, 3, 3]
        splits = build_research_splits(records, groups, seeds=(42, 43), test_size=0.25)
        for split in splits:
            train_groups = {groups[index] for index in split["train_indices"]}
            test_groups = {groups[index] for index in split["test_indices"]}
            self.assertFalse(train_groups & test_groups)

    def test_same_split_seeds_are_shared_by_models(self):
        records = self._records()
        groups = [0, 0, 1, 1, 2, 2, 3, 3]
        splits = build_research_splits(records, groups, seeds=(42, 43), test_size=0.25)
        result = evaluate_scenario(records, splits, SCENARIOS["scenario_a_prior_performance"])
        model_seed_lists = {
            tuple(split["seed"] for split in model["split_metrics"])
            for model in result.values()
        }
        self.assertEqual(model_seed_lists, {(42, 43)})

    def test_scenarios_define_prior_grade_boundary(self):
        self.assertIn("G1", SCENARIOS["scenario_a_prior_performance"])
        self.assertNotIn("G1", SCENARIOS["scenario_b_no_prior_grade"])
        self.assertEqual(TARGET, "G3")

    def test_subject_is_categorical_in_model_preprocessing(self):
        records = self._records()
        model = build_model("Ridge", SCENARIOS["scenario_a_prior_performance"])
        model.fit(records[list(SCENARIOS["scenario_a_prior_performance"])], records[TARGET])
        predictions = model.predict(records[list(SCENARIOS["scenario_a_prior_performance"])])
        self.assertEqual(len(predictions), len(records))
        self.assertIn("subject", model.named_steps["columntransformer"].transformers[1][2])

    def test_metric_aggregation_is_correct(self):
        summary = aggregate_metric_values([1.0, 3.0])
        self.assertEqual(summary["mean"], 2.0)
        self.assertEqual(summary["std"], 1.0)
        self.assertEqual(summary["min"], 1.0)
        self.assertEqual(summary["max"], 3.0)

    def test_baseline_comparison_is_positive_for_lower_model_error(self):
        baseline = [
            {"overall": {"mae": 3.0}},
            {"overall": {"mae": 2.0}},
        ]
        model = [
            {"overall": {"mae": 1.0}},
            {"overall": {"mae": 1.5}},
        ]
        result = compare_mae_to_baseline(model, baseline)
        self.assertEqual(result["mean"], 1.25)
        self.assertEqual(result["min"], 0.5)
        self.assertEqual(result["max"], 2.0)

    def test_manifest_contains_required_metadata(self):
        records = self._records()
        groups = [0, 0, 1, 1, 2, 2, 3, 3]
        splits = build_research_splits(records, groups, seeds=(42,), test_size=0.25)
        manifest = build_manifest(records, groups, splits)
        for field in (
            "dataset_source",
            "row_count",
            "identity_groups",
            "identity_group_fields",
            "scenarios",
            "models",
            "split_strategy",
            "split_seeds",
            "generated_at_utc",
        ):
            self.assertIn(field, manifest)
        self.assertEqual(manifest["identity_group_fields"], list(ID_FIELDS))

    def test_results_serialization_has_deterministic_structure(self):
        report = {
            "manifest": {"row_count": 1, "generated_at_utc": "fixed"},
            "scenarios": {
                "scenario_a_prior_performance": {
                    "features": ["G1"],
                    "target": "G3",
                    "models": {},
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, metrics_path = write_results(report, Path(directory))
            self.assertEqual(
                json.loads(manifest_path.read_text()),
                report["manifest"],
            )
            self.assertEqual(
                json.loads(metrics_path.read_text()),
                {"scenarios": report["scenarios"]},
            )

    def test_identity_group_summary_reports_single_and_multiple_groups(self):
        summary = identity_group_summary([0, 0, 1, 2, 2, 3])
        self.assertEqual(summary["identity_groups"], 4)
        self.assertEqual(summary["groups_with_multiple_subject_rows"], 2)
        self.assertEqual(summary["single_record_groups"], 2)


if __name__ == "__main__":
    unittest.main()
