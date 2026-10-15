-- ============================================================================
-- Camada analitica: views sobre as facts e dimensoes.
--
-- Aqui (e so aqui) se calculam as metricas DERIVADAS. Metricas ADITIVAS (vem
-- das facts e somam-se):
--
--   clicks, impressions            fact_campaign_costs
--   cost                           fact_campaign_costs
--   conversions = count(*)         fact_conversions  (uma linha = uma conversao)
--   revenue                        fact_conversions
--
-- Metricas DERIVADAS (racios; calculam-se no fim):
--
--   CPC    = cost / clicks             quanto custa cada click
--   CPM    = cost / impressions * 1000 custo por mil impressoes
--   CTR    = clicks / impressions      fracao de impressoes que gera click
--   CR     = conversions / clicks      conversion rate
--   CPA    = cost / conversions        quanto custa cada conversao
--   EPC    = revenue / clicks          earnings per click
--   ROAS   = revenue / cost            retorno por unidade gasta
--   profit = revenue - cost
--   ROI    = profit / cost
--
-- REGRA DE OURO: soma primeiro, divide depois.
-- Um racio nao e aditivo. Para obter o ROAS de uma semana NAO se faz a media
-- dos ROAS diarios; soma-se a receita, soma-se o custo, e divide-se. Qualquer
-- dashboard que agregue estas views deve voltar a somar as colunas aditivas e
-- recalcular o racio - nunca fazer AVG(roas).
--
-- NULLIF(x, 0) devolve NULL quando x = 0, e uma divisao por NULL da NULL em vez
-- de "division by zero". Um dia sem conversoes tem CPA indefinido, nao infinito.
--
-- NULLS NAO SAO ZEROS. Alguns providers nao reportam impressions (NULL). Se
-- somassemos todos os clicks e dividissemos pelas impressions que existem, o CTR
-- ficaria inflacionado. O CTR usa por isso so os clicks DAS LINHAS que reportam
-- impressions (clicks_with_impressions); o CPM idem com o custo.
--
-- ARMADILHA (fan-out): nunca juntar fact_conversions com fact_campaign_costs e
-- SOMAR depois: cada custo seria repetido por cada conversao. Agrega-se cada
-- fact separadamente, ao grain da view, e juntam-se os RESULTADOS.
--
-- DATAS: o custo conta no dia da sua hora (cost_date); a conversao conta no dia
-- da VISITA (visit_date), para ficar no mesmo dia do custo do click que a gerou.
-- ============================================================================

DROP VIEW IF EXISTS v_reconciliation_daily;
DROP VIEW IF EXISTS v_campaign_daily;
DROP VIEW IF EXISTS v_traffic_source_daily;
DROP VIEW IF EXISTS v_offer_daily;


-- ----------------------------------------------------------------------------
-- GRAIN: 1 linha = 1 campanha x 1 dia
-- ----------------------------------------------------------------------------
CREATE VIEW v_campaign_daily AS
WITH cost_metrics AS (
    SELECT cost_date AS report_date, campaign_id,
           sum(cost)        AS cost,
           sum(clicks)      AS clicks,
           sum(impressions) AS impressions,
           sum(clicks) FILTER (WHERE impressions IS NOT NULL) AS clicks_with_impressions,
           sum(cost)   FILTER (WHERE impressions IS NOT NULL) AS cost_with_impressions
    FROM fact_campaign_costs
    GROUP BY cost_date, campaign_id
),
conversion_metrics AS (
    SELECT visit_date AS report_date, campaign_id,
           count(*) AS conversions, sum(revenue) AS revenue
    FROM fact_conversions
    GROUP BY visit_date, campaign_id
),
combined AS (
    -- FULL JOIN: pode haver custo sem conversoes (e, em teoria, o inverso)
    SELECT COALESCE(k.report_date, v.report_date)   AS report_date,
           COALESCE(k.campaign_id, v.campaign_id)   AS campaign_id,
           COALESCE(k.clicks, 0)       AS clicks,
           k.impressions,
           k.clicks_with_impressions, k.cost_with_impressions,
           COALESCE(v.conversions, 0)  AS conversions,
           COALESCE(k.cost, 0)         AS cost,
           COALESCE(v.revenue, 0)      AS revenue
    FROM cost_metrics k
    FULL JOIN conversion_metrics v USING (report_date, campaign_id)
)
SELECT m.report_date,
       m.campaign_id,
       c.name  AS campaign_name,
       c.geo,
       ts.name AS traffic_source_name,
       w.name  AS workspace_name,
       m.clicks, m.impressions, m.conversions, m.cost, m.revenue,
       round(m.cost / NULLIF(m.clicks, 0), 4)                              AS cpc,
       round(m.cost_with_impressions / NULLIF(m.impressions, 0) * 1000, 4) AS cpm,
       round(m.clicks_with_impressions::numeric / NULLIF(m.impressions, 0), 4) AS ctr,
       round(m.conversions::numeric / NULLIF(m.clicks, 0), 4)              AS cr,
       round(m.cost / NULLIF(m.conversions, 0), 4)                         AS cpa,
       round(m.revenue / NULLIF(m.clicks, 0), 4)                           AS epc,
       round(m.revenue / NULLIF(m.cost, 0), 4)                             AS roas,
       m.revenue - m.cost                                                  AS profit,
       round((m.revenue - m.cost) / NULLIF(m.cost, 0), 4)                  AS roi
