# core/ui/explorer_map.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
from typing import Optional

import pandas as pd
import pydeck as pdk
import streamlit as st

from core.cache.get_stations import update_usgs_station_cache

# Nome do CSV produzido por core/cache/get_stations.py
BASE_STATIONS_FILENAME = "usgs_00060_00065_base_from_ts_metadata.csv"


def _project_root() -> Path:
    # Estamos em core/ui/explorer_map.py → sobe 2 níveis até a raiz do projeto
    # parents[0] = explorer_map.py, [1] = ui, [2] = core, [3] = raiz
    return Path(__file__).resolve().parents[3]


def _stations_csv_path() -> Path:
    data_dir = _project_root() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / BASE_STATIONS_FILENAME


def _file_age(path: Path) -> Optional[timedelta]:
    if not path.exists():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - mtime


def _format_age(age: Optional[timedelta]) -> str:
    if age is None:
        return "missing"
    total_hours = age.total_seconds() / 3600.0
    if total_hours < 1:
        return f"{total_hours:.1f} h"
    total_days = total_hours / 24.0
    if total_days < 1:
        return f"{total_hours:.1f} h"
    return f"{total_days:.1f} d"


@st.cache_data(show_spinner=False)
def _load_stations_df(csv_path_str: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path_str)

    # Normaliza tipos e adiciona colunas de conveniência
    df["monitoring_location_id"] = df["monitoring_location_id"].astype(str)
    df["site_no"] = df["monitoring_location_id"].str.replace("USGS-", "", regex=False)

    # Flags booleanas
    df["has_00060"] = df["has_00060"].astype(bool)
    df["has_00065"] = df["has_00065"].astype(bool)

    # HUC2 / HUC4 derivadas para filtro
    df["hydrologic_unit_code"] = df["hydrologic_unit_code"].astype(str)
    df["HUC2"] = df["hydrologic_unit_code"].str.slice(0, 2)
    df["HUC4"] = df["hydrologic_unit_code"].str.slice(0, 4)

    # lat/lon numéricos e sem NaN
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    return df


