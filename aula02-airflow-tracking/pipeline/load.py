"""LOAD: escrever no PostgreSQL (analytics) de forma IDEMPOTENTE.

IDEMPOTENCIA: executar a mesma carga 1, 2 ou 10 vezes deixa a base de dados
no mesmo estado. Sem isto, qualquer retry do Airflow ou backfill duplicaria
dados - e retries e backfills sao rotina, nao excecao.

Como: a PRIMARY KEY identifica o evento (click_id, conversion_id) e o
INSERT ... ON CONFLICT (pk) DO UPDATE ("upsert") diz ao PostgreSQL o que fazer
quando a linha ja existe: atualiza em vez de duplicar.

Aqui as chaves sao COMPOSTAS (a origem nao tem um ID por linha): uma conversao
e (click_id, conversion_type_id, postback_timestamp); um custo horario e
(datetime, campaign_id, investment_provider).

    naive_insert()   INSERT simples      -> 3 execucoes = 3x as linhas
    upsert()         ON CONFLICT         -> 3 execucoes = as mesmas linhas

(ver scripts/demo_idempotency.py)
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import psycopg
from psycopg import sql

from pipeline.config import SQL_DIR, get_settings
from pipeline.transform import KEYS, read_transformed

log = logging.getLogger(__name__)

# Ordem importa: as FKs apontam para tras. workspace e traffic_source antes de
# campaign (que os referencia); todas as dimensoes antes dos factos.
DIMENSION_TABLES = {
    "workspaces": "dim_workspace",
    "traffic_sources": "dim_traffic_source",
    "campaigns": "dim_campaign",
    "offers": "dim_offer",
}
FACT_TABLES = {
    "conversions": "fact_conversions",
    "campaign_costs": "fact_campaign_costs",
    "daily_control": "fact_daily_control",
}


def connect(database_url: str | None = None, **kwargs: Any) -> psycopg.Connection:
    """Liga a base ANALYTICS. O URL vem de DATABASE_URL, nunca do codigo."""
    return psycopg.connect(database_url or get_settings().database_url, **kwargs)


def apply_sql_files(conn: psycopg.Connection, names: tuple[str, ...] = ("schema.sql", "analytics.sql")) -> None:
    """Cria tabelas e views se nao existirem. Os ficheiros sao idempotentes."""
    for name in names:
        path = SQL_DIR / name
        if path.exists():
            conn.execute(path.read_text())
    conn.commit()


def _records(df: pd.DataFrame) -> list[tuple]:
    """DataFrame -> tuplos de tipos Python (o psycopg nao conhece numpy). NaN -> None."""
    return df.astype(object).where(df.notna(), None).values.tolist()


def naive_insert(conn: psycopg.Connection, table: str, df: pd.DataFrame) -> int:
    """A ma versao: INSERT simples. Serve so para a demonstracao."""
    cols = list(df.columns)
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, cols)),
        sql.SQL(", ").join(sql.Placeholder() * len(cols)),
    )
    with conn.cursor() as cur:
        cur.executemany(query, _records(df))
    return len(df)


def upsert(conn: psycopg.Connection, table: str, df: pd.DataFrame, key: list[str]) -> dict[str, int]:
    """A boa versao: INSERT ... ON CONFLICT (chave) DO UPDATE.

    `key` e a lista de colunas da chave primaria (uma ou varias).

    Devolve quantas linhas foram inseridas e quantas ja existiam (atualizadas).
    O truque `xmax = 0` e uma particularidade do PostgreSQL: numa linha
    acabada de inserir o xmax e 0; numa atualizada nao.
    """
    cols = list(df.columns)
    updates = [c for c in cols if c not in key]
    query = sql.SQL(
        "INSERT INTO {table} ({cols}) VALUES ({vals}) "
        "ON CONFLICT ({key}) DO UPDATE SET {sets}, updated_at = now() "
        "RETURNING (xmax = 0) AS inserted"
    ).format(
        table=sql.Identifier(table),
        cols=sql.SQL(", ").join(map(sql.Identifier, cols)),
        vals=sql.SQL(", ").join(sql.Placeholder() * len(cols)),
        key=sql.SQL(", ").join(map(sql.Identifier, key)),
        sets=sql.SQL(", ").join(
            sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in updates
        ),
    )
    inserted = updated = 0
    if df.empty:
        return {"inserted": 0, "updated": 0}
    with conn.cursor() as cur:
        cur.executemany(query, _records(df), returning=True)
        while True:
            (was_inserted,) = cur.fetchone()
            inserted += was_inserted
            updated += not was_inserted
            if not cur.nextset():
                break
    return {"inserted": inserted, "updated": updated}


def _load(transform_meta: dict[str, Any], tables: dict[str, str]) -> dict[str, Any]:
    results: dict[str, dict[str, int]] = {}
    with connect() as conn:
        apply_sql_files(conn)
        # Uma transacao: ou entram todas as tabelas deste passo, ou nenhuma.
        with conn.transaction():
            for name, table in tables.items():
                df = read_transformed(transform_meta["files"][name], name)
                results[table] = upsert(conn, table, df, KEYS[name])
                log.info("%-18s %s", table, results[table])
    return {**transform_meta, "loaded": {**transform_meta.get("loaded", {}), **results}}


def run_load_dimensions(transform_meta: dict[str, Any]) -> dict[str, Any]:
    """Task `load_dimensions`."""
    return _load(transform_meta, DIMENSION_TABLES)


def run_load_facts(load_meta: dict[str, Any]) -> dict[str, Any]:
    """Task `load_facts`: conversions, campaign_costs e daily_control (todas apontam para as dimensoes)."""
    return _load(load_meta, FACT_TABLES)
