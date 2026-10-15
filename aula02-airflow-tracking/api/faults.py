"""FAULT INJECTION: partir a API de proposito, para ver o Airflow reagir.

    POST /admin/mode/healthy
    POST /admin/mode/http_500
    POST /admin/mode/slow
    POST /admin/mode/rate_limit?fail_times=2
    POST /admin/mode/invalid_payload
    POST /admin/mode/schema_drift
    GET  /admin/mode

AVISO - SO PARA FORMACAO.
Um endpoint que muda o comportamento de um servico em runtime, sem autenticacao
e acessivel pela mesma porta do trafego normal, NAO seria implementado assim em
producao. Em producao, a injecao de falhas faz-se com ferramentas dedicadas
(chaos engineering: Toxiproxy, Chaos Mesh, Gremlin...), em ambientes isolados,
com autenticacao, auditoria e um botao de "parar tudo". E um servico real nunca
expoe controlos de sabotagem no seu proprio API publico.

O estado vive em memoria: reiniciar o container volta ao modo `healthy`.

O que cada modo faz
-------------------
healthy          comportamento normal
http_500         TODOS os endpoints (incl. /health) respondem 500
slow             endpoints de dados demoram API_SLOW_DELAY_SECONDS (/health e rapido)
rate_limit       as primeiras `fail_times` chamadas (a qualquer endpoint) levam 429;
                 depois a API recupera - para o retry ter sucesso
invalid_payload  valores que violam o contrato em ~1 de cada 5 registos de conversions
                 e campaign-costs (revenue/cost negativos, country_code com 3 letras,
                 clicks negativos)
schema_drift     o producer renomeia um campo sem avisar:
                 campaign-costs.cost -> cost_amount, conversions.revenue -> revenue_amount

invalid_payload e schema_drift devolvem payload CRU, sem passar pelos modelos
Pydantic - simulam um producer que quebrou o contrato. Se passassem pelo
response model (producer-side validation), o proprio FastAPI recusava a
resposta e a pipeline nunca veria o problema.
"""

from __future__ import annotations

import asyncio
import threading
from enum import Enum
from typing import Any

from fastapi import APIRouter, HTTPException

from api.config import get_api_settings


class Mode(str, Enum):
    healthy = "healthy"
    http_500 = "http_500"
    slow = "slow"
    rate_limit = "rate_limit"
    invalid_payload = "invalid_payload"
    schema_drift = "schema_drift"


class FaultState:
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


STATE = FaultState()


# --------------------------------------------------------------------------
# Dependencias: correm antes de cada endpoint normal
# --------------------------------------------------------------------------

async def common_faults() -> None:
    """Falhas que afetam TODOS os endpoints normais, /health incluido."""
    if STATE.mode is Mode.http_500:
        raise HTTPException(500, "Injected fault: http_500")
    if STATE.consume_rate_limit():
        raise HTTPException(429, "Injected fault: rate_limit", headers={"Retry-After": "5"})


async def data_faults() -> None:
    """Falhas dos endpoints de dados: as comuns + lentidao."""
    await common_faults()
    if STATE.mode is Mode.slow:
        # async: nao bloqueia o servidor, so ESTE pedido fica pendurado
        await asyncio.sleep(get_api_settings().slow_delay_seconds)


# --------------------------------------------------------------------------
# Corrupcao do payload (producer que quebra o contrato)
# --------------------------------------------------------------------------

_DRIFT_RENAMES = {
    "conversions": ("revenue", "revenue_amount"),
    "campaign_costs": ("cost", "cost_amount"),
}


def corrupt(kind: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Devolve as linhas adulteradas, ou None se o modo atual nao adultera `kind`.

    `kind` e "conversions" ou "campaign_costs". As dimensoes e o daily_control
    nunca sao adulterados.
    """
    if kind not in _DRIFT_RENAMES:
        return None

    if STATE.mode is Mode.schema_drift:
        old, new = _DRIFT_RENAMES[kind]
        return [{(new if k == old else k): v for k, v in row.items()} for row in rows]

    if STATE.mode is Mode.invalid_payload:
        money_field = _DRIFT_RENAMES[kind][0]
        bad = []
        for i, row in enumerate(rows):
            row = dict(row)
            if i % 10 == 0:  # numero negativo: viola ge=0
                row[money_field] = -abs(row[money_field]) - 1
            if i % 10 == 5:
                if kind == "conversions":  # pais com 3 letras: viola o formato
                    row["country_code"] = "PRT"
                else:  # clicks negativos
                    row["clicks"] = -5
            bad.append(row)
        return bad

    return None


# --------------------------------------------------------------------------
# Endpoints de administracao (nunca afetados pelas falhas: tens de poder curar)
# --------------------------------------------------------------------------

admin = APIRouter(prefix="/admin", tags=["admin (so para formacao)"])


@admin.get("/mode")
def get_mode() -> dict[str, Any]:
    return {"mode": STATE.mode.value, "rate_limit_remaining": STATE.rate_limit_remaining}


@admin.post("/mode/{mode}")
def set_mode(mode: Mode, fail_times: int = 2) -> dict[str, Any]:
    """Muda o modo. `fail_times` so conta no modo rate_limit."""
    STATE.set(mode, fail_times)
    return get_mode()
