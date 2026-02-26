import os
from datetime import timezone

import pandas as pd
import streamlit as st
import altair as alt

from core.cache.get_station_timeseries import (
    _site_from_monitoring_location_id,
    ensure_iv_window,
    PCODE_FLOW,
    PCODE_STAGE,
    PCODE_TEMP,
    PCODE_SC,
    PCODE_DO,
    PCODE_PH,
    PCODE_TURB,
)
from core.ui.strings.loader import get_strings


# Parâmetros disponíveis (código -> rótulo)
PARAM_LABELS = {
    PCODE_FLOW: "00060 – Flow (Discharge)",
    PCODE_STAGE: "00065 – Stage (Gage height)",
    PCODE_TEMP: "00010 – Water temperature",
    PCODE_SC: "00095 – Specific conductance",
    PCODE_DO: "00300 – Dissolved oxygen",
    PCODE_PH: "00400 – pH",
    PCODE_TURB: "63680 – Turbidity",
}

# Ordem preferida no selectbox
PARAM_ORDER = [
    PCODE_FLOW,
    PCODE_STAGE,
    PCODE_TEMP,
    PCODE_SC,
    PCODE_DO,
    PCODE_PH,
    PCODE_TURB,
]

TIME_WINDOWS_DAYS = [1, 2, 3, 5, 7]

US_TIMEZONES = [
    "UTC",
    "US/Eastern",
    "US/Central",
    "US/Mountain",
    "US/Pacific",
    "US/Alaska",
    "US/Hawaii",
    # "Local station time"  # placeholder futuro
]


