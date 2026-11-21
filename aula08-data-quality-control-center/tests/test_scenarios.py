"""Cenarios e simuladores: determinismo e os 9 problemas plantados."""

from datetime import date, timedelta

import pytest

from simulators import erobella_api, trafficjunky_api, voluum_api
from simulators.scenarios import FAULTS, PROVIDERS, control_rows, fx_rate, load_scenario, simulated_now

AS_OF, DAYS = date(2026, 11, 13), 14


def fetch(module, scenario_name, providers=None):
    scenario = load_scenario(scenario_name, providers)
    return module.fetch(AS_OF, DAYS, scenario, simulated_now(AS_OF))


def test_healthy_has_no_faults_and_broken_has_the_nine():
    assert load_scenario("healthy").faults == frozenset()
    assert load_scenario("broken").faults == frozenset(FAULTS)
    assert len(FAULTS) == 9


def test_provider_filter_limits_faults():
    s = load_scenario("broken", ["voluum"])
    assert s.providers == ("voluum",)
    assert s.faults == {f for f, (p, _, _) in FAULTS.items() if p == "voluum"}


def test_unknown_scenario_or_provider_rejected():
    with pytest.raises(ValueError):
        load_scenario("chaos")
    with pytest.raises(ValueError):
        load_scenario("broken", ["nope"])


def test_simulators_are_deterministic():
    assert fetch(voluum_api, "broken") == fetch(voluum_api, "broken")
    assert fetch(erobella_api, "healthy")["rows"] == fetch(erobella_api, "healthy")["rows"]


def test_healthy_payloads_are_complete():
    e, t, v = (fetch(m, "healthy") for m in (erobella_api, trafficjunky_api, voluum_api))
    assert len(e["rows"]) == 14 and len(t["rows"]) == 56 and len(v["rows"]) == 70
    assert v["meta"]["total_rows"] == 70 and v["meta"]["truncated"] is False


def test_erobella_faults():
    rows = fetch(erobella_api, "broken")["rows"]
    days = {r["day"] for r in rows}
    assert "2026-11-11" not in days                                   # 1. missing day
    assert any(r["clicks"] is None for r in rows)                     # 2. NULL
    assert all("cost_eur" not in r and r["cost"]["amount"] for r in rows)  # 3. schema drift


def test_trafficjunky_faults():
    healthy, broken = fetch(trafficjunky_api, "healthy")["rows"], fetch(trafficjunky_api, "broken")["rows"]
    keys = [(r["day"], r["campaign_id"]) for r in broken]
    assert len(keys) - len(set(keys)) == 1                            # 4. duplicate
    day_cost = lambda rows, d: sum(r["cost"] for r in rows if r["day"] == d)  # noqa: E731
    assert day_cost(broken, "2026-11-13") < 0.3 * day_cost(healthy, "2026-11-13")   # 5. spend drop (~-74%)
    h = next(r for r in healthy if r["campaign_id"] == "tj-2002")
    b = next(r for r in broken if r["campaign_id"] == "tj-2002" and r["day"] == h["day"])
    assert b["ecpc"] == pytest.approx(h["ecpc"] * 1.06, rel=1e-3)     # 6. ecpc mismatch


def test_voluum_faults():
    p = fetch(voluum_api, "broken")
    assert p["meta"]["truncated"] and p["meta"]["total_rows"] > len(p["rows"])      # 7. pagination
    assert max(r["day"] for r in p["rows"]) == "2026-11-11"                           # 8. stale (2 days)
    assert any(r["revenue"] > 0 and r["conversions"] == 0 for r in p["rows"])         # 9. revenue w/o conversions


def test_voluum_conversions_match_report():
    p = fetch(voluum_api, "healthy")
    assert len(p["conversions"]) == sum(r["conversions"] for r in p["rows"])


def test_control_is_independent_of_api_faults_but_knows_the_real_spend_drop():
    healthy, broken = (control_rows(AS_OF, DAYS, load_scenario(n)) for n in ("healthy", "broken"))
    total = lambda rows: sum(r["investment"] for r in rows)  # noqa: E731
    assert total(broken) < total(healthy)  # o spend drop e REAL: o controlo interno tambem o regista
    assert {r["campaign_id"] for r in broken} == {r["campaign_id"] for r in healthy}


def test_fx_rate_is_stable_and_plausible():
    assert fx_rate(date(2026, 11, 13)) == fx_rate(date(2026, 11, 13))
    assert all(0.90 < fx_rate(AS_OF - timedelta(days=i)) < 0.94 for i in range(30))


def test_every_planted_problem_names_a_check_that_exists_in_the_config():
    """A tabela dos 9 problemas (README) tem de apontar para checks reais."""
    from quality.runner import load_checks

    names = {c["name"] for c in load_checks()}
    for fault, (_, _, detected_by) in FAULTS.items():
        check = detected_by.split(" ")[0]
        assert check in names, f"{fault}: check {check!r} not in quality_checks.yaml"
