"""O CONTRATO INTERNO (canonical): como os nossos dados SAO, venham de onde vierem.

    contrato do provider  !=  contrato interno

Cada provider tem o seu schema (ver contracts/trafficjunky.py e
contracts/erobella.py): campos diferentes, nomes diferentes, estruturas
diferentes. Depois da transformacao especifica de cada um, TODOS produzem
exatamente este modelo. E o que a base de dados e as analises conhecem.

Duas perguntas, dois contratos:

    validate_source     "o payload que o provider enviou tem a forma esperada?"
    validate_canonical  "depois da transformacao, o registo respeita o nosso modelo?"

Decisoes deste modelo:

* So METRICAS BASE (impressions, clicks, cost). CPC, CPM e CTR nao sao fonte de
  verdade: calculam-se na view (sql/analytics.sql) a partir das base. Os
  providers enviam estes racios, mas arredondados e por vezes errados.
* `currency` e obrigatoria: um custo sem moeda e um numero sem significado.
  Custos de moedas diferentes NUNCA se somam sem conversao. (Nesta aula os dois
  providers faturam em EUR: simplificacao pedagogica.)
* `source_specific_id` e opcional: TrafficJunky nao o tem (NULL), a Erobella usa
  o label do creative. Uma string vazia NAO e valida: NULL e NULL.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Provider(str, Enum):
    trafficjunky = "trafficjunky"
    erobella = "erobella"


# ISO 4217: tres letras maiusculas.
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Count = Annotated[int, Field(strict=True, ge=0)]
# Dinheiro: Decimal (nunca float), nao negativo, ate 4 casas (= NUMERIC(14,4)).
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4, allow_inf_nan=False)]


class CampaignDailyStat(BaseModel):
    """GRAIN: 1 linha = 1 dia + 1 provider + 1 campanha + 1 source_specific_id."""

    # extra="forbid": o modelo e NOSSO, por isso um campo desconhecido e um erro.
    # (Nos contratos dos providers, que nao controlamos, ignoramos extras.)
    model_config = ConfigDict(extra="forbid")

    date: dt.date
    provider: Provider
    campaign_id: UUID
    source_specific_id: Annotated[str, Field(min_length=1)] | None = None
    currency: Currency
    impressions: Count
    clicks: Count
    cost: Money
