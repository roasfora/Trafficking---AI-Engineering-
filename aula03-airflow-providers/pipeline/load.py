"""LOAD: escrever no PostgreSQL de forma IDEMPOTENTE.

IDEMPOTENCIA: executar a mesma carga 1, 2 ou 10 vezes deixa a base de dados no
mesmo estado. Retries do Airflow, backfills e "Clear task" voltam a correr a mesma
janela; sem idempotencia cada gesto duplicaria dados em silencio.

Como: a chave (date, provider, campaign_id, source_specific_id) identifica a linha e
INSERT ... ON CONFLICT DO UPDATE ("upsert") atualiza em vez de duplicar.

ARMADILHA: source_specific_id e NULL no TrafficJunky. Numa unique constraint normal
NULL nunca e igual a NULL, o conflito nunca dispararia e cada recarga duplicaria
as linhas. Por isso a constraint e UNIQUE NULLS NOT DISTINCT (ver sql/schema.sql).
Nao se usa uma string vazia como "sentinela": NULL significa "nao ha", e deve
continuar a ser NULL.
"""

from __future__ import annotations

import csv
import logging
from typing import Any
from uuid import UUID

import psycopg

from contracts.canonical import CampaignDailyStat
from pipeline.config import CAMPAIGNS_CSV, SQL_DIR, get_settings
from pipeline.validate import read_json

log = logging.getLogger(__name__)

COLUMNS = ["date", "provider", "campaign_id", "source_specific_id", "currency", "impressions", "clicks", "cost"]
KEY = ["date", "provider", "campaign_id", "source_specific_id"]


def connect(database_url: str | None = None, **kwargs: Any) -> psycopg.Connection:
    """Liga a base ANALYTICS. O URL vem de DATABASE_URL, nunca do codigo."""
    return psycopg.connect(database_url or get_settings().database_url, **kwargs)


def seed_dim_campaign(conn: psycopg.Connection) -> int:
    """Carrega data/campaigns.csv em dim_campaign.

    Na realidade esta dimensao e sincronizada por OUTRO sistema; aqui e uma lista
    fixa. A mock API le o mesmo ficheiro, por isso os nomes coincidem.
    """
    with CAMPAIGNS_CSV.open() as f:
        rows = [(UUID(r["campaign_id"]), r["campaign_name"]) for r in csv.DictReader(f)]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO dim_campaign (campaign_id, campaign_name) VALUES (%s, %s) "
            "ON CONFLICT (campaign_id) DO UPDATE SET campaign_name = EXCLUDED.campaign_name, updated_at = now()",
            rows,
        )
    return len(rows)


def apply_schema(conn: psycopg.Connection) -> None:
    """Cria tabelas e views se nao existirem e carrega a dimensao. Idempotente."""
    for name in ("schema.sql", "analytics.sql"):
        conn.execute((SQL_DIR / name).read_text())
    seed_dim_campaign(conn)
    conn.commit()


def campaign_mapping(conn: psycopg.Connection) -> dict[str, UUID]:
    """{campaign_name: campaign_id}: o mapping que os transforms usam."""
    return {name: cid for cid, name in conn.execute("SELECT campaign_id, campaign_name FROM dim_campaign")}


def fetch_campaign_mapping() -> dict[str, UUID]:
    """Garante o schema e devolve o mapping nome -> campaign_id.

    O transform precisa de dim_campaign ANTES do load: numa base de dados nova a
    tabela ainda nao existe. apply_schema e idempotente, por isso chama-se sempre.
    """
    with connect() as conn:
        apply_schema(conn)
        return campaign_mapping(conn)


def _params(row: dict[str, Any] | CampaignDailyStat) -> tuple:
    data = row.model_dump() if isinstance(row, CampaignDailyStat) else row
    provider = data["provider"]
    return (
        data["date"], getattr(provider, "value", provider), data["campaign_id"],
        data["source_specific_id"], data["currency"], data["impressions"], data["clicks"], data["cost"],
    )


def naive_insert(conn: psycopg.Connection, table: str, rows: list[CampaignDailyStat]) -> int:
    """A ma versao: INSERT simples. Serve so para a demonstracao."""
    with conn.cursor() as cur:
        cur.executemany(
            f"INSERT INTO {table} ({', '.join(COLUMNS)}) VALUES ({', '.join(['%s'] * len(COLUMNS))})",
            [_params(r) for r in rows],
        )
    return len(rows)


def upsert_stats(conn: psycopg.Connection, rows: list[CampaignDailyStat], table: str = "fact_campaign_daily") -> dict[str, int]:
    """A boa versao: INSERT ... ON CONFLICT (chave) DO UPDATE.

    Devolve quantas linhas foram inseridas e quantas ja existiam (atualizadas). O
    truque `xmax = 0` e uma particularidade do PostgreSQL: numa linha acabada de
    inserir o xmax e 0; numa atualizada nao.
    """
    if not rows:
        return {"inserted": 0, "updated": 0}
    updates = [c for c in COLUMNS if c not in KEY]
    query = (
        f"INSERT INTO {table} ({', '.join(COLUMNS)}) VALUES ({', '.join(['%s'] * len(COLUMNS))}) "
        f"ON CONFLICT ({', '.join(KEY)}) DO UPDATE SET "
        + ", ".join(f"{c} = EXCLUDED.{c}" for c in updates)
        + ", updated_at = now() RETURNING (xmax = 0) AS inserted"
    )
    inserted = updated = 0
    with conn.cursor() as cur:
        cur.executemany(query, [_params(r) for r in rows], returning=True)
        while True:
            (was_inserted,) = cur.fetchone()
            inserted += was_inserted
            updated += not was_inserted
            if not cur.nextset():
                break
    return {"inserted": inserted, "updated": updated}


def run_load(meta: dict[str, Any]) -> dict[str, Any]:
    """Task `load`: staging/canonical.json -> fact_campaign_daily, numa transacao."""
    rows = [CampaignDailyStat.model_validate(r) for r in read_json(meta["staging_path"])]
    with connect() as conn:
        apply_schema(conn)
        with conn.transaction():
            result = upsert_stats(conn, rows)
    log.info("%s %s: %d linhas -> inseridas=%d atualizadas=%d",
             meta["provider"], meta["date"], len(rows), result["inserted"], result["updated"])
    return {**meta, "loaded": result}
