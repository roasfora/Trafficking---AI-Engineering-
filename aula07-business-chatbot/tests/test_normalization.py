"""raw -> analytics: a normalizacao e SQL (sql/05_normalize.sql), por isso testa-se contra o PostgreSQL."""

import pytest

from tools.postgres import execute

pytestmark = pytest.mark.usefixtures("pg")
A = "analytics.campaign_performance_daily"
FX_USD_EUR = 0.92  # sql/05_normalize.sql (taxa fixa so da PoC)


def one(sql, params=()):
    return execute(sql, params)[1][0][0]


def owner_one(sql):
    """As tabelas raw so o dono le (o role do agente nao tem acesso)."""
    from config import get_settings
    import psycopg

    url = get_settings().index_database_url.replace("postgresql+psycopg", "postgresql")
    with psycopg.connect(url) as conn:
        return conn.execute(sql).fetchone()[0]


def test_seed_covers_14_days_and_three_providers():
    assert one(f"SELECT COUNT(DISTINCT date) FROM {A}") == 14
    assert one(f"SELECT MIN(date) FROM {A}").isoformat() == "2026-10-26"
    assert one(f"SELECT MAX(date) FROM {A}").isoformat() == "2026-11-08"
    assert sorted(r[0] for r in execute(f"SELECT DISTINCT provider FROM {A}")[1]) == ["erobella", "trafficjunky", "voluum"]


@pytest.mark.parametrize("provider,expected", [("erobella", 4), ("trafficjunky", 4), ("voluum", 5)])
def test_three_to_five_campaigns_per_provider(provider, expected):
    assert one(f"SELECT COUNT(DISTINCT campaign_id) FROM {A} WHERE provider = %s", (provider,)) == expected


def test_erobella_maps_creative_to_campaign_and_cost_eur():
    assert owner_one("SELECT SUM(cost_eur) FROM raw.erobella_creative_stats") == one(
        f"SELECT SUM(cost) FROM {A} WHERE provider = 'erobella'")
    assert one(f"SELECT SUM(impressions) FROM {A} WHERE provider = 'erobella'") == owner_one(
        "SELECT SUM(impressions) FROM raw.erobella_creative_stats")
    # campaign_id = label do creative; traffic_source = partner
    row = execute(f"SELECT campaign_id, campaign_name, traffic_source FROM {A} WHERE provider = 'erobella' AND campaign_id = 'EB-NATIVE-A' LIMIT 1")[1][0]
    assert row == ("EB-NATIVE-A", "EB-NATIVE-A", "partner_alpha")


def test_erobella_daily_totals_equal_sum_of_creatives():
    assert owner_one("""
        SELECT COUNT(*) FROM raw.erobella_daily_stats d JOIN (
            SELECT day, SUM(impressions) i, SUM(clicks) c, SUM(cost_eur) cost FROM raw.erobella_creative_stats GROUP BY day
        ) s USING (day) WHERE d.impressions <> s.i OR d.clicks <> s.c OR ABS(d.cost_eur - s.cost) > 0.001""") == 0


def test_trafficjunky_cost_is_converted_usd_to_eur():
    raw = float(owner_one("SELECT SUM(cost) FROM raw.trafficjunky_campaign_stats"))
    canonical = float(one(f"SELECT SUM(cost) FROM {A} WHERE provider = 'trafficjunky'"))
    assert canonical == pytest.approx(raw * FX_USD_EUR, abs=0.05)
    assert one(f"SELECT SUM(conversions) FROM {A} WHERE provider = 'trafficjunky'") == owner_one(
        "SELECT SUM(conversions) FROM raw.trafficjunky_campaign_stats")


def test_voluum_keeps_visits_country_and_revenue():
    assert float(one(f"SELECT SUM(revenue) FROM {A} WHERE provider = 'voluum'")) == pytest.approx(
        float(owner_one("SELECT SUM(revenue) FROM raw.voluum_report")))
    assert one(f"SELECT COUNT(*) FROM {A} WHERE provider = 'voluum' AND (visits IS NULL OR country IS NULL)") == 0


def test_missing_fields_are_null_not_zero():
    """Erobella nao reporta conversoes/receita; TJ nao reporta receita: NULL, nunca 0."""
    assert one(f"SELECT COUNT(*) FROM {A} WHERE provider = 'erobella' AND (conversions IS NOT NULL OR revenue IS NOT NULL)") == 0
    assert one(f"SELECT COUNT(*) FROM {A} WHERE provider = 'trafficjunky' AND revenue IS NOT NULL") == 0
    assert one(f"SELECT COUNT(*) FROM {A} WHERE provider <> 'voluum' AND visits IS NOT NULL") == 0


def test_analytics_has_no_provider_reported_ratios():
    cols = {r[0] for r in execute("SELECT column_name FROM information_schema.columns WHERE table_schema='analytics'")[1]}
    assert not cols & {"ctr", "cpc", "cr", "ecpm", "ecpc", "cpa", "ctr_pct", "ecpm_eur"}


def test_cpc_is_ratio_of_sums_not_average_of_ratios():
    ratio_of_sums, avg_of_ratios = execute(f"""
        SELECT SUM(cost) / NULLIF(SUM(clicks), 0), AVG(cost / NULLIF(clicks, 0))
        FROM {A} WHERE provider = 'erobella'""")[1][0]
    assert float(ratio_of_sums) == pytest.approx(0.1396, abs=0.01)
    # o outlier (EB-PUSH-D com 9 cliques) inflaciona a media dos rácios: por isso AVG(cpc) e proibido
    assert float(avg_of_ratios) > 2 * float(ratio_of_sums)


def test_semantic_cpc_expression_runs_and_matches_manual_value():
    from tools.metrics import get_metric_definition

    expr = get_metric_definition("cpc")["expression"]
    value = one(f"SELECT {expr} FROM {A} WHERE provider = 'voluum' AND date = '2026-11-08'")
    assert float(value) == pytest.approx(0.4434, abs=0.0005)


def test_planted_patterns_exist():
    # queda de CR no TJ-Banner-DE a partir de 2026-11-02
    cr = lambda cond: float(one(f"SELECT 100.0*SUM(conversions)/SUM(clicks) FROM {A} WHERE campaign_name='TJ-Banner-DE' AND {cond}"))  # noqa: E731
    assert cr("date < '2026-11-02'") > 1.8 * cr("date >= '2026-11-02'")
    # CTR bom mas CR mau
    ctr, conv = execute(f"SELECT 100.0*SUM(clicks)/SUM(impressions), 100.0*SUM(conversions)/SUM(clicks) FROM {A} WHERE campaign_name='TJ-Native-FR'")[1][0]
    assert float(ctr) > 1.2 and float(conv) < 0.6
    # melhor e pior ROAS no voluum
    roas = dict(execute(f"SELECT campaign_name, SUM(revenue)/SUM(cost) FROM {A} WHERE provider='voluum' GROUP BY 1")[1])
    assert max(roas, key=roas.get) == "VL-HEALTH-FR" and min(roas, key=roas.get) == "VL-VPN-UK"


def test_erobella_rates_price_depends_on_model():
    assert owner_one("SELECT COUNT(*) FROM raw.erobella_rates WHERE model = 'revshare' AND price_eur >= 30") >= 1
    assert "PERCENTAGE" in owner_one(
        "SELECT col_description('raw.erobella_rates'::regclass, 4)")
