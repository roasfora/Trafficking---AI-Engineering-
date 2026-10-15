"""Synthetic Tracking API (o PRODUCER).

Uma API fictícia que expoe, num so servico, o que na realidade vive em dois
sistemas (ver data-structure-reference.md): conversoes e custos (Mongo) e
campanhas / daily control (Postgres). Os dados sao sinteticos e
determinísticos (ver generator.py).

    GET /health
    GET /workspaces  /traffic-sources  /campaigns  /offers      (dimensoes)
    GET /conversions     janela sobre postback_timestamp
    GET /campaign-costs  janela sobre datetime (custo por hora)
    GET /daily-control   janela sobre date (agregado diario)

Filtros dos factos:
    start_date  inclusivo   end_date  EXCLUSIVO   (intervalo [start, end), UTC)
    campaign_id, traffic_source_id, limit (1-1000), offset

O intervalo meio-aberto [start, end) e o mesmo que o Airflow usa nas
data intervals. Dois dias consecutivos [dia1, dia2) e [dia2, dia3) nunca
partilham nem perdem um registo na fronteira.

Producer-side validation
------------------------
Na resposta normal, cada linha e passada pelos modelos Pydantic ANTES de sair:
a API garante que cumpre o contrato. Isto NAO dispensa a validacao no consumer
(task `validate`): quando o producer muda sem avisar, ninguem o valida a ele.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from api import faults, generator
from api.config import get_api_settings
from api.schemas import (
    Campaign,
    CampaignCost,
    Conversion,
    DailyControl,
    Offer,
    Page,
    TrafficSource,
    Workspace,
)

UTC = timezone.utc

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
MAX_WINDOW_DAYS = 31
# Sem start_date/end_date devolvemos este dia fixo (e nao "ontem"):
# uma API de formacao tem de dar a mesma resposta amanha.
DEFAULT_WINDOW_START = datetime(2026, 10, 1, tzinfo=UTC)

app = FastAPI(
    title="Synthetic Tracking API",
    version="2.0.0",
    description="Producer de dados sinteticos de tracking, para a aula de Airflow.",
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _window(start_date: Optional[datetime], end_date: Optional[datetime]) -> tuple[datetime, datetime]:
    """Resolve [start, end) com defaults e valida o pedido (erros do CLIENTE = 422)."""
    if start_date is None and end_date is None:
        start, end = DEFAULT_WINDOW_START, DEFAULT_WINDOW_START + timedelta(days=1)
    elif end_date is None:
        start = _as_utc(start_date)  # type: ignore[arg-type]
        end = start + timedelta(days=1)
    elif start_date is None:
        end = _as_utc(end_date)
        start = end - timedelta(days=1)
    else:
        start, end = _as_utc(start_date), _as_utc(end_date)

    if end <= start:
        raise HTTPException(422, "end_date tem de ser posterior a start_date")
    if end - start > timedelta(days=MAX_WINDOW_DAYS):
        raise HTTPException(422, f"janela maxima: {MAX_WINDOW_DAYS} dias")
    return start, end


def _respond(
    model: type, rows: list[dict[str, Any]], limit: int, offset: int, kind: str = ""
) -> JSONResponse:
    """Pagina e constroi o envelope VALIDANDO cada linha contra o contrato."""
    # Fault injection (api/faults.py): um producer que quebra o contrato devolve
    # payload cru, SEM passar pelos modelos. So acontece nos modos de falha.
    corrupted = faults.corrupt(kind, rows)
    if corrupted is not None:
        page_rows = corrupted[offset : offset + limit]
        return JSONResponse(
            jsonable_encoder(
                {"data": page_rows, "count": len(page_rows), "total": len(rows), "limit": limit, "offset": offset}
            )
        )

    page_rows = rows[offset : offset + limit]
    page = Page[model](  # type: ignore[valid-type]
        data=[model(**r) for r in page_rows],
        count=len(page_rows),
        total=len(rows),
        limit=limit,
        offset=offset,
    )
    return JSONResponse(page.model_dump(mode="json"))


# Dependencias de fault injection (no-ops quando o modo e `healthy`).
DATA_FAULTS = [Depends(faults.data_faults)]

LimitQ = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="itens por pagina")
OffsetQ = Query(0, ge=0, description="quantos itens saltar")
StartQ = Query(None, description="inclusivo (UTC se sem fuso)")
EndQ = Query(None, description="EXCLUSIVO")
CampaignQ = Query(None, description="UUID da campanha")
TrafficSourceQ = Query(None, description="UUID da fonte de trafego (da campanha)")


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

app.include_router(faults.admin)  # so para formacao: ver api/faults.py


@app.get("/health", dependencies=[Depends(faults.common_faults)])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/workspaces", dependencies=DATA_FAULTS, response_model=None,
         responses={200: {"model": Page[Workspace]}})
def workspaces(limit: int = LimitQ, offset: int = OffsetQ):
    return _respond(Workspace, generator.list_workspaces(), limit, offset)


@app.get("/traffic-sources", dependencies=DATA_FAULTS, response_model=None,
         responses={200: {"model": Page[TrafficSource]}})
def traffic_sources(limit: int = LimitQ, offset: int = OffsetQ):
    return _respond(TrafficSource, generator.list_traffic_sources(), limit, offset)


@app.get("/campaigns", dependencies=DATA_FAULTS, response_model=None,
         responses={200: {"model": Page[Campaign]}})
def campaigns(limit: int = LimitQ, offset: int = OffsetQ):
    return _respond(Campaign, generator.list_campaigns(), limit, offset)


@app.get("/offers", dependencies=DATA_FAULTS, response_model=None,
         responses={200: {"model": Page[Offer]}})
def offers(limit: int = LimitQ, offset: int = OffsetQ):
    return _respond(Offer, generator.list_offers(), limit, offset)


@app.get("/conversions", dependencies=DATA_FAULTS, response_model=None,
         responses={200: {"model": Page[Conversion]}})
def conversions(
    start_date: Optional[datetime] = StartQ,
    end_date: Optional[datetime] = EndQ,
    campaign_id: Optional[str] = CampaignQ,
    traffic_source_id: Optional[str] = TrafficSourceQ,
    limit: int = LimitQ,
    offset: int = OffsetQ,
):
    """Conversoes com `start_date <= postback_timestamp < end_date`."""
    start, end = _window(start_date, end_date)
    rows = generator.list_conversions(get_api_settings().seed, start, end, campaign_id, traffic_source_id)
    return _respond(Conversion, rows, limit, offset, kind="conversions")


@app.get("/campaign-costs", dependencies=DATA_FAULTS, response_model=None,
         responses={200: {"model": Page[CampaignCost]}})
def campaign_costs(
    start_date: Optional[datetime] = StartQ,
    end_date: Optional[datetime] = EndQ,
    campaign_id: Optional[str] = CampaignQ,
    traffic_source_id: Optional[str] = TrafficSourceQ,
    limit: int = LimitQ,
    offset: int = OffsetQ,
):
    """Custo por hora com `start_date <= datetime < end_date`."""
    start, end = _window(start_date, end_date)
    rows = generator.list_campaign_costs(get_api_settings().seed, start, end, campaign_id, traffic_source_id)
    return _respond(CampaignCost, rows, limit, offset, kind="campaign_costs")


@app.get("/daily-control", dependencies=DATA_FAULTS, response_model=None,
         responses={200: {"model": Page[DailyControl]}})
def daily_control(
    start_date: Optional[datetime] = StartQ,
    end_date: Optional[datetime] = EndQ,
    campaign_id: Optional[str] = CampaignQ,
    traffic_source_id: Optional[str] = TrafficSourceQ,
    limit: int = LimitQ,
    offset: int = OffsetQ,
):
    """Agregado diario dos dias cuja meia-noite cai em `[start_date, end_date)`."""
    start, end = _window(start_date, end_date)
    rows = generator.list_daily_control(get_api_settings().seed, start, end, campaign_id, traffic_source_id)
    return _respond(DailyControl, rows, limit, offset, kind="daily_control")
