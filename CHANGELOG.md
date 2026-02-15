# Changelog

All notable changes to this project will be documented in this file.

The format is loosely inspired by Keep a Changelog.
Versioning follows semantic versioning principles where applicable.

---

## [0.6.0] – 2026-02-15
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

### Technical Scope
- 35 files changed
- ~1460 insertions
- Full modular LLM-analysis subsystem introduced
- No breaking changes to forecasting architecture (v0.5.x preserved)

---

## [0.5.0] – 2026-02-12
Title: Final Forecasting Architecture

### Added
- Ridge regression production implementation
- Chronos Bolt / Chronos T5 support
- Admin/User model gating
- Gaussian prediction intervals (80%)
- Multi-horizon forecasting (H=1–3)
- Refactored PlayGround forecasting workflow

### Notes
- Consolidated forecasting architecture prior to LLM integration.

---

## [0.3.0] – 2026-02-10
### Added
- Forecasting UI
- Persistence model with noise parameter
- Prediction interval options
- Session isolation logic

---

## [0.2.0] – 2026-01-09
### Finalized
- Water AInalytics US data acquisition
- Explorer & Map stabilization

---

## [0.1.0] – 2026-01-08
### Initial Release
- Explorer & Map MVP
- Core project bootstrap

---

## Pre-release
### 2026-01-05
- Project skeleton bootstrap
