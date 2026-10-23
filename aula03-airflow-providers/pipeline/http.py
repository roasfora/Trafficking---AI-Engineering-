"""Cliente HTTP: o unico sitio onde se constroi um cliente para um provider.

Seja mock ou API real (USE_MOCK_API), a pipeline recebe um `ProviderSettings` e
daqui sai um httpx.Client pronto: URL base, token e TIMEOUT.

O timeout nao e um detalhe: sem ele, uma API pendurada deixava a task a correr
para sempre. Com ele, o pedido desiste, a task falha e o Airflow decide o que fazer
(retries, retry_delay). raise_for_status() transforma um 500 ou um 429 numa excecao.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from pipeline.config import ProviderSettings

log = logging.getLogger(__name__)


def make_client(provider: ProviderSettings, timeout: float) -> httpx.Client:
    headers = {"Authorization": f"Bearer {provider.token}"} if provider.token else {}
    return httpx.Client(base_url=provider.base_url, headers=headers, timeout=timeout)


def get(client: httpx.Client, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
    response = client.get(path, params=params)
    if response.status_code == 429:
        log.warning("%s devolveu 429 (rate limit). Retry-After=%s", path, response.headers.get("Retry-After"))
    response.raise_for_status()
    return response
