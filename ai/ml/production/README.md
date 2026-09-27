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

## Phase 8 admin readiness monitoring

Phase 8 adds an admin-only, read-only view of genuine source evidence and the
existing Phase 7 readiness gates. The endpoint is
`GET /api/admin/ml/training-readiness`; it uses the standard login and admin
role checks and returns only aggregate counts, readiness states, blocker
explanations, and informational guidance. The `/admin/ml-readiness` page loads
when opened and refreshes only when an administrator requests it.

Phase 7 remains the sole source for readiness analysis and thresholds:

- `MIN_ELIGIBLE_ROWS = 100`
- `MIN_UNIQUE_STUDENTS = 30`
- `MIN_UNIQUE_TARGET_DATES = 4`
- `MIN_VALIDATION_ROWS = 20`
- `MIN_VALIDATION_STUDENTS = 10`

The monitoring endpoint calls the canonical production feature builder and
Phase 7 readiness/temporal split logic, but disables baseline model evaluation.
Validation row and student counts are reported only after that temporal split
can be constructed; otherwise they are unavailable. No estimator is fitted by
the monitoring request.

Source evidence counts (such as quiz attempts, published paper assessments,
valid scored paper rows, and attendance records) are displayed separately from
eligible training snapshots. A quiz attempt or paper score by itself is not an
eligible snapshot. Eligibility requires a valid scored target paper assessment
with earlier quiz or paper evidence for the same student, class, and subject.
Attendance alone is not qualifying academic evidence. Useful data accumulates
through ordinary student learning activity and normal recording/publishing of
valid assessments across multiple students and target dates; the monitor never
creates or recommends manufactured activity.

Responses intentionally exclude student and account identities, individual
marks or answers, feature rows, filesystem details, credentials, and artifact
metadata. The endpoint performs read-only queries and creates no predictions,
training snapshots, interventions, school records, or artifacts. Phase 8 does
not train or deploy a model, alter any readiness threshold or decision-support
rule, or change `PredictionService`. There is no overall readiness percentage;
each gate is reported independently, and deployment readiness remains false
until a later authorized phase establishes it.

## Phase 9 guarded local candidate training

Phase 9 defines a fail-closed local path from genuine MySQL evidence to an
explicitly staged, loader-validated candidate. It does not synthesize school
records, use UCI research data, use `performance_model.pkl` or
`label_encoder.pkl`, change the feature contract, or alter prediction or
decision-support behavior.

Run the real-database readiness gate and temporal candidate evaluation without
writing files:

`python -m ai.ml.production.train_local_model --dry-run`

The training gate calls the canonical Phase 7 readiness analysis before fitting
any estimator. Both `training_ready` and `evaluation_ready` must be true. A
failure returns `training_refused` with aggregate counts and blockers; it does
not fit candidate models or create a directory. Phase 7 thresholds remain the
only readiness thresholds. When gates pass, the fixed Phase 7 candidates
(`DummyRegressor`, Ridge with `StandardScaler`, `RandomForestRegressor`, and
`GradientBoostingRegressor`) are evaluated on the same deterministic temporal
holdout. Selection ranks temporal-validation MAE; RMSE and R² are retained, and
undefined R² is represented as unavailable.

`MODEL_TRAINING_VERSION = "1"` and
`MODEL_APPROVAL_POLICY_VERSION = "1"` identify this workflow and its policy.
Dummy is an evaluation baseline only and can never be selected for packaging.
A non-Dummy candidate must have finite MAE/RMSE and finite R² when defined, beat
Dummy on temporal-validation MAE, and achieve at least
`MIN_MAE_IMPROVEMENT_VS_DUMMY = 0.10` relative MAE improvement. This 10% value is
a Siksha Sarathi project approval heuristic, not a universal scientific rule.
It is not lowered to make a candidate pass. Passing is called
`candidate_approval_eligible`, not a claim of accuracy or production readiness.

Only after that policy passes does the workflow create a fresh instance of the
selected candidate and fit it on all eligible production rows, using exactly
`MODEL_FEATURE_COLUMNS`. Packaging requires an explicit staging directory, for
example:

`python -m ai.ml.production.train_local_model --output-dir /tmp/siksha-model-candidate`

Staging is separate from `ai/ml/production/artifacts/` and contains only
`model.joblib`, `manifest.json`, and `evaluation_report.json`. It contains no
training rows or identities. The manifest reuses the existing
`ProductionArtifactLoader` contract, including artifact/model/feature/target
metadata, timestamps, source, aggregate training counts, validation strategy
and metrics, relative model filename, and checksum. SHA-256 is calculated from
the serialized model bytes after writing the model file.

