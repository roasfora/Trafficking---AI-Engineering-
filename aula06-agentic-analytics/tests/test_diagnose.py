from datetime import date

import pytest

from workflows.diagnose_metric_drop import diagnose_metric_drop, format_report

pytestmark = pytest.mark.usefixtures("pg")
DAY = date(2026, 11, 5)


def test_total_cr_drop():
    r = diagnose_metric_drop("conversion_rate", DAY)
    assert (r["previous_value"], r["current_value"]) == (8.15, 7.28)
    assert r["direction"] == "drop"


def test_synonym_is_resolved():
    assert diagnose_metric_drop("taxa de conversão", DAY)["metric"] == "conversion_rate"


def test_provider_rates():
    r = diagnose_metric_drop("conversion_rate", DAY)
    by = {s["segment"]: s for s in r["providers"]}
    assert (by["trafficjunky"]["previous_value"], by["trafficjunky"]["current_value"]) == (8.32, 8.33)
    assert (by["erobella"]["previous_value"], by["erobella"]["current_value"]) == (7.90, 6.03)


def test_contributions_add_up_to_total_change():
    r = diagnose_metric_drop("conversion_rate", DAY)
    assert sum(s["contribution_pp"] for s in r["providers"]) == pytest.approx(r["change_pp"], abs=0.01)
    # campanhas do provider escolhido somam a contribuicao desse provider
    top = next(s for s in r["providers"] if s["segment"] == r["top_provider"])
    assert sum(s["contribution_pp"] for s in r["campaigns"]) == pytest.approx(top["contribution_pp"], abs=0.005)
    for s in r["providers"] + r["campaigns"]:
        assert s["contribution_pp"] == pytest.approx(s["rate_effect_pp"] + s["mix_effect_pp"], abs=0.002)


def test_top_provider_and_campaign():
    r = diagnose_metric_drop("conversion_rate", DAY)
    assert r["top_provider"] == "erobella"
    worst = r["campaigns"][0]  # ordenado do que mais baixou
    assert worst["segment"] == "EB ES Sports Native"
    assert (worst["previous_value"], worst["current_value"]) == (8.57, 2.09)


def test_no_change_stops_early():
    r = diagnose_metric_drop("conversion_rate", date(2026, 11, 3))
    assert r["direction"] == "no_change" and r["providers"] == []
    assert "nada a diagnosticar" in format_report(r)


def test_unsupported_metric():
    r = diagnose_metric_drop("cpc", DAY)
    assert r["supported_metrics"] == ["conversion_rate"]
