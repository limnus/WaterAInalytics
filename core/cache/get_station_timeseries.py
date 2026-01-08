import os
import csv
import random
import requests
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd  # para salvar em Parquet

IV_ENDPOINT = "https://waterservices.usgs.gov/nwis/iv/"

# Alvos: flow e stage
PCODE_FLOW = "00060"
PCODE_STAGE = "00065"

# Parâmetros de qualidade de água contínuos mais comuns
PCODE_TEMP = "00010"   # Water temperature
PCODE_SC   = "00095"   # Specific conductance
PCODE_DO   = "00300"   # Dissolved oxygen
PCODE_PH   = "00400"   # pH
PCODE_TURB = "63680"   # Turbidity

# Conjuntos úteis
HYDRO_PARAMETERS = [PCODE_FLOW, PCODE_STAGE]
QW_PARAMETERS = [PCODE_TEMP, PCODE_SC, PCODE_DO, PCODE_PH, PCODE_TURB]
ALL_PARAMETERS = HYDRO_PARAMETERS + QW_PARAMETERS


def _site_from_monitoring_location_id(mid: str) -> str:
    # "USGS-01013500" -> "01013500"
    return str(mid).replace("USGS-", "").strip()


def load_base_station_ids(base_csv_path: str) -> List[str]:
    """
    Loads the base CSV produced by your OGC discovery step and returns
    a list of USGS site numbers (e.g., "01013500").
    """
    sites: List[str] = []
    with open(base_csv_path, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            mid = (row.get("monitoring_location_id") or "").strip()
            if not mid.startswith("USGS-"):
                continue
            sites.append(_site_from_monitoring_location_id(mid))

    # remove duplicates while preserving order
    seen = set()
    uniq = []
    for s in sites:
        if s and s not in seen:
            uniq.append(s)
            seen.add(s)
    return uniq


def _request_json(
    session: requests.Session,
    url: str,
    params: Dict[str, str],
    headers: Dict[str, str],
    timeout: int = 60,
) -> Dict[str, Any]:
    r = session.get(url, params=params, headers=headers, timeout=timeout)
    # IV returns 4xx on "no data" combos sometimes; keep it explicit
    r.raise_for_status()
    return r.json()


def _parse_iv_json(js: Dict[str, Any]) -> Dict[str, List[Tuple[str, Optional[float]]]]:
    """
    Returns {parameter_code: [(datetime_iso, value_float_or_None), ...]}
    """
    out: Dict[str, List[Tuple[str, Optional[float]]]] = {}

    for ts in (js.get("value", {}) or {}).get("timeSeries", []) or []:
        var = ts.get("variable", {}) or {}
        vcode_list = var.get("variableCode", []) or []
        pcode = None
        if vcode_list and isinstance(vcode_list, list):
            pcode = vcode_list[0].get("value")

        if not pcode:
            continue

        values_blocks = ts.get("values", []) or []
        if not values_blocks:
            out.setdefault(pcode, [])
            continue

        # Typically one block in values[]
        pts: List[Tuple[str, Optional[float]]] = []
        for block in values_blocks:
            for v in block.get("value", []) or []:
                dt = v.get("dateTime")
                sval = v.get("value")
                if not dt:
                    continue
                try:
                    fval = float(sval) if sval is not None and sval != "" else None
                except Exception:
                    fval = None
                pts.append((dt, fval))

        out[pcode] = pts

    return out


def fetch_iv_timeseries(
    site: str,
    *,
    parameter_codes: List[str] = None,
    period: Optional[str] = "P7D",
    startDT: Optional[str] = None,
    endDT: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, List[Tuple[str, Optional[float]]]]:
    """
    Fetch IV time series for a given USGS site.

    Rules (per USGS docs):
    - Do not mix period with startDT/endDT.
    - If endDT is provided, startDT must also be provided.
    """
    if parameter_codes is None:
        parameter_codes = HYDRO_PARAMETERS  # mantém comportamento anterior

    if endDT and not startDT:
        raise ValueError("endDT requires startDT (per USGS IV rules).")

    if period and (startDT or endDT):
        raise ValueError("Do not mix period with startDT/endDT (per USGS IV rules).")

    params: Dict[str, str] = {
        "format": "json",
        "sites": site,
        "parameterCd": ",".join(parameter_codes),
    }

    if period:
        params["period"] = period
    if startDT:
        params["startDT"] = startDT
    if endDT:
        params["endDT"] = endDT

    headers: Dict[str, str] = {
        "User-Agent": "WaterWatch/0.1 (contact: you@example.com)",
        "Accept": "application/json",
    }

    # Water Services supports api_key as query param. Some deployments also accept headers,
    # but the doc commonly references api_key via api.data.gov. If you have a key, add it here.
    if api_key:
        params["api_key"] = api_key

    with requests.Session() as session:
        js = _request_json(session, IV_ENDPOINT, params=params, headers=headers, timeout=timeout)

    return _parse_iv_json(js)


def cache_iv_daily_parquet(
    site: str,
    *,
    parameter_codes: Optional[List[str]] = None,
    days: int = 7,
    out_root: str = "iv_cache",
    api_key: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, List[Tuple[str, Optional[float]]]]:
    """
    Baixa IV para um site, separa por parâmetro e data, e grava Parquets diários:

        {out_root}/{site}/{parameter}/{YYYY-MM-DD}.parquet

    Retorna o mesmo dict que fetch_iv_timeseries: {pcode: [(datetime_iso, value), ...]}.
    """
    if parameter_codes is None:
        parameter_codes = ALL_PARAMETERS

    # Usa janela relativa em dias (ex.: P7D)
    period = f"P{int(days)}D"

    data = fetch_iv_timeseries(
        site,
        parameter_codes=parameter_codes,
        period=period,
        api_key=api_key,
        timeout=timeout,
    )

    # Grava Parquets diários
    for pcode, pts in data.items():
        if not pts:
            continue
        df = pd.DataFrame(pts, columns=["datetime", "value"])
        # Usa a parte YYYY-MM-DD do datetime ISO
        df["date"] = df["datetime"].str.slice(0, 10)

        for day, df_day in df.groupby("date"):
            out_dir = os.path.join(out_root, site, pcode)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{day}.parquet")
            df_day.to_parquet(out_path, index=False)

    return data


def _summarize_series(points: List[Tuple[str, Optional[float]]]) -> str:
    if not points:
        return "no points"
    # Points arrive time-ordered for most requests; still be defensive:
    points_sorted = sorted(points, key=lambda x: x[0])
    first_dt, first_val = points_sorted[0]
    last_dt, last_val = points_sorted[-1]
    return f"n={len(points_sorted)} first={first_dt} last={last_dt} last_value={last_val}"


if __name__ == "__main__":
    # ---- CONFIG ----
    base_csv = "usgs_00060_00065_base_from_ts_metadata.csv"  # ajuste se necessário
    sample_n = 5
    days = 7  # janela usada para cache (P7D)
    out_root = "iv_cache"

    api_key = os.getenv("USGS_API_KEY")  # opcional

    sites = load_base_station_ids(base_csv)
    if not sites:
        raise SystemExit(f"No USGS sites found in base CSV: {base_csv}")

    if sample_n > len(sites):
        sample_n = len(sites)

    sample_sites = random.sample(sites, k=sample_n)

    print(f"Loaded {len(sites)} sites from base CSV.")
    print(f"Sampling {len(sample_sites)} sites: {', '.join(sample_sites)}\n")

    for site in sample_sites:
        print("=" * 80)
        print(f"Site: {site}")

        try:
            # Baixa todos os parâmetros (hydro + qualidade) e grava Parquets diários
            data = cache_iv_daily_parquet(
                site,
                parameter_codes=ALL_PARAMETERS,
                days=days,
                out_root=out_root,
                api_key=api_key,
                timeout=60,
            )
        except requests.exceptions.HTTPError as e:
            print(f"HTTPError for site={site}: {e}")
            continue
        except Exception as e:
            print(f"Error for site={site}: {e}")
            continue

        # ---- Resumo para TODOS os parâmetros retornados ----
        if not data:
            print("No parameters returned.")
        else:
            for pcode, pts in data.items():
                print(f"{pcode}: {_summarize_series(pts)}")
