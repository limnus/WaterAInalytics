# Code freeze checklist — v0.10.0

Use this checklist before creating the consolidated `v0.10.0` tag.

## A. Code and configuration
- [ ] `core/version.py` shows `v0.10.0`
- [ ] `.env.example` includes every runtime knob needed by the app
- [ ] article demo defaults point to Flow (`00060`) for the main preset
- [ ] no secrets are hard-coded
- [ ] line-ending policy file is committed (`.gitattributes`)

## B. Tests
- [ ] targeted regression suite passes locally
- [ ] deterministic quantitative brief tests pass
- [ ] article demo preset tests pass
- [ ] article bundle summary tests pass
- [ ] official station-context enrichment tests pass
- [ ] Ollama provider tests pass
- [ ] release documentation and manifest tests pass

## C. Manual checks
- [ ] login/admin flow works
- [ ] Playground truncation works
- [ ] paper core preset runs
- [ ] paper supplement preset runs
- [ ] article mode fails explicitly if trained artifacts are missing
- [ ] Forecasting produces CSV, run JSON, summary JSON, and summary CSV artifacts
- [ ] Ridge training produces `training_manifest.json`
- [ ] official context enrichment fails soft when unavailable
- [ ] local LLM path is optional and non-blocking
- [ ] presentation modes produce visibly distinct output forms

## D. Documentation
- [ ] `README.md` reflects the real system and article-ready workflow
- [ ] `docs/design/architecture.md` reflects the real architecture
- [ ] `docs/REPRODUCIBILITY_v0.10.0.md` is current
- [ ] `docs/RUNBOOK_v0.10.0.md` is current
- [ ] `docs/RELEASE_VALIDATION_v0.10.0.md` is current
- [ ] `CHANGELOG.md` includes `v0.10.0` article-ready steps

## E. Article readiness
- [ ] deterministic analysis is the baseline method
- [ ] optional LLM use is clearly secondary/additive
- [ ] fixed evaluation presets are documented for the main and supplementary paper cases
- [ ] exported artifacts needed for figures/examples are reproducible
- [ ] trained-model manifests exist for the article presets
- [ ] experiment summaries are available for manuscript support

## F. Release action
When all items above are checked, create the consolidated release tag:

```bash
git tag -a v0.10.0 -m "WaterAInalytics v0.10.0 - article-ready feature-complete release"
git push origin v0.10.0
```
