from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from core.context_enrichment.official_us_context import (
    enrich_us_station_context,
    get_station_context_markdown,
    lookup_station_base_context,
)


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _DummySession:
    def get(self, url, params=None, headers=None, timeout=None):
        if "census" in url:
            return _DummyResponse(
                {
                    "result": {
                        "geographies": {
                            "Counties": [
                                {
                                    "NAME": "Kennebec County",
                                    "GEOID": "23011",
                                    "COUNTY": "011",
                                    "STATE": "23",
                                }
                            ]
                        }
                    }
                }
            )
        if "weather.gov" in url:
            return _DummyResponse(
                {
                    "properties": {
                        "gridId": "GYX",
                        "gridX": 10,
                        "gridY": 20,
                        "forecast": "https://api.weather.gov/gridpoints/GYX/10,20/forecast",
                        "forecastHourly": "https://api.weather.gov/gridpoints/GYX/10,20/forecast/hourly",
                        "forecastOffice": "https://api.weather.gov/offices/GYX",
                        "timeZone": "America/New_York",
                        "relativeLocation": {
                            "properties": {"city": "Augusta", "state": "ME"}
                        },
                    }
                }
            )
        if "epqs" in url:
            return _DummyResponse({"value": 53.2, "units": "Meters", "source": "3DEP"})
        raise AssertionError(f"Unexpected URL: {url}")


def test_lookup_station_base_context_reads_station_csv(tmp_path):
    csv_path = tmp_path / "stations.csv"
    pd.DataFrame(
        [
            {
                "monitoring_location_id": "USGS-01013500",
                "lat": 44.31,
                "lon": -69.78,
                "state_name": "Maine",
                "hydrologic_unit_code": "01030003",
            }
        ]
    ).to_csv(csv_path, index=False)

    ctx = lookup_station_base_context("USGS-01013500", csv_path=csv_path)
    assert ctx["state_name"] == "Maine"
    assert ctx["hydrologic_unit_code"] == "01030003"
    assert ctx["lat"] == 44.31


def test_enrich_station_context_merges_official_sources_and_renders(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pd.DataFrame(
        [
            {
                "monitoring_location_id": "USGS-01013500",
                "lat": 44.31,
                "lon": -69.78,
                "state_name": "Maine",
                "hydrologic_unit_code": "01030003",
            }
        ]
    ).to_csv(data_dir / "usgs_00060_00065_base_from_ts_metadata.csv", index=False)

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    monkeypatch.setattr(
        "core.context_enrichment.official_us_context._stations_csv_path",
        lambda: data_dir / "usgs_00060_00065_base_from_ts_metadata.csv",
    )
    monkeypatch.setattr("core.context_enrichment.official_us_context._context_cache_dir", lambda: cache_dir)
    monkeypatch.setattr("core.context_enrichment.official_us_context.requests.Session", lambda: _DummySession())

    ctx = enrich_us_station_context("USGS-01013500", timeout_s=5, cache_ttl_days=14, force_refresh=True)
    assert ctx["base_context"]["state_name"] == "Maine"
    assert ctx["census"]["county_name"] == "Kennebec County"
    assert ctx["nws"]["forecast_office"] == "GYX"
    assert ctx["elevation"]["elevation_m"] == 53.2
    assert any("Kennebec County" in item for item in ctx["narrative"]["key_findings"])

    md = get_station_context_markdown(ctx)
    assert "Official Station Context" in md
    assert "Elevation (USGS)" in md
    assert "Kennebec County" in md

    cache_file = cache_dir / "USGS-01013500.json"
    assert cache_file.exists()
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["station_id"] == "USGS-01013500"
