# WaterAInalytics — v0.10.0

WaterAInalytics is a research-oriented Streamlit application for hydrologic time-series exploration, short-horizon forecasting, and interpretable forecast analysis.

The current `v0.10.0` line is the **feature-complete for article** cycle. Its priorities are:
- strong reproducibility;
- robust execution with explicit validation of paper-mode assets;
- clearer operator workflows for article demonstrations;
- interpretable, evidence-linked outputs that are exportable for manuscript support.

## Current scope

The app currently supports:
- local authentication with Admin/User roles plus Playground demo access;
- station discovery and interactive exploration;
- USGS time-series visualization;
- forecasting with Persistence, Ridge, and Chronos-backed models;
- standardized forecast artifacts (`forecast.csv` + `forecast_run.json`);
- deterministic quantitative analysis of forecast behavior;
- optional local LLM refinement through Ollama;
- official station-context enrichment using USGS/Census/NWS metadata;
- article-mode presets for the paper core and supplementary experiments;
- auditable trained-model manifests and compact experiment summaries.

## Article-ready scope in v0.10.0

The `v0.10.0` release line freezes the article-facing workflow around these principles:
- deterministic analysis remains the methodological baseline;
- article mode uses strict model-artifact validation (no silent fallback);
- the main paper preset uses **Flow / Discharge (`00060`)** across three fixed stations;
- a supplementary preset exposes **Turbidity (`63680`)** for `USGS-07374525` without editing `.env`;
- trained Ridge artifacts are accompanied by `training_manifest.json`;
- runs export compact `experiment_summary.json` and `experiment_summary.csv` files for manuscript support.

## Main tabs

### Explorer & Map
Browse stations and inspect discovery metadata.

### Plot Time Series
Plot cached and/or retrieved station time series.

### Forecasting
Generate short-horizon forecasts, run paper-mode presets, validate trained artifacts, and download structured artifacts plus manuscript-oriented summaries.

### Agentic AI Forecasting Analysis
Produce a deterministic quantitative brief, optionally enriched with official station context and optionally refined with a local LLM.

### Admin Panel
Manage users and model administration features.

## Repository structure

```text
app.py
core/
  article_demo/          reproducible paper presets and export bundles
  auth/                  authentication, admin reset, session handling
  cache/                 USGS station and time-series cache helpers
  processing/            IV processing
  analysis/              time-series indicators
  forecast_models/       forecasting models, artifacts, and output schema
  llm_analysis/          deterministic + LLM-backed analysis pipeline
  ui/                    Streamlit tabs and rendering helpers
  config/                centralized environment/runtime settings
  context_enrichment/    official station context enrichment
  release/               release manifest and smoke checks
  utils/                 file-system cache helpers
  pipeline/              processing pipeline glue
  version.py

docs/
  design/architecture.md
  REPRODUCIBILITY_v0.10.0.md
  RUNBOOK_v0.10.0.md
  CODE_FREEZE_CHECKLIST_v0.10.0.md
  RELEASE_VALIDATION_v0.10.0.md
  contracts/

tests/
requirements.txt
```

## Quick start

### 1) Create and activate a virtual environment

Windows PowerShell example:

```powershell
C:envs\waterainalytics\Scripts\Activate.ps1
```

### 2) Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 3) Create `.env`

Start from the example file:

```bash
copy .env.example .env
```

At minimum, review these values:
- `AUTH_ADMIN_INITIAL_PASSWORD`
- `AUTH_ADMIN_RESET_PASSWORD`
- `SESSION_TIMEOUT_MINUTES`
- `PLAYGROUND_REPORT_TRUNCATION_RATIO`
- `OLLAMA_BASE_URL`
- `OLLAMA_TIMEOUT_S`
- `STATION_CONTEXT_ENRICHMENT_ENABLED`
- `STATION_CONTEXT_TIMEOUT_S`
- `STATION_CONTEXT_CACHE_DAYS`
- `ARTICLE_DEMO_ENABLED`
- `ARTICLE_DEMO_STATION_IDS`
- `ARTICLE_DEMO_PARAMETER_CODE`
- `ARTICLE_DEMO_MODEL_KEY`

### 4) Run the app

```bash
streamlit run app.py
```

## Recommended article workflow

### Paper core preset
Use article mode preset:
- **Paper Core — Flow (00060)**
- stations: `USGS-05586100`, `USGS-07010000`, `USGS-07374525`
- model: `ridge`
- horizon: 24 hours

### Supplementary quality preset
Use article mode preset:
- **Paper Supplement — Turbidity (63680)**
- station: `USGS-07374525`
- model: `ridge`
- horizon: 24 hours

### Required trained-artifact set for the paper preset
For each station/parameter/model used in article mode, the system expects a directory like:

```text
data/models/<model_key>/<station_id>/<parameter>/
```

At minimum, Ridge runs should preserve:
- `meta.json`
- `weights.npz`
- `training_manifest.json`

If required artifacts are missing, article mode fails explicitly instead of silently falling back to another model.

## Forecast and manuscript-support artifacts

The forecasting tab is expected to emit:
- `forecast.csv`: row-oriented forecast output for UI/download workflows;
- `forecast_run.json`: structured run artifact containing metadata, requested model, effective model, timestamps, article-preset metadata, and per-station context required by downstream analysis;
- `experiment_summary.json`: compact manuscript-oriented run summary;
- `experiment_summary.csv`: one row per station with training/run metadata merged when available.

These artifacts are the hand-off boundary into the Agentic Analysis tab and the article-support bundle.

## Deterministic vs LLM-backed analysis

The default methodological path is:
1. deterministic quantitative brief;
2. optional official station-context enrichment;
3. optional local LLM refinement.

The deterministic layer is the baseline analytical surface for the paper-oriented version. LLM refinement is additive, not authoritative.

## Tests

Run the targeted suite used during the `v0.10.0` article-ready cycle:

```bash
python -m pytest -q   tests/test_env_config.py   tests/test_auth_storage.py   tests/test_playground_output.py   tests/test_forecast_output_schema.py   tests/test_forecast_context_adapter.py   tests/test_quantitative_brief.py   tests/test_ollama_provider.py   tests/test_station_context_enrichment.py   tests/test_agentic_presentation.py   tests/test_quantitative_brief_rendering.py   tests/test_article_demo_presets.py   tests/test_article_demo_bundle.py   tests/test_release_docs.py   tests/test_release_manifest.py   tests/test_run_release_checks.py
```

## Reproducibility notes

See:
- `docs/design/architecture.md`
- `docs/REPRODUCIBILITY_v0.10.0.md`
- `docs/RUNBOOK_v0.10.0.md`
- `docs/CODE_FREEZE_CHECKLIST_v0.10.0.md`
- `docs/RELEASE_VALIDATION_v0.10.0.md`

## Known boundaries in v0.10.0

The following remain intentionally constrained:
- external LLM use is optional and may be disabled in operational or review contexts;
- web/context enrichment must degrade safely if remote services are unavailable;
- land-cover / urbanization / vegetation enrichment is still outside the frozen article scope unless added through a reliable canonical source;
- article-mode presets target the fixed paper demonstrations and are not meant to replace the broader exploratory UI.

## Release validation

Run the machine-readable release smoke checks before creating the consolidated release tag:

```bash
python run_release_checks.py
```

The JSON report is written to `artifacts/release_checks/release_check_report.json`.