FROM combined m
JOIN dim_campaign c        USING (campaign_id)
JOIN dim_traffic_source ts ON ts.traffic_source_id = c.traffic_source_id
JOIN dim_workspace w       ON w.workspace_id = c.workspace_id;


-- ----------------------------------------------------------------------------
-- GRAIN: 1 linha = 1 fonte de trafego x 1 dia
--
-- O custo nao traz a fonte: obtem-se pela campanha (dim_campaign). A conversao
-- traz a sua propria traffic_source_id (e o quality_check garante que coincide
-- com a da campanha).
-- ----------------------------------------------------------------------------
CREATE VIEW v_traffic_source_daily AS
WITH cost_metrics AS (
    SELECT k.cost_date AS report_date, c.traffic_source_id,
           sum(k.cost) AS cost, sum(k.clicks) AS clicks, sum(k.impressions) AS impressions,
           sum(k.clicks) FILTER (WHERE k.impressions IS NOT NULL) AS clicks_with_impressions,
           sum(k.cost)   FILTER (WHERE k.impressions IS NOT NULL) AS cost_with_impressions
    FROM fact_campaign_costs k
    JOIN dim_campaign c USING (campaign_id)
    GROUP BY k.cost_date, c.traffic_source_id
),
conversion_metrics AS (
    SELECT visit_date AS report_date, traffic_source_id,
           count(*) AS conversions, sum(revenue) AS revenue
    FROM fact_conversions
    GROUP BY visit_date, traffic_source_id
),
combined AS (
    SELECT COALESCE(k.report_date, v.report_date)             AS report_date,
           COALESCE(k.traffic_source_id, v.traffic_source_id) AS traffic_source_id,
           COALESCE(k.clicks, 0) AS clicks, k.impressions,
           k.clicks_with_impressions, k.cost_with_impressions,
           COALESCE(v.conversions, 0) AS conversions,
           COALESCE(k.cost, 0) AS cost, COALESCE(v.revenue, 0) AS revenue
    FROM cost_metrics k
    FULL JOIN conversion_metrics v USING (report_date, traffic_source_id)
)
SELECT m.report_date,
       m.traffic_source_id,
       ts.name AS traffic_source_name,
       m.clicks, m.impressions, m.conversions, m.cost, m.revenue,
       round(m.cost / NULLIF(m.clicks, 0), 4)                              AS cpc,
       round(m.cost_with_impressions / NULLIF(m.impressions, 0) * 1000, 4) AS cpm,
       round(m.clicks_with_impressions::numeric / NULLIF(m.impressions, 0), 4) AS ctr,
       round(m.conversions::numeric / NULLIF(m.clicks, 0), 4)              AS cr,
       round(m.cost / NULLIF(m.conversions, 0), 4)                         AS cpa,
       round(m.revenue / NULLIF(m.clicks, 0), 4)                           AS epc,
       round(m.revenue / NULLIF(m.cost, 0), 4)                             AS roas,
       m.revenue - m.cost                                                  AS profit,
       round((m.revenue - m.cost) / NULLIF(m.cost, 0), 4)                  AS roi
