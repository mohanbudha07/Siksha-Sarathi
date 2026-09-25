"""Grouped, repeated external research evaluation on the UCI data.

Run from the repository root with::

    ./venv/bin/python -m ai.ml.evaluate_uci_research

This experiment is external research only. It never writes a production
model, changes the application, or changes the database.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


DATA_DIR = Path(__file__).resolve().parent
RESULTS_DIR = DATA_DIR / "research" / "results"
ID_FIELDS = (
    "school", "sex", "age", "address", "famsize", "Pstatus", "Medu",
    "Fedu", "Mjob", "Fjob", "reason", "nursery", "internet",
)
NUMERIC_FEATURES = ("G1", "failures", "studytime", "absences")
TARGET = "G3"
SPLIT_SEEDS = (42, 43, 44, 45, 46)
TEST_SIZE = 0.2
MODEL_NAMES = ("DummyRegressor", "Ridge", "RandomForestRegressor", "GradientBoostingRegressor")
SCENARIOS = {
    "scenario_a_prior_performance": ("G1", "failures", "studytime", "absences", "subject"),
    "scenario_b_no_prior_grade": ("failures", "studytime", "absences", "subject"),
}
FEATURES = SCENARIOS["scenario_a_prior_performance"]
MODEL_CONFIGS = {
    "DummyRegressor": {"strategy": "mean"},
    "Ridge": {"alpha": 10.0},
    "RandomForestRegressor": {"n_estimators": 100, "random_state": 42},
    "GradientBoostingRegressor": {
        "n_estimators": 100,
        "learning_rate": 0.05,
        "max_depth": 2,
        "random_state": 42,
    },
}


def load_subject_records(data_dir=DATA_DIR):
    """Load UCI subject records and proxy identity groups."""
    datasets = []
    for filename, subject in (("student-mat.csv", "Mathematics"),
                              ("student-por.csv", "Portuguese")):
        frame = pd.read_csv(Path(data_dir) / filename, sep=";")
        required = set(ID_FIELDS) | set(NUMERIC_FEATURES) | {TARGET}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{filename} is missing: {', '.join(sorted(missing))}")
        frame = frame.copy()
        frame["subject"] = subject
        datasets.append(frame)

    records = pd.concat(datasets, ignore_index=True)
    for field in (*NUMERIC_FEATURES, TARGET):
        records[field] = pd.to_numeric(records[field], errors="raise")
    if records[list(ID_FIELDS) + list(NUMERIC_FEATURES) + [TARGET]].isna().any().any():
        raise ValueError("Missing identity, feature, or target values")
    if not records[["G1", TARGET]].apply(lambda col: col.between(0, 20).all()).all():
        raise ValueError("UCI grades must be on the original 0-20 scale")
    groups = pd.MultiIndex.from_frame(records[list(ID_FIELDS)]).factorize()[0]
    return records, groups


def identity_group_summary(groups):
    sizes = pd.Series(groups).value_counts()
    return {
        "identity_groups": int(len(sizes)),
        "groups_with_multiple_subject_rows": int((sizes > 1).sum()),
        "single_record_groups": int((sizes == 1).sum()),
        "group_size_distribution": {
            str(int(size)): int(count)
            for size, count in sizes.value_counts().sort_index().items()
        },
        "proxy_key_collision_diagnostics": {
            "label": "ambiguous proxy-key collisions; not verified students",
            "maximum_proxy_group_size": int(sizes.max()),
            "groups_with_size_greater_than_two": int((sizes > 2).sum()),
            "rows_inside_collision_groups": int(sizes[sizes > 2].sum()),
            "policy": "keep collision groups together conservatively to prevent identity leakage",
        },
    }


def build_research_splits(records, groups, seeds=SPLIT_SEEDS, test_size=TEST_SIZE):
    """Create deterministic shared group splits for every model and scenario."""
    groups = np.asarray(groups)
    splits = []
    for seed in seeds:
        splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        train_idx, test_idx = next(splitter.split(records, groups=groups))
        train_groups = set(groups[train_idx])
        test_groups = set(groups[test_idx])
        if train_groups & test_groups:
            raise AssertionError("Identity groups crossed a research split")
        splits.append({
            "seed": int(seed),
            "train_indices": train_idx.tolist(),
            "test_indices": test_idx.tolist(),
            "train_rows": int(len(train_idx)),
            "test_rows": int(len(test_idx)),
            "train_groups": int(len(train_groups)),
            "test_groups": int(len(test_groups)),
        })
    return splits


def grouped_holdout(records, groups, test_size=TEST_SIZE, random_state=42):
    """Backward-compatible single grouped split for existing research tests."""
    split = build_research_splits(
        records,
        groups,
        seeds=(random_state,),
        test_size=test_size,
    )[0]
    return np.asarray(split["train_indices"]), np.asarray(split["test_indices"])


def _preprocessing(features):
    numeric = [feature for feature in features if feature != "subject"]
    return ColumnTransformer([
        ("numbers", StandardScaler(), numeric),
        ("subject", OneHotEncoder(handle_unknown="ignore"), ["subject"]),
    ])


def build_model(model_name, features):
    """Build one unfitted candidate with preprocessing inside its pipeline."""
    if model_name == "DummyRegressor":
        return DummyRegressor(strategy="mean")
    if model_name == "Ridge":
        return make_pipeline(_preprocessing(features), Ridge(alpha=10.0))
    if model_name == "RandomForestRegressor":
        return make_pipeline(
            _preprocessing(features),
            RandomForestRegressor(n_estimators=100, random_state=42),
        )
    if model_name == "GradientBoostingRegressor":
        return make_pipeline(
            _preprocessing(features),
            GradientBoostingRegressor(
                n_estimators=100,
                learning_rate=0.05,
                max_depth=2,
                random_state=42,
            ),
        )
    raise ValueError(f"Unknown research model: {model_name}")


def calculate_metrics(y_true, predictions):
    return {
        "mae": float(mean_absolute_error(y_true, predictions)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, predictions))),
        "r2": float(r2_score(y_true, predictions)),
    }


def aggregate_metric_values(values):
    numeric_values = [float(value) for value in values]
    return {
        "mean": float(np.mean(numeric_values)),
        "std": float(np.std(numeric_values, ddof=0)),
        "min": float(np.min(numeric_values)),
        "max": float(np.max(numeric_values)),
    }


def aggregate_split_metrics(split_metrics):
    return {
        metric: aggregate_metric_values([split[metric] for split in split_metrics])
        for metric in ("mae", "rmse", "r2")
    }


def compare_mae_to_baseline(model_split_metrics, baseline_split_metrics):
    """Return positive values when a model improves over baseline MAE."""
    improvements = [
        baseline["overall"]["mae"] - model["overall"]["mae"]
        for baseline, model in zip(baseline_split_metrics, model_split_metrics)
    ]
    return aggregate_metric_values(improvements)


def evaluate_scenario(records, splits, features):
    """Evaluate all candidates on the exact same group splits."""
    scenario_results = {}
    for model_name in MODEL_NAMES:
        split_metrics = []
        for split in splits:
            train = records.iloc[split["train_indices"]]
            test = records.iloc[split["test_indices"]]
            model = build_model(model_name, features)
            model.fit(train[list(features)], train[TARGET])
            predictions = model.predict(test[list(features)])
            split_metrics.append({
                "seed": split["seed"],
                "overall": calculate_metrics(test[TARGET], predictions),
                "by_subject": {
                    subject: calculate_metrics(
                        test.loc[test["subject"] == subject, TARGET],
                        predictions[(test["subject"] == subject).to_numpy()],
                    )
                    for subject in ("Mathematics", "Portuguese")
                    if int((test["subject"] == subject).sum()) >= 2
                },
            })

        subject_aggregates = {}
        for subject in ("Mathematics", "Portuguese"):
            subject_splits = [
                split["by_subject"][subject]
                for split in split_metrics
                if subject in split["by_subject"]
            ]
            if subject_splits:
                subject_aggregates[subject] = aggregate_split_metrics(subject_splits)
        scenario_results[model_name] = {
            "split_metrics": split_metrics,
            "aggregate": aggregate_split_metrics(
                [split["overall"] for split in split_metrics]
            ),
            "by_subject": subject_aggregates,
            "model_parameters": MODEL_CONFIGS[model_name],
        }

    for model_result in scenario_results.values():
        model_result["mae_improvement_vs_baseline"] = compare_mae_to_baseline(
            model_result["split_metrics"],
            scenario_results["DummyRegressor"]["split_metrics"],
        )
    return scenario_results


def build_manifest(records, groups, splits):
    grouping = identity_group_summary(groups)
    return {
        "dataset_source": "UCI Student Performance dataset, student-mat.csv and student-por.csv",
        "dataset_role": "external research only",
        "row_count": int(len(records)),
        **grouping,
        "identity_group_fields": list(ID_FIELDS),
        "target": TARGET,
        "target_scale": "original UCI 0-20 grade scale",
        "scenarios": {
            name: {"features": list(features), "target": TARGET}
            for name, features in SCENARIOS.items()
        },
        "models": list(MODEL_NAMES),
        "model_parameters": MODEL_CONFIGS,
        "split_strategy": "repeated GroupShuffleSplit; same split indices shared by all models within each scenario",
        "test_size": TEST_SIZE,
        "split_seeds": list(SPLIT_SEEDS),
        "split_summary": [
            {
                key: value
                for key, value in split.items()
                if key not in ("train_indices", "test_indices")
            }
            for split in splits
        ],
        "tuning": "No hyperparameter search; conservative fixed parameters avoid outer-test leakage.",
        "python_version": platform.python_version(),
        "sklearn_version": sklearn.__version__,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def run_experiment(data_dir=DATA_DIR):
    records, groups = load_subject_records(data_dir)
    splits = build_research_splits(records, groups)
    report = {
        "manifest": build_manifest(records, groups, splits),
        "scenarios": {},
    }
    for scenario_name, features in SCENARIOS.items():
        report["scenarios"][scenario_name] = {
            "features": list(features),
            "target": TARGET,
            "models": evaluate_scenario(records, splits, features),
        }
    first_split = splits[0]
    scenario_models = report["scenarios"]["scenario_a_prior_performance"]["models"]
    legacy_names = {
        "DummyRegressor": "Mean-grade baseline",
        "Ridge": "Ridge",
        "GradientBoostingRegressor": "Gradient Boosting",
    }
    report.update({
        "rows": int(len(records)),
        "train_rows": first_split["train_rows"],
        "test_rows": first_split["test_rows"],
        "results": {
            legacy_names[name]: {
                "overall": scenario_models[name]["split_metrics"][0]["overall"],
                "by_subject": scenario_models[name]["split_metrics"][0]["by_subject"],
            }
            for name in legacy_names
        },
    })
    return report


def write_results(report, results_dir=RESULTS_DIR):
    results_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = results_dir / "experiment_manifest.json"
    metrics_path = results_dir / "metrics.json"
    manifest_path.write_text(
        json.dumps(report["manifest"], indent=2, sort_keys=True) + "\n"
    )
    metrics_path.write_text(
        json.dumps({"scenarios": report["scenarios"]}, indent=2, sort_keys=True) + "\n"
    )
    return manifest_path, metrics_path


def print_summary(report):
    print("UCI Student Performance: external research benchmark only")
    manifest = report["manifest"]
    print(
        f"Rows: {manifest['row_count']} | identity groups: {manifest['identity_groups']} | "
        f"multi-record groups: {manifest['groups_with_multiple_subject_rows']} | "
        f"single-record groups: {manifest['single_record_groups']}"
    )
    print("Scenario | Model | MAE mean +/- std | RMSE mean +/- std | R2 mean +/- std | MAE improvement vs baseline")
    for scenario_name, scenario in report["scenarios"].items():
        for model_name, model in scenario["models"].items():
            aggregate = model["aggregate"]
            improvement = model["mae_improvement_vs_baseline"]["mean"]
            print(
                f"{scenario_name} | {model_name} | "
                f"{aggregate['mae']['mean']:.4f} +/- {aggregate['mae']['std']:.4f} | "
                f"{aggregate['rmse']['mean']:.4f} +/- {aggregate['rmse']['std']:.4f} | "
                f"{aggregate['r2']['mean']:.4f} +/- {aggregate['r2']['std']:.4f} | "
                f"{improvement:.4f}"
            )
    print("UCI results do not validate Nepalese students or the production model.")


def main():
    report = run_experiment()
    manifest_path, metrics_path = write_results(report)
    print_summary(report)
    print(f"Saved research manifest: {manifest_path}")
    print(f"Saved research metrics: {metrics_path}")


if __name__ == "__main__":
    main()
