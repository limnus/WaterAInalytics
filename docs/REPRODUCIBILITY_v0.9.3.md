# Reproducibility guide — v0.9.3

This document defines how to reproduce the `v0.9.3` article-hardening build of WaterAInalytics.

## 1. Scope

The scope of reproducibility for `v0.9.3` is:
- local application setup;
- deterministic forecasting/analysis workflow where applicable;
- optional-but-bounded external services;
- auditable forecast artifacts and documented configuration.

## 2. Environment baseline

### Python environment
Use a dedicated virtual environment and install exactly the dependencies declared in `requirements.txt`.

### Configuration file
Create `.env` from `.env.example` and record the exact values used for any reported experiment or figure.

### Recommended environment evidence bundle
For a paper or supplement, archive:
- git commit hash;
- git tag (if applicable);
- `requirements.txt`;
- sanitized `.env` template with non-secret values preserved;
- `forecast_run.json` outputs used in the reported analysis;
- generated tables/figures or exported summaries.

## 3. Deterministic baseline

The deterministic baseline for forecast analysis is the quantitative brief. It is the default reproducible surface because it does not require remote or generative services.

To maximize reproducibility:
- prefer deterministic analysis as the canonical reported output;
- use LLM refinement as optional presentation support;
- preserve the exact forecast artifacts used as input.

## 4. External dependencies and their status

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

## 5. Recommended execution protocol

1. Activate a clean virtual environment.
2. Install dependencies from `requirements.txt`.
3. Prepare `.env`.
4. Run the targeted regression tests.
5. Launch the app.
6. Run forecasting for the selected station(s).
7. Export `forecast.csv` and `forecast_run.json`.
8. Run Agentic Analysis with deterministic brief enabled.
9. Optionally enable official context enrichment.
10. Optionally enable local LLM refinement and record the model name.

## 6. Minimum regression test suite for v0.9.3

```bash
python -m pytest -q \
  tests/test_env_config.py \
  tests/test_auth_storage.py \
  tests/test_playground_output.py \
  tests/test_forecast_output_schema.py \
  tests/test_forecast_context_adapter.py \
  tests/test_quantitative_brief.py \
  tests/test_ollama_provider.py \
  tests/test_station_context_enrichment.py \
  tests/test_agentic_presentation.py \
  tests/test_quantitative_brief_rendering.py \
  tests/test_release_docs.py
```

## 7. Known sources of nondeterminism

The following may vary across runs or machines:
- local LLM generations;
- network-backed context enrichment;
- model runtime latency;
- remote-service availability.

The following should remain stable for a fixed code state and fixed inputs:
- configuration parsing;
- auth/admin mechanics;
- playground truncation behavior;
- forecast-output schema construction;
- deterministic quantitative brief structure.

## 8. Reporting guidance for the paper

When a figure, table, or qualitative example is reported, include or preserve:
- station ID;
- parameter(s);
- forecast horizon;
- model used;
- whether official context enrichment was enabled;
- whether LLM refinement was enabled;
- exact output artifact version/schema.

## 9. Freeze rule for article-ready snapshots

A snapshot is considered reproducible enough for article use when:
- the targeted regression suite passes;
- README and architecture docs match the codebase;
- `.env.example` covers the required runtime options;
- forecast artifacts are exportable and parseable;
- deterministic analysis remains usable without LLM access.
