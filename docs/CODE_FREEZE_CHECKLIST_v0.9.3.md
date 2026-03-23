# Code freeze checklist — v0.9.3

Use this checklist before creating the consolidated `v0.9.3` tag.

## A. Code and configuration
- [ ] `core/version.py` shows `v0.9.3`
- [ ] `.env.example` includes every runtime knob needed by the app
- [ ] no secrets are hard-coded
- [ ] no placeholder-only production-facing tabs remain in the article scope
- [ ] line-ending policy file is committed (`.gitattributes`)

## B. Tests
- [ ] targeted regression suite passes locally
- [ ] deterministic quantitative brief tests pass
- [ ] official station-context enrichment tests pass
- [ ] Ollama provider tests pass
- [ ] release documentation test passes

## C. Manual checks
- [ ] login/admin flow works
- [ ] Playground truncation works
- [ ] Forecasting produces both CSV and JSON artifacts
- [ ] multi-station forecast hand-off works in Agentic Analysis
- [ ] official context enrichment fails soft when unavailable
- [ ] local LLM path is optional and non-blocking
- [ ] presentation modes produce visibly distinct output forms

## D. Documentation
- [ ] `README.md` reflects the real system, not the old skeleton
- [ ] `docs/design/architecture.md` reflects the real architecture
- [ ] `docs/REPRODUCIBILITY_v0.9.3.md` is current
- [ ] `docs/RUNBOOK_v0.9.3.md` is current
- [ ] `CHANGELOG.md` includes `v0.9.3` hardening steps

## E. Article readiness
- [ ] deterministic analysis is the baseline method
- [ ] optional LLM use is clearly secondary/additive
- [ ] fixed evaluation stations are documented for demonstration
- [ ] exported artifacts needed for figures/examples are reproducible
- [ ] open UX backlog items are documented and not mistaken for completed scope

## F. Release action
When all items above are checked, create the consolidated release tag:

```bash
git tag -a v0.9.3 -m "WaterAInalytics v0.9.3 - article hardening consolidated release"
git push origin v0.9.3
```
