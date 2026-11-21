"""Data Quality Control Center (Streamlit).

REGRA: o dashboard LE a qualidade, nao a define.
Todos os PASS/WARN/FAIL vem de data_quality.check_results; aqui so se filtram, contam e desenham.
Os botoes "Run ... scenario" chamam o pipeline (que corre os checks e grava na tabela); o dashboard nunca decide estados.

    streamlit run dashboard/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # permite `import config`, `import db`...

import altair as alt
import pandas as pd
import streamlit as st

from config import get_settings
from db import connect
from quality.pipeline import run_pipeline

STATUS_COLORS = {"PASS": "#2ecc71", "WARN": "#f1c40f", "FAIL": "#e74c3c"}
STATUS_SCALE = alt.Scale(domain=list(STATUS_COLORS), range=list(STATUS_COLORS.values()))
HEALTH = {"GREEN": "#2ecc71", "YELLOW": "#f1c40f", "RED": "#e74c3c", "GREY": "#6c757d"}
LAYER_NAMES = {"bronze": "Bronze", "silver": "Silver", "semantic": "Gold"}
PROVIDER_NAMES = {"erobella": "Erobella", "trafficjunky": "TrafficJunky", "voluum": "Voluum"}

RESULTS_SQL = """SELECT run_id, checked_at, provider, dataset, layer, check_name, dimension, status,
                        observed_value, expected_value, threshold, details
                 FROM data_quality.check_results ORDER BY checked_at DESC LIMIT 20000"""
RUNS_SQL = "SELECT * FROM data_quality.pipeline_runs ORDER BY started_at DESC LIMIT 200"
API_RUNS_SQL = """SELECT a.run_id, a.provider, a.rows_received, a.total_rows, a.latest_data_date, p.started_at
                  FROM raw.api_runs a JOIN data_quality.pipeline_runs p USING (run_id) ORDER BY p.started_at"""


# ------------------------------------------------------------------ dados (so leitura)
def load_table(sql: str) -> pd.DataFrame:
    with connect() as conn:
        return pd.DataFrame(conn.execute(sql).fetchall())


def load_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    results, runs, api = load_table(RESULTS_SQL), load_table(RUNS_SQL), load_table(API_RUNS_SQL)
    if not results.empty:
        results["checked_at"] = pd.to_datetime(results["checked_at"], utc=True)
        results["message"] = results["details"].map(lambda d: d.get("message", ""))
        results["layer_name"] = results["layer"].map(LAYER_NAMES)
    return results, runs, api


def health_color(counts: dict) -> str:
    """Cor do cartao a partir de contagens JA calculadas pela tabela (nao reavalia nenhum check)."""
    if counts.get("FAIL"):
        return "RED"
    if counts.get("WARN"):
        return "YELLOW"
    return "GREEN" if counts.get("PASS") else "GREY"


def counts_of(df: pd.DataFrame) -> dict:
    return {s: int((df["status"] == s).sum()) for s in STATUS_COLORS} if not df.empty else {}


# ------------------------------------------------------------------ UI helpers
def card(title: str, value: str, color: str = "#e6e6e6", sub: str = "") -> str:
    return (f"<div class='dq-card'><div class='dq-title'>{title}</div>"
            f"<div class='dq-value' style='color:{color}'>{value}</div><div class='dq-sub'>{sub}</div></div>")


CSS = """
<style>
.dq-card {background:#1b1f27; border:1px solid #2c323d; border-radius:10px; padding:14px 16px; height:100%;}
.dq-title {font-size:.78rem; text-transform:uppercase; letter-spacing:.06em; color:#9aa4b2;}
.dq-value {font-size:1.9rem; font-weight:700; line-height:1.25;}
.dq-sub {font-size:.8rem; color:#9aa4b2; min-height:1.1rem;}
.dq-badge {display:inline-block; padding:2px 10px; border-radius:999px; font-weight:700; font-size:.78rem; color:#0e1117;}
.dq-cell {border-radius:8px; padding:8px 10px; text-align:center; font-weight:600; color:#0e1117;}
</style>
"""


def run_controls() -> None:
    st.sidebar.header("Run controls")
    observe = st.sidebar.checkbox("Observe mode", value=True,
                                  help="Observe: um FAIL bloqueia o publish mas as camadas seguintes continuam a ser "
                                       "verificadas (mostra todos os problemas). Desligado = strict: o pipeline para no primeiro FAIL.")
    for label, scenario in (("Run healthy scenario", "healthy"), ("Run broken scenario", "broken")):
        if st.sidebar.button(label, width="stretch"):
            with st.spinner(f"Running {scenario} scenario..."):
                result = run_pipeline(scenario=scenario, gate_mode="observe" if observe else "strict", log=lambda *_: None)
            st.session_state["run_select"] = result.run_id
            st.rerun()


def sidebar_filters(results: pd.DataFrame, runs: pd.DataFrame) -> dict:
    st.sidebar.header("Filters")
    run_ids = list(runs["run_id"])
    labels = {r["run_id"]: f"{r['started_at']:%d %b %H:%M} · {r['scenario']} · {r['status']}" for _, r in runs.iterrows()}
    if st.session_state.get("run_select") not in run_ids:
        st.session_state["run_select"] = run_ids[0]
    run_id = st.sidebar.selectbox("run_id", run_ids, key="run_select", format_func=lambda r: labels[r])
    dates = results["checked_at"].dt.date
    date_range = st.sidebar.date_input("date range", (dates.min(), dates.max()))
    pick = lambda label, col: st.sidebar.multiselect(label, sorted(results[col].unique()))
    return {"run_id": run_id, "date_range": date_range, "provider": pick("provider", "provider"),
            "layer": pick("layer", "layer"), "status": pick("status", "status"), "dimension": pick("dimension", "dimension")}


def apply_filters(results: pd.DataFrame, f: dict) -> pd.DataFrame:
    out = results
    if isinstance(f["date_range"], tuple) and len(f["date_range"]) == 2:
        d = out["checked_at"].dt.date
        out = out[(d >= f["date_range"][0]) & (d <= f["date_range"][1])]
    for col in ("provider", "layer", "status", "dimension"):
        if f[col]:
            out = out[out[col].isin(f[col])]
    return out


# ------------------------------------------------------------------ seccoes
def top_kpis(cur: pd.DataFrame, run: pd.Series, api_cur: pd.DataFrame) -> None:
    c = counts_of(cur)
    total = sum(c.values())
    health = f"{c.get('PASS', 0) / total:.0%}" if total else "n/a"
    latest = api_cur["latest_data_date"].max() if not api_cur.empty else None
    publish = run["status"] if run["status"] in ("PUBLISHED", "BLOCKED") else "RUNNING"
    cols = st.columns(5)
    cols[0].markdown(card("Overall health", health, HEALTH[health_color(c)], f"{total} checks"), unsafe_allow_html=True)
    cols[1].markdown(card("Critical failures", str(c.get("FAIL", 0)), STATUS_COLORS["FAIL"] if c.get("FAIL") else "#e6e6e6"), unsafe_allow_html=True)
    cols[2].markdown(card("Warnings", str(c.get("WARN", 0)), STATUS_COLORS["WARN"] if c.get("WARN") else "#e6e6e6"), unsafe_allow_html=True)
    cols[3].markdown(card("Latest fresh data", f"{latest:%d %b}" if latest is not None and pd.notna(latest) else "n/a"), unsafe_allow_html=True)
    cols[4].markdown(card("Publish status", publish, STATUS_COLORS["FAIL"] if publish == "BLOCKED" else STATUS_COLORS["PASS"] if publish == "PUBLISHED" else "#e6e6e6",
                          f"gate mode: {run['gate_mode']}"), unsafe_allow_html=True)


def provider_cards(cur: pd.DataFrame, api_cur: pd.DataFrame) -> None:
    st.subheader("Provider health")
    cols = st.columns(3)
    for col, provider in zip(cols, PROVIDER_NAMES):
        c = counts_of(cur[cur["provider"] == provider])
        color = health_color(c)
        latest = api_cur[api_cur["provider"] == provider]["latest_data_date"]
        latest_txt = f"{latest.iloc[0]:%d %b}" if len(latest) and pd.notna(latest.iloc[0]) else "n/a"
        col.markdown(
            f"<div class='dq-card'><div class='dq-title'>{PROVIDER_NAMES[provider]}</div>"
            f"<div><span class='dq-badge' style='background:{HEALTH[color]}'>{color}</span></div>"
            f"<div class='dq-sub' style='margin-top:8px'>PASS {c.get('PASS', 0)} · WARN {c.get('WARN', 0)} · FAIL {c.get('FAIL', 0)}</div>"
            f"<div class='dq-sub'>latest data: {latest_txt}</div></div>", unsafe_allow_html=True)


def lineage(cur: pd.DataFrame) -> None:
    st.subheader("Dataset lineage: Bronze → Silver → Gold")
    for provider, name in PROVIDER_NAMES.items():
        cols = st.columns([1.2, 1, 1, 1])
        cols[0].markdown(f"**{name}**")
        for col, layer in zip(cols[1:], LAYER_NAMES):
            sub = cur[(cur["provider"] == provider) & (cur["layer"] == layer)]
            c = counts_of(sub)
            color = health_color(c)
            text = "not run" if not c else ("FAIL" if c.get("FAIL") else "WARN" if c.get("WARN") else "PASS")
            col.markdown(f"<div class='dq-cell' style='background:{HEALTH[color]}'>{LAYER_NAMES[layer]}: {text}</div>", unsafe_allow_html=True)
    st.caption("Layers a provider never reached show 'not run': in strict mode a FAIL stops the pipeline before the next layer.")


def charts(results_f: pd.DataFrame, cur: pd.DataFrame, api: pd.DataFrame, runs: pd.DataFrame) -> None:
    left, right = st.columns(2)

    with left:
        st.markdown("**1. Quality status over time**")
        if results_f.empty:
            st.caption("no data for these filters")
        else:
            started = runs.set_index("run_id")["started_at"]
            over = results_f.groupby(["run_id", "status"]).size().reset_index(name="checks")
            over["run"] = over["run_id"].map(lambda r: f"{started[r]:%d %b %H:%M}" if r in started else r)
            st.altair_chart(alt.Chart(over).mark_bar().encode(
                x=alt.X("run:N", sort=None, title=None), y=alt.Y("checks:Q", title="checks"),
                color=alt.Color("status:N", scale=STATUS_SCALE, sort=["PASS", "WARN", "FAIL"]),
                tooltip=["run", "status", "checks"]).properties(height=240), use_container_width=True)

    with right:
        st.markdown("**2. Provider health (selected run)**")
        if cur.empty:
            st.caption("no data for these filters")
        else:
            ph = cur.groupby(["provider", "status"]).size().reset_index(name="checks")
            st.altair_chart(alt.Chart(ph).mark_bar().encode(
                x=alt.X("provider:N", title=None), y="checks:Q",
                color=alt.Color("status:N", scale=STATUS_SCALE), tooltip=["provider", "status", "checks"]).properties(height=240),
                use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.markdown("**3. Freshness lag (hours, selected run)**")
        fr = cur[cur["details"].map(lambda d: d.get("check_type") == "freshness")]
        if fr.empty:
            st.caption("no freshness checks in this selection")
        else:
            base = alt.Chart(fr).encode(x=alt.X("provider:N", title=None))
            bars = base.mark_bar().encode(y=alt.Y("observed_value:Q", title="lag (h)"),
                                          color=alt.Color("status:N", scale=STATUS_SCALE, legend=None),
                                          tooltip=["provider", "observed_value", "threshold", "status"])
            rule = base.mark_tick(color="#ffffff", thickness=2, size=40).encode(y="threshold:Q")
            st.altair_chart((bars + rule).properties(height=240), use_container_width=True)
            st.caption("White tick = maximum delay allowed by the check.")

    with right:
        st.markdown("**4. Row volume over time (rows received per run)**")
        if api.empty:
            st.caption("no API runs yet")
        else:
            st.altair_chart(alt.Chart(api).mark_line(point=True).encode(
                x=alt.X("started_at:T", title=None), y=alt.Y("rows_received:Q", title="rows"),
                color="provider:N", tooltip=["provider", "rows_received", "total_rows", "started_at"]).properties(height=240),
                use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.markdown("**5. Reconciliation difference % (selected run)**")
        rec = cur[cur["dimension"] == "reconciliation"].copy()
        if rec.empty:
            st.caption("no reconciliation checks in this selection")
        else:
            rec["diff_pct"] = rec["details"].map(lambda d: d.get("diff_pct", 0.0))
            rec["check"] = rec["provider"] + " · " + rec["check_name"]
            st.altair_chart(alt.Chart(rec).mark_bar().encode(
                y=alt.Y("check:N", sort="-x", title=None), x=alt.X("diff_pct:Q", title="difference %"),
                color=alt.Color("status:N", scale=STATUS_SCALE, legend=None),
                tooltip=["check", "diff_pct", "status"]).properties(height=max(240, 18 * len(rec))), use_container_width=True)

    with right:
        st.markdown("**6. Failed checks by dimension (selected run)**")
        bad = cur[cur["status"] != "PASS"]
        if bad.empty:
            st.caption("nothing failing: every check passed")
        else:
            bd = bad.groupby(["dimension", "status"]).size().reset_index(name="checks")
            st.altair_chart(alt.Chart(bd).mark_bar().encode(
                y=alt.Y("dimension:N", sort="-x", title=None), x="checks:Q",
                color=alt.Color("status:N", scale=STATUS_SCALE), tooltip=["dimension", "status", "checks"]).properties(height=240),
                use_container_width=True)


def failing_checks_and_drilldown(cur: pd.DataFrame) -> None:
    st.subheader("Latest failing checks")
    bad = cur[cur["status"] != "PASS"].copy()
    if bad.empty:
        st.success("No WARN or FAIL in this selection.")
        return
    bad["order"] = bad["status"].map({"FAIL": 0, "WARN": 1})
    bad = bad.sort_values(["order", "provider", "layer", "check_name"])
    st.dataframe(bad[["status", "provider", "layer_name", "check_name", "dimension", "observed_value", "expected_value", "message"]],
                 width="stretch", hide_index=True)

    st.subheader("Drill-down")
    labels = {i: f"{r['status']} · {r['provider']} · {r['check_name']}" for i, r in bad.iterrows()}
    chosen = st.selectbox("Select a check", list(labels), format_func=lambda i: labels[i])
    r = bad.loc[chosen]
    d = r["details"]
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown(f"**{r['check_name']}**: {r['message']}")
        st.markdown(f"**Why it matters.** {d.get('why_it_matters') or d.get('description') or '(no description in config)'}")
        if d.get("capped_by_severity"):
            st.info("This check is configured with severity=warning: it can raise WARN but never block the publish. "
                    "An anomaly is not an error: it means *investigate*.")
    with c2:
        st.markdown(f"<span class='dq-badge' style='background:{STATUS_COLORS[r['status']]}'>{r['status']}</span>", unsafe_allow_html=True)
    st.table(pd.DataFrame({"field": ["provider", "layer", "dimension", "observed", "expected", "threshold", "run_id", "checked_at"],
                           "value": [r["provider"], r["layer_name"], r["dimension"], r["observed_value"], r["expected_value"],
                                     r["threshold"], r["run_id"], str(r["checked_at"])]}).astype(str))
    with st.expander("Technical details (details jsonb)"):
        st.json(d)


# ------------------------------------------------------------------ pagina
def main() -> None:
    st.set_page_config(page_title="Data Quality Control Center", page_icon="🛡️", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("Data Quality Control Center")
    st.caption("Bronze → Silver → Gold")

    run_controls()
    try:
        results, runs, api = load_all()
    except Exception as exc:
        st.error(f"Cannot read the quality tables ({type(exc).__name__}). Start PostgreSQL with `docker compose up -d postgres` "
                 f"and check DATABASE_URL ({get_settings().database_url.split('@')[-1]}).")
        st.stop()
    if runs.empty or results.empty:
        st.info("No runs yet. Use **Run healthy scenario** in the sidebar (or `python -m quality.demo_run --scenario healthy`).")
        st.stop()

    filters = sidebar_filters(results, runs)
    results_f = apply_filters(results, filters)
    cur = results_f[results_f["run_id"] == filters["run_id"]]
    run = runs[runs["run_id"] == filters["run_id"]].iloc[0]
    api_cur = api[api["run_id"] == filters["run_id"]] if not api.empty else api

    st.caption("A pipeline that runs successfully is not necessarily a pipeline that produces trustworthy data.")
    top_kpis(cur, run, api_cur)
    st.write("")
    provider_cards(cur, api_cur)
    st.write("")
    lineage(cur)
    st.divider()
    charts(results_f, cur, api, runs)
    st.divider()
    failing_checks_and_drilldown(cur)
    st.caption("The dashboard reads quality. It does not define quality: every status comes from data_quality.check_results.")


main()
