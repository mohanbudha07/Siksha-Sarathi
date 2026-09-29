"""Inference helper for the trained external xAPI research model."""

from __future__ import annotations

from pathlib import Path
import joblib
import pandas as pd

from ai.ml.xapi.train_xapi_model import FEATURES

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "artifacts" / "xapi_performance_model.joblib"


def predict_performance(features: dict):
    missing = [feature for feature in FEATURES if feature not in features]
    if missing:
        raise ValueError(f"Missing required features: {missing}")

    model = joblib.load(MODEL_PATH)
    frame = pd.DataFrame([{feature: features[feature] for feature in FEATURES}])
    result = model.predict(frame)[0]
    label_names = {"L": "Low", "M": "Middle", "H": "High"}
    return {"class": str(result), "label": label_names.get(str(result), str(result))}


if __name__ == "__main__":
    example = {
        "StageID": "HighSchool",
        "GradeID": "G-10",
        "SectionID": "A",
        "Topic": "Science",
        "Semester": "F",
        "Relation": "Father",
        "ParentAnsweringSurvey": "Yes",
        "ParentschoolSatisfaction": "Good",
        "StudentAbsenceDays": "Under-7",
        "raisedhands": 60,
        "VisITedResources": 75,
        "AnnouncementsView": 45,
        "Discussion": 60,
    }
    print(predict_performance(example))
