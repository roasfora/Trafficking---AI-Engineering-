-- ANALYTICS: modelo canonico comum aos tres providers.
-- NAO guarda ratios (cpc, ctr, cr...): so somas. Os ratios vem do semantic.yaml.
CREATE TABLE analytics.campaign_performance_daily (
    date           date    NOT NULL,
    provider       text    NOT NULL CHECK (provider IN ('erobella', 'trafficjunky', 'voluum')),
    campaign_id    text    NOT NULL,
    campaign_name  text    NOT NULL,
    traffic_source text,
    country        text,
    impressions    bigint  CHECK (impressions >= 0),
    visits         bigint  CHECK (visits >= 0),
    clicks         bigint  CHECK (clicks >= 0),
    conversions    bigint  CHECK (conversions >= 0),
    cost           numeric(14,4) NOT NULL CHECK (cost >= 0),
    revenue        numeric(14,4) CHECK (revenue >= 0),
    PRIMARY KEY (date, provider, campaign_id)
);

COMMENT ON TABLE analytics.campaign_performance_daily IS
  'Daily advertising performance per provider and campaign, normalized from the raw provider payloads. All money is EUR. Columns are NULL (not 0) when the provider does not report them.';
COMMENT ON COLUMN analytics.campaign_performance_daily.date IS 'Performance date (provider day; see provider notes for timezone differences).';
COMMENT ON COLUMN analytics.campaign_performance_daily.provider IS 'erobella | trafficjunky | voluum.';
COMMENT ON COLUMN analytics.campaign_performance_daily.campaign_id IS 'Provider campaign id as text. For Erobella it is the creative label.';
COMMENT ON COLUMN analytics.campaign_performance_daily.campaign_name IS 'Human-readable campaign name.';
COMMENT ON COLUMN analytics.campaign_performance_daily.traffic_source IS 'Erobella: partner. TrafficJunky: TrafficJunky. Voluum: traffic source name.';
COMMENT ON COLUMN analytics.campaign_performance_daily.country IS 'ISO-2 country code. Only Voluum reports it; NULL for the others.';
COMMENT ON COLUMN analytics.campaign_performance_daily.impressions IS 'Ad impressions.';
COMMENT ON COLUMN analytics.campaign_performance_daily.visits IS 'Tracker visits. Only Voluum reports it; NULL for the others.';
COMMENT ON COLUMN analytics.campaign_performance_daily.clicks IS 'Clicks.';
COMMENT ON COLUMN analytics.campaign_performance_daily.conversions IS 'Conversions. Erobella does not report conversions (NULL).';
COMMENT ON COLUMN analytics.campaign_performance_daily.cost IS 'Cost in EUR (TrafficJunky USD converted at a fixed PoC rate).';
COMMENT ON COLUMN analytics.campaign_performance_daily.revenue IS 'Revenue in EUR. Only Voluum reports it; NULL for the others, so ROAS exists only for voluum.';
