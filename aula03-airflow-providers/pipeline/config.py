"""Configuracao central. Nenhum outro ficheiro do pipeline chama os.getenv().

A pipeline pode falar com DUAS coisas diferentes, escolhidas por USE_MOCK_API:

    USE_MOCK_API=true   a mock API local (FastAPI): dados deterministicos,
                        a aula nao depende de nada externo.
    USE_MOCK_API=false  as APIs dos providers, com URLs e tokens do ambiente.

O resto da pipeline nao sabe qual das duas esta a usar: recebe um
`ProviderSettings` com o URL base, os caminhos e o token. E esta e a unica
"abstracao" de acesso a API que existe de proposito - nao ha framework de
providers.

Nunca ha tokens no codigo: vem do ambiente (.env, no .gitignore).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

try:  # opcional: permite um ficheiro .env sem o tornar obrigatorio
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"
CAMPAIGNS_CSV = ROOT / "data" / "campaigns.csv"


@dataclass(frozen=True)
class ProviderSettings:
    """Tudo o que e preciso para falar com UM provider."""

    name: str
    base_url: str
    stats_path: str
    health_path: str  # vazio = sem health check dedicado
    currency: str
    token: str | None = None
    total_path: str = ""  # so TrafficJunky
    total_strategy: str = "summary_endpoint"  # so TrafficJunky


@dataclass(frozen=True)
class Settings:
    database_url: str
    use_mock_api: bool
    trafficjunky: ProviderSettings
    erobella: ProviderSettings
    raw_dir: Path = ROOT / "data" / "raw"
    staging_dir: Path = ROOT / "data" / "staging"
    http_timeout_seconds: float = 5.0
    page_size: int = 5
    reconcile_tolerance: Decimal = Decimal("0.01")


def _flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def get_settings() -> Settings:
    """Le o ambiente no momento da chamada (e nao no import): facilita testes."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL nao esta definido. Copia .env.example para .env "
            "(nunca ponhas credenciais no codigo)."
        )
    use_mock = _flag("USE_MOCK_API")

    if use_mock:
        mock = os.getenv("MOCK_API_BASE_URL", "http://localhost:8001").rstrip("/")
        trafficjunky = ProviderSettings(
            name="trafficjunky", base_url=mock,
            stats_path="/mock/trafficjunky/stats",
            health_path="/mock/trafficjunky/health",
            total_path="/mock/trafficjunky/total",
            total_strategy=os.getenv("TRAFFICJUNKY_TOTAL_STRATEGY", "summary_endpoint"),
            currency=os.getenv("TRAFFICJUNKY_CURRENCY", "EUR"),
        )
        erobella = ProviderSettings(
            name="erobella", base_url=mock,
            stats_path="/mock/erobella/stats",
            health_path="/mock/erobella/health",
            currency=os.getenv("EROBELLA_CURRENCY", "EUR"),
        )
    else:
        trafficjunky = ProviderSettings(
            name="trafficjunky",
            base_url=os.getenv("TRAFFICJUNKY_BASE_URL", "").rstrip("/"),
            stats_path=os.getenv("TRAFFICJUNKY_STATS_PATH", "/campaigns/stats.json"),
            health_path=os.getenv("TRAFFICJUNKY_HEALTH_PATH", ""),
            total_path=os.getenv("TRAFFICJUNKY_TOTAL_PATH", ""),
            total_strategy=os.getenv("TRAFFICJUNKY_TOTAL_STRATEGY", "summary_endpoint"),
            currency=os.getenv("TRAFFICJUNKY_CURRENCY", "EUR"),
            token=os.getenv("TRAFFICJUNKY_BEARER_TOKEN"),
        )
        erobella = ProviderSettings(
            name="erobella",
            base_url=os.getenv("EROBELLA_BASE_URL", "").rstrip("/"),
            stats_path=os.getenv("EROBELLA_STATS_PATH", "/api/v1/stats"),
            health_path=os.getenv("EROBELLA_HEALTH_PATH", ""),
            currency=os.getenv("EROBELLA_CURRENCY", "EUR"),
            token=os.getenv("EROBELLA_API_TOKEN"),
        )

    return Settings(
        database_url=database_url,
        use_mock_api=use_mock,
        trafficjunky=trafficjunky,
        erobella=erobella,
        raw_dir=Path(os.getenv("PIPELINE_RAW_DIR", str(ROOT / "data" / "raw"))),
        staging_dir=Path(os.getenv("PIPELINE_STAGING_DIR", str(ROOT / "data" / "staging"))),
        http_timeout_seconds=float(os.getenv("PIPELINE_HTTP_TIMEOUT_SECONDS", "5")),
        page_size=int(os.getenv("PIPELINE_PAGE_SIZE", "5")),
        reconcile_tolerance=Decimal(os.getenv("RECONCILE_TOLERANCE", "0.01")),
    )
