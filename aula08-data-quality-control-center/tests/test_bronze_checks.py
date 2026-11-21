"""Checks da Bronze: 'recebemos os dados corretamente?'"""

from datetime import date, datetime, timedelta, timezone

import pytest

from quality import bronze_checks as bc
from quality.context import CheckContext

UTC = timezone.utc


def ctx(provider="voluum", **data):
    return CheckContext("run-x", provider, "bronze", as_of=date(2026, 11, 13), window=14, **data)


# ----------------------------------------------------------------------------- logica pura (sem base de dados)
def api_run(**kw):
    base = dict(requested_at=datetime(2026, 11, 14, 6, tzinfo=UTC), latest_data_date=date(2026, 11, 13), total_rows=10,
                truncated=False, messages=[], response_fields=["a", "b"])
    return {**base, **kw}


def test_freshness_pass_warn_fail():
    spec = {"name": "f", "max_delay_hours": 30}
    assert bc.freshness(spec, ctx(api_run=api_run()))[0].status == "PASS"                                   # 6h
    assert bc.freshness(spec, ctx(api_run=api_run(latest_data_date=date(2026, 11, 12))))[0].status == "WARN"  # 30h*0.8 < 30h <= 30h
    r = bc.freshness(spec, ctx(api_run=api_run(latest_data_date=date(2026, 11, 11))))[0]                       # 54h
    assert r.status == "FAIL" and r.observed_value == pytest.approx(54)


def test_freshness_without_data_fails():
    assert bc.freshness({"name": "f", "max_delay_hours": 30}, ctx(api_run=api_run(latest_data_date=None)))[0].status == "FAIL"


def test_schema_diff_missing_is_fail_new_field_is_warn():
    spec = {"name": "s", "expected_fields": ["a", "b"]}
    assert bc.schema_diff(spec, ctx(api_run=api_run(response_fields=["a", "b"])))[0].status == "PASS"
    assert bc.schema_diff(spec, ctx(api_run=api_run(response_fields=["a", "b", "c"])))[0].status == "WARN"
    r = bc.schema_diff(spec, ctx(api_run=api_run(response_fields=["a", "cost"])))[0]
    assert r.status == "FAIL" and r.details["missing_fields"] == ["b"] and r.details["unexpected_fields"] == ["cost"]


def test_row_count_reports_missing_days():
    days = [date(2026, 11, 13) - timedelta(days=i) for i in range(14) if i != 2]
    rows = [{"day": d} for d in days]
    r = bc.row_count({"name": "c", "keys": ["day"], "entities_per_day": 1, "warn_pct": 0, "fail_pct": 5}, ctx(bronze_rows=rows))[0]
    assert r.status == "FAIL" and r.details["missing_dates"] == ["2026-11-11"]
    assert (r.observed_value, r.expected_value) == (13, 14)


def test_null_rate_thresholds():
    spec = {"name": "n", "columns": ["clicks"], "warn_pct": 5, "fail_pct": 20}
    rows = lambda nulls: [{"clicks": None if i < nulls else 1} for i in range(20)]  # noqa: E731
    assert bc.null_rate(spec, ctx(bronze_rows=rows(0)))[0].status == "PASS"
    assert bc.null_rate(spec, ctx(bronze_rows=rows(2)))[0].status == "WARN"    # 10%
    assert bc.null_rate(spec, ctx(bronze_rows=rows(6)))[0].status == "FAIL"    # 30%


def test_duplicate_rows_uses_the_business_key():
    rows = [{"day": "d1", "campaign_id": "a", "cost": 1}, {"day": "d1", "campaign_id": "a", "cost": 2},
            {"day": "d1", "campaign_id": "b", "cost": 3}]
    r = bc.duplicate_rows({"name": "d", "keys": ["day", "campaign_id"]}, ctx(bronze_rows=rows))[0]
    assert r.status == "FAIL" and r.observed_value == 1   # mesma chave com valores diferentes tambem conta


def test_pagination_and_truncation():
    rows = [{"day": date(2026, 11, 13)}] * 5
    r = bc.pagination_complete({"name": "p"}, ctx(api_run=api_run(total_rows=9), bronze_rows=rows))[0]
    assert (r.status, r.observed_value, r.expected_value) == ("FAIL", 5, 9)
    assert bc.pagination_complete({"name": "p"}, ctx(api_run=api_run(total_rows=5), bronze_rows=rows))[0].status == "PASS"
    assert bc.truncated_response({"name": "t"}, ctx(api_run=api_run(truncated=True)))[0].status == "FAIL"
    assert bc.truncated_response({"name": "t"}, ctx(api_run=api_run()))[0].status == "PASS"


# ----------------------------------------------------------------------------- cenarios (base de dados)
def test_healthy_bronze_has_no_issues(healthy_run, get_results):
    issues = {k: r["status"] for k, r in get_results(healthy_run.run_id, "bronze").items() if r["status"] != "PASS"}
    assert issues == {}


def test_broken_erobella_missing_day_detected(broken_run, get_results):
    r = get_results(broken_run.run_id)[("erobella", "erobella_coverage")]
    assert r["status"] == "FAIL" and r["details"]["missing_dates"] == ["2026-11-11"]


def test_broken_erobella_unexpected_null_is_warn(broken_run, get_results):
    r = get_results(broken_run.run_id)[("erobella", "erobella_clicks_null_rate")]
    assert r["status"] == "WARN" and r["details"]["worst_column"] == "clicks"


def test_broken_erobella_schema_drift_detected(broken_run, get_results):
    r = get_results(broken_run.run_id)[("erobella", "erobella_schema")]
    assert r["status"] == "FAIL"
    assert r["details"]["missing_fields"] == ["cost_eur"] and r["details"]["unexpected_fields"] == ["cost"]


def test_broken_trafficjunky_duplicate_detected(broken_run, get_results):
    r = get_results(broken_run.run_id)[("trafficjunky", "trafficjunky_duplicates")]
    assert r["status"] == "FAIL" and r["observed_value"] == 1


def test_broken_voluum_pagination_and_truncation_detected(broken_run, get_results):
    res = get_results(broken_run.run_id)
    page = res[("voluum", "voluum_pagination")]
    assert page["status"] == "FAIL" and (page["observed_value"], page["expected_value"]) == (50, 60)
    assert res[("voluum", "voluum_truncated")]["status"] == "FAIL"


def test_broken_voluum_stale_data_detected(broken_run, get_results):
    r = get_results(broken_run.run_id)[("voluum", "voluum_freshness")]
    assert r["status"] == "FAIL" and r["observed_value"] == pytest.approx(54)


def test_bronze_preserves_what_the_provider_said(broken_run, conn):
    """Schema drift: a coluna tipada fica NULL (nada e 'corrigido'); a linha original fica intacta em raw_payload."""
    row = conn.execute("""SELECT cost_eur, raw_payload FROM raw.erobella_daily_stats WHERE run_id = %s LIMIT 1""",
                       (broken_run.run_id,)).fetchone()
    assert row["cost_eur"] is None and "amount" in row["raw_payload"]["cost"]


def test_bronze_does_not_convert_currency(healthy_run, conn):
    row = conn.execute("""SELECT cost, currency, source_currency FROM raw.trafficjunky_campaign_stats
                          WHERE run_id = %s LIMIT 1""", (healthy_run.run_id,)).fetchone()
    assert row["currency"] == row["source_currency"] == "USD"
