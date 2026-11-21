"""Checks semanticos: 'as metricas publicadas merecem confianca?'"""

import copy
from datetime import date

import pytest

from ingestion.normalize import normalize_provider
from quality import semantic_checks as mc
from quality.context import CheckContext
from semantic import load_semantic, metric_expression, metric_sql


def row(**kw):
    base = dict(date=date(2026, 11, 13), provider="voluum", campaign_id="c1", impressions=1000, clicks=10,
                conversions=1, cost=5.0, revenue=7.0)
    return {**base, **kw}


class StubCtx(CheckContext):
    """Contexto sem base de dados: `semantic_value` devolve o valor injetado."""

    def __init__(self, rows, values=None, **kw):
        super().__init__("run-x", "voluum", "semantic", silver_rows=rows, **kw)
        self._values = values or {}

    def semantic_value(self, metric, group_by=None):
        return self._values[metric]


# ----------------------------------------------------------------------------- semantic.yaml
def test_every_ratio_in_semantic_yaml_is_a_ratio_of_sums():
    semantic = load_semantic()
    for name, m in semantic["metrics"].items():
        if m["kind"] == "ratio_of_sums":
            assert "SUM(" in m["expression"] and "AVG" not in m["expression"].upper(), name
    assert metric_expression("cpc") == "SUM(cost) / NULLIF(SUM(clicks), 0)"


def test_metric_sql_is_generated_from_the_yaml_not_duplicated():
    sql = metric_sql("cpc", where="provider = 'voluum'", group_by="campaign_id")
    assert "SUM(cost) / NULLIF(SUM(clicks), 0)" in sql and "GROUP BY campaign_id" in sql


# ----------------------------------------------------------------------------- logica pura
def test_ratio_bounds_flags_impossible_ctr():
    spec = {"name": "b", "bounds": {"ctr": [0, 100], "cr": [0, 100]}}
    ok = mc.ratio_bounds(spec, StubCtx([row()]))[0]
    bad = mc.ratio_bounds(spec, StubCtx([row(clicks=5000)]))[0]               # CTR = 500%
    assert ok.status == "PASS" and bad.status == "FAIL" and bad.details["violations"][0]["metric"] == "ctr"
    assert mc.ratio_bounds(spec, StubCtx([row(conversions=50)]))[0].status == "FAIL"   # CR = 500%


def test_no_avg_of_ratios_catches_a_bad_metric_definition():
    bad = copy.deepcopy(load_semantic())
    bad["metrics"]["cpc"]["expression"] = "AVG(cost / clicks)"
    r = mc.no_avg_of_ratios({"name": "n"}, StubCtx([], semantic=bad))[0]
    assert r.status == "FAIL" and r.details["offenders"] == ["cpc"]
    assert mc.no_avg_of_ratios({"name": "n"}, StubCtx([]))[0].status == "PASS"


def test_ratio_of_sums_fails_when_the_metric_is_an_average_of_ratios():
    rows = [row(cost=10, clicks=100), row(campaign_id="c2", cost=500, clicks=1000)]
    spec = {"name": "r", "metrics": {"cpc": {"numerator": "cost", "denominator": "clicks"}}}
    right = mc.ratio_of_sums(spec, StubCtx(rows, {"cpc": 510 / 1100}))[0]
    wrong = mc.ratio_of_sums(spec, StubCtx(rows, {"cpc": (0.10 + 0.50) / 2}))[0]       # media dos CPC = 0.30
    assert right.status == "PASS" and wrong.status == "FAIL"


def test_roas_must_be_null_when_provider_has_no_revenue():
    spec = {"name": "a", "metric": "roas", "requires": ["revenue"]}
    no_revenue = [row(revenue=None)]
    assert mc.metric_availability(spec, StubCtx(no_revenue, {"roas": None}))[0].status == "PASS"
    assert mc.metric_availability(spec, StubCtx(no_revenue, {"roas": 0.0}))[0].status == "FAIL"   # 0 inventado
    assert mc.metric_availability(spec, StubCtx([row()], {"roas": 1.4}))[0].status == "PASS"
    assert mc.metric_availability(spec, StubCtx([row()], {"roas": None}))[0].status == "FAIL"


