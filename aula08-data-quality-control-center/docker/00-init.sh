#!/bin/bash
# Corre UMA vez, quando o volume do Postgres nasce: cria a base de metadados do Airflow
# e aplica sql/*.sql (schemas raw / analytics / data_quality + referencia + views).
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE airflow;"
for f in /sql/*.sql; do
  echo "applying $f"
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$f"
done
