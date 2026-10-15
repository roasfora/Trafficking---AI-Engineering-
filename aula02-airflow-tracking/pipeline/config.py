"""Configuracao do pipeline (consumer).

Nenhum outro ficheiro do pipeline chama os.getenv(). Repara que existem DUAS
bases de dados na historia, e que so uma e configurada aqui:

* analytics (DATABASE_URL)  -> o destino do ETL. Configurada aqui.
* metadados do Airflow      -> pertence ao Airflow. O pipeline nunca lhe toca.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # opcional: permite um ficheiro .env sem o tornar obrigatorio
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_base_url: str = "http://localhost:8000"
    staging_dir: Path = ROOT / "data" / "staging"
    http_timeout_seconds: float = 5.0
    page_size: int = 500
    freshness_max_lag_hours: float = 6.0


def get_settings() -> Settings:
    """Le o ambiente no momento da chamada (e nao no import): facilita testes."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL nao esta definido. Copia .env.example para .env "
            "(nunca ponhas credenciais no codigo)."
        )
    return Settings(
        database_url=database_url,
        api_base_url=os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/"),
        staging_dir=Path(os.getenv("PIPELINE_STAGING_DIR", str(ROOT / "data" / "staging"))),
        http_timeout_seconds=float(os.getenv("PIPELINE_HTTP_TIMEOUT_SECONDS", "5")),
        page_size=int(os.getenv("PIPELINE_PAGE_SIZE", "500")),
        freshness_max_lag_hours=float(os.getenv("PIPELINE_FRESHNESS_MAX_LAG_HOURS", "6")),
    )