def _get_selected_stations_from_session() -> pd.DataFrame:
    """
    Lê de st.session_state["explorer_selected_ids"] a lista de monitoring_location_id,
    gera site_no, retorna um DF com colunas [monitoring_location_id, site_no].
    """
    ids = st.session_state.get("explorer_selected_ids", []) or []
    rows = []
    for mid in ids:
        site = _site_from_monitoring_location_id(mid)
        rows.append(
            {
                "monitoring_location_id": mid,
                "site_no": site,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["monitoring_location_id", "site_no"])
    return pd.DataFrame(rows)


def _role_limitations(
    role: str | None,
    days: int,
    pcode: str,
    tz_name: str,
) -> tuple[int, str, str]:
    """
    Aplica as limitações de role (Playground vs User/Admin) para janela, parâmetro e timezone.
    Retorna (effective_days, effective_pcode, effective_tz) e emite avisos se necessário.
    """
    effective_days = days
    effective_pcode = pcode
    effective_tz = tz_name

    if role and role.lower() == "playground":
        # Playground: apenas 1 dia
        if days > 1:
            effective_days = 1
            st.warning("Playground role is limited to 1-day windows. Using 1 day.")

        # Playground: apenas Stage
        if pcode != PCODE_STAGE:
            effective_pcode = PCODE_STAGE
            st.warning("Playground role is restricted to parameter 00065 (Stage).")

        # Playground: apenas UTC
        if tz_name != "UTC":
            effective_tz = "UTC"
            st.warning("Playground role is restricted to UTC time zone. Using UTC.")

    return effective_days, effective_pcode, effective_tz


def _convert_timezone(df: pd.DataFrame, tz_name: str) -> pd.DataFrame:
    """
    Converte a coluna datetime_utc para um timezone de exibição, criando datetime_plot.
    Assume datetime_utc com timezone UTC (ou converte).
    """
    if df.empty:
        return df

    # Garante datetime_utc como datetime com tz UTC
    if not pd.api.types.is_datetime64tz_dtype(df["datetime_utc"]):
        df = df.copy()
        df["datetime_utc"] = pd.to_datetime(
            df["datetime_utc"], utc=True, errors="coerce"
        )

    if tz_name == "UTC":
        df["datetime_plot"] = df["datetime_utc"]
        return df

    try:
        df = df.copy()
        df["datetime_plot"] = df["datetime_utc"].dt.tz_convert(tz_name)
    except Exception:
        # Se falhar por algum motivo, volta para UTC
        df["datetime_plot"] = df["datetime_utc"]
    return df


def _plot_timeseries(df: pd.DataFrame, param_label: str) -> None:
    if df.empty:
        st.warning("No data available for the selected configuration.")
        return

    with st.expander("Diagnostics (raw IV data)", expanded=False):
        st.write(
            {
                "rows": int(len(df)),
                "datetime_utc_min": str(df["datetime_utc"].min()) if "datetime_utc" in df.columns else None,
                "datetime_utc_max": str(df["datetime_utc"].max()) if "datetime_utc" in df.columns else None,
                "value_dtype": str(df["value"].dtype) if "value" in df.columns else None,
                "value_nunique": int(df["value"].nunique(dropna=True)) if "value" in df.columns else None,
                "value_min": float(pd.to_numeric(df["value"], errors="coerce").min()) if "value" in df.columns else None,
                "value_max": float(pd.to_numeric(df["value"], errors="coerce").max()) if "value" in df.columns else None,
            }
        )

        if "date_utc" in df.columns:
            counts = df.groupby("date_utc").size().sort_index()
            st.write("Rows per day (date_utc):")
            st.dataframe(counts.rename("rows").reset_index(), use_container_width=True)

        st.write("Head (10):")
        st.dataframe(df.head(10), use_container_width=True)
        st.write("Tail (10):")
        st.dataframe(df.tail(10), use_container_width=True)

    # Gráfico de série temporal com uma curva por estação
    chart = (
        alt.Chart(df)
        .mark_line()
        .encode(
            x=alt.X("datetime_plot:T", title="Time"),
            y=alt.Y("value:Q", title=param_label),
            color=alt.Color("site_no:N", title="Station"),
            tooltip=[
                "site_no",
                "datetime_plot:T",
                "value:Q",
                "unit:N",
            ],
        )
        .properties(height=300)
        .interactive()
    )

    st.altair_chart(chart, width="stretch")

    # Boxplot por estação
    box = (
        alt.Chart(df)
        .mark_boxplot()
        .encode(
            x=alt.X("site_no:N", title="Station"),
            y=alt.Y("value:Q", title=param_label),
            color=alt.Color("site_no:N", legend=None),
        )
        .properties(height=200)
    )
    st.altair_chart(box, width="stretch")

    # Resumo estatístico por estação
    stats = (
        df.groupby("site_no")["value"]
        .agg(["count", "min", "max", "mean", "std"])
        .rename(columns={"count": "n"})
    )

    # Último valor por estação
    last_vals = (
        df.sort_values("datetime_utc")
        .groupby("site_no")
        .tail(1)[["site_no", "datetime_utc", "value"]]
        .set_index("site_no")
        .rename(columns={"datetime_utc": "last_time", "value": "last_value"})
    )

    stats = stats.join(last_vals, how="left")

    st.subheader("Summary")
    st.dataframe(stats, width="stretch")


def render_plot_timeseries(role: str | None) -> None:
    """
    Aba 'Plot Time Series'.

    - Usa estações selecionadas na Explorer & Map (st.session_state["explorer_selected_ids"]).
    - Permite escolher janela (1,2,3,5,7 dias) e um parâmetro.
    - Respeita limitações de Playground (1 dia, Stage, UTC, 1 estação).
    - Baixa/cached dados via ensure_iv_window e plota série + boxplot + resumo.
    """
    S = get_strings()

    st.subheader("Selected stations (from Explorer & Map)")
    df_sel = _get_selected_stations_from_session()
    if df_sel.empty:
        st.warning(
            "No stations selected. Please use the 'Explorer & Map' tab to select stations first."
        )
        return

    st.dataframe(df_sel, width="stretch")

    # Seleção efetiva de estações para uso nesta aba
    df_used = df_sel.copy()
    if role and role.lower() == "playground" and len(df_sel) > 1:
        # Para Playground, limitar a uma estação (determinística: menor site_no)
        df_used = df_sel.sort_values("site_no").head(1)
        site_used = df_used.iloc[0]["site_no"]
        st.warning(
            f"Playground role is limited to a single station for plotting. "
            f"Using station {site_used} from the selected set."
        )

    # Controles (colunas: esquerda = configuração, direita = plots)
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.markdown("### Configuration")

        # Janela de tempo (dias)
        default_days = 1
        days_str = st.radio(
            "Time window",
            options=[f"{d} day" if d == 1 else f"{d} days" for d in TIME_WINDOWS_DAYS],
            index=TIME_WINDOWS_DAYS.index(default_days),
        )
        # extrai inteiro
        days = int(days_str.split()[0])
        st.caption(
            "Longer windows may increase download time and local storage usage."
        )

        # Parâmetro (único)
        param_codes = PARAM_ORDER
        default_param = PCODE_STAGE  # Stage como default razoável
        param_labels = [PARAM_LABELS[p] for p in param_codes]
        default_index = param_codes.index(default_param)
        selected_label = st.selectbox(
            "Parameter",
            options=param_labels,
            index=default_index,
        )
        # mapeia de volta para pcode
        label_to_code = {PARAM_LABELS[p]: p for p in param_codes}
        pcode = label_to_code[selected_label]

        # Timezone
        tz_label = st.selectbox("Time zone", options=US_TIMEZONES, index=0)

        st.markdown("---")

        api_key = os.getenv("USGS_API_KEY")
        cache_root = "iv_cache"

        if st.button("Fetch data and plot", type="primary"):
            eff_days, eff_pcode, eff_tz = _role_limitations(role, days, pcode, tz_label)

            all_frames: list[pd.DataFrame] = []
            with st.spinner("Fetching and caching IV data from USGS…"):
                for _, row in df_used.iterrows():
                    site = row["site_no"]
                    try:
                        df_site = ensure_iv_window(
                            site,
                            eff_pcode,
                            days=eff_days,
                            out_root=cache_root,
                            api_key=api_key,
                        )
                    except Exception as e:
                        st.error(f"Error fetching data for site {site}: {e}")
                        continue

                    if df_site.empty:
                        continue

                    # Garante colunas esperadas
                    if "site_no" not in df_site.columns:
                        df_site["site_no"] = site
                    df_site["parameter_code"] = eff_pcode

                    all_frames.append(df_site)

            if not all_frames:
                st.warning("No data returned for the selected configuration.")
                return

            df_all = pd.concat(all_frames, ignore_index=True)

            # Conversão de timezone para exibição
            df_all = _convert_timezone(df_all, eff_tz)

            with col_right:
                st.markdown(
                    f"### Time series – {PARAM_LABELS[eff_pcode]} (TZ: {eff_tz})"
                )
                _plot_timeseries(df_all, PARAM_LABELS[eff_pcode])

        else:
            with col_right:
                st.info(
                    "Configure the options on the left and click "
                    "'Fetch data and plot' to see the plots."
                )
