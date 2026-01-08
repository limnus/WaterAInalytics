import os
import csv
import time
import requests
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlencode

BASE_TS_ITEMS = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/time-series-metadata/items"

PCODES = ("00060", "00065")

TS_PROPERTIES = "monitoring_location_id,parameter_code,state_name,hydrologic_unit_code"


# -----------------------------
# HTTP helpers
# -----------------------------
def _truncate(s: str, n: int = 800) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else (s[:n] + " …")


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    headers: Dict[str, str],
    *,
    params: Optional[Dict[str, str]] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    method = method.upper()

    if method == "GET":
        r = session.get(url, headers=headers, params=params, timeout=timeout)
    else:
        raise ValueError(f"Unsupported method: {method}")

    if r.status_code >= 400:
        msg = _truncate(r.text)
        raise requests.exceptions.HTTPError(
            f"HTTP {r.status_code} {method} {r.url}\nResponse (truncated): {msg}",
            response=r,
        )

    return r.json()


def find_next(js: Dict[str, Any]) -> Optional[str]:
    for link in js.get("links", []):
        if link.get("rel") == "next" and link.get("href"):
            return link["href"]
    return None


def extract_point(ft: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    geom = ft.get("geometry") or {}
    if geom.get("type") == "Point":
        coords = geom.get("coordinates", [])
        if isinstance(coords, list) and len(coords) >= 2:
            return coords[0], coords[1]  # lon, lat
    return None, None


# -----------------------------
# Core logic (reused as Admin function)
# -----------------------------
def collect_sites_from_time_series_metadata(
    session: requests.Session,
    headers: Dict[str, str],
    parameter_code: str,
    limit: int = 10000,
    polite_sleep_s: float = 0.0,
) -> Dict[str, Dict[str, Any]]:
    """
    Returns dict:
      monitoring_location_id -> base metadata + flags
    """
    params = {
        "f": "json",
        "limit": str(limit),
        "parameter_code": parameter_code,
        "properties": TS_PROPERTIES,
        "skipGeometry": "FALSE",
    }

    url = BASE_TS_ITEMS
    out: Dict[str, Dict[str, Any]] = {}
    page = 0

    while True:
        page += 1
        print(f"[time-series-metadata {parameter_code}] page {page}…")

        js = request_json(session, "GET", url, headers, params=params)
        feats = js.get("features", []) or []

        for ft in feats:
            props = ft.get("properties", {}) or {}
            mid = props.get("monitoring_location_id")
            if not mid:
                continue

            # Restrict to USGS sites only
            if not str(mid).startswith("USGS-"):
                continue

            lon, lat = extract_point(ft)

            rec = out.get(mid)
            if rec is None:
                rec = {
                    "monitoring_location_id": mid,
                    "lat": lat,
                    "lon": lon,
                    "state_name": props.get("state_name"),
                    "hydrologic_unit_code": props.get("hydrologic_unit_code"),
                    "has_00060": False,
                    "has_00065": False,
                }
                out[mid] = rec

            if parameter_code == "00060":
                rec["has_00060"] = True
            elif parameter_code == "00065":
                rec["has_00065"] = True

        next_url = find_next(js)
        if not next_url:
            break

        # Follow next link as-is
        url = next_url
        params = None

        if polite_sleep_s:
            time.sleep(polite_sleep_s)

    return out


def write_base_csv(path: str, data: Dict[str, Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    rows = sorted(data.values(), key=lambda r: r["monitoring_location_id"])
    fieldnames = [
        "monitoring_location_id",
        "lat",
        "lon",
        "state_name",
        "hydrologic_unit_code",
        "has_00060",
        "has_00065",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


# -----------------------------
# Public Admin function
# -----------------------------
def update_usgs_station_cache(
    output_csv_path: str,
    *,
    polite_sleep_s: float = 0.0,
) -> str:
    """
    Admin function.

    Builds (or refreshes) the national list of USGS surface-water stations
    that have parameter 00060 and/or 00065, and writes the BASE CSV.

    Returns
    -------
    str
        Absolute path to the generated CSV file.
    """
    api_key = os.getenv("USGS_API_KEY")

    headers: Dict[str, str] = {
        "User-Agent": "WaterWatch/0.1 (contact: you@example.com)",
    }
    if api_key:
        headers["X-Api-Key"] = api_key

    session = requests.Session()

    merged: Dict[str, Dict[str, Any]] = {}

    for p in PCODES:
        part = collect_sites_from_time_series_metadata(
            session,
            headers,
            p,
            polite_sleep_s=polite_sleep_s,
        )
        for k, v in part.items():
            if k not in merged:
                merged[k] = v
            else:
                merged[k]["has_00060"] = merged[k]["has_00060"] or v["has_00060"]
                merged[k]["has_00065"] = merged[k]["has_00065"] or v["has_00065"]
                if merged[k]["lat"] is None and v["lat"] is not None:
                    merged[k]["lat"] = v["lat"]
                if merged[k]["lon"] is None and v["lon"] is not None:
                    merged[k]["lon"] = v["lon"]

    print(f"USGS stations with 00060/00065: {len(merged)}")

    write_base_csv(output_csv_path, merged)

    return os.path.abspath(output_csv_path)


# -----------------------------
# Local test runner
# -----------------------------
if __name__ == "__main__":
    out = update_usgs_station_cache(
        output_csv_path="usgs_00060_00065_base_from_ts_metadata.csv",
        polite_sleep_s=0.0,
    )
    print(f"Base station list written to:\n  {out}")