def _start_background_refresh(csv_path: Path) -> None:
    """
    Dispara atualização em segundo plano usando threading.
    Evita bloquear o app quando o CSV está apenas levemente desatualizado.
    """
    key = "stations_refresh_in_progress"
    if st.session_state.get(key):
        return

    st.session_state[key] = True

    def _worker() -> None:
        # Importante: não chamar APIs do Streamlit dentro da thread.
        update_usgs_station_cache(output_csv_path=str(csv_path), polite_sleep_s=0.0)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def _ensure_stations_df() -> pd.DataFrame:
    """
    Gera / carrega o DataFrame de estações, aplicando a lógica:

    - Se não existe ou tem > 7 dias: baixa agora (bloco) e carrega.
    - Se tem > 1 dia e <= 7: carrega e dispara atualização em background.
    - Se tem <= 1 dia: apenas carrega.
    """
    csv_path = _stations_csv_path()
    age = _file_age(csv_path)

    status_placeholder = st.empty()

    # Caso 1: inexistente ou muito velho
    if age is None or age > timedelta(days=7):
        with status_placeholder.status(
            "Updating USGS station list (full refresh)…", expanded=True
        ) as st_status:
            out = update_usgs_station_cache(
                output_csv_path=str(csv_path),
                polite_sleep_s=0.0,
            )
            st_status.write(f"Station list written to: `{out}`")
            st_status.update(
                label="USGS station list updated.",
                state="complete",
                expanded=False,
            )

        _load_stations_df.clear()
        df = _load_stations_df(str(csv_path))
        st.info(f"Loaded fresh station list (age: {_format_age(_file_age(csv_path))}).")
        return df

    # Caso 2: entre 1 e 7 dias
    if age > timedelta(days=1):
        st.info(
            f"Using cached station list (age: {_format_age(age)}). "
            "A background refresh has been started; it will be used in future runs."
        )
        _start_background_refresh(csv_path)
        df = _load_stations_df(str(csv_path))
        return df

    # Caso 3: até 24h
    st.success(f"Using recent station list (age: {_format_age(age)}).")
    df = _load_stations_df(str(csv_path))
    return df


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.subheader("Filters")

    with st.expander("Filter stations", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            states = sorted(df["state_name"].dropna().unique())
            state_sel = st.multiselect("State", states, key="expl_states")

        with c2:
            huc2_vals = sorted(df["HUC2"].dropna().unique())
            huc2_sel = st.multiselect("HUC2", huc2_vals, key="expl_huc2")

        with c3:
            require_flow = st.checkbox("Has flow (00060)", value=False, key="expl_flow")
            require_stage = st.checkbox("Has stage (00065)", value=False, key="expl_stage")

        c4, c5 = st.columns([3, 2])
        with c4:
            search_text = st.text_input(
                "Search by station id or state",
                key="expl_search",
                placeholder="e.g., 01013500, Maine, USGS-01013500…",
            )
        with c5:
            huc4_vals = sorted(df["HUC4"].dropna().unique())
            huc4_sel = st.multiselect("HUC4", huc4_vals, key="expl_huc4")

    df_f = df.copy()

    if state_sel:
        df_f = df_f[df_f["state_name"].isin(state_sel)]

    if huc2_sel:
        df_f = df_f[df_f["HUC2"].isin(huc2_sel)]

    if huc4_sel:
        df_f = df_f[df_f["HUC4"].isin(huc4_sel)]

    if require_flow:
        df_f = df_f[df_f["has_00060"]]

    if require_stage:
        df_f = df_f[df_f["has_00065"]]

    if search_text:
        q = search_text.strip().lower()
        if q:
            df_f = df_f[
                df_f["monitoring_location_id"].str.lower().str.contains(q)
                | df_f["site_no"].str.lower().str.contains(q)
                | df_f["state_name"].fillna("").str.lower().str.contains(q)
            ]

    return df_f


def _init_selection_state() -> None:
    if "explorer_selected_ids" not in st.session_state:
        st.session_state["explorer_selected_ids"] = []


def _selection_ui(df_all: pd.DataFrame, df_filtered: pd.DataFrame) -> None:
    _init_selection_state()
    selected_ids = st.session_state["explorer_selected_ids"]

    st.subheader("Selected stations")

    # Mostra tabela com as estações selecionadas
    if selected_ids:
        df_sel = df_all[df_all["monitoring_location_id"].isin(selected_ids)]
        st.dataframe(
            df_sel[
                ["monitoring_location_id", "site_no", "state_name", "hydrologic_unit_code"]
            ].sort_values("monitoring_location_id"),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("No stations selected yet.")

    c1, c2, c3 = st.columns([2, 1, 1])

    # Adicionar nova estação (a partir do conjunto filtrado)
    with c1:
        df_candidates = df_filtered[
            ~df_filtered["monitoring_location_id"].isin(selected_ids)
        ].copy()
        df_candidates["label"] = (
            df_candidates["site_no"].astype(str)
            + " — "
            + df_candidates["state_name"].fillna("")
            + " — HUC "
            + df_candidates["hydrologic_unit_code"].astype(str)
        )

        options = ["(None)"] + df_candidates["label"].tolist()
        choice = st.selectbox(
            "Add station from current filters",
            options=options,
            key="expl_add_choice",
        )

    with c2:
        if st.button("Add", width="stretch"):
            if choice != "(None)":
                sel_row = df_candidates[df_candidates["label"] == choice]
                if not sel_row.empty:
                    mid = sel_row["monitoring_location_id"].iloc[0]
                    if mid not in selected_ids:
                        selected_ids.append(mid)
                        st.session_state["explorer_selected_ids"] = selected_ids
                        st.rerun()

    with c3:
        if st.button("Clear all", width="stretch"):
            st.session_state["explorer_selected_ids"] = []
            st.rerun()

    # Remoção individual opcional
    if selected_ids:
        with st.expander("Remove a single station", expanded=False):
            df_sel = df_all[df_all["monitoring_location_id"].isin(selected_ids)].copy()
            df_sel["label"] = (
                df_sel["site_no"].astype(str)
                + " — "
                + df_sel["state_name"].fillna("")
                + " — HUC "
                + df_sel["hydrologic_unit_code"].astype(str)
            )
            options_rm = df_sel["label"].tolist()
            choice_rm = st.selectbox(
                "Select station to remove",
                options=options_rm,
                key="expl_remove_choice",
            )
            if st.button("Remove selected", width="stretch"):
                row_rm = df_sel[df_sel["label"] == choice_rm]
                if not row_rm.empty:
                    mid_rm = row_rm["monitoring_location_id"].iloc[0]
                    st.session_state["explorer_selected_ids"] = [
                        mid for mid in selected_ids if mid != mid_rm
                    ]
                    st.rerun()


def _map_ui(df_filtered: pd.DataFrame, df_all: pd.DataFrame) -> None:
    st.subheader("Map")

    if df_filtered.empty:
        st.warning("No stations match the current filters.")
        return

    _init_selection_state()
    selected_ids = st.session_state["explorer_selected_ids"]
    df_sel = df_all[df_all["monitoring_location_id"].isin(selected_ids)]

    # Viewport centralizado na média das estações filtradas
    view_state = pdk.ViewState(
        latitude=float(df_filtered["lat"].mean()),
        longitude=float(df_filtered["lon"].mean()),
        zoom=3,
        pitch=0,
    )

    layers = []

    # Todas as estações filtradas (fundo) — pontos pequenos em pixels
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            data=df_filtered,
            get_position="[lon, lat]",
            get_radius=4,                 # raio em pixels
            radius_units="pixels",
            get_fill_color="[160, 160, 160, 120]",
            pickable=True,
        )
    )

    # Estações selecionadas (destaque) — um pouco maiores
    if not df_sel.empty:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=df_sel,
                get_position="[lon, lat]",
                get_radius=7,             # raio em pixels
                radius_units="pixels",
                get_fill_color="[0, 180, 255, 220]",
                pickable=True,
        )
    )

    tooltip = {
        "html": "<b>{monitoring_location_id}</b><br/>{state_name}<br/>HUC {hydrologic_unit_code}",
        "style": {"backgroundColor": "steelblue", "color": "white"},
    }

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style=None,
    )

    st.pydeck_chart(deck, width="stretch")


def render_explorer_map(role: Optional[str] = None) -> None:
    """
    Main entrypoint for the 'Explorer & Map' tab.

    - Carrega / atualiza a base de estações USGS (cache local CSV).
    - Aplica filtros dropdown.
    - Permite gerenciar uma lista de estações selecionadas.
    - Mostra o mapa com destaque para as selecionadas.
    - Para o papel Playground, limita a ~20% das estações.
    """
    st.markdown("### Station Explorer & Map")

    df_all = _ensure_stations_df()

    # Restrição para Playground: subamostra (~20%)
    if role == "Playground" and not df_all.empty:
        df_play = df_all.sample(frac=0.2, random_state=42)
        st.warning(
            f"Playground mode: showing a random subset of {len(df_play)} "
            f"of {len(df_all)} stations (~20%)."
        )
        df_base = df_play
    else:
        df_base = df_all
        st.caption(f"{len(df_base)} stations available.")

    df_filtered = _apply_filters(df_base)

    st.caption(f"{len(df_filtered)} station(s) match current filters.")

    _selection_ui(df_all=df_all, df_filtered=df_filtered)

    # Separador visual entre a lista de estações e o mapa
    st.divider()

    _map_ui(df_filtered=df_filtered, df_all=df_all)
