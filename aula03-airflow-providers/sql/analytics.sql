-- ============================================================================
-- Camada analitica: os racios (CPC, CPM, CTR) calculam-se AQUI.
--
-- A fact guarda so metricas BASE (impressions, clicks, cost). Os racios derivam-se:
--
--   CPC = cost / clicks
--   CPM = cost / impressions * 1000
--   CTR = clicks / impressions           (fracao: 0.0255 = 2,55 %)
--
-- NULLIF(x, 0) devolve NULL quando x = 0, e uma divisao por NULL da NULL em vez de
-- "division by zero": uma linha sem clicks tem CPC indefinido, nao infinito.
--
-- RACIOS DO PROVIDER vs RACIOS RECALCULADOS
-- Os providers enviam ecpc/ecpm/ctr. Nao os guardamos: vem arredondados (2 casas),
-- em unidades diferentes (ctr em %), e, ao somar campanhas duplicadas, o racio de
-- uma delas deixa de fazer sentido. Recalculados a partir das metricas base sao
-- consistentes entre providers e entre agregacoes.
--
-- REGRA DE OURO: soma primeiro, divide depois. Nunca AVG(cpc).
--
-- MOEDAS: NUNCA se somam moedas diferentes. Ambas as views agrupam por currency.
-- ============================================================================

DROP VIEW IF EXISTS v_campaign_daily;
DROP VIEW IF EXISTS v_stat_ratios;

-- GRAIN: o da fact (1 dia + 1 provider + 1 campanha + 1 source_specific_id).
CREATE VIEW v_stat_ratios AS
SELECT f.date, f.provider, f.campaign_id, c.campaign_name, f.source_specific_id, f.currency,
       f.impressions, f.clicks, f.cost,
       round(f.cost / NULLIF(f.clicks, 0), 4)                         AS cpc,
       round(f.cost / NULLIF(f.impressions, 0) * 1000, 4)             AS cpm,
       round(f.clicks::numeric / NULLIF(f.impressions, 0), 6)         AS ctr
FROM fact_campaign_daily f
JOIN dim_campaign c USING (campaign_id);

-- GRAIN: 1 dia + 1 provider + 1 campanha + 1 moeda (os creatives da Erobella somam-se).
CREATE VIEW v_campaign_daily AS
SELECT date, provider, campaign_id, campaign_name, currency,
       sum(impressions)::bigint AS impressions,
       sum(clicks)::bigint      AS clicks,
       sum(cost)                AS cost,
       round(sum(cost) / NULLIF(sum(clicks), 0), 4)                    AS cpc,
       round(sum(cost) / NULLIF(sum(impressions), 0) * 1000, 4)        AS cpm,
       round(sum(clicks)::numeric / NULLIF(sum(impressions), 0), 6)    AS ctr
FROM v_stat_ratios
GROUP BY date, provider, campaign_id, campaign_name, currency;
