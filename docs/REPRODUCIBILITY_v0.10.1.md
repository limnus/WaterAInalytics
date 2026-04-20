# WaterAInalytics reproducibility guide — v0.10.1

This guide describes the reproducibility expectations for the `v0.10.1` stabilization line.

## 1. Scope of reproducibility

`v0.10.1` preserves the article-ready baseline established in `v0.10.0` and adds targeted hardening in three areas:
- article-mode runs now fail explicitly when required trained artifacts are missing;
- Ridge article-mode validation now requires `training_manifest.json`;
- shared experiment exports and article bundles sanitize local absolute paths.

## 2. Artifacts to preserve

For a paper-facing run, preserve at least:
- `forecast.csv`;
- `forecast_run.json`;
- `experiment_summary.json`;
- `experiment_summary.csv`;
- `training_manifest.json` for every trained model used by article mode;
- generated tables/figures or exported summaries.

## 3. Deterministic baseline

The deterministic baseline for forecast analysis is the quantitative brief. It remains the default reproducible surface because it does not require remote or generative services.

To maximize reproducibility:
- prefer deterministic analysis as the canonical reported output;
- use LLM refinement as optional presentation support;
- preserve the exact forecast artifacts and training manifests used as input.

## 4. Article-mode presets

### Paper Core — Flow (00060)
Fixed configuration:
- stations: `USGS-05586100`, `USGS-07010000`, `USGS-07374525`;
- parameter: `00060`;
- model: `ridge`;
- horizon: 24 hours.

### Paper Supplement — Turbidity (63680)
Fixed configuration:
- station: `USGS-07374525`;
- parameter: `63680`;
- model: `ridge`;
- horizon: 24 hours.

Article mode should fail explicitly if required trained artifacts are missing for the chosen preset. It must not silently fall back to Persistence.

## 5. Required trained-artifact set

For every station/parameter/model combination used in article mode, preserve:
- `meta.json`;
- `weights.npz`;
- `training_manifest.json`.

For Ridge, the training manifest should record at least:
- station and parameter;
- trained timestamp;
- alpha / best_alpha;
- validation RMSE;
- train/validation counts;
- files generated.

## 6. Export-safety expectations

Artifacts intended for sharing outside the development machine should not expose local absolute filesystem paths.

Expected behavior in `v0.10.1`:
- `experiment_summary.json` and `experiment_summary.csv` keep useful artifact references without exposing machine-rooted paths;
- article bundles sanitize local path fields such as station-context source paths and execution-log paths before export.

## 7. External dependencies and their status

### Optional local LLM (`Ollama`)
Role:
- optional local refinement/summarization.

Reproducibility note:
- model availability and inference latency depend on the local runtime;
- the exact model name should be recorded when used.

### Official station context services
Possible services include:
- USGS Water Data;
- Census Geocoder;
- USGS elevation service;
- NWS API.

Reproducibility note:
- these services enrich context but should not be the sole source of core analytical claims;
- caching should be enabled and the cache retention documented for a given run.

## 8. Recommended execution protocol

1. Activate a clean virtual environment.
2. Install dependencies from `requirements.txt`.
3. Prepare `.env`.
4. Run the targeted regression tests or full `pytest -q`.
5. Launch the app.
6. Train/freeze Ridge artifacts for the article-mode stations if they are not already present.
7. Run forecasting for the selected article preset.
8. Export `forecast.csv`, `forecast_run.json`, `experiment_summary.json`, and `experiment_summary.csv`.
9. Run Agentic Analysis with deterministic brief enabled.
10. Optionally enable official context enrichment.
11. Optionally enable local LLM refinement and record the model name.

## 9. Minimum release-oriented regression suite for v0.10.1

```bash
python -m pytest -q tests/test_auth_storage.py tests/test_article_mode_validation.py tests/test_forecasting_article_mode_runtime.py tests/test_forecast_output_schema.py tests/test_article_demo_bundle.py tests/test_release_docs.py tests/test_release_manifest.py tests/test_run_release_checks.py
```

## 10. Known sources of nondeterminism

The following may vary across runs or machines:
- local LLM generations;
- network-backed context enrichment;
- model runtime latency;
- remote-service availability.

The following should remain stable for a fixed code state and fixed inputs:
- configuration parsing;
- auth/admin mechanics;
- article-preset selection;
- strict artifact validation;
- forecast-output schema construction;
- deterministic quantitative brief structure;
- experiment-summary export structure;
- export path sanitization behavior.

## 11. Freeze rule for article-ready snapshots

A snapshot is considered reproducible enough for article use when:
- the targeted regression suite passes;
- README and architecture docs match the codebase;
- `.env.example` covers the required runtime options;
- article-mode presets are available without editing `.env` between experiments;
- article mode fails explicitly when required artifacts are missing;
- forecast artifacts, training manifests, and experiment summaries are exportable and parseable;
- deterministic analysis remains usable without LLM access.
