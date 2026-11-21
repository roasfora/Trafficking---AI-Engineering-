"""Checks da Silver: 'os dados normalizados fazem sentido?'  + a normalizacao em si."""

from datetime import date

import pytest

from ingestion import normalize as normalize_module
from ingestion.normalize import normalize_provider
from quality import silver_checks as sc
from quality.context import CheckContext


def ctx(rows, provider="voluum", **kw):
    return CheckContext("run-x", provider, "silver", silver_rows=rows, **kw)


def row(**kw):
    base = dict(date=date(2026, 11, 13), provider="voluum", campaign_id="c1", campaign_name="C1", traffic_source="X",
                country="FR", impressions=1000, clicks=10, conversions=1, cost=5.0, revenue=7.0, currency="EUR")
    return {**base, **kw}


# ----------------------------------------------------------------------------- logica pura
def test_not_null_lists_the_columns_with_nulls():
    r = sc.not_null({"name": "n", "columns": ["cost", "clicks"]}, ctx([row(cost=None), row(campaign_id="c2")]))[0]
    assert r.status == "FAIL" and r.details["null_counts"] == {"cost": 1, "clicks": 0} and "cost (1)" in r.message


def test_min_value_and_allowed_values():
    assert sc.min_value({"name": "m", "columns": ["cost"], "min": 0}, ctx([row(cost=-1)]))[0].status == "FAIL"
    assert sc.min_value({"name": "m", "columns": ["cost", "revenue"], "min": 0}, ctx([row(revenue=None)]))[0].status == "PASS"
    spec = {"name": "a", "column": "provider", "allowed": ["voluum"]}
    assert sc.allowed_values(spec, ctx([row(provider="other")]))[0].status == "FAIL"


def test_unique_grain():
    spec = {"name": "u", "keys": ["date", "provider", "campaign_id"]}
    assert sc.unique_grain(spec, ctx([row(), row(campaign_id="c2")]))[0].status == "PASS"
    r = sc.unique_grain(spec, ctx([row(), row()]))[0]
    assert r.status == "FAIL" and r.observed_value == 1


def test_country_and_currency():
    assert sc.country_iso2({"name": "c"}, ctx([row(country=None)]))[0].status == "PASS"   # NULL e valido: o provider nao reporta
    assert sc.country_iso2({"name": "c", "warn_pct": 0, "fail_pct": 100}, ctx([row(country="Portugal")]))[0].status == "WARN"
    assert sc.currency_is_eur({"name": "e"}, ctx([row(currency="USD")]))[0].status == "FAIL"


def test_clicks_le_impressions_warn_then_fail_by_rate():
    spec = {"name": "x", "warn_pct": 0, "fail_pct": 5}
    ok = [row(campaign_id=f"c{i}") for i in range(30)]
    assert sc.clicks_le_impressions(spec, ctx(ok))[0].status == "PASS"
    assert sc.clicks_le_impressions(spec, ctx(ok + [row(clicks=2000)]))[0].status == "WARN"   # 1/31 = 3%
    assert sc.clicks_le_impressions(spec, ctx(ok[:5] + [row(clicks=2000)]))[0].status == "FAIL"  # 1/6 = 17%


def test_conversions_and_cost_invariants():
    spec = {"name": "x", "warn_pct": 0, "fail_pct": 5}
    assert sc.conversions_le_clicks(spec, ctx([row(conversions=99)]))[0].status == "FAIL"
    assert sc.cost_without_impressions(spec, ctx([row(impressions=0)]))[0].status == "FAIL"
    assert sc.cost_without_impressions(spec, ctx([row(impressions=None)]))[0].status == "PASS"   # NULL != 0


def test_revenue_without_conversions_needs_zero_not_null():
    spec = {"name": "r", "warn_pct": 0, "fail_pct": 20}
    assert sc.revenue_without_conversions(spec, ctx([row(conversions=0, revenue=50.0)] + [row(campaign_id=f"c{i}") for i in range(30)]))[0].status == "WARN"
    assert sc.revenue_without_conversions(spec, ctx([row(conversions=None, revenue=50.0)]))[0].status == "PASS"


def test_rolling_avg_change_detects_a_drop_and_reports_numbers():
    days = [date(2026, 11, d) for d in range(1, 9)]
    rows = [row(date=d, cost=1260.0) for d in days[:-1]] + [row(date=days[-1], cost=320.0)]
    r = sc.rolling_avg_change({"name": "v", "metric": "cost", "lookback_days": 7, "warn_pct": 40, "fail_pct": 70}, ctx(rows))[0]
    assert r.status == "FAIL"                                       # -75%: o cap de severidade e aplicado pelo runner
    assert r.observed_value == pytest.approx(-0.746, abs=0.01) and r.expected_value == pytest.approx(1260)
    assert r.threshold == pytest.approx(-0.40)


