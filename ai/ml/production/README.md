# Production ML Runtime Foundation

## Phase 7 local readiness boundary

This repository intentionally does not create or load a production artifact during
Phase 7. The runtime remains read-only and evaluation-only: it can inspect the
canonical feature dataset, apply the strict local readiness guardrails, and
report whether the current MySQL data is suitable for serious model evaluation.
It does not train, save, or deploy a model.

The project explicitly forbids creating:

- `ai/ml/production/artifacts/manifest.json`
- any production model pickle/joblib artifact in the production directory
- any deployment or in-place model replacement from the local readiness CLI

The only allowed Phase 7 actions are to build features in memory, evaluate
training-readiness, and report honest structured results.

## Required readiness guardrails

The readiness engine must enforce the following project guardrails:

- `MIN_ELIGIBLE_ROWS = 100`
- `MIN_UNIQUE_STUDENTS = 30`
- `MIN_UNIQUE_TARGET_DATES = 4`
- `MIN_VALIDATION_ROWS = 20`
- `MIN_VALIDATION_STUDENTS = 10`

These thresholds are not lowered to make local data pass. If the database does
not meet them, the report returns `insufficient_data` or `data_quality_blocked`
with the blocking reasons instead of claiming evaluation readiness.

## Temporal validation contract

The evaluation path uses a time-safe holdout that keeps training and validation
separated by target date. It requires at least two distinct dates and then
selects the most recent dates for validation while preserving a non-overlapping
train/validation split. The validation split must also satisfy the minimum row
and student counts above.

The public readiness states are:

- `pipeline_only`
- `data_quality_blocked`
- `insufficient_data`
- `evaluation_ready`

The corresponding uppercase summary state remains `PIPELINE_ONLY`,
`DATA_QUALITY_BLOCKED`, `INSUFFICIENT_DATA`, and `EVALUATED_NOT_DEPLOYED` when
needed by existing callers, while the primary readiness state stays lowercase for
API compatibility and tests.

## Privacy-safe reporting

The report includes a privacy-safe aggregate summary with:

- eligible rows
- unique students
- unique target dates
- subjects represented
- classes represented
- earliest/latest target dates
- rows by subject, class, and target date
- evidence coverage ratios
- snapshots per student summary

The readiness report is aggregate-only and never exposes individual student
records or row-level predictions.

## Local CLI

Run the read-only local evaluation from the project root with:

`python -m ai.ml.production.evaluate_local_training`

Optional JSON output:

`python -m ai.ml.production.evaluate_local_training --json /tmp/training_readiness.json`

This command reads the canonical dataset from the configured MySQL connection and
prints the privacy-safe training-readiness result. It never writes a model or
artifact file.

## Artifact boundary and deployment state

`ProductionArtifactLoader` is intentionally fail-closed. It is for future trusted
artifacts only and does not load anything from the local runtime until the
workflow produces a valid manifest and model file under the controlled artifact
directory. Until then, `deployment_ready` remains `False` and no production model
is claimed as available.

`PredictionService` still builds time-safe features for forecast requests, but it
uses the observed-analytics fallback unless a valid artifact is available.

Teacher decision support is versioned separately as `DECISION_SUPPORT_VERSION =
"1"`. When a validated forecast exists, its deterministic product bands are
`review` below 50, `monitor` from 50 through below 75, and `stronger_outlook` at
75 or above. These are product heuristics, not official grade or pass
boundaries, probabilities, confidence values, diagnoses, or guarantees.
