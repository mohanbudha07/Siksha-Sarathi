import pandas as pd

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import KFold, cross_validate


# --------------------------------------------------
# 1. Load UCI Mathematics dataset
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
# 3. Define tuned Gradient Boosting model
# --------------------------------------------------

model = GradientBoostingRegressor(
    n_estimators=100,
    learning_rate=0.05,
    max_depth=3,
    random_state=42
)


# --------------------------------------------------
# 4. Define 5-fold cross-validation
# --------------------------------------------------

cv = KFold(
    n_splits=5,
    shuffle=True,
    random_state=42
)


# --------------------------------------------------
# 5. Evaluate model
# --------------------------------------------------

scoring = {
    "MAE": "neg_mean_absolute_error",
    "RMSE": "neg_root_mean_squared_error",
    "R2": "r2"
}

scores = cross_validate(
    model,
    X,
    y,
    cv=cv,
    scoring=scoring
)


# --------------------------------------------------
# 6. Calculate average scores
# --------------------------------------------------

mae = -scores["test_MAE"].mean()
rmse = -scores["test_RMSE"].mean()
r2 = scores["test_R2"].mean()


# --------------------------------------------------
# 7. Display results
# --------------------------------------------------

print("\nTuned Gradient Boosting Results")
print("=" * 50)

print(f"MAE  : {mae:.4f}")
print(f"RMSE : {rmse:.4f}")
print(f"R2   : {r2:.4f}")
