# xAPI External Student Performance Model

This module trains a machine-learning model using the public
**Students' Academic Performance Dataset (xAPI-Edu-Data)**.

It is external research only and is intentionally separate from
`ai/ml/production/`, because the xAPI feature schema does not match Siksha
Sarathi's longitudinal school-data feature contract.

## Dataset
Place `xAPI-Edu-Data.csv` at:

`ai/ml/xapi/data/xAPI-Edu-Data.csv`

## Train
From the repository root:

`python -m ai.ml.xapi.train_xapi_model`

The trainer compares:
- DummyClassifier
- LogisticRegression
- RandomForestClassifier
- GradientBoostingClassifier

using stratified 5-fold cross-validation. Model selection uses Macro F1 first
and accuracy second.

## Demo prediction
After training:

`python -m ai.ml.xapi.predict_xapi`

## Interpretation
This model demonstrates ML on real external LMS records. It must not be
presented as validated for Nepalese Grade 10 students. The production
Siksha Sarathi model remains `ai/ml/production/`.
