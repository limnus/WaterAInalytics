from pathlib import Path

from core.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_app_version_is_v093() -> None:
    assert APP_VERSION == "v0.9.3"


def test_release_docs_exist() -> None:
    expected = [
        ROOT / "README.md",
        ROOT / "CHANGELOG.md",
        ROOT / "docs" / "design" / "architecture.md",
        ROOT / "docs" / "REPRODUCIBILITY_v0.9.3.md",
        ROOT / "docs" / "RUNBOOK_v0.9.3.md",
        ROOT / "docs" / "CODE_FREEZE_CHECKLIST_v0.9.3.md",
        ROOT / ".gitattributes",
    ]
    missing = [str(path.relative_to(ROOT)) for path in expected if not path.exists()]
    assert not missing, f"Missing release docs/artifacts: {missing}"
