# WaterAInalytics — v0.9.3

WaterAInalytics is a research-oriented Streamlit application for hydrologic time-series exploration, short-horizon forecasting, and interpretable forecast analysis.

The current `v0.9.3` line is the article-hardening cycle. Its priorities are:
- reproducibility;
- robust execution with graceful degradation;
- clearer operator workflows;
- interpretable, evidence-linked outputs.

## Current scope

The app currently supports:
- local authentication with Admin/User roles;
- station discovery and interactive exploration;
- USGS time-series visualization;
- forecasting with Persistence, Ridge, and Chronos-backed models;
- standardized forecast artifacts (`forecast.csv` + `forecast_run.json`);
- deterministic quantitative analysis of forecast behavior;
- optional local LLM refinement through Ollama;
- official station-context enrichment using USGS/Census/NWS metadata;
- Playground-safe output truncation.

## Main tabs

### Explorer & Map
Browse stations and inspect discovery metadata.

### Plot Time Series
Plot cached and/or retrieved station time series.

### Forecasting
Generate short-horizon forecasts and download structured artifacts.

### Agentic AI Forecasting Analysis
Produce a deterministic quantitative brief, optionally enriched with official station context and optionally refined with a local LLM.

### Admin Panel
Manage users and model administration features.

## Repository structure

```text
app.py
core/
  auth/                 authentication, admin reset, session handling
  cache/                USGS station and time-series cache helpers
  processing/           IV processing
  analysis/             time-series indicators
  forecast_models/      forecasting models and output schema
  llm_analysis/         deterministic + LLM-backed analysis pipeline
  ui/                   Streamlit tabs and rendering helpers
  config/               centralized environment/runtime settings
  context_enrichment/   official station context enrichment
  utils/                file-system cache helpers
  pipeline/             processing pipeline glue
  version.py

docs/
  design/architecture.md
  REPRODUCIBILITY_v0.9.3.md
  RUNBOOK_v0.9.3.md
  CODE_FREEZE_CHECKLIST_v0.9.3.md
  contracts/

tests/
requirements.txt
```

## Quick start

### 1) Create and activate a virtual environment

Windows PowerShell example:

```powershell
C:\venvs\waterainalytics\Scripts\Activate.ps1
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

### 4) Run the app

```bash
streamlit run app.py
```

## Tests

Run the targeted suite used during the `v0.9.3` hardening cycle:

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

## Forecast artifacts

The forecasting tab is expected to emit:
- `forecast.csv`: row-oriented forecast output for UI/download workflows;
- `forecast_run.json`: structured run artifact containing metadata, requested model, effective model, timestamps, and per-station context required by downstream analysis.

These artifacts are the hand-off boundary into the Agentic Analysis tab.

## Deterministic vs LLM-backed analysis

The default methodological path is:
1. deterministic quantitative brief;
2. optional official station-context enrichment;
3. optional local LLM refinement.

The deterministic layer is the baseline analytical surface for the paper-oriented version. LLM refinement is additive, not authoritative.

## Reproducibility notes

See:
- `docs/design/architecture.md`
- `docs/REPRODUCIBILITY_v0.9.3.md`
- `docs/RUNBOOK_v0.9.3.md`
- `docs/CODE_FREEZE_CHECKLIST_v0.9.3.md`

## Known boundaries in v0.9.3

The following remain intentionally constrained:
- external LLM use is optional and may be disabled in operational or review contexts;
- web/context enrichment must degrade safely if remote services are unavailable;
- broad geologic/land-cover enrichment is not yet part of the current frozen scope;
- the Agentic Analysis tab still has a future UX backlog item to unify all analysis actions behind a single final execution flow.
