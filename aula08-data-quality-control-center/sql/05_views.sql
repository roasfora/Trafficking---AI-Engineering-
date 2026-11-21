-- GOLD / SEMANTIC: views sobre a camada publicada. Sempre "ratio of sums": nunca AVG de rácios.
-- (As formulas canonicas estao em semantic.yaml; estas views sao a versao SQL para consumidores.)

CREATE OR REPLACE VIEW analytics.v_metrics_provider_daily AS
SELECT
    date,
    provider,
    SUM(cost)                                               AS spend,
    SUM(impressions)                                        AS impressions,
    SUM(clicks)                                             AS clicks,
    SUM(conversions)                                        AS conversions,
    SUM(revenue)                                            AS revenue,
    SUM(cost) / NULLIF(SUM(clicks), 0)                      AS cpc,
    100.0 * SUM(clicks) / NULLIF(SUM(impressions), 0)       AS ctr,
    100.0 * SUM(conversions) / NULLIF(SUM(clicks), 0)       AS cr,
    SUM(cost) / NULLIF(SUM(conversions), 0)                 AS cpa,
    SUM(revenue) / NULLIF(SUM(cost), 0)                     AS roas   -- NULL onde nao ha revenue
FROM analytics.published_campaign_performance_daily
GROUP BY date, provider;

CREATE OR REPLACE VIEW analytics.v_metrics_campaign_daily AS
SELECT
    date,
    provider,
    campaign_id,
    campaign_name,
    SUM(cost)                                               AS spend,
    SUM(impressions)                                        AS impressions,
    SUM(clicks)                                             AS clicks,
    SUM(conversions)                                        AS conversions,
    SUM(revenue)                                            AS revenue,
    SUM(cost) / NULLIF(SUM(clicks), 0)                      AS cpc,
    100.0 * SUM(clicks) / NULLIF(SUM(impressions), 0)       AS ctr,
    100.0 * SUM(conversions) / NULLIF(SUM(clicks), 0)       AS cr,
    SUM(cost) / NULLIF(SUM(conversions), 0)                 AS cpa,
    SUM(revenue) / NULLIF(SUM(cost), 0)                     AS roas
FROM analytics.published_campaign_performance_daily
GROUP BY date, provider, campaign_id, campaign_name;

-- Pronto para o chatbot da Aula 07 (no futuro): o que esta errado AGORA, no ultimo run.
-- SELECT * FROM data_quality.current_issues;
CREATE OR REPLACE VIEW data_quality.current_issues AS
SELECT
    r.run_id,
    r.checked_at,
    r.provider,
    r.layer,
    r.check_name,
    r.dimension,
    r.status,
    r.observed_value,
    r.expected_value,
    r.threshold,
    r.details ->> 'message' AS message,
    r.details
FROM data_quality.check_results r
WHERE r.run_id = (SELECT run_id FROM data_quality.pipeline_runs ORDER BY started_at DESC LIMIT 1)
  AND r.status IN ('WARN', 'FAIL');
