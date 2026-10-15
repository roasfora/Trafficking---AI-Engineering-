-- ============================================================================
-- Modelo dimensional (analytics database)
--
-- Estrutura real: ver data-structure-reference.md (aqui, o "dataset minimo").
--
--   dim_workspace <-- dim_campaign --> dim_traffic_source        dim_offer
--                          ^    ^                ^                   ^
--                          |    |                |                   |
--        fact_campaign_costs    +---- fact_conversions --------------+
--        fact_daily_control --> dim_campaign
--
-- Este ficheiro e IDEMPOTENTE (CREATE ... IF NOT EXISTS): correr 1 ou 10 vezes
-- da o mesmo resultado. A pipeline aplica-o no inicio de cada carga.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- DIMENSOES: descrevem "quem/o que/onde". Poucas linhas, mudam devagar.
-- A PRIMARY KEY e o identificador natural da origem (um UUID do Voluum/Postgres).
-- Estrategia de mudanca: SCD tipo 1 (o valor novo substitui o antigo).
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS dim_workspace (
    workspace_id  TEXT         PRIMARY KEY,
    name          TEXT         NOT NULL,
    loaded_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dim_traffic_source (
    traffic_source_id  TEXT         PRIMARY KEY,
    name               TEXT         NOT NULL,
    currency_code      CHAR(3)      NOT NULL,
    deleted            BOOLEAN      NOT NULL,          -- soft delete, como na origem
    loaded_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Hierarquia da origem: Workspace 1-* TrafficSource 1-* Campaign.
-- A campanha referencia a sua fonte e o seu workspace.
CREATE TABLE IF NOT EXISTS dim_campaign (
    campaign_id        TEXT         PRIMARY KEY,
    name               TEXT         NOT NULL,
    geo                CHAR(2)      NOT NULL,           -- ISO-2, ou 'WW' (worldwide)
    traffic_source_id  TEXT         NOT NULL REFERENCES dim_traffic_source (traffic_source_id),
    workspace_id       TEXT         NOT NULL REFERENCES dim_workspace (workspace_id),
    is_paused          BOOLEAN      NOT NULL,
    created            TIMESTAMPTZ  NOT NULL,
    loaded_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- A rede de afiliacao (affiliate network) vive aqui como atributos da oferta,
-- sem dimensao propria: ainda nao tem atributos que o justifiquem.
CREATE TABLE IF NOT EXISTS dim_offer (
    offer_id                TEXT           PRIMARY KEY,
    name                    TEXT           NOT NULL,
    country_code            CHAR(2),                      -- opcional (NULL = oferta global)
    affiliate_network_id    TEXT           NOT NULL,
    affiliate_network_name  TEXT           NOT NULL,
    payout                  NUMERIC(12, 4) NOT NULL CHECK (payout >= 0),
    currency_code           CHAR(3)        NOT NULL,
    deleted                 BOOLEAN        NOT NULL,
    loaded_at               TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ    NOT NULL DEFAULT now()
);


-- ----------------------------------------------------------------------------
-- FACTS: descrevem "o que aconteceu". Muitas linhas, so crescem.
--
-- GRAIN (a frase mais importante deste ficheiro):
--   fact_conversions     -> 1 linha = 1 conversao (um postback)
--   fact_campaign_costs  -> 1 linha = 1 campanha x 1 hora x 1 investment_provider
--   fact_daily_control   -> 1 linha = 1 campanha x 1 dia
--
-- Nao ha fact de clicks: na origem os clicks nao sao guardados um a um, so
-- chegam agregados por hora, dentro do custo. Os clicks vivem em
-- fact_campaign_costs.
--
-- As PRIMARY KEYS sao COMPOSTAS e naturais: a origem nao tem um ID por linha.
-- E ela que torna a carga idempotente (ON CONFLICT sobre a chave inteira).
--
-- Guardamos metricas ADITIVAS (cost, revenue, clicks, impressions...): podem ser
-- somadas por qualquer dimensao. NAO guardamos CPC, CTR, ROAS, profit...: sao
-- racios/derivados, calculam-se depois (ver analytics.sql). Um racio nao se soma.
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fact_conversions (
    click_id                   TEXT           NOT NULL,
    conversion_type_id         INTEGER        NOT NULL,
    postback_timestamp         TIMESTAMPTZ    NOT NULL,    -- quando a conversao nos foi reportada
    visit_timestamp            TIMESTAMPTZ    NOT NULL,    -- quando o utilizador clicou
    visit_date                 DATE           NOT NULL,    -- dia UTC da visita (calculado no transform)
    campaign_id                TEXT           NOT NULL REFERENCES dim_campaign (campaign_id),
    traffic_source_id          TEXT           NOT NULL REFERENCES dim_traffic_source (traffic_source_id),
    offer_id                   TEXT           NOT NULL REFERENCES dim_offer (offer_id),
    country_code               CHAR(2)        NOT NULL,    -- pais do visitante
    revenue                    NUMERIC(14, 4) NOT NULL CHECK (revenue >= 0),  -- USD, aditiva
    revenue_original_currency  NUMERIC(14, 4) NOT NULL CHECK (revenue_original_currency >= 0),
    loaded_at                  TIMESTAMPTZ    NOT NULL DEFAULT now(),  -- 1a vez que vimos a linha
    updated_at                 TIMESTAMPTZ    NOT NULL DEFAULT now(),  -- ultima vez que a recarregamos
    -- Um click pode ter varias conversoes (tipos diferentes, momentos diferentes).
    PRIMARY KEY (click_id, conversion_type_id, postback_timestamp)
);

CREATE TABLE IF NOT EXISTS fact_campaign_costs (
    datetime             TIMESTAMPTZ    NOT NULL,          -- inicio da hora
    cost_date            DATE           NOT NULL,          -- dia UTC (calculado no transform)
    campaign_id          TEXT           NOT NULL REFERENCES dim_campaign (campaign_id),
    -- sem dim_investment_provider nesta versao: o provider e uma coluna simples
    -- (16 valores). Passa a dimensao quando tiver atributos (fee, conta...).
    investment_provider  TEXT           NOT NULL,
    cost                 NUMERIC(14, 4) NOT NULL CHECK (cost >= 0),  -- USD, aditiva
    clicks               BIGINT         CHECK (clicks >= 0),         -- NULL = o provider nao reporta
    impressions          BIGINT         CHECK (impressions >= 0),    -- NULL = o provider nao reporta
    loaded_at            TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ    NOT NULL DEFAULT now(),
    PRIMARY KEY (datetime, campaign_id, investment_provider)
);

-- Agregado diario que vem de OUTRO sistema (Postgres do backoffice), distinto
-- dos eventos. Serve para reconciliar: os dois lados devem concordar, exceto
-- onde um humano escreveu os numeros (is_manual).
CREATE TABLE IF NOT EXISTS fact_daily_control (
    date         DATE           NOT NULL,
    campaign_id  TEXT           NOT NULL REFERENCES dim_campaign (campaign_id),
    revenue      NUMERIC(12, 2) NOT NULL CHECK (revenue >= 0),
    investment   NUMERIC(12, 2) NOT NULL CHECK (investment >= 0),
    is_manual    BOOLEAN        NOT NULL,
    loaded_at    TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ    NOT NULL DEFAULT now(),
    PRIMARY KEY (date, campaign_id)
);

-- Indices para os filtros e agregacoes mais comuns (nao afetam o grain).
CREATE INDEX IF NOT EXISTS ix_fact_conversions_visit_date     ON fact_conversions (visit_date);
CREATE INDEX IF NOT EXISTS ix_fact_conversions_postback       ON fact_conversions (postback_timestamp);
CREATE INDEX IF NOT EXISTS ix_fact_conversions_campaign       ON fact_conversions (campaign_id);
CREATE INDEX IF NOT EXISTS ix_fact_campaign_costs_cost_date   ON fact_campaign_costs (cost_date);
CREATE INDEX IF NOT EXISTS ix_fact_campaign_costs_campaign    ON fact_campaign_costs (campaign_id);