def test_metric_vs_provider_converts_currency_before_comparing():
    # custo canonico 92 EUR / 100 clicks = 0.92 EUR/click; provider diz ecpc 1.00 USD, fx 0.92 -> igual
    silver = [row(provider="trafficjunky", campaign_id="t1", cost=92.0, clicks=100)]
    bronze = [dict(day=date(2026, 11, 13), campaign_id="t1", clicks=100, ecpc=1.0, source_currency="USD")]
    spec = {"name": "c", "metric": "cpc", "provider_field": "ecpc", "warn_pct": 3, "fail_pct": 10}
    ctx = StubCtx(silver, bronze_rows=bronze, fx_rates={("2026-11-13", "USD"): 0.92})
    assert mc.metric_vs_provider(spec, ctx)[0].status == "PASS"
    bronze[0]["ecpc"] = 1.06
    r = mc.metric_vs_provider(spec, StubCtx(silver, bronze_rows=bronze, fx_rates={("2026-11-13", "USD"): 0.92}))[0]
    assert r.status == "WARN" and r.observed_value == pytest.approx(0.06, abs=0.001)


# ----------------------------------------------------------------------------- cenarios
def test_healthy_semantic_layer_has_no_issues(healthy_run, get_results):
    issues = {k: r["status"] for k, r in get_results(healthy_run.run_id, "semantic").items() if r["status"] != "PASS"}
    assert issues == {}


def test_roas_exists_only_for_voluum(healthy_run, get_results):
    res = get_results(healthy_run.run_id, "semantic")
    for provider in ("erobella", "trafficjunky", "voluum"):
        assert res[(provider, "semantic_roas_availability")]["status"] == "PASS"
    assert res[("voluum", "semantic_roas_availability")]["details"]["provider_reports_inputs"] is True
    assert res[("trafficjunky", "semantic_roas_availability")]["details"]["provider_reports_inputs"] is False


def test_views_do_not_use_avg_of_ratios(healthy_run, get_results):
    assert get_results(healthy_run.run_id, "semantic")[("platform", "semantic_no_avg_of_ratios")]["status"] == "PASS"


def test_additivity_holds_for_the_real_semantic_layer(healthy_run, get_results):
    res = get_results(healthy_run.run_id, "semantic")
    assert all(res[("voluum", f"semantic_additivity_{m}")]["status"] == "PASS" for m in ("spend", "clicks", "conversions", "revenue"))


def test_ratio_of_sums_check_catches_a_wrong_expression_on_real_data(healthy_run, conn):
    normalize_provider(conn, "voluum", healthy_run.run_id)
    bad = copy.deepcopy(load_semantic())
    bad["metrics"]["cpc"]["expression"] = "AVG(cost / NULLIF(clicks, 0))"
    ctx = CheckContext(healthy_run.run_id, "voluum", "semantic", conn=conn, semantic=bad)
    spec = {"name": "r", "metrics": {"cpc": {"numerator": "cost", "denominator": "clicks"}}}
    assert mc.ratio_of_sums(spec, ctx)[0].status == "FAIL"


def test_broken_trafficjunky_provider_cpc_mismatch_is_detected(broken_run, get_results):
    r = get_results(broken_run.run_id)[("trafficjunky", "trafficjunky_cpc_reconciliation")]
    assert r["status"] == "WARN"
    per = r["details"]["per_campaign"]
    assert per["tj-2002"]["diff_pct"] == pytest.approx(6.0, abs=0.5)
    assert all(abs(v["diff_pct"]) < 0.5 for k, v in per.items() if k != "tj-2002")


def test_voluum_cpc_matches_the_provider_in_both_scenarios(healthy_run, broken_run, get_results):
    for run in (healthy_run, broken_run):
        assert get_results(run.run_id)[("voluum", "voluum_cpc_reconciliation")]["status"] == "PASS"
