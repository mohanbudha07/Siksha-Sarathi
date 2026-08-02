import os
import joblib
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load the trained model and label encoder
model = joblib.load(os.path.join(BASE_DIR, "performance_model.pkl"))
label_encoder = joblib.load(os.path.join(BASE_DIR, "label_encoder.pkl"))


def predict_result(quiz_score, attendance, study_hours):
    """
    Predict student performance.

    Parameters:
        quiz_score (int or float)
        attendance (int or float)
        study_hours (int or float)

    Returns:
        str: Predicted performance category
    """

    data = pd.DataFrame([{
        "quiz_score": quiz_score,
        "attendance": attendance,
        "study_hours": study_hours
    }])

    prediction = model.predict(data)

    result = label_encoder.inverse_transform(prediction)

    return result[0]


if __name__ == "__main__":
    print("Prediction:", predict_result(90, 95, 4))