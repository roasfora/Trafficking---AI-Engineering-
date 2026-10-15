"""DEMO: carga ingenua vs carga idempotente.

Carrega as MESMAS conversoes de um dia tres vezes, de duas maneiras:

    demo_naive_conversions        INSERT simples, sem chave primaria
    demo_idempotent_conversions   chave primaria composta + INSERT ... ON CONFLICT DO UPDATE
                                  (o mesmo upsert() que a pipeline usa em fact_conversions)

Simula o que acontece num retry ou num backfill: a mesma janela chega outra vez.

    docker compose exec -w /opt/airflow/project airflow python -m scripts.demo_idempotency

(ou, no host, com DATABASE_URL a apontar para localhost:  python -m scripts.demo_idempotency)

Usa tabelas proprias: nao toca em fact_conversions. Cada execucao recria-as, por
isso podes repetir a demo as vezes que quiseres. `--cleanup` apaga-as.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from api import generator
from api.config import get_api_settings
from pipeline.load import apply_sql_files, connect, naive_insert, upsert
from pipeline.transform import KEYS, transform

NAIVE = "demo_naive_conversions"
IDEMPOTENT = "demo_idempotent_conversions"
KEY = KEYS["conversions"]  # click_id, conversion_type_id, postback_timestamp


def count(conn, table: str) -> tuple[int, int]:
    """(linhas, chaves distintas)"""
    return conn.execute(
        f"SELECT count(*), count(DISTINCT ({', '.join(KEY)})) FROM {table}"
    ).fetchone()


def main() -> None:
    day = datetime(2026, 10, 1, tzinfo=timezone.utc)
    rows = generator.list_conversions(get_api_settings().seed, day, day + timedelta(days=1))
    df = transform("conversions", rows)  # o mesmo transform da pipeline

    with connect() as conn:
        apply_sql_files(conn)
        conn.execute(f"DROP TABLE IF EXISTS {NAIVE}, {IDEMPOTENT}")
        if "--cleanup" in sys.argv:
            conn.commit()
            print("Tabelas de demo apagadas.")
            return

        # Mesmas colunas que fact_conversions. A UNICA diferenca esta aqui:
        conn.execute(f"CREATE TABLE {NAIVE} (LIKE fact_conversions INCLUDING DEFAULTS)")  # sem PK
        conn.execute(f"CREATE TABLE {IDEMPOTENT} (LIKE fact_conversions INCLUDING ALL)")  # com PK composta
        conn.commit()

        print(f"\nCada execucao carrega as MESMAS {len(df)} conversoes ({day.date()}).\n")
        row = "{:<10}{:<29}{:<29}{}"
        print(row.format("", "INGENUO (insert)", "IDEMPOTENTE (upsert)", ""))
        print(row.format("execucao", "linhas / chaves distintas", "linhas / chaves distintas", "inseridas / atualizadas"))
        print("-" * 88)

        for run in (1, 2, 3):
            naive_insert(conn, NAIVE, df)
            result = upsert(conn, IDEMPOTENT, df, key=KEY)
            conn.commit()
            n_rows, n_keys = count(conn, NAIVE)
            i_rows, i_keys = count(conn, IDEMPOTENT)
            print(row.format(f"run {run}", f"{n_rows} / {n_keys}", f"{i_rows} / {i_keys}",
                             f"{result['inserted']} / {result['updated']}"))

        dup = conn.execute(
            f"SELECT count(*) FROM (SELECT 1 FROM {NAIVE} GROUP BY {', '.join(KEY)} HAVING count(*) > 1) d"
        ).fetchone()[0]
        revenue = conn.execute(f"SELECT sum(revenue) FROM {NAIVE}").fetchone()[0]
        real = conn.execute(f"SELECT sum(revenue) FROM {IDEMPOTENT}").fetchone()[0]
        print("-" * 88)
        print(f"\nIngenuo:     {dup} conversoes aparecem 3 vezes. Receita: {revenue:,.2f} USD (devia ser {real:,.2f}).")
        print("Idempotente: continua a ter exatamente uma linha por chave. Receita correta.")
        print("\nOlha para as colunas loaded_at / updated_at em demo_idempotent_conversions:")
        print("  loaded_at  = quando vimos a conversao pela 1a vez  (nao muda)")
        print("  updated_at = a ultima vez que a recarregamos       (muda a cada run)")
        print("\nApagar as tabelas de demo:  python -m scripts.demo_idempotency --cleanup\n")


if __name__ == "__main__":
    main()
