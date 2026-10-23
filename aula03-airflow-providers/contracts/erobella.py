"""CONTRATO DE ORIGEM da Erobella: o que o PROVEDOR nos envia.

Muito diferente do TrafficJunky. Nao ha campanhas: a resposta tem tres partes.

    by_day_creative   uma linha por DIA e CREATIVE (o desempenho)
    by_creative       uma linha por CREATIVE (label, link, ...)
    by_day            o TOTAL do dia

O desempenho esta por creative; a campanha so aparece escondida no `link` do
creative (o URL da campanha de tracking). Para saber de que campanha e uma linha de
desempenho e preciso cruzar by_day_creative com by_creative pelo `label`, e extrair o
UUID do link. Nada disto existe no TrafficJunky.

Mesmas regras que o contrato do TrafficJunky: extra="ignore" (o provider nao e nosso),
campos que CONSUMIMOS obrigatorios. ATENCAO: formato INFERIDO dos tickets.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Count = Annotated[int, Field(strict=True, ge=0)]


class EroDayCreative(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: dt.date
    label: Annotated[str, Field(min_length=1)]
    impressions: Count
    clicks: Count
    cost_eur: Decimal  # a moeda esta no NOME do campo
    ctr_pct: Decimal | None = None  # reportado pelo provider (em %); nao e fonte de verdade
    ecpm_eur: Decimal | None = None


class EroCreative(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: Annotated[str, Field(min_length=1)]
    # OPCIONAL: um creative pode nao ter link. O transform rejeita essas linhas.
    link: str | None = None
    partner: str | None = None
    headline: str | None = None
    text: str | None = None
    tag: str | None = None
    image: str | None = None


class EroDay(BaseModel):
    """O total do dia, reportado pelo provider: serve de CONTROLO na reconciliacao."""

    model_config = ConfigDict(extra="ignore")

    date: dt.date
    cost_eur: Decimal
    impressions: Count | None = None
    clicks: Count | None = None


class EroResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    by_day_creative: list[EroDayCreative]
    by_creative: list[EroCreative]
    by_day: list[EroDay]
