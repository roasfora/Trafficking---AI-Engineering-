"""Ligacao ao PostgreSQL (psycopg 3). Uma funcao, para ser facil de trocar nos testes."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from config import Settings, get_settings


def connect(settings: Settings | None = None, autocommit: bool = False) -> psycopg.Connection:
    settings = settings or get_settings()
    return psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=autocommit, connect_timeout=5)
