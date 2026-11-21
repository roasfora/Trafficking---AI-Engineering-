"""Configuracao da PoC. Variaveis de ambiente (ou .env); nenhum segredo, nenhuma API real."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

try:  # opcional: so ajuda a carregar o .env quando o python-dotenv esta instalado
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).parent
PROVIDERS = ("erobella", "trafficjunky", "voluum")


@dataclass(frozen=True)
class Settings:
    database_url: str
    as_of_date: date
    window_days: int
    scenario: str
    providers: tuple
    gate_mode: str          # strict | observe
    webhook_url: str
    payload_dir: Path
    checks_file: Path
    semantic_file: Path


def get_settings() -> Settings:
    """Le o ambiente de cada vez que e chamada (os testes mudam DATABASE_URL)."""
    providers = tuple(p.strip() for p in os.getenv("PROVIDERS", "").split(",") if p.strip()) or PROVIDERS
    unknown = set(providers) - set(PROVIDERS)
    if unknown:
        raise ValueError(f"unknown provider(s): {sorted(unknown)} (valid: {PROVIDERS})")
    gate_mode = os.getenv("GATE_MODE", "observe").strip().lower()
    if gate_mode not in ("strict", "observe"):
        raise ValueError("GATE_MODE must be 'strict' or 'observe'")
    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql://dq:dq@localhost:5436/dq"),
        as_of_date=date.fromisoformat(os.getenv("AS_OF_DATE", "2026-11-13")),
        window_days=int(os.getenv("WINDOW_DAYS", "14")),
        scenario=os.getenv("SCENARIO", "healthy").strip().lower(),
        providers=providers,
        gate_mode=gate_mode,
        webhook_url=os.getenv("DQ_WEBHOOK_URL", "").strip(),
        payload_dir=Path(os.getenv("PAYLOAD_DIR", str(ROOT / "logs" / "payloads"))),
        checks_file=Path(os.getenv("CHECKS_FILE", str(ROOT / "config" / "quality_checks.yaml"))),
        semantic_file=Path(os.getenv("SEMANTIC_FILE", str(ROOT / "semantic.yaml"))),
    )
