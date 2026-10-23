"""CONTRATO DE ORIGEM do TrafficJunky: o que o PROVIDER nos envia.

Responde a uma pergunta: "o payload recebido tem a forma esperada?". Nao e o
modelo interno (contracts/canonical.py): os nomes e a estrutura sao os do provider.

    TrafficJunky: uma linha por CAMPANHA do provider e dia, paginada (limit/offset).

extra="ignore": o provider nao e nosso e acrescenta campos quando quer; isso nao
nos deve partir. O que SIM nos parte e desaparecer ou mudar de tipo um campo que
CONSUMIMOS (campaign_name, campaign_type, impressions, clicks, cost): sao
obrigatorios.

Os racios (ecpc, ecpm, ctr) sao opcionais e nao os usamos: o modelo analitico
recalcula-os a partir das metricas base.

ATENCAO: formato INFERIDO dos tickets, nao copiado de documentacao da API real.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Count = Annotated[int, Field(strict=True, ge=0)]


class TJCampaignStat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    campaign_id: int | str | None = None  # id no provider; so para logs
    campaign_name: Annotated[str, Field(min_length=1)]
    campaign_type: str  # "deal" e ignorado pelo transform
    impressions: Count
    clicks: Count
    cost: Decimal
    # racios reportados pelo provider (nao sao fonte de verdade)
    ecpc: Decimal | None = None
    ecpm: Decimal | None = None
    ctr: Decimal | None = None  # em percentagem


class TJStatsPage(BaseModel):
    """Uma pagina da resposta de stats."""

    model_config = ConfigDict(extra="ignore")

    data: list[TJCampaignStat]
    total: Count
    limit: Annotated[int, Field(strict=True, ge=1)]
    offset: Count


class TJTotal(BaseModel):
    """Resposta do endpoint de total de controlo (mock; ver README)."""

    model_config = ConfigDict(extra="ignore")

    date: dt.date
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    total_cost: Decimal