FROM combined m
JOIN dim_traffic_source ts USING (traffic_source_id);


-- ----------------------------------------------------------------------------
-- GRAIN: 1 linha = 1 oferta x 1 dia
--
-- So receita e conversoes: o CUSTO NAO TEM OFERTA. fact_campaign_costs nao sabe
-- a que oferta pertence o trafego, por isso nao ha CPA nem profit por oferta.
-- Uma metrica so existe ao grain em que todos os seus ingredientes existem.
-- ----------------------------------------------------------------------------
CREATE VIEW v_offer_daily AS
SELECT f.visit_date AS report_date,
       f.offer_id,
       o.name AS offer_name,
       o.affiliate_network_name,
       count(*)       AS conversions,
       sum(f.revenue) AS revenue,
       round(sum(f.revenue) / NULLIF(count(*), 0), 4) AS revenue_per_conversion
FROM fact_conversions f
JOIN dim_offer o USING (offer_id)
GROUP BY f.visit_date, f.offer_id, o.name, o.affiliate_network_name;


-- ----------------------------------------------------------------------------
-- RECONCILIACAO: os eventos concordam com o daily control?
--
-- GRAIN: 1 linha = 1 campanha x 1 dia presente em fact_daily_control.
--
-- O daily control vem de outro sistema e as facts de eventos de outro. Devem
-- somar o mesmo, EXCETO nas linhas is_manual (escritas a mao). E a verificacao
-- que o quality_check usa; esta view torna-a visivel a quem analisa.
-- ----------------------------------------------------------------------------
CREATE VIEW v_reconciliation_daily AS
WITH conv AS (
    SELECT visit_date AS date, campaign_id, sum(revenue) AS revenue
    FROM fact_conversions GROUP BY visit_date, campaign_id
),
cost AS (
    SELECT cost_date AS date, campaign_id, sum(cost) AS cost
    FROM fact_campaign_costs GROUP BY cost_date, campaign_id
)
SELECT dc.date,
       dc.campaign_id,
       dc.is_manual,
       dc.revenue                          AS control_revenue,
       COALESCE(conv.revenue, 0)           AS events_revenue,
       dc.revenue - COALESCE(conv.revenue, 0) AS revenue_diff,
       dc.investment                       AS control_investment,
       COALESCE(cost.cost, 0)              AS events_cost,
       dc.investment - COALESCE(cost.cost, 0) AS investment_diff
FROM fact_daily_control dc
LEFT JOIN conv USING (date, campaign_id)
LEFT JOIN cost USING (date, campaign_id);


-- ============================================================================
-- Exemplos de consultas (para a aula; nao sao executados)
--
-- 1) Resumo por campanha num periodo: soma primeiro, divide depois.
--
--    SELECT campaign_name,
--           sum(clicks) AS clicks, sum(conversions) AS conversions,
--           sum(cost) AS cost, sum(revenue) AS revenue,
--           round(sum(revenue) / NULLIF(sum(cost), 0), 4) AS roas,      -- CORRETO
--           round(avg(roas), 4)                           AS roas_errado -- ERRADO
--    FROM v_campaign_daily
--    WHERE report_date BETWEEN '2026-10-01' AND '2026-10-07'
--    GROUP BY campaign_name
--    ORDER BY roas DESC NULLS LAST;
--
-- 2) Que fonte de trafego e mais rentavel?
--
--    SELECT traffic_source_name, sum(revenue) - sum(cost) AS profit
--    FROM v_traffic_source_daily GROUP BY 1 ORDER BY profit DESC;
--
-- 3) Onde e que os dois sistemas discordam?
--
--    SELECT * FROM v_reconciliation_daily
--    WHERE NOT is_manual AND (abs(revenue_diff) > 0.05 OR abs(investment_diff) > 0.05);
-- ============================================================================
