"""Tool 3: run_postgres_query, mais o acesso a PostgreSQL partilhado pelo resto.

Camadas de defesa (da mais fraca para a mais forte):
    prompt -> tool schema -> SQL guard -> role read-only do PostgreSQL
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg

from config import Settings, get_settings
from tools.sql_guard import SqlRejected, check_sql


def connect(settings: Settings | None = None) -> psycopg.Connection:
    """Ligacao read-only com timeout. Nunca devolvida nem logada ao modelo."""
    settings = settings or get_settings()
    conn = psycopg.connect(
        settings.database_url,
        options=f"-c statement_timeout={settings.statement_timeout_ms}",
        connect_timeout=5,
    )
    conn.read_only = True
    return conn


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def execute(sql: str, params: tuple = (), settings: Settings | None = None) -> tuple[list[str], list[tuple]]:
    """Corre SQL ja validado (guard ou template nosso). Devolve (colunas, linhas)."""
    with connect(settings) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [col.name for col in cur.description]
        return columns, cur.fetchall()


def run_postgres_query(sql: str) -> dict[str, Any]:
    """Run ONE read-only SELECT on PostgreSQL and return the rows.

    Only the table analytics.campaign_performance_daily may be queried.
    This is the tool for CURRENT NUMERIC FACTS (spend, clicks, rankings, trends).
    Use metric expressions from get_metric_definition. The result is capped
    at a maximum number of rows. If the query is rejected, the error says why:
    fix the SQL and try again.
    """
    settings = get_settings()
    try:
        safe_sql = check_sql(sql, max_rows=settings.max_rows, max_length=settings.max_query_length)
    except SqlRejected as exc:
        return {"error": f"Query rejected by SQL guard: {exc}"}
    try:
        columns, rows = execute(safe_sql, settings=settings)
    except psycopg.Error as exc:
        # Mensagem do PostgreSQL (sem connection string) para o modelo poder corrigir.
        return {"error": f"PostgreSQL error: {str(exc).splitlines()[0]}"}
    return {
        "executed_sql": safe_sql,
        "columns": columns,
        "rows": [[_jsonable(v) for v in row] for row in rows],
        "row_count": len(rows),
    }
