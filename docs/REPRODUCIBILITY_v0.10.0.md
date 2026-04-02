# Reproducibility guide — v0.10.0

This document defines how to reproduce the `v0.10.0` article-ready build of WaterAInalytics.

## 1. Scope

The scope of reproducibility for `v0.10.0` is:
- local application setup;
- reproducible article-mode forecasting for the paper presets;
- deterministic forecasting/analysis workflow where applicable;
- optional-but-bounded external services;
- auditable forecast artifacts, training manifests, and experiment summaries.

## 2. Environment baseline

### Python environment
Use a dedicated virtual environment and install exactly the dependencies declared in `requirements.txt`.

### Configuration file
Create `.env` from `.env.example` and record the exact non-secret values used for any reported experiment or figure.

### Recommended environment evidence bundle
For a paper or supplement, archive:
- git commit hash;
- git tag (if applicable);
- `requirements.txt`;
- sanitized `.env` template with non-secret values preserved;
- `forecast_run.json` outputs used in the reported analysis;
- `experiment_summary.json` and `experiment_summary.csv`;
- `training_manifest.json` for every trained model used by article mode;
- generated tables/figures or exported summaries.

## 3. Deterministic baseline

The deterministic baseline for forecast analysis is the quantitative brief. It is the default reproducible surface because it does not require remote or generative services.

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

Article mode should fail explicitly if required trained artifacts are missing for the chosen preset.

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

## 6. External dependencies and their status

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

## 7. Recommended execution protocol

1. Activate a clean virtual environment.
2. Install dependencies from `requirements.txt`.
3. Prepare `.env`.
4. Run the targeted regression tests.
5. Launch the app.
6. Train/freeze Ridge artifacts for the article-mode stations if they are not already present.
7. Run forecasting for the selected article preset.
8. Export `forecast.csv`, `forecast_run.json`, `experiment_summary.json`, and `experiment_summary.csv`.
9. Run Agentic Analysis with deterministic brief enabled.
10. Optionally enable official context enrichment.
11. Optionally enable local LLM refinement and record the model name.

## 8. Minimum regression test suite for v0.10.0

```bash
python -m pytest -q   tests/test_env_config.py   tests/test_auth_storage.py   tests/test_playground_output.py   tests/test_forecast_output_schema.py   tests/test_forecast_context_adapter.py   tests/test_quantitative_brief.py   tests/test_ollama_provider.py   tests/test_station_context_enrichment.py   tests/test_agentic_presentation.py   tests/test_quantitative_brief_rendering.py   tests/test_article_demo_presets.py   tests/test_article_demo_bundle.py   tests/test_release_docs.py   tests/test_release_manifest.py   tests/test_run_release_checks.py
```

## 9. Known sources of nondeterminism

The following may vary across runs or machines:
- local LLM generations;
- network-backed context enrichment;
- model runtime latency;
- remote-service availability.

The following should remain stable for a fixed code state and fixed inputs:
- configuration parsing;
- auth/admin mechanics;
- playground truncation behavior;
- article-preset selection;
- strict artifact validation;
- forecast-output schema construction;
- deterministic quantitative brief structure;
- experiment-summary export structure.

## 10. Reporting guidance for the paper

When a figure, table, or qualitative example is reported, include or preserve:
- article preset used;
- station ID;
- parameter(s);
- forecast horizon;
- model used;
- whether official context enrichment was enabled;
- whether LLM refinement was enabled;
- exact output artifact version/schema;
- training manifest used for the model.

## 11. Freeze rule for article-ready snapshots

A snapshot is considered reproducible enough for article use when:
- the targeted regression suite passes;
- README and architecture docs match the codebase;
- `.env.example` covers the required runtime options;
- article-mode presets are available without editing `.env` between experiments;
- forecast artifacts, training manifests, and experiment summaries are exportable and parseable;
- deterministic analysis remains usable without LLM access.
