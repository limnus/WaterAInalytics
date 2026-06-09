from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd


def load_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str | Path, payload: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def parse_utc(ts: str | pd.Timestamp) -> pd.Timestamp:
    out = pd.Timestamp(ts)
    if out.tzinfo is None:
        out = out.tz_localize("UTC")
    else:
        out = out.tz_convert("UTC")
    return out


def iso_utc(ts: str | pd.Timestamp) -> str:
    return parse_utc(ts).isoformat()


def site_no_from_station_id(station_id: str) -> str:
    station = str(station_id).strip()
    if station.upper().startswith("USGS-"):
        return station.split("-", 1)[1]
    return station


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def stable_seed(*parts: Any) -> int:
    joined = "||".join(str(x) for x in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:8]
    return int(digest, 16)


def derive_windows(data_end_utc: str | pd.Timestamp, train_days: int, eval_days: int) -> Dict[str, str]:
    """Derive contiguous hourly windows using inclusive endpoints.

    data_end_utc is treated as the last available hourly timestamp.
    Example for eval_days=7:
      eval window contains exactly 168 hourly timestamps.
    """
    data_end = parse_utc(data_end_utc)
    eval_hours = int(eval_days) * 24
    train_hours = int(train_days) * 24

    eval_end = data_end
    eval_start = eval_end - pd.Timedelta(hours=eval_hours - 1)
    train_end = eval_start - pd.Timedelta(hours=1)
    train_start = train_end - pd.Timedelta(hours=train_hours - 1)

    return {
        "data_end_utc": iso_utc(data_end),
        "train_start_utc": iso_utc(train_start),
        "train_end_utc": iso_utc(train_end),
        "eval_start_utc": iso_utc(eval_start),
        "eval_end_utc": iso_utc(eval_end),
        "expected_train_hours": train_hours,
        "expected_eval_hours": eval_hours,
    }


def normalize_case(case: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(case)
    out["station_id"] = str(out["station_id"])
    out["site_no"] = site_no_from_station_id(out["station_id"])
    out["parameter_code"] = str(out["parameter_code"])
    out["key"] = str(out["key"])
    out["label"] = str(out.get("label") or out["key"])
    out["group"] = str(out.get("group") or "ungrouped")
    out["priority"] = str(out.get("priority") or "preferred")
    out["availability_policy"] = str(out.get("availability_policy") or "include_if_valid")
    return out
