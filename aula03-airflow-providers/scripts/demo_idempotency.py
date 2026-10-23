"""DEMO: tres cargas do MESMO dia TrafficJunky, de tres maneiras.

    1. ingenua                 INSERT simples, sem chave                    -> duplica
    2. upsert + unique normal  ON CONFLICT, mas NULL != NULL na chave       -> duplica, SEM ERRO
    3. upsert + NULLS NOT DISTINCT  (o que a pipeline usa)                  -> nao duplica

A 2 e a armadilha: o TrafficJunky tem source_specific_id = NULL. Numa unique
constraint tradicional dois NULL nunca sao "iguais", o ON CONFLICT nunca dispara e
cada recarga acrescenta as mesmas linhas, sem nenhum erro. (Nao se resolve com uma
string vazia como sentinela: NULL significa "nao ha" e deve continuar a ser NULL.)

    docker compose exec -w /opt/airflow/project airflow python -m scripts.demo_idempotency

Usa tabelas proprias (demo_*): nao toca em fact_campaign_daily. `--cleanup` apaga-as.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal

from contracts.canonical import CampaignDailyStat
from mock_api import datasets
from pipeline import load
from pipeline.config import get_settings
from providers import trafficjunky as tj

TABLES = ("demo_naive", "demo_unique_plain", "demo_nulls_not_distinct")


def count(conn, table: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def main() -> None:
    day = date(2026, 10, 20)
    with load.connect() as conn:
        load.apply_schema(conn)
        conn.execute(f"DROP TABLE IF EXISTS {', '.join(TABLES)}")
        if "--cleanup" in sys.argv:
            conn.commit()
            print("Tabelas de demo apagadas.")
            return

        # o mesmo dia do TrafficJunky, transformado exatamente como na pipeline
        stats = [{**r, "cost": Decimal(str(r["cost"]))} for r in datasets.trafficjunky_full(42, day)]
        rows, _ = tj.build_canonical(stats, load.campaign_mapping(conn), day, get_settings().trafficjunky.currency)
        stats_models = [CampaignDailyStat.model_validate(r) for r in rows]

        conn.execute("CREATE TABLE demo_naive (LIKE fact_campaign_daily INCLUDING DEFAULTS)")  # sem chave
        conn.execute("CREATE TABLE demo_unique_plain (LIKE fact_campaign_daily INCLUDING DEFAULTS)")
        conn.execute("ALTER TABLE demo_unique_plain ADD CONSTRAINT uq_plain "
                     "UNIQUE (date, provider, campaign_id, source_specific_id)")  # NULL != NULL
        conn.execute("CREATE TABLE demo_nulls_not_distinct (LIKE fact_campaign_daily INCLUDING ALL)")  # NULLS NOT DISTINCT
        conn.commit()

        print(f"\nCada execucao carrega as MESMAS {len(stats_models)} linhas TrafficJunky ({day}).\n")
        row = "{:<10}{:<18}{:<28}{:<26}"
        print(row.format("execucao", "1. INSERT", "2. UPSERT + unique normal", "3. UPSERT + NULLS NOT DISTINCT"))
        print("-" * 82)
        for run in (1, 2, 3):
            load.naive_insert(conn, "demo_naive", stats_models)
            load.upsert_stats(conn, stats_models, table="demo_unique_plain")
            load.upsert_stats(conn, stats_models, table="demo_nulls_not_distinct")
            conn.commit()
            print(row.format(f"run {run}", f"{count(conn, 'demo_naive')} linhas",
                             f"{count(conn, 'demo_unique_plain')} linhas",
                             f"{count(conn, 'demo_nulls_not_distinct')} linhas"))
        print("-" * 82)
        print("\n1. Sem chave: cada carga duplica tudo.")
        print("2. Com ON CONFLICT mas unique normal: TAMBEM duplica, e sem nenhum erro (NULL != NULL).")
        print("3. UNIQUE NULLS NOT DISTINCT: continua com uma linha por campanha e dia.\n")
        print("Apagar as tabelas de demo:  python -m scripts.demo_idempotency --cleanup\n")


if __name__ == "__main__":
    main()
