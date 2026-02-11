from __future__ import annotations

import json
from pathlib import Path

from core.ml.mock_artifacts import generate_mock_ridge_artifacts


def test_generate_mock_ridge_artifacts_writes_json(tmp_path: Path):
    paths = generate_mock_ridge_artifacts(
        data_root=tmp_path,
        station_id="USGS-00000000",
        parameter_code="00060",
    )

    assert paths.base_dir().exists()
    for p in [paths.feature_spec_path(), paths.tuning_path(), paths.metrics_path()]:
        assert p.exists()
        obj = json.loads(p.read_text(encoding="utf-8"))
        assert isinstance(obj, dict)
