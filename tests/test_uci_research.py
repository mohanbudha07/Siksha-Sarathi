"""Protect the research experiment from subject overlap and target leakage."""

import unittest

import numpy as np

from ml.evaluate_uci_research import (
    FEATURES, grouped_holdout, load_subject_records, run_experiment,
)


class UciResearchTests(unittest.TestCase):
    def test_combined_files_keep_overlapping_students_in_one_group(self):
        records, groups = load_subject_records()
        self.assertEqual(len(records), 1044)
        self.assertEqual(len(set(groups)), 662)
        # These entries match on the archive's identity fields but have
        # different subject scores; they cannot cross train/test boundaries.
        self.assertEqual(groups[0], groups[395])
        self.assertNotEqual(records.iloc[0]["G3"], records.iloc[395]["G3"])
        self.assertNotIn("G2", FEATURES)
        self.assertNotIn("G3", FEATURES)

    def test_holdout_is_reproducible_with_no_matching_groups_on_both_sides(self):
        records, groups = load_subject_records()
        train, test = grouped_holdout(records, groups)
        train_again, test_again = grouped_holdout(records, groups)
        np.testing.assert_array_equal(train, train_again)
        np.testing.assert_array_equal(test, test_again)
        self.assertFalse(set(groups[train]) & set(groups[test]))
        self.assertEqual(len(train) + len(test), len(records))

    def test_reports_subject_errors_and_baseline_on_unseen_groups(self):
        result = run_experiment()
        self.assertEqual(result["rows"], 1044)
        self.assertEqual(result["train_rows"] + result["test_rows"], 1044)
        for model_name in ("Mean-grade baseline", "Ridge", "Gradient Boosting"):
            result_for_model = result["results"][model_name]
            self.assertTrue(np.isfinite(result_for_model["overall"]["mae"]))
            self.assertEqual(set(result_for_model["by_subject"]),
                             {"Mathematics", "Portuguese"})


if __name__ == "__main__":
    unittest.main()
