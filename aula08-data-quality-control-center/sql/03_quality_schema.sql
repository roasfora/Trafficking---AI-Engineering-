-- Data Quality is data: os resultados dos checks sao linhas numa tabela, nao logs.

CREATE SCHEMA IF NOT EXISTS data_quality;

CREATE TABLE IF NOT EXISTS data_quality.check_results (
    id             bigserial PRIMARY KEY,
    run_id         text             NOT NULL,
    checked_at     timestamptz      NOT NULL,
    provider       text             NOT NULL,
    dataset        text             NOT NULL,
    layer          text             NOT NULL CHECK (layer IN ('bronze', 'silver', 'semantic')),
    check_name     text             NOT NULL,
    dimension      text             NOT NULL,
    status         text             NOT NULL CHECK (status IN ('PASS', 'WARN', 'FAIL')),
    observed_value double precision,
    expected_value double precision,
    threshold      double precision,
    details        jsonb            NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_cr_run ON data_quality.check_results (run_id);
CREATE INDEX IF NOT EXISTS idx_cr_status ON data_quality.check_results (status);

CREATE TABLE IF NOT EXISTS data_quality.pipeline_runs (
    run_id          text PRIMARY KEY,
    scenario        text        NOT NULL,
    gate_mode       text        NOT NULL,
    started_at      timestamptz NOT NULL,
    finished_at     timestamptz,
    status          text        NOT NULL,           -- RUNNING | PUBLISHED | BLOCKED | ERROR
    publish_allowed boolean,
    gates           jsonb       NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS data_quality.alerts (
    alert_id    bigserial PRIMARY KEY,
    run_id      text        NOT NULL,
    check_name  text        NOT NULL,
    provider    text        NOT NULL,
    status      text        NOT NULL,
    message     text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    sent_at     timestamptz,
    destination text
);