def test_rolling_avg_change_small_wobble_passes():
    days = [date(2026, 11, d) for d in range(1, 9)]
    rows = [row(date=d, cost=1000.0 + 20 * i) for i, d in enumerate(days)]
    assert sc.rolling_avg_change({"name": "v", "metric": "cost", "warn_pct": 40, "fail_pct": 70}, ctx(rows))[0].status == "PASS"


# ----------------------------------------------------------------------------- cenarios
def test_healthy_silver_has_no_issues(healthy_run, get_results):
    issues = {k: r["status"] for k, r in get_results(healthy_run.run_id, "silver").items() if r["status"] != "PASS"}
    assert issues == {}


def test_broken_trafficjunky_duplicate_breaks_the_silver_grain(broken_run, get_results):
    r = get_results(broken_run.run_id)[("trafficjunky", "silver_unique_grain")]
    assert r["status"] == "FAIL" and r["observed_value"] == 1


def test_broken_trafficjunky_spend_drop_is_an_anomaly_not_an_error(broken_run, get_results):
    r = get_results(broken_run.run_id)[("trafficjunky", "daily_volume_change")]
    assert r["status"] == "WARN"                                        # severity=warning: investigar, nao bloquear
    assert r["details"]["capped_by_severity"] is True                   # o calculo deu FAIL (< -70%) mas foi limitado
    assert -0.80 < r["observed_value"] < -0.70 and r["threshold"] == pytest.approx(-0.40)


def test_broken_voluum_revenue_without_conversions_is_warn(broken_run, get_results):
    r = get_results(broken_run.run_id)[("voluum", "revenue_without_conversions")]
    assert r["status"] == "WARN" and r["observed_value"] == 2


# ----------------------------------------------------------------------------- normalizacao
def test_normalization_has_no_hardcoded_fx_rate():
    sql = normalize_module.SQL["trafficjunky"]
    assert "analytics.exchange_rate" in sql and "0.9" not in sql


def test_trafficjunky_is_converted_with_the_exchange_rate_table(healthy_run, conn):
    normalize_provider(conn, "trafficjunky", healthy_run.run_id)
    bad = conn.execute("""SELECT count(*) AS n FROM analytics.campaign_performance_daily s
                          JOIN raw.trafficjunky_campaign_stats b ON b.run_id = s.run_id AND b.day = s.date AND b.campaign_id = s.campaign_id
                          JOIN analytics.exchange_rate fx ON fx.date = s.date AND fx.source_currency = 'USD'
                          WHERE s.run_id = %s AND abs(s.cost - b.cost * fx.rate) > 1e-6""", (healthy_run.run_id,)).fetchone()["n"]
    assert bad == 0


def test_changing_the_rate_table_changes_silver_not_the_sql(healthy_run, conn):
    day = date(2026, 11, 13)
    original = conn.execute("SELECT rate FROM analytics.exchange_rate WHERE date = %s AND source_currency = 'USD'", (day,)).fetchone()["rate"]
    try:
        conn.execute("UPDATE analytics.exchange_rate SET rate = 1 WHERE date = %s AND source_currency = 'USD'", (day,))
        conn.commit()
        normalize_provider(conn, "trafficjunky", healthy_run.run_id)
        row = conn.execute("""SELECT s.cost AS silver, b.cost AS bronze FROM analytics.campaign_performance_daily s
                              JOIN raw.trafficjunky_campaign_stats b ON b.run_id = s.run_id AND b.day = s.date AND b.campaign_id = s.campaign_id
                              WHERE s.run_id = %s AND s.date = %s LIMIT 1""", (healthy_run.run_id, day)).fetchone()
        assert float(row["silver"]) == pytest.approx(float(row["bronze"]))   # rate = 1 -> USD == EUR
    finally:
        conn.execute("UPDATE analytics.exchange_rate SET rate = %s WHERE date = %s AND source_currency = 'USD'", (original, day))
        conn.commit()
        normalize_provider(conn, "trafficjunky", healthy_run.run_id)


def test_silver_nulls_are_not_zeros(healthy_run, conn):
    normalize_provider(conn, "erobella", healthy_run.run_id)
    normalize_provider(conn, "trafficjunky", healthy_run.run_id)
    row = conn.execute("""SELECT count(*) FILTER (WHERE provider = 'erobella' AND conversions IS NOT NULL) AS eb_conv,
                                 count(*) FILTER (WHERE provider IN ('erobella', 'trafficjunky') AND revenue IS NOT NULL) AS no_rev_conv
                          FROM analytics.campaign_performance_daily WHERE run_id = %s""", (healthy_run.run_id,)).fetchone()
    assert row["eb_conv"] == 0 and row["no_rev_conv"] == 0   # o provider nao reporta -> NULL (nunca 0)
