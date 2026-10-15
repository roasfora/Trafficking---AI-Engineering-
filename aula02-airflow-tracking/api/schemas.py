"""O DATA CONTRACT entre a API e a pipeline.

    A API e o producer.
    A pipeline e o consumer.
    O Pydantic representa o contrato entre ambos.

Este ficheiro e a unica fonte de verdade sobre COMO sao os dados:

* a API usa-o para construir as respostas   (validacao no producer);
* a pipeline usa-o na task `validate`       (validacao no consumer).

Sao duas validacoes diferentes, com propositos diferentes. A do producer diz
"eu cumpro o que prometi"; a do consumer diz "nao confio, verifico". Se o
producer quebrar o contrato (ver modo `schema_drift` em faults.py), so a
validacao no consumer o apanha - e por isso a pipeline NAO assume que a API
esta certa.

Os campos seguem a estrutura real (data-structure-reference.md), na versao
"dataset sintetico minimo" (secao 6 desse documento).

Nota de simplificacao: aqui o contrato e partilhado por ficheiro (o Airflow
monta esta pasta). Em producao seria um artefacto versionado (pacote, JSON
Schema, schema registry) com regras de compatibilidade entre versoes.

O que o contrato mostra
-----------------------
* campos obrigatorios vs opcionais   -> `?` na referencia = Optional aqui
                                        (Offer.country_code, CampaignCost.clicks/impressions)
* tipos                              -> IDs sao UUIDs em string; `"123"` nao e UUID
* enums                              -> investment_provider (16 valores)
* constraints                        -> cost/revenue >= 0, country_code com 2 letras
* datetime com timezone              -> AwareDatetime (sem timezone = erro)
* regras personalizadas              -> CampaignCost.datetime tem de ser hora certa
* campos desconhecidos               -> extra="forbid" (ver abaixo)
"""

from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Annotated, Generic, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

# --------------------------------------------------------------------------
# Tipos reutilizaveis
# --------------------------------------------------------------------------

# ID de entidade: um UUID em minusculas, como string. Em modo estrito: um int
# ou um UUID mal formado NAO passam.
EntityId = Annotated[
    str,
    Field(strict=True, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]

# clickId: 32 caracteres hexadecimais.
ClickId = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{32}$")]

# Metricas monetarias: nunca negativas, nunca NaN/Infinity.
Money = Annotated[float, Field(ge=0, allow_inf_nan=False)]

# Pais (ISO 3166-1 alpha-2): exatamente duas letras maiusculas. "PRT" e "pt"
# falham. (A geo de uma campanha tambem pode ser "WW" = worldwide.)
CountryCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]

# Moeda (ISO 4217): tres letras maiusculas.
CurrencyCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]

Name = Annotated[str, Field(min_length=1, max_length=200)]


class Contract(BaseModel):
    """Base de todos os modelos do contrato.

    extra="forbid": um campo que o contrato nao conhece e um ERRO.
    Trade-off: e mais rigido (um campo novo, aditivo, tambem parte a pipeline)
    mas torna a deriva visivel. Muitos consumers reais usam extra="ignore"
    para tolerar campos novos e so falham em remocoes/renomeacoes.
    """

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# Enums: o conjunto FECHADO de valores permitidos
# --------------------------------------------------------------------------

class InvestmentProvider(str, Enum):
    """Quem financiou o trafego (CampaignTrafficSourceData.investment_provider)."""

    exoclick = "exoclick"
    trafficstars = "trafficstars"
    reactiveclicks = "reactiveclicks"
    clickemistry = "clickemistry"
    dopaclicks = "dopaclicks"
    soladsmedia = "soladsmedia"
    pushground = "pushground"
    trafficgold = "trafficgold"
    traffichunt = "traffichunt"
    propellerads = "propellerads"
    adextrem = "adextrem"
    adness = "adness"
    tacoloco = "tacoloco"
    trafficjunky = "trafficjunky"
    trafficjunkynewaccount = "trafficjunkynewaccount"
    pushub = "pushub"