Before publishing the staging directory, the workflow loads it through
`ProductionArtifactLoader` and runs a smoke inference using one in-memory
eligible feature row. Exactly one finite prediction in the supported 0-100 range
is required. The row and prediction value are not written to reports. Loader or
smoke failure rejects the package and removes the temporary package directory.

Training never promotes automatically. Promotion is a separate explicit
operator action:

`python -m ai.ml.production.train_local_model --promote-from /tmp/siksha-model-candidate`

If an active artifact already exists, promotion refuses replacement unless
`--replace-active` is also supplied. A replacement retains the previous
artifact in a sibling `artifacts.backup-*` directory; a failed install restores
the previous active directory. For rollback, stop the backend, move the current
`artifacts` directory aside, restore the desired retained backup to the
`artifacts` name, then restart the backend. After any successful promotion,
restart the backend so its cached `ProductionArtifactLoader` result is not
stale. No hot reload is performed.

The current real MySQL dataset remains `pipeline_only` with `empty_dataset`,
zero eligible snapshots/students/target dates, and both training and evaluation
gates false. Consequently the real CLI must return `training_refused`, perform
no estimator fit, and create no staging bundle, manifest, model, or production
artifact directory. Synthetic DataFrames in automated tests verify code paths
only; they do not demonstrate school-model accuracy, validate Nepalese student
outcomes, or make the real database ready.

## Phase 10 observed-evidence learning recommendations

Phase 10 uses one framework-independent deterministic engine,
`ai/ml/production/learning_recommendations.py`, with
`LEARNING_RECOMMENDATION_VERSION = "1"`. It consumes normalized observed quiz,
paper, attendance, topic, repeated-mistake, and authorized-resource evidence.
Its provenance is `observed_academic_evidence`; neither student nor teacher
recommendations depend on `PredictionService` or a deployed model. A forecast
may appear separately on the teacher profile, but it is never a recommendation
cause or ranking input.

The existing topic heuristic is preserved: at least three question
observations across at least two distinct tagged questions, and accuracy below
60%, before a topic review is suggested. Topic suggestions sort by lowest
observed accuracy, then greater evidence volume, then stable subject/topic
order. Duplicate topic recommendations are removed. These are Siksha Sarathi
project heuristics, not universal education rules. At most the three highest
priority topic reviews are returned, preserving the existing student plan
limit. Repeated incorrect responses
may add a topic-level evidence detail, but never produce a card per question or
expose another student's answers.

Other observed-evidence rules preserve existing behavior: at least four quiz
questions and a skip rate of 25% or more can suggest reviewing unanswered
questions; the wording states that a skipped answer does not identify why it
was unanswered. At least two graded paper assessments and an average below 60%
can suggest reviewing recent marked work against lesson objectives; this is not
a pass/fail label or a causal claim. Attendance context can suggest checking
for lessons to catch up when at least five days and two absences are recorded.
Attendance never changes topic accuracy or diagnoses why academic performance
changed.

Resources are attached only when they exist and match the observed subject and
topic. Student notes are limited to subjects assigned to the student's current
class. Teacher-profile resources are limited to the assigned class and subject.
Quizzes must be published, parse as valid quiz content, match the subject and
tagged topic, and have no scheduled/active protected lab session. Missing
resources are stated plainly; normal notes and quiz browsing remains available.

`GET /api/student/practice-plan` retains the legacy `topics` field as a derived
compatibility view and adds the recommendation version, status, provenance, and
canonical `recommendations`. It reads only the authenticated student's own
recent evidence. The teacher learning profile includes the same recommendation
contract while preserving its existing topic, difficulty, paper, attendance,
attempt, mistake, forecast, and decision-support displays. Teacher support
plans are still created only after an explicit teacher action and remain
editable before submission. Recommendation kinds map to the existing
intervention source values (`topic`, `paper`, `attendance`, or `manual`);
recommendations are never written to a table.

Recommendations are recalculated from current records on GET and are not
persisted. These routes do not create interventions, predictions, or
artifacts. Phase 10 uses no Gemini, OpenAI, or other external language model.
Reasons describe recorded counts and do not infer understanding, motivation,
confidence, ability, or causation.

The current real database has three registered students and no quiz attempts,
paper evidence, or attendance evidence. It is expected to return `no_evidence`
and no personalized recommendation cards until genuine school activity is
recorded. The useful practice-quiz and learning-notes browsing paths remain
available in that state.
