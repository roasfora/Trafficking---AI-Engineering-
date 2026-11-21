-- SILVER: dados interpretados e normalizados (EUR, nomes canonicos). Grain: date + provider + campaign_id.
-- A tabela NAO tem chave primaria de proposito: se a normalizacao deixar passar duplicados,
-- quem os apanha é o check `unique_grain` (a Silver nao esconde problemas).

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.campaign_performance_daily (
    date            date        NOT NULL,
    provider        text        NOT NULL,
    campaign_id     text        NOT NULL,
    campaign_name   text,
    traffic_source  text,
    country         text,           -- NULL quando o provider nao reporta (nunca 'unknown', nunca 0)
    impressions     bigint,
    clicks          bigint,
    conversions     bigint,         -- NULL para erobella (nao reporta conversoes)
    cost            numeric,        -- EUR
    revenue         numeric,        -- EUR; NULL para erobella e trafficjunky (so o Voluum tem receita)
    currency        text        NOT NULL DEFAULT 'EUR',
    -- rastreabilidade da conversao
    source_currency text,
    fx_rate         numeric,
    run_id          text        NOT NULL,
    loaded_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cpd_grain ON analytics.campaign_performance_daily (date, provider, campaign_id);
CREATE INDEX IF NOT EXISTS idx_cpd_run   ON analytics.campaign_performance_daily (run_id, provider);

-- GOLD (consumer layer): so recebe dados quando a quality gate deixa publicar.
CREATE TABLE IF NOT EXISTS analytics.published_campaign_performance_daily (
    LIKE analytics.campaign_performance_daily INCLUDING DEFAULTS
);
ALTER TABLE analytics.published_campaign_performance_daily
    ADD COLUMN IF NOT EXISTS published_at timestamptz NOT NULL DEFAULT now();

-- Referencia: dimensao de campanhas (modelo realista simplificado).
CREATE TABLE IF NOT EXISTS analytics.campaigns (
    campaign_id    text PRIMARY KEY,
    name           text NOT NULL,
    geo            text,
    traffic_source text,
    workspace_id   integer,
    is_paused      boolean NOT NULL DEFAULT false,
    created        timestamptz
);

-- Referencia: taxas de cambio. A normalizacao le DAQUI; a taxa nunca esta escrita no SQL de normalizacao.
CREATE TABLE IF NOT EXISTS analytics.exchange_rate (
    date            date    NOT NULL,
    source_currency text    NOT NULL,
    target_currency text    NOT NULL,
    rate            numeric NOT NULL,
    PRIMARY KEY (date, source_currency, target_currency)
);

-- Controlo interno independente dos providers (investimento e receita por campanha/dia).
-- É a "segunda opiniao" usada na reconciliacao.
CREATE TABLE IF NOT EXISTS analytics.daily_control (
    date        date    NOT NULL,
    campaign_id text    NOT NULL,
    revenue     numeric,
    investment  numeric,
    is_manual   boolean NOT NULL DEFAULT false,
    PRIMARY KEY (date, campaign_id)
);
