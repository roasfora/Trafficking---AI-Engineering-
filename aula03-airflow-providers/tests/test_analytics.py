"""As views: racios recalculados a partir das metricas base."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from contracts.canonical import CampaignDailyStat
from pipeline import load

C1 = UUID("0b6116c0-9ed5-5398-8df0-72911f86933f")
C2 = UUID("85e7e1f3-64a2-50c6-a56a-5f6fa9915c19")
DAY = date(2026, 10, 20)


def stat(**kw):
    base = dict(date=DAY, provider="erobella", campaign_id=C2, source_specific_id="a", currency="EUR",
                impressions=10_000, clicks=200, cost=Decimal("50"))
    return CampaignDailyStat(**{**base, **kw})


def one(conn, query, *params):
    return conn.execute(query, params).fetchone()


def test_ratios_are_derived_from_the_base_metrics(conn):
    load.upsert_stats(conn, [stat()])
    cpc, cpm, ctr = one(conn, "SELECT cpc, cpm, ctr FROM v_stat_ratios")
    assert (cpc, cpm, ctr) == (Decimal("0.25"), Decimal("5"), Decimal("0.02"))  # 50/200, 50/10000*1000, 200/10000


def test_division_by_zero_gives_null_not_an_error(conn):
    load.upsert_stats(conn, [stat(clicks=0, impressions=0)])
    assert one(conn, "SELECT cpc, cpm, ctr FROM v_stat_ratios") == (None, None, None)


def test_creatives_are_summed_before_dividing(conn):
    """Soma primeiro, divide depois: o CPC da campanha nao e a media dos CPC dos creatives."""
    load.upsert_stats(conn, [
        stat(source_specific_id="a", clicks=100, cost=Decimal("10")),    # cpc 0.10
        stat(source_specific_id="b", clicks=300, cost=Decimal("90")),    # cpc 0.30
    ])
    right, wrong = one(conn, "SELECT v.cpc, (SELECT round(avg(cpc), 4) FROM v_stat_ratios) FROM v_campaign_daily v")
    assert right == Decimal("0.25") and wrong == Decimal("0.2")  # 100/400 vs (0.1+0.3)/2


def test_a_campaign_view_row_per_provider_and_currency(conn):
    """Moedas diferentes NUNCA se somam: cada moeda tem a sua linha."""
    load.upsert_stats(conn, [stat(source_specific_id="a"), stat(source_specific_id="b", currency="USD")])
    rows = conn.execute("SELECT currency, cost FROM v_campaign_daily ORDER BY currency").fetchall()
    assert rows == [("EUR", Decimal("50")), ("USD", Decimal("50"))]


def test_trafficjunky_and_erobella_converge_in_the_same_view(conn):
    load.upsert_stats(conn, [stat(provider="trafficjunky", campaign_id=C1, source_specific_id=None), stat()])
    rows = conn.execute("SELECT provider, campaign_name FROM v_campaign_daily ORDER BY provider").fetchall()
    assert rows == [("erobella", "EB PT Casino Native"), ("trafficjunky", "TJ PT Casino Desktop")]
