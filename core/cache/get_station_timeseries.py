import os
import csv
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

import requests
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
    (LEGACY: sem unidade. Mantido para compatibilidade.)
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


def _parse_iv_json_with_unit(js: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Versão estendida: retorna {pcode: {"unit": unit_str_or_None, "points": [(datetime_iso, value), ...]}}
    Usada pelo novo fluxo de cache em Parquet com unidade.
    """
    out: Dict[str, Dict[str, Any]] = {}

    for ts in (js.get("value", {}) or {}).get("timeSeries", []) or []:
        var = ts.get("variable", {}) or {}
        vcode_list = var.get("variableCode", []) or []
        pcode = None
        if vcode_list and isinstance(vcode_list, list):
            pcode = vcode_list[0].get("value")

        if not pcode:
            continue

        unit = None
        unit_info = var.get("unit") or {}
        if isinstance(unit_info, dict):
            unit = (unit_info.get("unitCode") or "").strip() or None

        values_blocks = ts.get("values", []) or []
        pts: List[Tuple[str, Optional[float]]] = []
        if values_blocks:
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

        out[pcode] = {
            "unit": unit,
            "points": pts,
        }

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

    LEGACY: retorna dict pcode -> lista de (datetime_iso, valor).
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

    OBS: fluxo LEGACY, sem unidade. Mantido para compatibilidade.
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

    # Grava Parquets diários (LEGACY: sem coluna unit, datetime como string)
    for pcode, pts in data.items():
        if not pts:
            continue
        df = pd.DataFrame(pts, columns=["datetime", "value"])
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


# -------------------------------------------------------------------
# NOVO FLUXO: ensure_iv_window – cache diário em Parquet com unidade e UTC
# -------------------------------------------------------------------

def ensure_iv_window(
    site: str,
    parameter_code: str,
    *,
    days: int = 7,
    out_root: str = "iv_cache",
    api_key: Optional[str] = None,
    timeout: int = 60,
) -> pd.DataFrame:
    """
    Garante que, para um site + parâmetro + janela (em dias, terminando em hoje UTC),
    existam Parquets diários em:

        {out_root}/{site}/{parameter_code}/{YYYY-MM-DD}.parquet

    Schema sugerido dos Parquets "novos":
        - site_no         (str)
        - parameter_code  (str)
        - unit            (str ou None)
        - datetime_utc    (datetime64[ns, UTC])
        - value           (float, com NaN)
        - date_utc        (str, YYYY-MM-DD)

    O fluxo:
    1. Verifica quais dias da janela já têm arquivo Parquet.
    2. Para dias faltantes, faz uma requisição IV (startDT/endDT) e grava apenas o que não existe.
    3. Lê todos os Parquets da janela e retorna um DataFrame concatenado (pode estar vazio).

    Compatível com Parquets "legados" (sem 'unit' etc.): se o arquivo existir mas sem coluna 'unit',
    será lido assim mesmo; as colunas ausentes aparecerão como NaN.
    """
    if days <= 0:
        raise ValueError("days must be a positive integer")

    # Hoje (UTC) como referência
    today_utc = datetime.utcnow().date()
    window_dates = [today_utc - timedelta(days=i) for i in range(days)]

    # Caminhos esperados
    base_dir = os.path.join(out_root, site, parameter_code)
    expected_paths = {
        d: os.path.join(base_dir, f"{d.isoformat()}.parquet") for d in window_dates
    }

    # Quais dias já têm arquivo?
    existing_dates = [d for d, p in expected_paths.items() if os.path.exists(p)]
    missing_dates = [d for d in window_dates if d not in existing_dates]

    # Se houver dias faltantes, faz uma chamada IV para cobrir a janela mínima
    if missing_dates:
        earliest = min(missing_dates)
        latest = max(missing_dates)

        # Intervalo [earliest, latest+1 dia) em UTC
        startDT = f"{earliest.isoformat()}T00:00:00Z"
        endDT = f"{(latest + timedelta(days=1)).isoformat()}T00:00:00Z"

        params: Dict[str, str] = {
            "format": "json",
            "sites": site,
            "parameterCd": parameter_code,
            "startDT": startDT,
            "endDT": endDT,
        }
        if api_key:
            params["api_key"] = api_key

        headers: Dict[str, str] = {
            "User-Agent": "WaterWatch/0.1 (contact: you@example.com)",
            "Accept": "application/json",
        }

        with requests.Session() as session:
            js = _request_json(session, IV_ENDPOINT, params=params, headers=headers, timeout=timeout)

        parsed = _parse_iv_json_with_unit(js)
        meta = parsed.get(parameter_code, {"unit": None, "points": []})
        unit = meta.get("unit")
        points = meta.get("points") or []

        if points:
            df_all = pd.DataFrame(points, columns=["datetime_iso", "value"])
            # Converte explicitamente para datetime UTC
            df_all["datetime_utc"] = pd.to_datetime(df_all["datetime_iso"], utc=True, errors="coerce")
            df_all = df_all.dropna(subset=["datetime_utc"])
            df_all["date_utc"] = df_all["datetime_utc"].dt.date.astype(str)

            # Colunas fixas
            df_all["site_no"] = site
            df_all["parameter_code"] = parameter_code
            df_all["unit"] = unit

            os.makedirs(base_dir, exist_ok=True)

            # Para cada dia faltante, grava se houver pontos
            for d in missing_dates:
                day_str = d.isoformat()
                df_day = df_all[df_all["date_utc"] == day_str]
                if df_day.empty:
                    continue
                out_path = expected_paths[d]
                df_day[
                    ["site_no", "parameter_code", "unit", "datetime_utc", "value", "date_utc"]
                ].to_parquet(out_path, index=False)

    # Agora lê todos os Parquets da janela (inclusive os "legados")
    frames: List[pd.DataFrame] = []
    for d, path in expected_paths.items():
        if not os.path.exists(path):
            # Sem dados para esse dia; ok, pode haver buracos
            continue
        try:
            df_day = pd.read_parquet(path)
        except Exception:
            # Se o arquivo estiver corrompido ou incompatível, ignora (ou poderia logar)
            continue

        # Harmoniza algumas colunas esperadas; se não existirem, cria
        if "site_no" not in df_day.columns:
            df_day["site_no"] = site
        if "parameter_code" not in df_day.columns:
            df_day["parameter_code"] = parameter_code
        if "unit" not in df_day.columns:
            df_day["unit"] = None

        # datetime_utc pode estar como string ou datetime sem timezone; tentar converte
        if "datetime_utc" in df_day.columns:
            df_day["datetime_utc"] = pd.to_datetime(
                df_day["datetime_utc"], utc=True, errors="coerce"
            )
        elif "datetime" in df_day.columns:
            df_day["datetime_utc"] = pd.to_datetime(
                df_day["datetime"], utc=True, errors="coerce"
            )
        else:
            # sem datetime, esse arquivo não serve para séries; ignora
            continue

        if "date_utc" not in df_day.columns:
            df_day["date_utc"] = df_day["datetime_utc"].dt.date.astype(str)

        frames.append(df_day)

    if not frames:
        return pd.DataFrame(
            columns=["site_no", "parameter_code", "unit", "datetime_utc", "value", "date_utc"]
        )

    df_out = pd.concat(frames, ignore_index=True)
    # Ordena por tempo
    df_out = df_out.sort_values("datetime_utc").reset_index(drop=True)
    return df_out


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
            # Baixa todos os parâmetros (hydro + qualidade) e grava Parquets diários (LEGACY)
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

        # Além disso, testa ensure_iv_window para um parâmetro, usando a mesma janela:
        try:
            df_test = ensure_iv_window(
                site,
                PCODE_STAGE,
                days=days,
                out_root=out_root,
                api_key=api_key,
                timeout=60,
            )
            print(f"ensure_iv_window: site={site} pcode={PCODE_STAGE} rows={len(df_test)}")
        except Exception as e:
            print(f"ensure_iv_window error for site={site}: {e}")
