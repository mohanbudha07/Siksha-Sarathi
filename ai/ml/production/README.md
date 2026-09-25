# Production ML Runtime Foundation

The production runtime is intentionally model-unavailable until a validated
local Siksha Sarathi artifact exists. The legacy files under `ai/ml/`,
including `performance_model.pkl` and `label_encoder.pkl`, are never selected
by this runtime.

A future artifact must live under `ai/ml/production/artifacts/` beside a
manifest named `manifest.json`. The manifest must match the exact feature
contract version and ordered `MODEL_FEATURE_COLUMNS` defined in
`feature_contract.py`, describe the `target_percent` percentage target, and
include a required SHA-256 checksum for the declared model file. SHA-256
provides artifact integrity, not authenticity; the artifact directory is
trusted application-controlled storage.

Pickle, joblib, and sklearn artifacts can execute code during deserialization.
Only artifacts generated through the trusted training and deployment workflow
may be placed there. Runtime must never load user-supplied model files, and no
artifact-upload functionality exists. Checksum verification occurs before any
deserialization. No artifact is currently committed.

`ProductionArtifactLoader` validates the manifest, model path, required SHA-256
checksum, and model `predict` interface before loading. It caches the result;
call `reset()` or `load(force_reload=True)` after an intentional artifact
replacement. Missing or invalid artifacts return structured unavailable states.

`PredictionService` first builds target-free, time-safe features for an
explicit student, class, subject, and calendar-date cutoff. It requires prior
academic evidence, validates model output in the 0-100 range, and otherwise
returns an observed-analytics fallback. It does not expose an HTTP endpoint.

The service reports evidence quality from observable evidence counts only. It
does not claim calibrated statistical confidence.
