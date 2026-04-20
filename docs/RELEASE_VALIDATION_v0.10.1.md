# WaterAInalytics v0.10.1 — Release Validation

This document defines the final validation workflow for the `v0.10.1` release line.

## Goals

- verify that the documented release assets are present;
- verify that the key runtime modules still import cleanly;
- verify that the release manifest reflects the hardened article-ready workflow;
- export a machine-readable JSON report for archival and audit;
- provide a repeatable operator procedure before tagging the consolidated `v0.10.1` release.

## Command

From the project root, run:

```bash
python run_release_checks.py
```

This writes a JSON report to:

```text
artifacts/release_checks/release_check_report.json
```

## Manifest-only mode

To export only the machine-readable manifest without import smoke checks:

```bash
python run_release_checks.py --manifest-only
```

## Expected pass condition

A successful release check should report:

- `"passed": true`
- no missing required files;
- no import failures in the smoke-check module list;
- release manifest entries for article presets and manuscript-support artifacts;
- strict article-mode validation expectations aligned with the hardened `v0.10.1` behavior.

## Suggested pre-tag routine

1. Run the regression suite used during the `v0.10.1` stabilization steps.
2. Run `python run_release_checks.py`.
3. Open the generated JSON report and verify:
   - version is `v0.10.1`;
   - release docs are present;
   - the key runtime modules import correctly;
   - article-mode expectations and manuscript-support artifacts are present in the manifest.
4. Open the app manually with `streamlit run app.py` and perform a final UI smoke pass for the paper presets.
5. Confirm that a shared export sample does not leak local absolute filesystem paths.
6. Only then create the consolidated `v0.10.1` tag.
