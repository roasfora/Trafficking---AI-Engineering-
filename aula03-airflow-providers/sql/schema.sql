-- ============================================================================
-- Modelo (analytics database): uma dimensao e uma fact.
--
--   dim_campaign  <--  fact_campaign_daily
--
-- GRAIN de fact_campaign_daily:
--
--   1 linha = 1 dia + 1 provider + 1 campanha + 1 source_specific_id
--
--   TrafficJunky: source_specific_id = NULL          (uma linha por campanha e dia)
--   Erobella:     source_specific_id = label creative (uma linha por creative e dia)
--
-- Duas fontes com grains de ORIGEM diferentes (campanha vs creative) convergem
-- neste grain comum: o que difere cabe numa coluna opcional.
--
-- Este ficheiro e IDEMPOTENTE (CREATE ... IF NOT EXISTS): correr 1 ou 10 vezes
-- da o mesmo resultado.
-- ============================================================================

CREATE TABLE IF NOT EXISTS dim_campaign (
    campaign_id    UUID         PRIMARY KEY,
    -- UNIQUE por simplificacao: o match dos providers e POR NOME. Na realidade
    -- podem existir nomes repetidos (usa-se "a mais recentemente criada").
    campaign_name  TEXT         NOT NULL UNIQUE,
    loaded_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- So metricas BASE e aditivas. CPC, CPM e CTR sao derivados: ver analytics.sql.
CREATE TABLE IF NOT EXISTS fact_campaign_daily (
    date                DATE           NOT NULL,
    provider            TEXT           NOT NULL CHECK (provider IN ('trafficjunky', 'erobella')),
    campaign_id         UUID           NOT NULL REFERENCES dim_campaign (campaign_id),
    source_specific_id  TEXT           CHECK (source_specific_id <> ''),  -- NULL permitido; '' nao
    currency            CHAR(3)        NOT NULL,
    impressions         BIGINT         NOT NULL CHECK (impressions >= 0),
    clicks              BIGINT         NOT NULL CHECK (clicks >= 0),
    cost                NUMERIC(14, 4) NOT NULL CHECK (cost >= 0),
    loaded_at           TIMESTAMPTZ    NOT NULL DEFAULT now(),  -- 1a vez que vimos a linha
    updated_at          TIMESTAMPTZ    NOT NULL DEFAULT now(),  -- ultima vez que a recarregamos

    -- A CHAVE DE IDEMPOTENCIA. Repara em NULLS NOT DISTINCT.
    --
    -- Numa unique constraint normal, NULL nunca e igual a NULL: duas linhas
    -- (dia, 'trafficjunky', campanha, NULL) seriam consideradas DIFERENTES, o
    -- ON CONFLICT nunca dispararia e cada recarga DUPLICARIA o TrafficJunky.
    -- NULLS NOT DISTINCT (PostgreSQL 15+) trata os NULL como iguais.
    CONSTRAINT uq_campaign_daily
        UNIQUE NULLS NOT DISTINCT (date, provider, campaign_id, source_specific_id)
);

CREATE INDEX IF NOT EXISTS ix_fact_campaign_daily_date ON fact_campaign_daily (date, provider);
