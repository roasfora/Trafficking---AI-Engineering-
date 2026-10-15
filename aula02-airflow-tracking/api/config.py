"""Configuracao da API (producer).

Mesma regra da aula 01: so este ficheiro le o ambiente.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:  # opcional: permite um ficheiro .env sem o tornar obrigatorio
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


@dataclass(frozen=True)
class ApiSettings:
    # Mesma seed => mesmos dados, sempre. E o que torna a demo repetivel
    # e o idempotency demo possivel (mesmos click_id em cada execucao).
    seed: int = 42
    slow_delay_seconds: float = 20.0


def get_api_settings() -> ApiSettings:
    return ApiSettings(
        seed=int(os.getenv("API_SEED", "42")),
        slow_delay_seconds=float(os.getenv("API_SLOW_DELAY_SECONDS", "20")),
    )
