import pandas as pd

from sklearn.model_selection import KFold, cross_validate
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


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
# 3. Define models
# --------------------------------------------------

models = {
    "Linear Regression": Pipeline([
        ("scaler", StandardScaler()),
        ("model", LinearRegression())
    ]),

    "Random Forest": RandomForestRegressor(
        n_estimators=200,
        random_state=42
    ),

    "Gradient Boosting": GradientBoostingRegressor(
        n_estimators=100,
        learning_rate=0.05,
        max_depth=2,
        random_state=42
    )
}


# --------------------------------------------------
# 4. Five-fold cross-validation
# --------------------------------------------------

cv = KFold(
    n_splits=5,
    shuffle=True,
    random_state=42
)


# --------------------------------------------------
# 5. Evaluation metrics
# --------------------------------------------------

scoring = {
    "MAE": "neg_mean_absolute_error",
    "RMSE": "neg_root_mean_squared_error",
    "R2": "r2"
}


# --------------------------------------------------
# 6. Compare models
# --------------------------------------------------

results = []

for name, model in models.items():

    scores = cross_validate(
        model,
        X,
        y,
        cv=cv,
        scoring=scoring
    )

    mae = -scores["test_MAE"].mean()
    rmse = -scores["test_RMSE"].mean()
    r2 = scores["test_R2"].mean()

    results.append({
        "Model": name,
        "MAE": mae,
        "RMSE": rmse,
        "R2": r2
    })


# --------------------------------------------------
# 7. Display results
# --------------------------------------------------

results_df = pd.DataFrame(results)

print("\nModel Comparison")
print("=" * 60)

print(
    results_df.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}"
    )
)

print("\nLower MAE and RMSE are better.")
print("Higher R2 is better.")
