"""FAULT INJECTION: partir um provider de propósito, para ver o Airflow reagir.

    POST /admin/trafficjunky/mode/http_500
    POST /admin/erobella/mode/schema_drift
    POST /admin/trafficjunky/mode/rate_limit?fail_times=2
    GET  /admin/state                      (modo de cada provider)
    POST /admin/reset                      (tudo para healthy)

O estado e POR PROVIDER: partir o TrafficJunky nao afeta a Erobella. E isso que
permite ver, ao mesmo tempo, um DAG a verde e outro a vermelho.

AVISO - SO PARA FORMACAO.
Um endpoint que muda o comportamento de um servico em runtime, sem autenticacao e
na mesma porta do trafego normal, NAO seria implementado assim em producao. Em
producao usa-se chaos engineering (Toxiproxy, Chaos Mesh...) em ambientes
isolados, com autenticacao e auditoria. O estado vive em memoria: reiniciar o
container volta a `healthy`.

Modos
-----
healthy        comportamento normal
http_500       todos os endpoints do provider (incl. health) respondem 500
timeout        os endpoints de DADOS demoram MOCK_TIMEOUT_DELAY_SECONDS (o health e rapido)
rate_limit     as primeiras `fail_times` chamadas ao provider levam 429; depois recupera
schema_drift   o provider renomeia, sem avisar, um campo que consumimos
partial_data   o endpoint de DETALHE devolve so parte dos dados; o total de controlo
               continua correto. Tudo corre "bem" ate a reconciliacao.
dirty_data     o provider envia dados que nao sabemos mapear para o nosso dominio
               (uma campanha sem correspondencia / um creative sem link)
"""

from __future__ import annotations

import asyncio
import threading
from enum import Enum
from typing import Any

from fastapi import APIRouter, HTTPException

from mock_api.config import get_mock_settings


class Mode(str, Enum):
    healthy = "healthy"
    http_500 = "http_500"
    timeout = "timeout"
    rate_limit = "rate_limit"
    schema_drift = "schema_drift"
    partial_data = "partial_data"
    dirty_data = "dirty_data"


class ProviderName(str, Enum):
    trafficjunky = "trafficjunky"
    erobella = "erobella"


class ProviderState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.mode = Mode.healthy
        self.rate_limit_remaining = 0

    def set(self, mode: Mode, fail_times: int = 2) -> None:
        with self._lock:
            self.mode = mode
            self.rate_limit_remaining = fail_times if mode is Mode.rate_limit else 0

    def consume_rate_limit(self) -> bool:
        """True se ESTE pedido deve levar 429."""
        with self._lock:
            if self.mode is Mode.rate_limit and self.rate_limit_remaining > 0:
                self.rate_limit_remaining -= 1
                return True
            return False


STATES: dict[ProviderName, ProviderState] = {p: ProviderState() for p in ProviderName}


def mode_of(provider: ProviderName) -> Mode:
    return STATES[provider].mode


def guard(provider: ProviderName, data: bool = True):
    """Dependencia FastAPI: aplica as falhas de disponibilidade antes do endpoint.

    data=False -> endpoint de health (so http_500 e rate_limit o afetam).
    data=True  -> endpoint de dados (tambem o modo timeout).
    """

    async def dependency() -> None:
        state = STATES[provider]
        if state.mode is Mode.http_500:
            raise HTTPException(500, f"Injected fault: {provider.value} http_500")
        if state.consume_rate_limit():
            raise HTTPException(429, "Injected fault: rate_limit", headers={"Retry-After": "5"})
        if data and state.mode is Mode.timeout:
            # async: nao bloqueia o servidor, so ESTE pedido fica pendurado
            await asyncio.sleep(get_mock_settings().timeout_delay_seconds)

    return dependency


# --------------------------------------------------------------------------
# Endpoints de administracao (nunca afetados pelas falhas: tens de poder curar)
# --------------------------------------------------------------------------

admin = APIRouter(prefix="/admin", tags=["admin (so para formacao)"])


@admin.get("/state")
def get_state() -> dict[str, Any]:
    return {p.value: {"mode": s.mode.value, "rate_limit_remaining": s.rate_limit_remaining}
            for p, s in STATES.items()}


@admin.post("/reset")
def reset() -> dict[str, Any]:
    for state in STATES.values():
        state.set(Mode.healthy)
    return get_state()


@admin.post("/{provider}/mode/{mode}")
def set_mode(provider: ProviderName, mode: Mode, fail_times: int = 2) -> dict[str, Any]:
    """Muda o modo de UM provider. `fail_times` so conta no modo rate_limit."""
    STATES[provider].set(mode, fail_times)
    return get_state()
