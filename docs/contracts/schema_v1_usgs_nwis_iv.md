# WaterWatch Data Contract — v2 (USGS Stations & IV Daily Cache)

This v2 contract supersedes the original **Schema v1 (USGS NWIS IV via HUC8)**, which described
HUC8-aggregated hourly CSV chunks. :contentReference[oaicite:2]{index=2}

The current WaterWatch architecture uses:

1. A **national station catalog** (base CSV) for discovery and mapping.
2. A **per-station, per-parameter, per-day Parquet cache** for Instantaneous Values (IV).

The HUC8, bucketed, and provider-normalized dataframe described in v1 is now considered
a **future aggregation layer** rather than the primary cache format.

---

## 1. Station Catalog — `usgs_00060_00065_base_from_ts_metadata.csv`

### Scope

- Provider: `usgs_stations`
- Source: USGS OGC API — `time-series-metadata` collection
- Stations: only monitoring locations where **parameter 00060 and/or 00065** exists
- Geometry: WGS84 point (lat/lon)

### File location

- Typically under:

  ```text
  {PROJECT_ROOT}/data/usgs_00060_00065_base_from_ts_metadata.csv
Populated/updated by:

python
Copy code
core.cache.get_stations.update_usgs_station_cache(output_csv_path=...)
Columns
Column	Type	Example	Notes
monitoring_location_id	str	USGS-01648000	OGC monitoring_location_id, prefixed with USGS-
lat	float	38.9	Latitude (WGS84)
lon	float	-77.0	Longitude (WGS84)
state_name	str	Maryland	From USGS state_name
hydrologic_unit_code	str	02070010	HUC code (variable length, often 8+ digits)
has_00060	bool	True	Station has discharge (flow) IV metadata
has_00065	bool	True	Station has gage height (stage) IV metadata

Derived columns in the app (not persisted in CSV)
When loaded into the app (see core/ui/explorer_map.py), the following helper columns
are added:

Column	Type	Example	Description
site_no	str	01648000	USGS site number (monitoring_location_id without USGS-)
HUC2	str	02	First 2 digits of hydrologic_unit_code
HUC4	str	0207	First 4 digits of hydrologic_unit_code

These derived fields are not required in the on-disk CSV contract but are considered
part of the in-memory station catalog for UI and selection logic.

2. Instantaneous Values Daily Cache — iv_cache/
Scope
Provider: usgs_nwis_iv

Source: USGS Water Services (NWIS IV)

Temporal granularity: raw IV points, grouped and stored per station / parameter / day

Storage: Parquet files on local disk

Directory layout
All IV cache files are written under a root cache directory, typically:

text
Copy code
{PROJECT_ROOT}/iv_cache/
Within this directory:

text
Copy code
iv_cache/
  {site_no}/
    {parameter_code}/
      {YYYY-MM-DD}.parquet
Where:

site_no — USGS site number (e.g., 01648000)

parameter_code — USGS parameter code (e.g., 00060, 00065, 00010, 00095, 00300, 00400, 63680)

YYYY-MM-DD — date extracted from the IV timestamp (local ISO string prefix)

Example:

text
Copy code
iv_cache/01648000/00060/2026-01-06.parquet
iv_cache/01648000/00065/2026-01-06.parquet
iv_cache/01648000/00010/2026-01-06.parquet
Producer function
Cache files are produced by:

python
Copy code
from core.cache.get_station_timeseries import cache_iv_daily_parquet

data = cache_iv_daily_parquet(
    site="01648000",
    parameter_codes=["00060", "00065", "00010", "00095", "00300", "00400", "63680"],
    days=7,
    out_root="iv_cache",
    api_key=os.getenv("USGS_API_KEY"),
)
days controls the lookback window (P{days}D in NWIS IV).

The function returns data as a dictionary {parameter_code: [(datetime_iso, value), ...]} for in-memory use, while writing Parquets to disk.

Parquet schema (per file)
Each daily Parquet file contains the raw IV points for a given station and parameter,
restricted to a single calendar date (local ISO prefix) extracted from the timestamp.

Columns:

Column	Type	Example	Notes
datetime	str	2026-01-06T17:15:00.000Z	Timestamp from USGS IV, as returned in the JSON dateTime field
value	float	12.34	Parsed numeric value; invalid/non-numeric values become NULL
date	str	2026-01-06	Date extracted from datetime (first 10 characters, YYYY-MM-DD)

Notes:

Timezone semantics follow USGS IV dateTime as-is (often UTC or with offset).

No aggregation is performed in v2: all individual IV points for that day are stored.

Station id (site_no) and parameter code (parameter_code) are encoded in the path,
not repeated as columns inside the Parquet.

3. Parameters of interest (v2)
While the cache can store any IV parameter supported by NWIS, v2 focuses on:

Hydrology (core)
00060 — Discharge (streamflow)

00065 — Gage height (stage)

Water quality (continuous sensors)
00010 — Water temperature

00095 — Specific conductance

00300 — Dissolved oxygen

00400 — pH

63680 — Turbidity

These are the default parameter_codes used by cache_iv_daily_parquet().

4. Future aggregation / HUC-level schema
The HUC8-aggregated hourly CSV schema defined in v1 remains a valid design target
for future aggregation layers (e.g., for ML training and basin-level dashboards), but:

It is no longer the canonical on-disk cache format.

Any future HUC-based schema (v3+) will derive from the per-station Parquet cache
described in v2.
