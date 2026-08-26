import pandas as pd

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import KFold, GridSearchCV


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
# 3. Define baseline Gradient Boosting model
# --------------------------------------------------

model = GradientBoostingRegressor(
    random_state=42
)


# --------------------------------------------------
# 4. Define hyperparameter search space
# --------------------------------------------------

param_grid = {
    "n_estimators": [50, 100, 150, 200],
    "learning_rate": [0.01, 0.05, 0.1],
    "max_depth": [1, 2, 3]
}


# --------------------------------------------------
# 5. Define 5-fold cross-validation
# --------------------------------------------------

cv = KFold(
    n_splits=5,
    shuffle=True,
    random_state=42
)


# --------------------------------------------------
# 6. Grid Search
# --------------------------------------------------

grid_search = GridSearchCV(
    estimator=model,
    param_grid=param_grid,
    cv=cv,
    scoring="neg_mean_squared_error",
    n_jobs=-1
)

grid_search.fit(X, y)


# --------------------------------------------------
# 7. Display best parameters
# --------------------------------------------------

print("\nBest Gradient Boosting Parameters")
print("=" * 50)

print(grid_search.best_params_)


# --------------------------------------------------
# 8. Display best CV RMSE
# --------------------------------------------------

best_rmse = (-grid_search.best_score_) ** 0.5

print("\nBest Cross-Validation RMSE:")
print(f"{best_rmse:.4f}")
