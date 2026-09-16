"""Reproducible, offline UCI Student Performance research comparison.

Run from the repository root: python -m ml.evaluate_uci_research
No application model is trained, saved or replaced by this experiment.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


DATA_DIR = Path(__file__).resolve().parent
ID_FIELDS = (
    "school", "sex", "age", "address", "famsize", "Pstatus", "Medu",
    "Fedu", "Mjob", "Fjob", "reason", "nursery", "internet",
)
NUMERIC_FEATURES = ("G1", "failures", "studytime", "absences")
FEATURES = (*NUMERIC_FEATURES, "subject")
TARGET = "G3"


def load_subject_records(data_dir=DATA_DIR):
    """Load each course as its own record and group likely matching students."""
    datasets = []
    for filename, subject in (("student-mat.csv", "Mathematics"),
                              ("student-por.csv", "Portuguese")):
        frame = pd.read_csv(Path(data_dir) / filename, sep=";")
        required = set(ID_FIELDS) | set(FEATURES) | {TARGET}
        required.remove("subject")
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{filename} is missing: {', '.join(sorted(missing))}")
        frame["subject"] = subject
        datasets.append(frame)

    records = pd.concat(datasets, ignore_index=True)
    # G1 is a first-period grade. UCI does not date absences/studytime, so
    # this retrospective dataset cannot establish a prospective warning date.
    for field in (*NUMERIC_FEATURES, TARGET):
        records[field] = pd.to_numeric(records[field], errors="raise")
    if records[list(ID_FIELDS) + list(FEATURES) + [TARGET]].isna().any().any():
        raise ValueError("Missing identity, feature, or target values")
    if not records[["G1", TARGET]].apply(lambda col: col.between(0, 20).all()).all():
        raise ValueError("UCI grades must be on the original 0–20 scale")
    # The archive has no student IDs. Its bundled student-merge.R uses these
    # 13 attributes for matching; collisions mean groups are only proxies.
    groups = pd.MultiIndex.from_frame(records[list(ID_FIELDS)]).factorize()[0]
    return records, groups


def grouped_holdout(records, groups, test_size=0.2, random_state=42):
    """Hold out whole matching-identity groups, including both subjects."""
    if len(records) != len(groups) or len(set(groups)) < 2:
        raise ValueError("Need matching group IDs and at least two identity groups")
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size,
                                 random_state=random_state)
    train_idx, test_idx = next(splitter.split(records, groups=groups))
    if set(groups[train_idx]) & set(groups[test_idx]):
        raise AssertionError("Identity groups must not cross train/test split")
    return train_idx, test_idx


def metrics(y_true, y_pred):
    return {
        "mae": mean_absolute_error(y_true, y_pred),
        "rmse": np.sqrt(mean_squared_error(y_true, y_pred)),
        "r2": r2_score(y_true, y_pred),
    }


def run_experiment(data_dir=DATA_DIR):
    records, groups = load_subject_records(data_dir)
    train_idx, test_idx = grouped_holdout(records, groups)
    train, test = records.iloc[train_idx], records.iloc[test_idx]
    x_train, x_test = train[list(FEATURES)], test[list(FEATURES)]
    y_train, y_test = train[TARGET], test[TARGET]

    def preprocessing():
        return ColumnTransformer([
            ("numbers", StandardScaler(), list(NUMERIC_FEATURES)),
            ("course", OneHotEncoder(handle_unknown="ignore"), ["subject"]),
        ])

    # Fixed settings: holdout data is never used for parameter tuning.
    models = {
        "Mean-grade baseline": DummyRegressor(strategy="mean"),
        "Ridge": make_pipeline(preprocessing(), Ridge(alpha=10.0)),
        "Gradient Boosting": make_pipeline(preprocessing(),
                                            GradientBoostingRegressor(
                                                n_estimators=100, max_depth=2,
                                                learning_rate=0.05, random_state=42)),
    }
    results = {}
    for name, model in models.items():
        model.fit(x_train, y_train)
        predictions = model.predict(x_test)
        results[name] = {
            "overall": metrics(y_test, predictions),
            "by_subject": {
                subject: metrics(y_test[test["subject"] == subject],
                                 predictions[(test["subject"] == subject).to_numpy()])
                for subject in ("Mathematics", "Portuguese")
                if (test["subject"] == subject).any()
            },
        }
    return {
        "rows": len(records), "identity_groups": len(set(groups)),
        "train_rows": len(train), "test_rows": len(test),
        "train_groups": len(set(groups[train_idx])),
        "test_groups": len(set(groups[test_idx])),
        "train_subjects": train["subject"].value_counts().to_dict(),
        "test_subjects": test["subject"].value_counts().to_dict(),
        "results": results,
    }


def main():
    report = run_experiment()
    print("UCI Portugal Student Performance: offline research only")
    print(f"{report['rows']} subject records, {report['identity_groups']} matching identity groups")
    print(f"Train: {report['train_rows']} records / {report['train_groups']} groups; "
          f"test: {report['test_rows']} records / {report['test_groups']} groups")
    print("Test records by subject:", report["test_subjects"])
    print("Target: G3 final grade on a 0–20 scale; lower MAE/RMSE is better")
    for name, outcome in report["results"].items():
        score = outcome["overall"]
        print(f"{name}: MAE={score['mae']:.3f}  RMSE={score['rmse']:.3f}  R²={score['r2']:.3f}")
        for subject, subject_score in outcome["by_subject"].items():
            print(f"  {subject}: MAE={subject_score['mae']:.3f}")
    print("No application model was updated. UCI does not timestamp all inputs; "
          "these results do not validate early warnings or Nepal Grade 10 predictions.")


if __name__ == "__main__":
    main()
