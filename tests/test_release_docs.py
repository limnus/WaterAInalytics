from pathlib import Path

from core.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_app_version_is_v0101() -> None:
    assert APP_VERSION == "v0.10.1"


def test_release_docs_exist() -> None:
    expected = [
        ROOT / "README.md",
        ROOT / "CHANGELOG.md",
        ROOT / "docs" / "design" / "architecture.md",
        ROOT / "docs" / "REPRODUCIBILITY_v0.10.1.md",
        ROOT / "docs" / "RUNBOOK_v0.10.1.md",
        ROOT / "docs" / "CODE_FREEZE_CHECKLIST_v0.10.1.md",
        ROOT / "docs" / "RELEASE_VALIDATION_v0.10.1.md",
        ROOT / ".gitattributes",
    ]
    missing = [str(path.relative_to(ROOT)) for path in expected if not path.exists()]
    assert not missing, f"Missing release docs/artifacts: {missing}"
