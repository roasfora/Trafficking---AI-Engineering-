-- Corre UMA vez, quando o volume do Postgres e criado.
--
-- A base "analytics" ja foi criada pela variavel POSTGRES_DB.
-- Aqui criamos a segunda: a dos METADADOS do Airflow.
--
--   analytics  -> dados do negocio (dim_campaign, fact_campaign_daily)
--   airflow    -> estado do Airflow (runs, tasks, logs)
CREATE DATABASE airflow;
