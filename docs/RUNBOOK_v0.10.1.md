# Operator runbook — v0.10.1

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
- `ARTICLE_DEMO_ENABLED`
- `ARTICLE_DEMO_STATION_IDS`
- `ARTICLE_DEMO_PARAMETER_CODE`
- `ARTICLE_DEMO_MODEL_KEY`

## 2. Smoke tests

```bash
python -m pytest -q
python run_release_checks.py
```

## 3. Launch

```bash
streamlit run app.py
```

## 4. Manual validation checklist

### Authentication/admin
- login works;
- admin reset uses `.env` secret path;
- Admin Users tab is functional;
- duplicate-user creation shows a friendly error instead of raw SQLite text.

### Playground
- output is truncated according to `.env`;
- truncation warning is visible.

### Forecasting
- paper core preset runs;
- supplementary turbidity preset runs;
- article mode fails explicitly if required trained artifacts are missing;
- article mode does not silently fall back to Persistence;
- `forecast.csv` downloads;
- `forecast_run.json` downloads;
- `experiment_summary.json` downloads;
- `experiment_summary.csv` downloads.

### Trained artifacts
- Ridge training from the Admin panel writes `meta.json`, `weights.npz`, and `training_manifest.json`;
- the training manifest contains station, parameter, alpha, validation counts, and timestamp.

### Export hygiene
- shared summaries do not expose local absolute paths;
- article bundles do not expose local absolute station-context or execution-log paths.

### Agentic Analysis
- deterministic quantitative brief renders;
- presentation modes render visibly differently;
- observed facts, interpretive inferences, alerts, and limitations are clearly separated;
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
- sample exported `experiment_summary.json` and `experiment_summary.csv`;
- `training_manifest.json` for the article presets;
- one clean article bundle export;
- screenshots or exported analysis for the fixed reference stations.

## 6. If a problem is found

### Config/auth problem
Check `.env`, admin reset flow, and session settings.

### Forecasting artifact problem
Inspect the latest `forecast_run.json` and `experiment_summary.json` and confirm the schema fields exist.

### Missing article artifact problem
If article mode fails before forecasting, confirm the required model directory contains `meta.json`, `weights.npz`, and `training_manifest.json` for the requested station/parameter/model.

### Export path leak problem
Inspect the exported JSON/ZIP contents and verify that local machine roots are not present. Shared exports should only retain sanitized relative references.

### Agentic Analysis confusion/problem
Treat deterministic brief output as the baseline. Disable optional LLM refinement to isolate whether the issue is in the local model path or in the deterministic layer.