# --------------------------------------------------------------------------
# Dimensoes (Postgres e Voluum)
# --------------------------------------------------------------------------

class Workspace(Contract):
    workspace_id: EntityId
    name: Name


class TrafficSource(Contract):
    traffic_source_id: EntityId
    name: Name
    currency_code: CurrencyCode
    deleted: bool  # soft delete: a fonte existe mas ja nao esta ativa


class Campaign(Contract):
    campaign_id: EntityId
    name: Name
    geo: CountryCode  # ISO-2, ou "WW"
    traffic_source_id: EntityId
    workspace_id: EntityId
    is_paused: bool
    created: AwareDatetime


class Offer(Contract):
    offer_id: EntityId
    name: Name
    # OPCIONAL: ofertas globais nao tem pais (`country{code,name}` e opcional na origem).
    country_code: CountryCode | None = None
    affiliate_network_id: EntityId
    affiliate_network_name: Name
    payout: Money
    currency_code: CurrencyCode
    deleted: bool


# --------------------------------------------------------------------------
# Factos
# --------------------------------------------------------------------------

class Conversion(Contract):
    """GRAIN: 1 linha = 1 conversao (um postback).

    Nao existe `conversion_id` na origem. Um mesmo click pode ter varias
    conversoes (tipos diferentes, momentos diferentes), por isso a chave
    natural e (click_id, conversion_type_id, postback_timestamp).
    """

    click_id: ClickId
    campaign_id: EntityId
    traffic_source_id: EntityId
    offer_id: EntityId
    visit_timestamp: AwareDatetime  # quando o utilizador clicou
    postback_timestamp: AwareDatetime  # quando a conversao nos foi reportada
    revenue: Money  # em USD
    revenue_original_currency: Money  # na moeda da oferta
    conversion_type_id: Annotated[int, Field(strict=True, ge=1)]
    country_code: CountryCode  # pais do visitante


class CampaignCost(Contract):
    """GRAIN: 1 linha = 1 campanha x 1 hora x 1 investment_provider."""

    datetime: AwareDatetime  # inicio da hora
    campaign_id: EntityId
    investment_provider: InvestmentProvider
    cost: Money
    # OPCIONAIS: nem todos os providers reportam clicks / impressions.
    # Um NULL aqui significa "nao sei", que e diferente de 0.
    clicks: Annotated[int, Field(strict=True, ge=0)] | None = None
    impressions: Annotated[int, Field(strict=True, ge=0)] | None = None

    @field_validator("datetime")
    @classmethod
    def must_be_top_of_the_hour(cls, v: dt.datetime) -> dt.datetime:
        """Regra personalizada: o custo e horario, logo minutos e segundos = 0."""
        if v.minute or v.second or v.microsecond:
            raise ValueError("deve ser o inicio de uma hora (minutos e segundos a zero)")
        return v


class DailyControl(Contract):
    """GRAIN: 1 linha = 1 campanha x 1 dia (agregado vindo do Postgres)."""

    date: dt.date
    campaign_id: EntityId
    revenue: Money
    investment: Money
    # True = alguem escreveu estes numeros a mao (podem nao bater com os eventos).
    is_manual: bool


# --------------------------------------------------------------------------
# Envelope de paginacao (limit / offset)
# --------------------------------------------------------------------------

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Todas as listas vem neste envelope.

    count  -> quantos itens vieram nESTA pagina
    total  -> quantos itens existem no total (para o filtro pedido)
    limit/offset -> o que foi pedido

    `total` existe para o consumer detetar TRUNCAGEM: se pediu 100 e ha 437,
    tem de paginar. Sem `total`, uma extracao parcial parece uma extracao
    completa - o pior tipo de bug em dados.
    """

    data: list[T]
    count: Annotated[int, Field(ge=0)]
    total: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1)]
    offset: Annotated[int, Field(ge=0)]
