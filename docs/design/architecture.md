# WaterAInalytics architecture — v0.10.0

This document reflects the actual application architecture targeted by the `v0.10.0` article-ready cycle.

## 1. System goals

WaterAInalytics is organized around five operational goals:
- discover and inspect hydrologic monitoring stations;
- visualize and process station time series;
- generate short-horizon forecasts with interchangeable models;
- produce interpretable forecast analysis with deterministic and optional LLM-assisted layers;
- export auditable artifacts suitable for manuscript preparation and supplementary material.

## 2. Top-level modules

### `app.py`
Streamlit entry point. Responsible for:
- locale bootstrap;
- session bootstrap;
- authentication gate;
- tab orchestration;
- page configuration.

### `core/auth/`
Authentication and session layer.
- SQLite-backed user store;
- default admin bootstrap;
- session timeout;
- admin reset flow;
- admin user-management hooks.

### `core/cache/`
Station and time-series cache helpers.
- station discovery cache;
- per-station/per-parameter IV cache.

### `core/processing/` and `core/analysis/`
Time-series normalization and indicator generation.

### `core/forecast_models/`
Forecasting subsystem.
- model registry;
- persistence model;
- ridge model;
- Chronos integration;
- prediction intervals;
- standardized output schema;
- trained-artifact manifests for article-facing Ridge runs.

### `core/article_demo/`
Article / reproducible demo subsystem.
- fixed paper presets;
- artifact validation for article mode;
- export bundles with run artifacts and experiment summaries.

### `core/llm_analysis/`
Forecast-analysis subsystem.
- forecast-to-analysis adapter;
- deterministic quantitative brief;
- optional local LLM runner;
- optional web/context collection;
- report rendering and traceability helpers.

### `core/context_enrichment/`
Official station-context enrichment.
- station metadata fusion;
- geographic context;
- elevation;
- weather-office/grid metadata;
- local cache for remote lookups.

### `core/release/`
Release manifest and machine-readable smoke checks.

### `core/ui/`
Streamlit rendering layer for tabs and presentation helpers.

## 3. Primary data flow

### A. Explorer flow
`UI → station discovery/cache → map/table rendering`

### B. Time-series flow
`station selection → cache fetch / retrieval → processing → indicators → plotting`

### C. Forecasting flow
`station selection + model selection → model registry → forecast generation → standardized dataframe/json artifacts → experiment summary export → session persistence`

### D. Article-mode forecasting flow
`paper preset selection → strict artifact validation → forecast generation with fixed station/parameter/model configuration → forecast_run.json + experiment_summary.* + optional bundle export`

### E. Agentic analysis flow
`latest forecast artifacts → deterministic adapter → quantitative brief → optional official context enrichment → optional LLM refinement → rendered analysis`

## 4. Forecasting boundary contract

The forecasting tab is the upstream producer for the Agentic Analysis tab and for article-support exports.

### Required outputs
- `forecast.csv`
- `forecast_run.json`

### Recommended article-support outputs
- `experiment_summary.json`
- `experiment_summary.csv`

### Expected content
At minimum, the run artifact should preserve:
- schema version;
- article-mode flag and selected preset when applicable;
- requested model key;
- effective model key actually used;
- station identifier;
- horizon step;
- forecast value(s);
- uncertainty metadata when available;
- history window used to generate the forecast;
- run timestamps and per-station metadata needed downstream.

This boundary exists to keep the analysis layer decoupled from model internals while still producing exportable evidence for the paper workflow.

## 5. Analysis stack

### Deterministic baseline
The deterministic layer is the primary analytical substrate for the paper-oriented version. It must:
- remain available without LLM access;
- rely on directly computed statistics and forecast metadata;
- avoid speculative language;
- degrade safely when optional context is unavailable;
- distinguish observed facts, interpretive inferences, alerts, limitations, and open questions.

### Optional official station context
The context-enrichment layer may add:
- coordinates;
- state and HUC;
- county;
- elevation;
- NWS office/grid references.

This layer enriches interpretation but must not become a hard dependency for baseline analysis.

### Optional local LLM refinement
The local LLM path is additive. It may improve readability or synthesis, but it must not replace:
- deterministic evidence;
- quantitative metrics;
- explicit traceability to forecast and context artifacts.

## 6. State and persistence

### Persistent local stores
- authentication database;
- IV cache;
- context-enrichment cache;
- optional forecast/model artifacts under `data/`;
- trained-model manifests for Ridge paper runs.

### Session state
The UI uses Streamlit session state for:
- current locale;
- login state;
- last forecast artifacts;
- selected station for downstream analysis;
- cached rendering preferences.

## 7. Failure-handling principles

The `v0.10.0` line follows these operational rules:
- local deterministic analysis must remain available if Ollama is offline;
- official-context enrichment must fail soft;
- article mode must fail explicitly if trained artifacts required by the selected preset are missing;
- forecasting artifacts must remain parseable even when some optional metadata is unavailable;
- Playground output must be intentionally truncated by configuration;
- secrets must come from `.env`, not hard-coded literals.

## 8. Reproducibility principles

The architecture supports reproducibility through:
- explicit run artifacts;
- environment-driven configuration;
- bounded and testable module interfaces;
- deterministic baseline analysis;
- fixed article presets;
- trained-model manifests;
- release and freeze documentation.

## 9. Known backlog after v0.10.0

Not yet part of the frozen design:
- unified single-button orchestration for the Agentic Analysis tab;
- richer land-cover / urbanization / vegetation / geology enrichment from canonical sources;
- broader automated evaluation harness tied directly to article figures/tables.
