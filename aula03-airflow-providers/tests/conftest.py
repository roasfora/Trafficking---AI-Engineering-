"""Fixtures partilhadas.

Os testes de base de dados correm num SCHEMA temporario do PostgreSQL de
desenvolvimento (docker compose up -d postgres), por isso nunca tocam nas tabelas
reais. Se o Postgres nao estiver acessivel, esses testes sao saltados.
"""

import os
import uuid

import psycopg
import pytest

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://providers:providers@localhost:5433/analytics"
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
    from pipeline.load import apply_schema, connect

    # autocommit: sem transacoes abertas a segurar locks (uma leitura numa view
    # bloquearia o DROP VIEW que a pipeline faz ao aplicar analytics.sql).
    with connect(db_url, autocommit=True) as c:
        apply_schema(c)
        yield c


@pytest.fixture
def env(monkeypatch, tmp_path, db_url):
    """Ambiente completo: BD temporaria, ficheiros em tmp, e a mock API EM MEMORIA.

    O cliente HTTP da pipeline e substituido por um TestClient da mock API: os
    testes exercitam o codigo real de extract/reconcile sem rede nem Docker.
    """
    from fastapi.testclient import TestClient

    import pipeline.http as pipeline_http
    from mock_api.main import app

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("USE_MOCK_API", "true")
    monkeypatch.setenv("PIPELINE_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("PIPELINE_STAGING_DIR", str(tmp_path / "staging"))
    monkeypatch.setenv("PIPELINE_PAGE_SIZE", "5")
    monkeypatch.setenv("RECONCILE_TOLERANCE", "0.01")
    monkeypatch.setattr(pipeline_http, "make_client", lambda provider, timeout: TestClient(app, base_url="http://mock"))
    admin = TestClient(app)
    admin.post("/admin/reset")
    yield admin
    admin.post("/admin/reset")
