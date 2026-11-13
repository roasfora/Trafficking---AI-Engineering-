-- RAW: subconjunto dos modelos reais (erobella.py, trafficjunky.py, voluum/responses.py).
-- Mantemos os nomes dos campos da API para o contrato ficar visivel; nao ha ratios "canonicos" aqui.

-- ---------------------------------------------------------------- Erobella
-- GET /stats -> by_day / by_day_creative / rates. Dias em UTC. Moeda: EUR.
CREATE TABLE raw.erobella_daily_stats (
    day          date PRIMARY KEY,
    impressions  integer,
    clicks       integer,
    ctr_pct      numeric(8,4),
    cost_eur     numeric(12,4),
    ecpm_eur     numeric(10,4),
    updated_at   timestamptz
);
COMMENT ON TABLE raw.erobella_daily_stats IS 'Erobella GET /stats by_day: totals per UTC day.';
COMMENT ON COLUMN raw.erobella_daily_stats.ctr_pct IS 'Provider-reported CTR as a percentage.';
COMMENT ON COLUMN raw.erobella_daily_stats.cost_eur IS 'What we are charged, in EUR.';
COMMENT ON COLUMN raw.erobella_daily_stats.ecpm_eur IS 'Provider-reported effective cost per thousand impressions, EUR.';

CREATE TABLE raw.erobella_creative_stats (
    day          date NOT NULL,
    label        text NOT NULL,
    partner      text NOT NULL,
    impressions  integer,
    clicks       integer,
    cost_eur     numeric(12,4),
    ctr_pct      numeric(8,4),
    ecpm_eur     numeric(10,4),
    PRIMARY KEY (day, label, partner)
);
COMMENT ON TABLE raw.erobella_creative_stats IS 'Erobella GET /stats by_day_creative: one row per UTC day and creative. Erobella has no conversions or revenue.';
COMMENT ON COLUMN raw.erobella_creative_stats.label IS 'Creative label. In analytics this becomes the campaign (Erobella has no campaign entity).';
COMMENT ON COLUMN raw.erobella_creative_stats.partner IS 'Partner account the creative belongs to.';

CREATE TABLE raw.erobella_rates (
    partner      text NOT NULL,
    country      text NOT NULL,
    model        text NOT NULL,
    price_eur    numeric(10,4),
    valid_from   date,
    valid_to     date
);
COMMENT ON TABLE raw.erobella_rates IS 'Erobella rates per partner and market. Reference data, not used to compute cost.';
COMMENT ON COLUMN raw.erobella_rates.model IS 'Pricing model (cpm, revshare). Determines how price_eur must be read.';
COMMENT ON COLUMN raw.erobella_rates.price_eur IS
  'Unit depends on model: cpm = EUR per thousand impressions; revshare = a PERCENTAGE (50.0 means 50%, not 50 EUR). Never use as a cost without checking model.';

-- ------------------------------------------------------------ TrafficJunky
-- Stats por campanha. A API devolve um dict por intervalo; aqui guardamos uma linha por dia.
CREATE TABLE raw.trafficjunky_campaign_stats (
    day            date NOT NULL,
    campaign_id    integer NOT NULL,
    campaign_name  text NOT NULL,
    campaign_type  text,
    impressions    integer,
    clicks         integer,
    conversions    integer,       -- a API devolve-o como string; aqui ja convertido
    ctr            numeric(8,4),  -- provider-reported, em %
    ecpm           numeric(10,4), -- provider-reported, USD
    ecpc           numeric(10,4), -- provider-reported, USD
    cost           numeric(12,4), -- USD
    PRIMARY KEY (day, campaign_id)
);
COMMENT ON TABLE raw.trafficjunky_campaign_stats IS 'TrafficJunky campaign stats, one row per day and campaign. Currency: USD.';
COMMENT ON COLUMN raw.trafficjunky_campaign_stats.ecpc IS 'Provider-reported cost per click in USD. Internal CPC is computed from canonical cost / clicks instead.';
COMMENT ON COLUMN raw.trafficjunky_campaign_stats.cost IS 'Cost in USD (converted to EUR in analytics).';

CREATE TABLE raw.trafficjunky_spot_stats (
    day          date NOT NULL,
    spot_id      integer NOT NULL,
    impressions  integer,
    clicks       integer,
    conversions  integer,
    revenue      numeric(12,4),
    ecpm         numeric(10,4),
    ecpc         numeric(10,4),
    ctr          numeric(8,4),
    PRIMARY KEY (day, spot_id)
);
COMMENT ON TABLE raw.trafficjunky_spot_stats IS 'TrafficJunky spots report (placements). Not mapped to campaigns, so not part of analytics in this PoC.';

-- ------------------------------------------------------------------ Voluum
-- GET /report (groupBy campaign, offer, country, trafficSource). As colunas dependem do groupBy/column pedidos.
CREATE TABLE raw.voluum_report (
    day                  date NOT NULL,
    campaign_id          uuid NOT NULL,
    campaign_name        text NOT NULL,
    traffic_source_id    uuid NOT NULL,
    traffic_source_name  text NOT NULL,
    offer_id             uuid NOT NULL,
    offer_name           text NOT NULL,
    country_code         text NOT NULL,
    visits               integer,
    clicks               integer,
    conversions          integer,
    impressions          integer,
    revenue              numeric(12,4),
    cost                 numeric(12,4),
    profit               numeric(12,4),
    ctr                  numeric(8,4),   -- provider-reported (clicks / visits, %)
    cr                   numeric(8,4),   -- provider-reported (conversions / visits, %)
    cpa                  numeric(12,4),
    cpc                  numeric(12,4),
    ecpm                 numeric(12,4),
    PRIMARY KEY (day, campaign_id, offer_id, country_code)
);
COMMENT ON TABLE raw.voluum_report IS 'Voluum GET /report rows (requested with tz=Europe/Lisbon, currency EUR). One row per day, campaign, offer and country.';
COMMENT ON COLUMN raw.voluum_report.cr IS 'Provider-reported CR over VISITS. The canonical conversion_rate uses CLICKS as denominator.';
COMMENT ON COLUMN raw.voluum_report.ctr IS 'Provider-reported ratio. Not used in analytics; computed from sums instead.';

CREATE TABLE raw.voluum_conversions (
    conversion_id         text PRIMARY KEY,
    campaign_id           uuid NOT NULL,
    campaign_name         text,
    traffic_source_name   text,
    offer_name            text,
    country_code          text,
    visit_timestamp       timestamp,
    postback_timestamp    timestamp,
    revenue               numeric(12,4),
    cost                  numeric(12,4),
    profit                numeric(12,4),
    conversion_type       text
);
COMMENT ON TABLE raw.voluum_conversions IS 'Voluum GET /report/conversions, subset. Only 2026-11-08 has detail rows in this PoC.';
COMMENT ON COLUMN raw.voluum_conversions.postback_timestamp IS 'When the conversion was reported back. Can be days after visit_timestamp.';
