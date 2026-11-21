"""Reconciliacao: Provider API -> Bronze -> Silver -> Gold, e Silver vs daily_control."""

import pytest

from quality import reconciliation as rec
from quality.context import CheckContext


def test_pure_compare_uses_percentage_and_thresholds():
    ctx = CheckContext("r", "voluum", "bronze", api_run={"total_rows": 60}, bronze_rows=[{}] * 50)
    r = rec.reconcile_api_to_bronze({"name": "x", "warn_pct": 0, "fail_pct": 1}, ctx)[0]
    assert (r.status, r.observed_value, r.expected_value) == ("FAIL", 50, 60) and r.details["diff_pct"] == pytest.approx(-16.67, abs=0.01)
    ok = CheckContext("r", "voluum", "bronze", api_run={"total_rows": 50}, bronze_rows=[{}] * 50)
    assert rec.reconcile_api_to_bronze({"name": "x", "warn_pct": 0, "fail_pct": 1}, ok)[0].status == "PASS"


def test_healthy_reconciles_at_every_step(healthy_run, get_results):
    res = get_results(healthy_run.run_id)
    recon = {k: r for k, r in res.items() if r["dimension"] == "reconciliation"}
    assert len(recon) >= 25                                       # api->bronze, bronze->silver, silver->gold, control
    assert {r["status"] for r in recon.values()} == {"PASS"}
    assert any(name.endswith("_spend") for _, name in recon)


def test_bronze_to_silver_spend_applies_the_fx_table(healthy_run, get_results):
    r = get_results(healthy_run.run_id)[("trafficjunky", "silver_bronze_to_silver_spend")]
    assert r["status"] == "PASS" and r["observed_value"] == pytest.approx(r["expected_value"], rel=1e-6)
    assert abs(r["details"]["diff_pct"]) < 0.001


def test_broken_voluum_api_to_bronze_row_count_mismatch(broken_run, get_results):
    r = get_results(broken_run.run_id)[("voluum", "voluum_api_to_bronze_row_count")]
    assert r["status"] == "FAIL" and (r["observed_value"], r["expected_value"]) == (50, 60)


def test_broken_control_reconciliation_flags_missing_data(broken_run, get_results):
    res = get_results(broken_run.run_id)
    assert res[("voluum", "voluum_control_reconciliation_spend")]["status"] == "FAIL"     # dias em falta
    assert res[("voluum", "voluum_control_reconciliation_revenue")]["status"] == "FAIL"
    eb = res[("erobella", "erobella_control_reconciliation_spend")]
    assert eb["status"] == "FAIL" and eb["observed_value"] == 0                            # sem cost_eur (schema drift)


def test_broken_trafficjunky_duplicate_inflates_spend_vs_control(broken_run, get_results):
    r = get_results(broken_run.run_id)[("trafficjunky", "trafficjunky_control_reconciliation_spend")]
    assert r["status"] == "WARN" and 1 < r["details"]["diff_pct"] < 5       # dinheiro contado duas vezes


def test_a_real_spend_drop_is_not_a_reconciliation_error(broken_run, get_results):
    """O spend drop do TrafficJunky e real: o controlo interno concorda. E uma anomalia, nao um erro."""
    res = get_results(broken_run.run_id)
    assert res[("trafficjunky", "daily_volume_change")]["status"] == "WARN"
    assert res[("trafficjunky", "silver_bronze_to_silver_spend")]["status"] == "PASS"
    assert res[("trafficjunky", "trafficjunky_control_reconciliation_spend")]["status"] != "FAIL"


def test_silver_to_gold_matches(healthy_run, get_results):
    res = get_results(healthy_run.run_id)
    assert all(res[(p, f"silver_to_gold_{m}")]["status"] == "PASS" for p in ("erobella", "trafficjunky", "voluum")
               for m in ("spend", "clicks", "conversions"))
