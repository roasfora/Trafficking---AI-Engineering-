"""Leitor da camada semantica (semantic.yaml). As formulas vivem no yaml, nunca duplicadas no codigo."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from config import get_settings


def load_semantic(path: Path | None = None) -> dict[str, Any]:
    with open(path or get_settings().semantic_file, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def metric_expression(name: str, semantic: dict | None = None) -> str:
    semantic = semantic or load_semantic()
    try:
        return semantic["metrics"][name]["expression"]
    except KeyError as exc:
        raise KeyError(f"unknown metric {name!r}") from exc


def metric_sql(name: str, where: str = "TRUE", group_by: str | None = None, semantic: dict | None = None) -> str:
    """SELECT da metrica sobre a tabela Silver. `where`/`group_by` sao fragmentos nossos, nunca input do utilizador."""
    semantic = semantic or load_semantic()
    expr = metric_expression(name, semantic)
    table = semantic["dataset"]
    cols = f"{group_by}, " if group_by else ""
    tail = f" GROUP BY {group_by}" if group_by else ""
    return f"SELECT {cols}{expr} AS value FROM {table} WHERE {where}{tail}"
