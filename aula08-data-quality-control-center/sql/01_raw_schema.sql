-- BRONZE / RAW: o que o provider disse, tal como o provider o disse.
-- Sem conversao de moeda, sem renomear metricas, sem recalcular rácios, sem corrigir valores.
-- Sem chaves primarias de proposito: se o provider enviar duplicados, a Bronze guarda-os
-- (quem decide o que fazer com eles é a Silver, e quem avisa é um check).

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS data_quality;

-- Uma linha por (run, provider): o que a API declarou sobre a resposta (paginacao, campos, mensagens).
CREATE TABLE IF NOT EXISTS raw.api_runs (
    run_id            text        NOT NULL,
    provider          text        NOT NULL,
    request_date      date        NOT NULL,          -- dia de dados esperado (o "hoje" da simulacao)
    requested_at      timestamptz NOT NULL,          -- quando a API foi chamada
    scenario          text        NOT NULL,
    source_currency   text,
    http_status       integer     NOT NULL DEFAULT 200,
    rows_received     integer     NOT NULL,          -- linhas na resposta
    total_rows        integer,                       -- total declarado pelo provider (paginacao)
    page_offset       integer,
    page_limit        integer,
    truncated         boolean     NOT NULL DEFAULT false,
    messages          jsonb       NOT NULL DEFAULT '[]',
    response_fields   jsonb       NOT NULL DEFAULT '[]',  -- campos vistos nas linhas (para schema_diff)
    latest_data_date  date,
    loaded_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, provider)
);

-- Erobella: totais por dia (UTC). cost_eur e ecpm_eur ja vem em EUR.
CREATE TABLE IF NOT EXISTS raw.erobella_daily_stats (
    run_id          text        NOT NULL,
    loaded_at       timestamptz NOT NULL DEFAULT now(),
    provider        text        NOT NULL DEFAULT 'erobella',
    request_date    date        NOT NULL,
    source_currency text        NOT NULL DEFAULT 'EUR',
    day             date,
    impressions     bigint,
    clicks          bigint,
    ctr_pct         numeric,
    cost_eur        numeric,
    ecpm_eur        numeric,
    rates           jsonb,
    updated_at      timestamptz,
    raw_payload     jsonb       NOT NULL       -- a linha original, intacta (inclui campos novos/renomeados)
);

-- TrafficJunky: por dia e campanha. Custo em USD, ratios do provider (ctr, ecpm, ecpc) tal como vieram.
CREATE TABLE IF NOT EXISTS raw.trafficjunky_campaign_stats (
    run_id          text        NOT NULL,
    loaded_at       timestamptz NOT NULL DEFAULT now(),
    provider        text        NOT NULL DEFAULT 'trafficjunky',
    request_date    date        NOT NULL,
    source_currency text        NOT NULL DEFAULT 'USD',
    day             date,
    campaign_id     text,
    campaign_name   text,
    campaign_type   text,
    impressions     bigint,
    clicks          bigint,
    conversions     bigint,
    ctr             numeric,
    ecpm            numeric,
    ecpc            numeric,
    cost            numeric,
    currency        text,
    raw_payload     jsonb       NOT NULL
);

-- Voluum: GET /report agrupado por dia e campanha. Ratios (ctr, cr, cpc, cpa) calculados pelo provider.
CREATE TABLE IF NOT EXISTS raw.voluum_report (
    run_id          text        NOT NULL,
    loaded_at       timestamptz NOT NULL DEFAULT now(),
    provider        text        NOT NULL DEFAULT 'voluum',
    request_date    date        NOT NULL,
    source_currency text        NOT NULL DEFAULT 'EUR',
    day             date,
    campaign_id     text,
    campaign_name   text,
    traffic_source  text,
    country         text,
    visits          bigint,
    clicks          bigint,
    conversions     bigint,
    impressions     bigint,
    revenue         numeric,
    cost            numeric,
    profit          numeric,
    ctr             numeric,
    cr              numeric,
    cpc             numeric,
    cpa             numeric,
    raw_payload     jsonb       NOT NULL
);

-- Voluum: uma linha por conversao. revenue = USD; revenue_original_currency = valor na moeda da fonte (EUR).
CREATE TABLE IF NOT EXISTS raw.voluum_conversions (
    run_id                    text        NOT NULL,
    loaded_at                 timestamptz NOT NULL DEFAULT now(),
    provider                  text        NOT NULL DEFAULT 'voluum',
    request_date              date        NOT NULL,
    source_currency           text        NOT NULL DEFAULT 'EUR',
    click_id                  text,
    campaign_id               text,
    visit_timestamp           timestamptz,
    postback_timestamp        timestamptz,
    revenue                   numeric,
    revenue_original_currency numeric,
    conversion_type_id        integer,
    country_code              text,
    offer_id                  text,
    traffic_source_id         text
);

CREATE INDEX IF NOT EXISTS idx_erobella_run ON raw.erobella_daily_stats (run_id);
CREATE INDEX IF NOT EXISTS idx_tj_run       ON raw.trafficjunky_campaign_stats (run_id);
CREATE INDEX IF NOT EXISTS idx_voluum_run   ON raw.voluum_report (run_id);
CREATE INDEX IF NOT EXISTS idx_voluum_conv_run ON raw.voluum_conversions (run_id);
