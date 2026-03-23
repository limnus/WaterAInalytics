# Operator runbook — v0.9.3

## 1. Setup

### Activate environment

```powershell
C:\venvs\waterainalytics\Scripts\Activate.ps1
```

### Install dependencies

```bash
python -m pip install -r requirements.txt
```

### Create `.env`

```bash
copy .env.example .env
```

Review at least:
- `AUTH_ADMIN_INITIAL_PASSWORD`
- `AUTH_ADMIN_RESET_PASSWORD`
- `SESSION_TIMEOUT_MINUTES`
- `PLAYGROUND_REPORT_TRUNCATION_RATIO`
- `OLLAMA_BASE_URL`
- `OLLAMA_TIMEOUT_S`
- `STATION_CONTEXT_ENRICHMENT_ENABLED`
- `STATION_CONTEXT_TIMEOUT_S`
- `STATION_CONTEXT_CACHE_DAYS`

## 2. Smoke tests

```bash
python -m pytest -q tests/test_release_docs.py
python -m pytest -q tests/test_env_config.py tests/test_auth_storage.py tests/test_playground_output.py
python -m pytest -q tests/test_forecast_output_schema.py tests/test_forecast_context_adapter.py
python -m pytest -q tests/test_quantitative_brief.py tests/test_station_context_enrichment.py tests/test_ollama_provider.py
python -m pytest -q tests/test_agentic_presentation.py tests/test_quantitative_brief_rendering.py
```

## 3. Launch

```bash
streamlit run app.py
```

## 4. Manual validation checklist

### Authentication/admin
- login works;
- admin reset uses `.env` secret path;
- Admin Users tab is functional.

### Playground
- output is truncated according to `.env`;
- truncation warning is visible.

### Forecasting
- one station run works;
- multi-station run works;
- `forecast.csv` downloads;
- `forecast_run.json` downloads.

### Agentic Analysis
- deterministic quantitative brief renders;
- presentation modes render visibly differently;
- station-context enrichment does not break the run if offline;
- Ollama model discovery lists installed models when available;
- analysis remains usable when Ollama is unavailable.

## 5. Suggested release-candidate record

Before declaring a candidate, save:
- current branch;
- commit hash;
- current tag(s);
- test command used;
- app version shown in UI;
- sample exported `forecast_run.json`;
- screenshots or exported analysis for the fixed reference stations.

## 6. If a problem is found

### Config/auth problem
Check `.env`, admin reset flow, and session settings.

### Forecasting artifact problem
Inspect the latest `forecast_run.json` and confirm the schema fields exist.

### Agentic Analysis confusion/problem
Treat deterministic brief output as the baseline. Disable optional LLM refinement to isolate whether the issue is in the local model path or in the deterministic layer.
