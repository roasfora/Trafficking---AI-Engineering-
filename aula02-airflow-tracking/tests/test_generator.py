"""O gerador tem de ser determinístico (a base da idempotencia) e coerente."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pytest

from api import generator

UTC = timezone.utc
D1 = datetime(2026, 10, 1, tzinfo=UTC)
D2 = D1 + timedelta(days=1)
D3 = D1 + timedelta(days=2)


def test_same_seed_same_data():
    a = generator.list_conversions(42, D1, D2)
    generator._day.cache_clear()
    assert generator.list_conversions(42, D1, D2) == a and len(a) > 0


def test_different_seed_different_click_ids():
    ids = lambda seed: {c["click_id"] for c in generator.list_conversions(seed, D1, D2)}  # noqa: E731
    assert ids(42).isdisjoint(ids(7))


def test_window_is_independent_of_how_it_is_requested():
    """[d1,d3) == [d1,d2) + [d2,d3): sem registos perdidos ou repetidos na fronteira."""
    for fn in (generator.list_conversions, generator.list_campaign_costs, generator.list_daily_control):
        assert fn(42, D1, D3) == fn(42, D1, D2) + fn(42, D2, D3)


def test_conversions_are_windowed_by_postback_timestamp():
    for c in generator.list_conversions(42, D1, D2):
        assert D1 <= c["postback_timestamp"] < D2


def test_postback_never_before_visit_and_stays_in_the_visit_day():
    convs = generator.list_conversions(42, D1, D3)
    assert convs
    for c in convs:
        assert c["postback_timestamp"] >= c["visit_timestamp"]
        assert c["postback_timestamp"].date() == c["visit_timestamp"].date()


def test_conversion_key_is_unique_but_click_id_is_not():
    convs = generator.list_conversions(42, D1, D3)
    keys = [(c["click_id"], c["conversion_type_id"], c["postback_timestamp"]) for c in convs]
    assert len(set(keys)) == len(keys)
    assert len({c["click_id"] for c in convs}) < len(convs)  # clicks com 2 conversoes (tipos 1 e 2)


def test_campaign_cost_grain_is_unique_and_hourly():
    costs = generator.list_campaign_costs(42, D1, D2)
    keys = [(c["datetime"], c["campaign_id"], c["investment_provider"]) for c in costs]
    assert len(set(keys)) == len(keys)
    assert all(c["datetime"].minute == 0 and c["datetime"].second == 0 for c in costs)
    assert {c["datetime"].hour for c in costs} == set(range(24))


def test_some_providers_have_null_impressions():
    costs = generator.list_campaign_costs(42, D1, D2)
    assert {c["investment_provider"] for c in costs if c["impressions"] is None} == {"pushground", "reactiveclicks"}
    assert all(c["clicks"] is not None for c in costs)


def test_a_campaign_can_have_several_providers_in_the_same_hour():
    per_hour = defaultdict(set)
    for c in generator.list_campaign_costs(42, D1, D2):
        per_hour[(c["datetime"], c["campaign_id"])].add(c["investment_provider"])
    assert max(len(v) for v in per_hour.values()) == 2


def test_daily_control_reconciles_with_the_events_unless_manual():
    for day_start in (D1, D2):
        day_end = day_start + timedelta(days=1)
        revenue, cost = defaultdict(float), defaultdict(float)
        for c in generator.list_conversions(42, day_start, day_end):
            revenue[c["campaign_id"]] += c["revenue"]
        for c in generator.list_campaign_costs(42, day_start, day_end):
            cost[c["campaign_id"]] += c["cost"]
        rows = generator.list_daily_control(42, day_start, day_end)
        assert rows
        for r in rows:
            if not r["is_manual"]:
                assert r["revenue"] == pytest.approx(revenue[r["campaign_id"]], abs=0.01)
                assert r["investment"] == pytest.approx(cost[r["campaign_id"]], abs=0.01)


def test_some_daily_control_rows_are_manual():
    rows = generator.list_daily_control(42, D1, D1 + timedelta(days=30))
    assert 0 < sum(r["is_manual"] for r in rows) < len(rows)


def test_revenue_in_usd_follows_the_offer_currency():
    eur_offer = next(o for o in generator.OFFERS if o["currency_code"] == "EUR")
    convs = [c for c in generator.list_conversions(42, D1, D3) if c["offer_id"] == eur_offer["offer_id"]]
    assert convs
    for c in convs:
        assert c["revenue"] == pytest.approx(c["revenue_original_currency"] * 1.08, abs=1e-3)


def test_filters():
    camp = generator.CAMPAIGNS[0]["campaign_id"]
    rows = generator.list_conversions(42, D1, D2, campaign_id=camp)
    assert rows and all(r["campaign_id"] == camp for r in rows)
    ts = generator.TRAFFIC_SOURCES[0]["traffic_source_id"]
    costs = generator.list_campaign_costs(42, D1, D2, traffic_source_id=ts)
    assert costs and len(costs) < len(generator.list_campaign_costs(42, D1, D2))


def test_conversion_traffic_source_matches_its_campaign():
    ts_of = {c["campaign_id"]: c["traffic_source_id"] for c in generator.CAMPAIGNS}
    assert all(c["traffic_source_id"] == ts_of[c["campaign_id"]] for c in generator.list_conversions(42, D1, D3))


def test_paused_campaigns_have_no_traffic():
    paused = [c["campaign_id"] for c in generator.CAMPAIGNS if c["is_paused"]]
    assert paused
    for cid in paused:
        assert generator.list_campaign_costs(42, D1, D3, campaign_id=cid) == []


def test_returned_rows_are_copies():
    row = generator.list_conversions(42, D1, D2)[0]
    row["revenue"] = -999
    assert generator.list_conversions(42, D1, D2)[0]["revenue"] != -999
