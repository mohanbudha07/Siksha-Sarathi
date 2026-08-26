import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

# --------------------------------------------------
# 1. Load dataset
# --------------------------------------------------

DATA_PATH = "ml/student-mat.csv"

data = pd.read_csv(DATA_PATH, sep=";")


# --------------------------------------------------
# 2. Select features and target
# --------------------------------------------------

features = [
    "G1",
    "failures",
    "studytime",
    "absences"
]

target = "G3"

X = data[features]
y = data[target]


# --------------------------------------------------
# 3. Train Gradient Boosting model
# --------------------------------------------------

model = GradientBoostingRegressor(
    random_state=42
)

model.fit(X, y)


# --------------------------------------------------
# 4. Calculate feature importance
# --------------------------------------------------

feature_importance = pd.Series(
    model.feature_importances_,
    index=X.columns
).sort_values(ascending=False)


# --------------------------------------------------
# 5. Display results
# --------------------------------------------------

print("\nGradient Boosting Feature Importance")
print("=" * 50)

print(feature_importance)

print("\nInterpretation:")
print("Higher importance means the feature contributes more")
print("to the model's prediction of G3.")
