"""Configuracao da mock API. Mesma regra: so este ficheiro le o ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # opcional
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# A lista de campanhas partilhada com a pipeline (a que vai para dim_campaign).
# No container esta montada em /app/data/campaigns.csv.
CAMPAIGNS_CSV = Path(__file__).resolve().parents[1] / "data" / "campaigns.csv"


@dataclass(frozen=True)
class MockSettings:
    # Mesma seed + mesmo dia => exatamente os mesmos dados.
    seed: int = 42
    timeout_delay_seconds: float = 20.0


def get_mock_settings() -> MockSettings:
    return MockSettings(
        seed=int(os.getenv("MOCK_SEED", "42")),
        timeout_delay_seconds=float(os.getenv("MOCK_TIMEOUT_DELAY_SECONDS", "20")),
    )
