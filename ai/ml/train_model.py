import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import joblib
import os

# Get the current folder (ml)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load dataset
csv_path = os.path.join(BASE_DIR, "student_performance.csv")
data = pd.read_csv(csv_path)

# Features and target
X = data[[
    "attendance",
    "assignment_score",
    "quiz_score",
    "study_hours"
]]
y = data["result"]

# Encode labels
label_encoder = LabelEncoder()
y_encoded = label_encoder.fit_transform(y)

# Train model
model = RandomForestClassifier(
    n_estimators=100,
    random_state=42
)

model.fit(X, y_encoded)

# Save model
model_path = os.path.join(BASE_DIR, "performance_model.pkl")
encoder_path = os.path.join(BASE_DIR, "label_encoder.pkl")

joblib.dump(model, model_path)
joblib.dump(label_encoder, encoder_path)

print("Model trained successfully!")
print("Model saved as:", model_path)
print("Label encoder saved as:", encoder_path)