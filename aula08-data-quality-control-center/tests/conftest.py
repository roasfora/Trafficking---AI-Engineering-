"""Fixtures. Os testes de integracao usam uma base SEPARADA (dq_test) para nunca tocar nos dados da demo.

Se o PostgreSQL nao estiver acessivel (docker compose up -d postgres), esses testes fazem skip.
Os testes de logica pura (anomalies, checks sobre dados em memoria) correm sempre.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ADMIN_URL = os.getenv("DQ_TEST_ADMIN_URL", "postgresql://dq:dq@localhost:5436/postgres")
TEST_URL = os.getenv("DQ_TEST_DATABASE_URL", "postgresql://dq:dq@localhost:5436/dq_test")

# Tem de ser definido ANTES de qualquer chamada a get_settings().
os.environ["DATABASE_URL"] = TEST_URL
os.environ["DQ_WEBHOOK_URL"] = ""
os.environ["AS_OF_DATE"] = "2026-11-13"
os.environ["GATE_MODE"] = "observe"
os.environ["PROVIDERS"] = ""
os.environ["SCENARIO"] = "healthy"


class CaptureNotifier:
    """Notifier de teste: guarda em memoria o que seria enviado."""

    def __init__(self):
        self.results = []

    def notify(self, result) -> None:
        self.results.append(result)


@pytest.fixture(scope="session")
def db(tmp_path_factory):
    """Cria a base dq_test (se faltar), aplica sql/*.sql e limpa as tabelas do pipeline."""
    try:
        with psycopg.connect(ADMIN_URL, autocommit=True, connect_timeout=3) as admin:
            exists = admin.execute("SELECT 1 FROM pg_database WHERE datname = 'dq_test'").fetchone()
            if not exists:
                admin.execute("CREATE DATABASE dq_test")
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL not reachable ({exc.__class__.__name__}): run `docker compose up -d postgres`")

    os.environ["PAYLOAD_DIR"] = str(tmp_path_factory.mktemp("payloads"))
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        for sql_file in sorted((ROOT / "sql").glob("*.sql")):
            conn.execute(sql_file.read_text(encoding="utf-8"))
        conn.execute("""TRUNCATE raw.api_runs, raw.erobella_daily_stats, raw.trafficjunky_campaign_stats,
                        raw.voluum_report, raw.voluum_conversions, analytics.campaign_performance_daily,
                        analytics.published_campaign_performance_daily, analytics.daily_control,
                        data_quality.check_results, data_quality.pipeline_runs, data_quality.alerts
                        RESTART IDENTITY""")
    return TEST_URL


@pytest.fixture()
def conn(db):
    from db import connect

    with connect() as c:
        yield c


@pytest.fixture(scope="session")
def get_results(db):
    """get_results(run_id, layer=None) -> {(provider, check_name): linha de check_results}"""
    from db import connect

    def _get(run_id: str, layer: str | None = None) -> dict:
        sql = "SELECT * FROM data_quality.check_results WHERE run_id = %s"
        params = [run_id]
        if layer:
            sql += " AND layer = %s"
            params.append(layer)
        with connect() as c:
            return {(r["provider"], r["check_name"]): r for r in c.execute(sql, params).fetchall()}

    return _get


@pytest.fixture(scope="session")
def healthy_run(db):
    from quality.pipeline import run_pipeline

    return run_pipeline("healthy", gate_mode="observe", notifier=CaptureNotifier(), log=lambda *_: None)


@pytest.fixture(scope="session")
def broken_run(db, healthy_run):  # depende de healthy_run: assim ha sempre um "ultimo bom" publicado antes
    from quality.pipeline import run_pipeline

    notifier = CaptureNotifier()
    result = run_pipeline("broken", gate_mode="observe", notifier=notifier, log=lambda *_: None)
    result.notifier = notifier
    return result
