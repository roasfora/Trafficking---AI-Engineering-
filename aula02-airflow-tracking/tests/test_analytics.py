"""As views: metricas derivadas calculadas a partir de facts aditivas."""

from decimal import Decimal

import pytest

WS, TS, OFFER, C1, C2, C3 = "w", "t", "o", "c1", "c2", "c3"


@pytest.fixture
def seeded(conn):
    conn.execute("INSERT INTO dim_workspace (workspace_id, name) VALUES (%s, 'W')", (WS,))
    conn.execute("INSERT INTO dim_traffic_source (traffic_source_id, name, currency_code, deleted) VALUES (%s,'T','USD',false)", (TS,))
    conn.execute("INSERT INTO dim_offer (offer_id,name,affiliate_network_id,affiliate_network_name,payout,currency_code,deleted) "
                 "VALUES (%s,'O','n','N',10,'USD',false)", (OFFER,))
    for cid in (C1, C2, C3):
        conn.execute("INSERT INTO dim_campaign (campaign_id,name,geo,traffic_source_id,workspace_id,is_paused,created) "
                     "VALUES (%s,%s,'PT',%s,%s,false,'2026-06-01+00')", (cid, cid, TS, WS))

    def cost(day, hour, campaign, provider, c, clicks, impressions):
        conn.execute(
            "INSERT INTO fact_campaign_costs (datetime,cost_date,campaign_id,investment_provider,cost,clicks,impressions) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)", (f"{day} {hour:02d}:00+00", day, campaign, provider, c, clicks, impressions))

    def conv(n, day, campaign, revenue):
        conn.execute(
            "INSERT INTO fact_conversions (click_id,conversion_type_id,postback_timestamp,visit_timestamp,visit_date,"
            "campaign_id,traffic_source_id,offer_id,country_code,revenue,revenue_original_currency) "
            "VALUES (%s,1,%s,%s,%s,%s,%s,%s,'PT',%s,%s)",
            (f"k{n}", f"{day} 12:05+00", f"{day} 12:00+00", day, campaign, TS, OFFER, revenue, revenue))

    # C1 dia 1: dois providers; o 2.o NAO reporta impressions
    cost("2026-10-01", 10, C1, "exoclick", 50, 100, 10000)
    cost("2026-10-01", 11, C1, "reactiveclicks", 10, 50, None)
    for i in range(3):
        conv(f"a{i}", "2026-10-01", C1, 20)
    # C1 dia 2: ROAS bem diferente
    cost("2026-10-02", 10, C1, "exoclick", 20, 100, 5000)
    conv("b0", "2026-10-02", C1, 100)
    # C2 dia 1: custo sem nenhuma conversao
    cost("2026-10-01", 10, C2, "exoclick", 10, 10, 1000)

    # daily control: C1/dia1 bate certo; C1/dia2 diverge (90 vs 100); C2/dia1 diverge mas e manual
    for day, camp, rev, inv, manual in [("2026-10-01", C1, 60, 60, False), ("2026-10-02", C1, 90, 20, False),
                                        ("2026-10-01", C2, 999, 999, True)]:
        conn.execute("INSERT INTO fact_daily_control (date,campaign_id,revenue,investment,is_manual) "
                     "VALUES (%s,%s,%s,%s,%s)", (day, camp, rev, inv, manual))
    conn.commit()


def one(conn, query, *params):
    return conn.execute(query, params).fetchone()


def test_derived_metrics(conn, seeded):
    row = one(conn, "SELECT clicks, conversions, cost, revenue, cpc, cr, cpa, epc, roas, profit, roi "
                    "FROM v_campaign_daily WHERE campaign_id = %s AND report_date = '2026-10-01'", C1)
    clicks, conversions, cost, revenue, cpc, cr, cpa, epc, roas, profit, roi = row
    assert (clicks, conversions, cost, revenue) == (150, 3, 60, 60)
    assert (cpc, cr, cpa, epc, roas, profit, roi) == (Decimal("0.4"), Decimal("0.02"), 20, Decimal("0.4"), 1, 0, 0)


def test_ctr_and_cpm_ignore_rows_without_impressions(conn, seeded):
    """100 dos 150 clicks vem de rows com impressions: CTR = 100/10000, nao 150/10000."""
    ctr, cpm, impressions = one(conn, "SELECT ctr, cpm, impressions FROM v_campaign_daily "
                                      "WHERE campaign_id = %s AND report_date = '2026-10-01'", C1)
    assert impressions == 10000
    assert ctr == Decimal("0.0100")      # certo; o ingenuo daria 0.0150
    assert cpm == Decimal("5.0000")      # 50 / 10000 * 1000


def test_division_by_zero_gives_null_not_an_error(conn, seeded):
    row = one(conn, "SELECT conversions, cpa, cr, roas, profit FROM v_campaign_daily "
                    "WHERE campaign_id = %s AND report_date = '2026-10-01'", C2)
    assert row[0] == 0 and row[1] is None        # CPA indefinido
    assert row[2] == 0 and row[3] == 0 and row[4] == -10


def test_ratios_are_not_additive(conn, seeded):
    """ROAS da semana != media dos ROAS diarios."""
    correct, wrong = one(conn, "SELECT round(sum(revenue)/NULLIF(sum(cost),0),4), round(avg(roas),4) "
                               "FROM v_campaign_daily WHERE campaign_id = %s", C1)
    assert correct == Decimal("2.0")      # 160 / 80
    assert wrong == Decimal("3.0")        # (1 + 5) / 2
    assert correct != wrong


def test_no_fan_out_totals_match_the_facts(conn, seeded):
    totals = (one(conn, "SELECT sum(cost) FROM fact_campaign_costs")[0], one(conn, "SELECT sum(revenue) FROM fact_conversions")[0])
    for view in ("v_campaign_daily", "v_traffic_source_daily"):
        assert one(conn, f"SELECT sum(cost), sum(revenue) FROM {view}") == totals
    assert one(conn, "SELECT sum(revenue), sum(conversions) FROM v_offer_daily") == (totals[1], 4)


def test_traffic_source_view_gets_cost_from_the_campaign(conn, seeded):
    cost, conversions = one(conn, "SELECT cost, conversions FROM v_traffic_source_daily WHERE report_date = '2026-10-01'")
    assert (cost, conversions) == (70, 3)   # C1 (60) + C2 (10)


def test_reconciliation_view(conn, seeded):
    rows = {(str(d), c): (m, rd, idiff) for d, c, m, rd, idiff in conn.execute(
        "SELECT date, campaign_id, is_manual, revenue_diff, investment_diff FROM v_reconciliation_daily")}
    assert rows[("2026-10-01", C1)] == (False, 0, 0)
    assert rows[("2026-10-02", C1)] == (False, -10, 0)       # control 90, eventos 100
    assert rows[("2026-10-01", C2)][0] is True               # manual: discorda, e esta bem
