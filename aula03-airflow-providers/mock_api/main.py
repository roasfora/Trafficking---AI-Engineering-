"""Mock API dos providers (para a aula nao depender de APIs externas).

    GET /mock/trafficjunky/health
    GET /mock/trafficjunky/stats?startDate=DD/MM/YYYY&endDate=DD/MM/YYYY&limit=&offset=
    GET /mock/trafficjunky/total?date=YYYY-MM-DD       (total de CONTROLO, independente)

    GET /mock/erobella/health
    GET /mock/erobella/stats?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD    (inclusivo)

    POST /admin/<provider>/mode/<modo>      (ver faults.py)

Representacoes pedagogicas INFERIDAS dos tickets, nao copias das APIs reais.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query

from mock_api import datasets, faults
from mock_api.config import get_mock_settings
from mock_api.faults import Mode, ProviderName

app = FastAPI(
    title="Mock provider APIs",
    version="1.0.0",
    description="TrafficJunky e Erobella falsos, determinísticos, com fault injection (so para formacao).",
)
app.include_router(faults.admin)

TJ = ProviderName.trafficjunky
EB = ProviderName.erobella


def _tj_date(value: str) -> date:
    """O TrafficJunky pede datas como DD/MM/YYYY (sem timezone)."""
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        raise HTTPException(422, "data invalida: usa DD/MM/YYYY") from None


# --------------------------------------------------------------------------
# TrafficJunky
# --------------------------------------------------------------------------

@app.get("/mock/trafficjunky/health", dependencies=[Depends(faults.guard(TJ, data=False))])
def tj_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/mock/trafficjunky/stats", dependencies=[Depends(faults.guard(TJ))])
def tj_stats(
    startDate: str,
    endDate: str,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    start, end = _tj_date(startDate), _tj_date(endDate)
    if start != end:
        raise HTTPException(422, "o mock so suporta startDate == endDate (um dia de cada vez)")

    mode = faults.mode_of(TJ)
    rows = datasets.trafficjunky_full(get_mock_settings().seed, start, dirty=mode is Mode.dirty_data)

    if mode is Mode.partial_data:
        # O provider devolve so parte das campanhas, MAS o `total` da paginacao e
        # coerente com o que devolve: a verificacao de paginacao do extract nao
        # apanha nada. So o total de controlo (/total) sabe a verdade.
        rows = rows[: max(1, math.ceil(len(rows) * 0.6))]
    if mode is Mode.schema_drift:
        # o provider renomeia, sem avisar, um campo que consumimos
        rows = [{("spend" if k == "cost" else k): v for k, v in r.items()} for r in rows]

    return {"data": rows[offset : offset + limit], "total": len(rows), "limit": limit, "offset": offset}


@app.get("/mock/trafficjunky/total", dependencies=[Depends(faults.guard(TJ))])
def tj_total(date: date) -> dict[str, Any]:
    """Total diario de CONTROLO, independente do detalhe (nunca truncado)."""
    dirty = faults.mode_of(TJ) is Mode.dirty_data
    total = datasets.trafficjunky_total(get_mock_settings().seed, date, dirty=dirty)
    return {"date": date.isoformat(), "currency": "EUR", "total_cost": float(total)}


# --------------------------------------------------------------------------
# Erobella: a resposta tem TRES partes (por creative e dia, por creative, por dia)
# --------------------------------------------------------------------------

@app.get("/mock/erobella/health", dependencies=[Depends(faults.guard(EB, data=False))])
def eb_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/mock/erobella/stats", dependencies=[Depends(faults.guard(EB))])
def eb_stats(start_date: date, end_date: date) -> dict[str, Any]:
    if end_date < start_date or (end_date - start_date).days > 6:
        raise HTTPException(422, "intervalo invalido (maximo 7 dias)")
    mode = faults.mode_of(EB)
    dirty = mode is Mode.dirty_data
    seed = get_mock_settings().seed
    days = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]

    by_day_creative = [r for d in days for r in datasets.erobella_day_creative(seed, d, dirty)]
    by_day = [r for d in days for r in datasets.erobella_by_day(seed, d, dirty)]  # total COMPLETO

    if mode is Mode.partial_data:
        # os creatives vem incompletos; o total do dia (by_day) continua correto
        by_day_creative = by_day_creative[: max(1, math.ceil(len(by_day_creative) * 0.6))]
    if mode is Mode.schema_drift:
        by_day_creative = [{("spend_eur" if k == "cost_eur" else k): v for k, v in r.items()}
                           for r in by_day_creative]

    return {"by_day_creative": by_day_creative, "by_creative": datasets.erobella_creatives(dirty),
            "by_day": by_day}
