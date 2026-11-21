"""SILVER: interpreta a Bronze. Nomes canonicos, tudo em EUR, grain = date + provider + campaign_id.

A taxa USD->EUR vem de analytics.exchange_rate (JOIN por dia): nunca esta escrita no SQL.
Se faltar a taxa de um dia, o custo fica NULL (e o check not_null di-lo), nao e inventado.
A Silver NAO esconde problemas: duplicados da Bronze passam para a Silver e o check unique_grain apanha-os.
"""

from __future__ import annotations

SQL = {
    "erobella": """
        INSERT INTO analytics.campaign_performance_daily
            (date, provider, campaign_id, campaign_name, traffic_source, country, impressions, clicks,
             conversions, cost, revenue, currency, source_currency, fx_rate, run_id)
        SELECT e.day, 'erobella', 'erobella-total', 'Erobella (account total)', 'Erobella', NULL,
               e.impressions, e.clicks, NULL, e.cost_eur, NULL,
               'EUR', e.source_currency, 1, e.run_id
        FROM raw.erobella_daily_stats e
        WHERE e.run_id = %(run_id)s
    """,
    "trafficjunky": """
        INSERT INTO analytics.campaign_performance_daily
            (date, provider, campaign_id, campaign_name, traffic_source, country, impressions, clicks,
             conversions, cost, revenue, currency, source_currency, fx_rate, run_id)
        SELECT t.day, 'trafficjunky', t.campaign_id, t.campaign_name, 'TrafficJunky', NULL,
               t.impressions, t.clicks, t.conversions,
               t.cost * CASE WHEN t.currency = 'EUR' THEN 1 ELSE fx.rate END,
               NULL, 'EUR', t.currency,
               CASE WHEN t.currency = 'EUR' THEN 1 ELSE fx.rate END, t.run_id
        FROM raw.trafficjunky_campaign_stats t
        LEFT JOIN analytics.exchange_rate fx
               ON fx.date = t.day AND fx.source_currency = t.currency AND fx.target_currency = 'EUR'
        WHERE t.run_id = %(run_id)s
    """,
    "voluum": """
        INSERT INTO analytics.campaign_performance_daily
            (date, provider, campaign_id, campaign_name, traffic_source, country, impressions, clicks,
             conversions, cost, revenue, currency, source_currency, fx_rate, run_id)
        SELECT v.day, 'voluum', v.campaign_id, v.campaign_name, v.traffic_source, v.country,
               v.impressions, v.clicks, v.conversions, v.cost, v.revenue,
               'EUR', v.source_currency, 1, v.run_id
        FROM raw.voluum_report v
        WHERE v.run_id = %(run_id)s
    """,
}


def normalize_provider(conn, provider: str, run_id: str) -> int:
    """Reconstroi a Silver de UM provider a partir da Bronze deste run. Devolve o numero de linhas."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM analytics.campaign_performance_daily WHERE provider = %s", (provider,))
        cur.execute(SQL[provider], {"run_id": run_id})
        n = cur.rowcount
    conn.commit()
    return n
