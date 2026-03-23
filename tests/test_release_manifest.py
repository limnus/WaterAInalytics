from core.release.manifest import build_release_manifest, run_release_smoke_checks
from core.version import APP_VERSION


def test_build_release_manifest_has_expected_sections() -> None:
    manifest = build_release_manifest()
    assert manifest["app_version"] == APP_VERSION
    assert manifest["agentic_analysis"]["deterministic_quantitative_brief"] is True
    assert "required" in manifest["files"]
    assert manifest["forecast_models"]["supported_model_keys"]


def test_release_smoke_checks_pass_in_repo_state() -> None:
    report = run_release_smoke_checks()
    assert report["summary"]["passed"] is True
    assert report["summary"]["missing_required_files"] == []
    assert report["summary"]["import_failures"] == []
