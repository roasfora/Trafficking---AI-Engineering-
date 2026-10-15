-- Corre UMA vez, quando o volume do Postgres e criado.
--
-- A base "analytics" ja foi criada pela variavel POSTGRES_DB.
-- Aqui criamos a segunda: a dos METADADOS do Airflow.
--
--   analytics  -> dados do negocio (dim_*, fact_*)      <- o nosso ETL escreve aqui
--   airflow    -> estado do Airflow (runs, tasks, logs) <- so o Airflow escreve aqui
--
-- Num sistema real seriam servidores (e utilizadores) diferentes.
CREATE DATABASE airflow;
