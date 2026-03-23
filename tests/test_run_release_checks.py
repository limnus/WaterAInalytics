from pathlib import Path

from run_release_checks import main


def test_run_release_checks_manifest_only_writes_report(tmp_path: Path) -> None:
    out = tmp_path / "manifest_only.json"
    rc = main(["--manifest-only", "--output", str(out)])
    assert rc == 0
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert '"manifest"' in text


def test_run_release_checks_full_writes_report(tmp_path: Path) -> None:
    out = tmp_path / "release_report.json"
    rc = main(["--output", str(out)])
    assert rc == 0
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert '"summary"' in text
    assert '"passed": true' in text.lower()
