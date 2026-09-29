"""Train and evaluate a real student-performance model on xAPI-Edu-Data.

External research only: this model is intentionally separate from the
Siksha Sarathi production next-paper prediction pipeline because the external
dataset does not share the same longitudinal feature contract.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "xAPI-Edu-Data.csv"
ARTIFACT_DIR = BASE_DIR / "artifacts"

TARGET = "Class"

CATEGORICAL_FEATURES = [
    "StageID",
    "GradeID",
    "SectionID",
    "Topic",
    "Semester",
    "Relation",
    "ParentAnsweringSurvey",
    "ParentschoolSatisfaction",
    "StudentAbsenceDays",
]

NUMERIC_FEATURES = [
    "raisedhands",
    "VisITedResources",
    "AnnouncementsView",
    "Discussion",
]

FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
LABEL_NAMES = {"L": "Low", "M": "Middle", "H": "High"}


def load_dataset(path=DATA_PATH):
    frame = pd.read_csv(path)
    required = set(FEATURES) | {TARGET}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")

    frame = frame[FEATURES + [TARGET]].copy()
    if frame.empty:
        raise ValueError("Dataset is empty")
    if frame.isna().any().any():
        raise ValueError("Dataset contains missing values")

    labels = set(frame[TARGET].astype(str))
    if not labels.issubset({"L", "M", "H"}):
        raise ValueError(f"Unexpected target labels: {sorted(labels)}")

    for column in NUMERIC_FEATURES:
        frame[column] = pd.to_numeric(frame[column], errors="raise")

    return frame


def make_preprocessor():
    return ColumnTransformer(
        [
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
        ],
        remainder="drop",
    )


def candidate_models():
    return {
        "DummyClassifier": DummyClassifier(strategy="most_frequent"),
        "LogisticRegression": LogisticRegression(
            max_iter=3000,
            class_weight="balanced",
            random_state=42,
        ),
        "RandomForestClassifier": RandomForestClassifier(
            n_estimators=300,
            class_weight="balanced",
            random_state=42,
        ),
        "GradientBoostingClassifier": GradientBoostingClassifier(
            n_estimators=150,
            learning_rate=0.05,
            max_depth=2,
            random_state=42,
        ),
    }


def make_pipeline(estimator):
    return Pipeline(
        [
            ("preprocess", make_preprocessor()),
            ("model", estimator),
        ]
    )


def evaluate_candidates(frame):
    X = frame[FEATURES]
    y = frame[TARGET]
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    results = []

    for name, estimator in candidate_models().items():
        scores = cross_validate(
            make_pipeline(estimator),
            X,
            y,
            cv=cv,
            scoring={"accuracy": "accuracy", "macro_f1": "f1_macro"},
            n_jobs=-1,
        )
        results.append(
            {
                "model_name": name,
                "accuracy_mean": float(np.mean(scores["test_accuracy"])),
                "accuracy_std": float(np.std(scores["test_accuracy"])),
                "macro_f1_mean": float(np.mean(scores["test_macro_f1"])),
                "macro_f1_std": float(np.std(scores["test_macro_f1"])),
            }
        )

    return sorted(
        results,
        key=lambda item: (item["macro_f1_mean"], item["accuracy_mean"]),
        reverse=True,
    )


def train_final_model(frame, selected_model_name):
    X = frame[FEATURES]
    y = frame[TARGET]
    train_X, test_X, train_y, test_y = train_test_split(
        X,
        y,
        test_size=0.20,
        stratify=y,
        random_state=42,
    )

    pipeline = make_pipeline(candidate_models()[selected_model_name])
    pipeline.fit(train_X, train_y)
    predictions = pipeline.predict(test_X)

    holdout = {
        "accuracy": float(accuracy_score(test_y, predictions)),
        "macro_f1": float(f1_score(test_y, predictions, average="macro")),
        "confusion_matrix": confusion_matrix(
            test_y, predictions, labels=["L", "M", "H"]
        ).tolist(),
        "classification_report": classification_report(
            test_y,
            predictions,
            labels=["L", "M", "H"],
            output_dict=True,
            zero_division=0,
        ),
        "test_rows": int(len(test_y)),
    }

    final_pipeline = make_pipeline(candidate_models()[selected_model_name])
    final_pipeline.fit(X, y)
    return final_pipeline, holdout


def run_training():
    frame = load_dataset()
    evaluation = evaluate_candidates(frame)
    non_dummy = [x for x in evaluation if x["model_name"] != "DummyClassifier"]
    if not non_dummy:
        raise RuntimeError("No valid non-dummy model candidate")

    selected = max(
        non_dummy,
        key=lambda item: (item["macro_f1_mean"], item["accuracy_mean"]),
    )

    model, holdout = train_final_model(frame, selected["model_name"])
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    model_path = ARTIFACT_DIR / "xapi_performance_model.joblib"
    report_path = ARTIFACT_DIR / "evaluation_report.json"
    manifest_path = ARTIFACT_DIR / "manifest.json"

    joblib.dump(model, model_path)

    report = {
        "dataset": "xAPI-Edu-Data",
        "dataset_rows": int(len(frame)),
        "target": TARGET,
        "label_meanings": LABEL_NAMES,
        "features": FEATURES,
        "model_comparison": evaluation,
        "selected_model": selected["model_name"],
        "holdout": holdout,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    manifest = {
        "artifact_role": "external_research_model",
        "dataset": "xAPI-Edu-Data",
        "dataset_rows": int(len(frame)),
        "model_type": selected["model_name"],
        "target": TARGET,
        "target_meaning": "Low / Middle / High academic performance class",
        "features": FEATURES,
        "production_usage": False,
        "reason_not_production": (
            "The xAPI feature schema differs from the Siksha Sarathi production "
            "school-data feature contract."
        ),
        "model_file": model_path.name,
        "evaluation_report": report_path.name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    print("\nxAPI ML training complete")
    print("=" * 60)
    print(f"Rows: {len(frame)}")
    print(f"Selected model: {selected['model_name']}")
    print(f"CV Macro F1: {selected['macro_f1_mean']:.4f}")
    print(f"CV Accuracy: {selected['accuracy_mean']:.4f}")
    print(f"Holdout Macro F1: {holdout['macro_f1']:.4f}")
    print(f"Holdout Accuracy: {holdout['accuracy']:.4f}")
    print(f"Model: {model_path}")
    print(f"Report: {report_path}")
    print("\nExternal research artifact only; production school ML remains separate.")


if __name__ == "__main__":
    run_training()
