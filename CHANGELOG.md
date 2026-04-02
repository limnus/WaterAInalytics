# Changelog

All notable changes to this project will be documented in this file.

The format is loosely inspired by Keep a Changelog.
Versioning follows semantic versioning principles where applicable.

---

## [0.10.0] - 2026-04-02
Title: Article-ready feature-complete cycle

### Added
- Strict article-mode model validation for paper presets, preventing silent fallback when trained artifacts are missing.
- Reproducible paper presets for the core Flow (`00060`) experiment and the supplementary Turbidity (`63680`) experiment.
- `training_manifest.json` written alongside trained Ridge artifacts.
- Compact `experiment_summary.json` and `experiment_summary.csv` exports for manuscript support.
- Deterministic narrative structure separated into observed facts, interpretive inferences, alerts, limitations, and open questions.
- Release documentation and manifest updates aligned with the article-ready workflow.

### Changed
- App version aligned to `v0.10.0`.
- Article demo defaults updated so the main paper path uses Flow (`00060`).
- README, reproducibility guide, runbook, freeze checklist, and release validation docs updated to reflect the article-ready baseline.
- Release manifest now documents article presets, manuscript-support artifacts, and trained-artifact expectations.

### Notes
- `v0.10.0` is the feature-complete-for-article line.
- Deterministic analysis remains the baseline method; LLM refinement remains optional and secondary.

---

## [0.9.3] - 2026-03-23
Title: Article-hardening cycle (consolidation in progress)

### Added
- Centralized runtime configuration via `.env`-backed settings.
- Admin reset path without hard-coded secret.
- Functional Admin Users management flow.
- Playground output truncation with configurable ratio.
- Standardized forecasting output schema and structured `forecast_run.json` artifact.
- Deterministic quantitative forecast brief.
- Ollama model discovery and clearer local-LLM error handling.
- Official station-context enrichment with cached USGS/Census/NWS metadata.
- Visible presentation modes for Agentic Analysis output.
- Reproducibility/runbook/freeze documentation for the article-ready cycle.
- Release documentation regression test.

### Changed
- Forecasting → Agentic Analysis hand-off hardened for multi-station use.
- Agentic Analysis UI simplified to reduce overlapping controls.
- README and architecture documentation updated to match the real system.
- Line-ending policy documented through `.gitattributes`.
- App version aligned to `v0.9.3`.

### Notes
- `v0.9.3` remains the active hardening line until the final consolidated tag is cut.
- Deterministic analysis is the baseline article method; LLM refinement remains optional.

---

## [0.6.0] - 2026-02-15
Commit: c4d3dd0  
Tag: v0.6.0  
Title: Agentic AI Forecasting Analysis MVP

### Added
- New **Agentic AI Forecasting Analysis** tab integrated into the main UI.
- Modular `core/llm_analysis` architecture:
  - Pipeline orchestration layer
  - Fixed pipeline orchestrator (MVP)
  - Forecast context adapter
  - Web context collector (DuckDuckGo search via `ddgs`)
  - Rule-based fact extraction engine (MVP)
  - Markdown report generator
  - Report style templates
- Web context cache system:
  - Stable key hashing
  - Local storage layer
  - Retention policy module
- Playground safety guardrails:
  - Domain allowlist (USGS / NOAA / Weather.gov)
  - Domain filtering in web collector
- Radio-based cache control logic (Use Cache vs Force Refresh)
- Evidence rendering with snippet-level traceability
- Structured audit block in generated reports
- Requirements updated (LLM + web tooling dependencies)

### Changed
- `app.py` updated to integrate agentic analysis flow.
- `core/ui/forecasting.py` adjusted for compatibility.
- Version bumped to 0.6.0.
- UI adjustments for report tone and extended layout.

---

## [0.5.0] - 2026-02-12
Title: Final Forecasting Architecture

### Added
- Ridge regression production implementation
- Chronos Bolt / Chronos T5 support
- Admin/User model gating
- Gaussian prediction intervals (80%)
- Multi-horizon forecasting (H=1-3)
- Refactored PlayGround forecasting workflow

---

## [0.3.0] - 2026-02-10
### Added
- Forecasting UI
- Persistence model with noise parameter
- Prediction interval options
- Session isolation logic

---

## [0.2.0] - 2026-01-09
### Finalized
- Water AInalytics US data acquisition
- Explorer & Map stabilization

---

## [0.1.0] - 2026-01-08
### Initial Release
- Explorer & Map MVP
- Core project bootstrap
