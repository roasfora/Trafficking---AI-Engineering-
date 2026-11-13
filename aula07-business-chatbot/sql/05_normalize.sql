-- NORMALIZACAO: raw.* (formas diferentes) -> analytics.campaign_performance_daily (uma forma).
-- E aqui que os nomes dos providers viram nomes comuns:
--   Erobella cost_eur / TrafficJunky cost (USD) / Voluum cost  ->  analytics.cost (EUR)
-- Nao copiamos ctr/cpc/cr/ecpm dos providers: cada um calcula-os a sua maneira.
--
-- Taxa FX FIXA so para a PoC: 1 USD = 0.92 EUR. Um sistema real usa a taxa do dia.
INSERT INTO analytics.campaign_performance_daily
    (date, provider, campaign_id, campaign_name, traffic_source, country,
     impressions, visits, clicks, conversions, cost, revenue)

-- Erobella: a "campanha" e o creative (a API nao tem campanhas). Sem conversoes nem receita.
SELECT day, 'erobella', label, label, partner, NULL::text,
       impressions, NULL::bigint, clicks, NULL::bigint, cost_eur, NULL::numeric
FROM raw.erobella_creative_stats

UNION ALL

-- TrafficJunky: custo em USD convertido para EUR. Sem receita ao nivel da campanha.
SELECT day, 'trafficjunky', campaign_id::text, campaign_name, 'TrafficJunky', NULL::text,
       impressions, NULL::bigint, clicks, conversions, ROUND(cost * 0.92, 4), NULL::numeric
FROM raw.trafficjunky_campaign_stats

UNION ALL

-- Voluum: tracker. Unico que reporta visits, country e revenue.
SELECT day, 'voluum', campaign_id::text, campaign_name, traffic_source_name, country_code,
       impressions, visits, clicks, conversions, cost, revenue
FROM raw.voluum_report;
