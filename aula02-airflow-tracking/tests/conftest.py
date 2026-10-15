"""Fixtures partilhadas.

Os testes de base de dados correm num SCHEMA temporario do PostgreSQL de
desenvolvimento (docker compose up -d postgres), por isso nunca tocam nas
tabelas reais. Se o Postgres nao estiver acessivel, esses testes sao saltados.
"""

import os
import uuid

import psycopg
import pytest

from pipeline.config import SQL_DIR

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://tracking:tracking@localhost:5432/analytics"
)


@pytest.fixture
def db_url():
    """Um schema novo por teste; apagado no fim. Devolve o URL a usar."""
    schema = f"test_{uuid.uuid4().hex[:8]}"
    try:
        admin = psycopg.connect(TEST_DATABASE_URL, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL nao acessivel (docker compose up -d postgres)")
    admin.execute(f"CREATE SCHEMA {schema}")
    sep = "&" if "?" in TEST_DATABASE_URL else "?"
    url = f"{TEST_DATABASE_URL}{sep}options=-csearch_path%3D{schema}"
    try:
        yield url
    finally:
        admin.execute(f"DROP SCHEMA {schema} CASCADE")
        admin.close()


@pytest.fixture
def conn(db_url):
    from pipeline.load import apply_sql_files, connect

    # autocommit: sem transacoes abertas a segurar locks (uma leitura numa view
    # bloquearia o DROP VIEW que a pipeline faz ao aplicar analytics.sql).
    with connect(db_url, autocommit=True) as c:
        apply_sql_files(c)
        yield c


@pytest.fixture
def sql_dir():
    return SQL_DIR
