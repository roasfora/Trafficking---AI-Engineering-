"""Tool 1: get_dataset_metadata. Metadata TECNICA vinda do catalogo do PostgreSQL."""

from __future__ import annotations

from typing import Any

from tools.metrics import load_semantic
from tools.postgres import execute

_cache: dict[str, dict[str, Any]] = {}

COLUMNS_SQL = """
SELECT c.column_name,
       c.data_type,
       col_description(format('%%I.%%I', c.table_schema, c.table_name)::regclass, c.ordinal_position)
FROM information_schema.columns c
WHERE c.table_schema = %s AND c.table_name = %s
ORDER BY c.ordinal_position
"""

TABLE_SQL = "SELECT obj_description(format('%%I.%%I', %s::text, %s::text)::regclass, 'pg_class')"


def clear_cache() -> None:
    _cache.clear()


def get_dataset_metadata(dataset_name: str) -> dict[str, Any]:
    """Return the technical metadata of an allowed dataset: description, column names,
    PostgreSQL types and column descriptions (read from the PostgreSQL catalog).

    Use it to confirm which columns exist before writing SQL.
    Only datasets declared in the semantic layer are available.
    """
    allowed = [load_semantic()["dataset"]]
    if dataset_name not in allowed:
        return {"error": "Dataset not allowed", "allowed_datasets": allowed}
    if dataset_name in _cache:
        return _cache[dataset_name]

    schema, table = dataset_name.split(".")
    _, columns = execute(COLUMNS_SQL, (schema, table))
    _, table_row = execute(TABLE_SQL, (schema, table))
    result = {
        "dataset": dataset_name,
        "description": table_row[0][0],
        "columns": [{"name": n, "type": t, "description": d} for n, t, d in columns],
    }
    _cache[dataset_name] = result
    return result
