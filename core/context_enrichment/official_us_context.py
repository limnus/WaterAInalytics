from __future__ import annotations

import json
import math
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import requests

_BASE_STATIONS_FILENAME = "usgs_00060_00065_base_from_ts_metadata.csv"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _stations_csv_path() -> Path:
    return _project_root() / "data" / _BASE_STATIONS_FILENAME


def _context_cache_dir() -> Path:
    p = Path(tempfile.gettempdir()) / "waterainalytics_station_context"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_path(station_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (station_id or "unknown"))
    return _context_cache_dir() / f"{safe}.json"


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    if not math.isfinite(out):
        return None
    return out


def _get_int_env(name: str, default: int, *, min_value: int, max_value: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return max(min_value, min(max_value, value))


def _get_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def lookup_station_base_context(station_id: str, csv_path: str | Path | None = None) -> Dict[str, Any]:
    path = Path(csv_path) if csv_path else _stations_csv_path()
    base: Dict[str, Any] = {
        "station_id": station_id,
        "lat": None,
        "lon": None,
        "state_name": None,
        "hydrologic_unit_code": None,
    }
    if not path.exists():
        return base

    try:
        df = pd.read_csv(path, dtype={"monitoring_location_id": str, "hydrologic_unit_code": str, "state_name": str})
    except Exception:
        return base

    if "monitoring_location_id" not in df.columns:
        return base

    row = df[df["monitoring_location_id"].astype(str) == str(station_id)]
    if row.empty:
        return base
    rec = row.iloc[0]
    return {
        "station_id": str(station_id),
        "lat": _safe_float(rec.get("lat")),
        "lon": _safe_float(rec.get("lon")),
        "state_name": (str(rec.get("state_name")).strip() if pd.notna(rec.get("state_name")) else None),
        "hydrologic_unit_code": (str(rec.get("hydrologic_unit_code")).strip() if pd.notna(rec.get("hydrologic_unit_code")) else None),
    }


def _fetch_census_county(*, lat: float, lon: float, timeout_s: int, session: requests.Session) -> Dict[str, Any]:
    url = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
    params = {
        "x": f"{lon:.6f}",
        "y": f"{lat:.6f}",
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "layers": "Census Counties",
        "format": "json",
    }
    r = session.get(url, params=params, timeout=timeout_s)
    r.raise_for_status()
    js = r.json() or {}
    counties = (((js.get("result") or {}).get("geographies") or {}).get("Counties") or [])
    if not counties:
        return {"status": "empty"}
    c0 = counties[0] or {}
    return {
        "status": "ok",
        "county_name": c0.get("NAME") or c0.get("BASENAME"),
        "county_geoid": c0.get("GEOID"),
        "county_fips": c0.get("COUNTY"),
        "state_fips": c0.get("STATE"),
    }


def _fetch_nws_point(*, lat: float, lon: float, timeout_s: int, session: requests.Session) -> Dict[str, Any]:
    url = f"https://api.weather.gov/points/{lat:.6f},{lon:.6f}"
    headers = {"User-Agent": "WaterAInalytics/0.9.3 (station-context)"}
    r = session.get(url, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    js = r.json() or {}
    p = js.get("properties") or {}
    rel = ((p.get("relativeLocation") or {}).get("properties") or {})
    return {
        "status": "ok",
        "forecast_office": p.get("gridId") or p.get("cwa"),
        "forecast_grid_x": p.get("gridX"),
        "forecast_grid_y": p.get("gridY"),
        "forecast_url": p.get("forecast"),
        "forecast_hourly_url": p.get("forecastHourly"),
        "forecast_office_url": p.get("forecastOffice"),
        "relative_city": rel.get("city"),
        "relative_state": rel.get("state"),
        "time_zone": p.get("timeZone"),
    }


def _fetch_epqs_elevation(*, lat: float, lon: float, timeout_s: int, session: requests.Session) -> Dict[str, Any]:
    url = "https://epqs.nationalmap.gov/v1/json"
    params = {
        "x": f"{lon:.6f}",
        "y": f"{lat:.6f}",
        "units": "Meters",
        "wkid": "4326",
        "includeDate": "false",
    }
    r = session.get(url, params=params, timeout=timeout_s)
    r.raise_for_status()
    js = r.json() or {}

    value = js.get("value")
    units = js.get("units")
    source = js.get("source")

    if value is None:
        q = (((js.get("USGS_Elevation_Point_Query_Service") or {}).get("Elevation_Query") or {}))
        value = q.get("Elevation")
        units = units or q.get("Units")
        source = source or q.get("Data_Source")

    elev = _safe_float(value)
    if elev is None:
        return {"status": "empty"}

    return {
        "status": "ok",
        "elevation_m": elev,
        "elevation_units": units or "Meters",
        "elevation_source": source or "USGS EPQS / 3DEP",
    }


def _load_cache(station_id: str, *, ttl_days: int) -> Optional[Dict[str, Any]]:
    path = _cache_path(station_id)
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    ts = float(obj.get("cached_at_epoch") or 0)
    if ts <= 0:
        return None
    age_s = time.time() - ts
    if age_s > ttl_days * 86400:
        return None
    return obj


def _save_cache(station_id: str, obj: Dict[str, Any]) -> None:
    path = _cache_path(station_id)
    payload = dict(obj)
    payload["cached_at_epoch"] = int(time.time())
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def build_station_context_narrative(station_context: Dict[str, Any]) -> Dict[str, Any]:
    base = station_context.get("base_context") or {}
    census = station_context.get("census") or {}
    nws = station_context.get("nws") or {}
    elevation = station_context.get("elevation") or {}

    findings = []
    limitations = []
    open_questions = []

    county_name = census.get("county_name")
    state_name = base.get("state_name") or nws.get("relative_state")
    huc = base.get("hydrologic_unit_code")
    lat = base.get("lat")
    lon = base.get("lon")
    elevation_m = elevation.get("elevation_m")
    office = nws.get("forecast_office")

    if lat is not None and lon is not None:
        findings.append(f"Station coordinates are approximately {lat:.4f}, {lon:.4f}.")
    if county_name or state_name:
        county_part = county_name or "an unresolved county"
        state_part = state_name or "an unresolved state"
        findings.append(f"The monitoring point falls in {county_part}, {state_part}.")
    if huc:
        findings.append(f"The station is tagged with hydrologic unit code {huc}.")
    if elevation_m is not None:
        findings.append(f"Approximate ground elevation at the monitoring point is {elevation_m:.1f} m above sea level.")
    if office:
        findings.append(f"The nearest National Weather Service forecast grid is associated with office {office}.")
    if nws.get("forecast_url"):
        findings.append("A point forecast URL is available from the official NWS API for this location.")

    if not findings:
        limitations.append("Official station context could not be enriched from the currently available station metadata and remote services.")
    if not elevation_m:
        limitations.append("Elevation could not be resolved from the official USGS point service for this station.")
    if not county_name:
        limitations.append("County-level geography could not be resolved from the Census geocoder for this station.")
    if not office:
        limitations.append("NWS point metadata could not be resolved for this station, so local forecast-office context is missing.")

    open_questions.append(
        "Would adding land-cover, canopy, imperviousness, and watershed-boundary layers materially improve forecast interpretation for this station?"
    )

    return {
        "key_findings": findings,
        "limitations": limitations,
        "open_questions": open_questions,
    }


def enrich_us_station_context(
    station_id: str,
    *,
    timeout_s: Optional[int] = None,
    cache_ttl_days: Optional[int] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    enabled = _get_bool_env("STATION_CONTEXT_ENRICHMENT_ENABLED", True)
    timeout_s = timeout_s or _get_int_env("STATION_CONTEXT_TIMEOUT_S", 15, min_value=3, max_value=120)
    cache_ttl_days = cache_ttl_days or _get_int_env("STATION_CONTEXT_CACHE_DAYS", 14, min_value=1, max_value=180)

    base = lookup_station_base_context(station_id)
    out: Dict[str, Any] = {
        "station_id": station_id,
        "enabled": enabled,
        "retrieved_at_utc": _utc_now_iso(),
        "base_context": base,
        "census": {"status": "skipped"},
        "nws": {"status": "skipped"},
        "elevation": {"status": "skipped"},
        "sources": [
            {
                "name": "local_station_cache",
                "path": str(_stations_csv_path()),
                "status": "ok" if base.get("lat") is not None and base.get("lon") is not None else "missing_or_unresolved",
            }
        ],
    }

    if not enabled:
        out["narrative"] = build_station_context_narrative(out)
        return out

    if not force_refresh:
        cached = _load_cache(station_id, ttl_days=cache_ttl_days)
        if cached is not None:
            cached["cache_hit"] = True
            return cached

    lat = _safe_float(base.get("lat"))
    lon = _safe_float(base.get("lon"))
    if lat is None or lon is None:
        out["narrative"] = build_station_context_narrative(out)
        _save_cache(station_id, out)
        return out

    session = requests.Session()
    fetchers = [
        ("census", _fetch_census_county, "https://geocoding.geo.census.gov/geocoder/"),
        ("nws", _fetch_nws_point, "https://api.weather.gov"),
        ("elevation", _fetch_epqs_elevation, "https://epqs.nationalmap.gov/v1/docs"),
    ]
    for key, fn, source_url in fetchers:
        try:
            out[key] = fn(lat=lat, lon=lon, timeout_s=timeout_s, session=session)
        except Exception as e:
            out[key] = {"status": "error", "error": f"{type(e).__name__}: {e}"}
        out["sources"].append({"name": key, "url": source_url, "status": out[key].get("status")})

    out["narrative"] = build_station_context_narrative(out)
    out["cache_hit"] = False
    _save_cache(station_id, out)
    return out


def get_station_context_markdown(station_context: Dict[str, Any]) -> str:
    lines = []
    base = station_context.get("base_context") or {}
    census = station_context.get("census") or {}
    nws = station_context.get("nws") or {}
    elevation = station_context.get("elevation") or {}
    narrative = station_context.get("narrative") or {}

    lines.append("#### Official Station Context")
    lines.append("")
    lines.append(f"- **Station:** {station_context.get('station_id')}")
    if base.get("state_name"):
        lines.append(f"- **State:** {base.get('state_name')}")
    if base.get("hydrologic_unit_code"):
        lines.append(f"- **HUC:** {base.get('hydrologic_unit_code')}")
    if base.get("lat") is not None and base.get("lon") is not None:
        lines.append(f"- **Coordinates:** {base.get('lat'):.4f}, {base.get('lon'):.4f}")
    if census.get("county_name"):
        lines.append(f"- **County (Census):** {census.get('county_name')} ({census.get('county_geoid') or 'GEOID NA'})")
    if elevation.get("elevation_m") is not None:
        lines.append(f"- **Elevation (USGS):** {elevation.get('elevation_m'):.1f} m")
    if nws.get("forecast_office"):
        lines.append(f"- **NWS office/grid:** {nws.get('forecast_office')} ({nws.get('forecast_grid_x')}, {nws.get('forecast_grid_y')})")
    if nws.get("forecast_url"):
        lines.append(f"- **NWS point forecast URL:** {nws.get('forecast_url')}")
    lines.append("")

    for title, key in (
        ("Context Findings", "key_findings"),
        ("Context Limitations", "limitations"),
        ("Open Questions", "open_questions"),
    ):
        items = [x for x in (narrative.get(key) or []) if isinstance(x, str) and x.strip()]
        if not items:
            continue
        lines.append(f"#### {title}")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines).strip()
