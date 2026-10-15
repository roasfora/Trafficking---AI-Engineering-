"""Gerador de dados sinteticos, modelado sobre a estrutura real (ver
data-structure-reference.md).

Na realidade os dados vivem em dois sitios:

    Mongo     Conversion, CampaignTrafficSourceData (custo por hora)
    Postgres  Campaign, TrafficSource, Workspace, DailyControl (agregado diario)

A nossa API sintetica expoe os dois lados num so servico, para a pipeline ter
UMA fonte a consumir. Os dois lados sao gerados de forma CONSISTENTE: o
DailyControl de um dia e a soma das conversoes e dos custos desse dia (exceto
nas linhas `is_manual`, que um humano escreveu e que podem discordar).
Essa consistencia e o que permite ao `quality_check` fazer uma reconciliacao.

Tudo e DETERMINISTICO: mesma seed + mesmo dia => exatamente os mesmos dados,
com os mesmos IDs. Porque importa:

* Idempotencia: a pipeline pode correr duas vezes sobre o mesmo dia e a API
  tem de devolver as mesmas chaves.
* Backfill: reprocessar 2026-10-03 hoje ou para a semana da o mesmo resultado.

Cada DIA tem o seu gerador aleatorio, semeado com f"{seed}:{dia}". Nao ha
estado partilhado entre dias.
"""

from __future__ import annotations

import hashlib
import math
import random
import uuid
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from typing import Any, Optional

UTC = timezone.utc

# IDs de entidades: UUIDs (como no Voluum), mas FIXOS - nao dependem da seed.
_NS = uuid.UUID("6f1d3c2e-8a4b-4c5d-9e7f-0a1b2c3d4e5f")


def _uid(kind: str, n: int) -> str:
    return str(uuid.uuid5(_NS, f"{kind}:{n}"))


def _hex_id(text: str) -> str:
    """ID de 32 hex (o formato de um clickId)."""
    return hashlib.md5(text.encode()).hexdigest()


# --------------------------------------------------------------------------
# Dimensoes (pequenas e fixas)
# --------------------------------------------------------------------------

WORKSPACES: list[dict[str, Any]] = [
    {"workspace_id": _uid("workspace", 1), "name": "Team Alpha"},
    {"workspace_id": _uid("workspace", 2), "name": "Team Beta"},
]

# (n, nome, slug do provider, moeda da fonte, deleted)
_TRAFFIC_SOURCES = [
    (1, "ExoClick", "exoclick", "USD", False),
    (2, "TrafficStars", "trafficstars", "EUR", False),
    (3, "PropellerAds", "propellerads", "USD", False),
    (4, "TrafficJunky", "trafficjunky", "USD", False),
    (5, "PushGround", "pushground", "EUR", False),
    (6, "Legacy Network", "adness", "USD", True),  # soft-deleted: ja nao tem trafego
]
TRAFFIC_SOURCES: list[dict[str, Any]] = [
    {"traffic_source_id": _uid("ts", n), "name": name, "currency_code": cur, "deleted": deleted}
    for n, name, _slug, cur, deleted in _TRAFFIC_SOURCES
]

# (n, nome, pais, id da rede, nome da rede, payout, moeda, deleted)
_OFFERS = [
    (1, "Casino Welcome Bonus PT", "PT", 1, "AdCombo", 55.0, "USD", False),
    (2, "Sports Betting ES", "ES", 2, "MaxBounty", 70.0, "USD", False),
    (3, "Keto Trial BR", "BR", 1, "AdCombo", 30.0, "USD", False),
    (4, "Quick Loan DE", "DE", 3, "ClickDealer", 22.0, "EUR", False),
    (5, "Dating Premium FR", "FR", 3, "ClickDealer", 14.0, "EUR", False),
    (6, "VPN Subscription", None, 2, "MaxBounty", 9.0, "USD", False),  # sem pais: opcional
    (7, "Retired Offer", "PT", 1, "AdCombo", 40.0, "USD", True),
]
OFFERS: list[dict[str, Any]] = [
    {
        "offer_id": _uid("offer", n), "name": name, "country_code": country,
        "affiliate_network_id": _uid("network", net), "affiliate_network_name": net_name,
        "payout": payout, "currency_code": cur, "deleted": deleted,
    }
    for n, name, country, net, net_name, payout, cur, deleted in _OFFERS
]
_OFFER_BY_N = {o[0]: o for o in _OFFERS}

# Taxa para USD. Simplificacao: fixa (o exchange_rate real e opcional).
_FX_TO_USD = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27}

# Probabilidade de um click converter, por oferta.
_OFFER_CR = {1: 0.020, 2: 0.015, 3: 0.030, 4: 0.030, 5: 0.040, 6: 0.060}

# (n, nome, geo, n da fonte, n do workspace, pausada, peso de volume,
#  n da oferta, providers de investimento [(slug, quota)], created)
_CAMPAIGNS = [
    (1, "PT Casino - ExoClick", "PT", 1, 1, False, 3.0, 1, [("exoclick", 1.0), ("trafficgold", 0.3)], date(2026, 6, 1)),
    (2, "ES Sports - TrafficStars", "ES", 2, 1, False, 2.5, 2, [("trafficstars", 1.0)], date(2026, 6, 15)),
    (3, "BR Keto - PropellerAds", "BR", 3, 2, False, 2.0, 3, [("propellerads", 1.0)], date(2026, 7, 2)),
    (4, "DE Loans - TrafficJunky", "DE", 4, 2, False, 1.5, 4, [("trafficjunky", 1.0)], date(2026, 7, 20)),
    (5, "FR Dating - PushGround", "FR", 5, 1, False, 1.5, 5, [("pushground", 1.0)], date(2026, 8, 3)),
    (6, "WW VPN - ExoClick", "WW", 1, 2, False, 2.0, 6, [("exoclick", 1.0), ("reactiveclicks", 0.4)], date(2026, 8, 18)),
    (7, "PT Casino Retargeting", "PT", 1, 1, True, 0.0, 1, [("exoclick", 1.0)], date(2026, 5, 10)),
    (8, "US Keto Test", "US", 3, 2, True, 0.0, 3, [("propellerads", 1.0)], date(2026, 5, 22)),
]
CAMPAIGNS: list[dict[str, Any]] = [
    {
        "campaign_id": _uid("campaign", c[0]), "name": c[1], "geo": c[2],
        "traffic_source_id": _uid("ts", c[3]), "workspace_id": _uid("workspace", c[4]),
        "is_paused": c[5], "created": datetime.combine(c[9], time.min, tzinfo=UTC),
    }
    for c in _CAMPAIGNS
]

# CPC medio (USD) por provider de investimento: a base do custo.
_PROVIDER_CPC = {
    "exoclick": 0.55, "trafficstars": 0.62, "propellerads": 0.50, "trafficjunky": 0.75,
    "pushground": 0.45, "trafficgold": 0.40, "reactiveclicks": 0.35,
}
# Estes providers nao reportam impressions (-> NULL). Os nulos fazem parte do contrato.
_NO_IMPRESSIONS = {"pushground", "reactiveclicks"}

_COUNTRIES = ["PT", "ES", "BR", "DE", "FR", "GB", "US"]
_BASE_CLICKS_PER_HOUR = 30
_MAX_POSTBACK_DELAY_SECONDS = 3 * 3600
_MIN_POSTBACK_DELAY_SECONDS = 30


# --------------------------------------------------------------------------
# Geracao por dia: custos, conversoes e daily control, sempre COERENTES
# --------------------------------------------------------------------------

def _hour_profile(hour: int) -> float:
    """Mais trafego ao fim do dia (pico por volta das 20h)."""
    return 0.6 + 0.4 * math.cos((hour - 20) / 24 * 2 * math.pi)


@lru_cache(maxsize=128)
def _day(seed: int, day: date) -> dict[str, tuple[dict[str, Any], ...]]:
    rng = random.Random(f"{seed}:{day.isoformat()}")
    midnight = datetime.combine(day, time.min, tzinfo=UTC)
    end_of_day = midnight + timedelta(days=1)

    costs: list[dict[str, Any]] = []
    conversions: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []

    for n, _name, geo, ts_n, _ws, paused, weight, offer_n, providers, _created in _CAMPAIGNS:
        if paused or weight <= 0:
            continue  # campanha pausada: sem trafego
        campaign_id = _uid("campaign", n)
        ts_id = _uid("ts", ts_n)
        payout, currency = _OFFER_BY_N[offer_n][5], _OFFER_BY_N[offer_n][6]
        cr = _OFFER_CR[offer_n]
        day_revenue = day_cost = 0.0

        for hour in range(24):
            hour_start = midnight + timedelta(hours=hour)
            total_clicks = 0

            # --- custo desta campanha nesta hora, por provider -------------
            for provider, share in providers:
                clicks = int(
                    _BASE_CLICKS_PER_HOUR * weight * share * _hour_profile(hour) * rng.uniform(0.7, 1.3)
                )
                cost = round(clicks * _PROVIDER_CPC[provider] * rng.uniform(0.8, 1.2), 4)
                impressions = (
                    None if provider in _NO_IMPRESSIONS else int(clicks / rng.uniform(0.008, 0.03))
                )
                costs.append(
                    {
                        "datetime": hour_start, "campaign_id": campaign_id,
                        "investment_provider": provider, "cost": cost,
                        "clicks": clicks, "impressions": impressions,
                    }
                )
                total_clicks += clicks
                day_cost += cost

            # --- conversoes dos clicks desta hora ---------------------------
            expected = total_clicks * cr
            n_conv = int(expected) + (1 if rng.random() < expected - int(expected) else 0)
            for i in range(n_conv):
                click_id = _hex_id(f"{seed}:{day.isoformat()}:{n}:{hour}:{i}")
                visit_ts = hour_start + timedelta(seconds=rng.randrange(3600))
                country = geo if (geo != "WW" and rng.random() < 0.85) else rng.choice(_COUNTRIES)

                # tipo 1 = a conversao principal; 10% tem tambem uma de tipo 2
                # (ex.: upsell), que chega depois e vale metade. O MESMO click_id
                # aparece em duas linhas: por isso a chave de uma conversao e
                # (click_id, conversion_type_id, postback_timestamp).
                first_delay = rng.randint(_MIN_POSTBACK_DELAY_SECONDS, _MAX_POSTBACK_DELAY_SECONDS)
                events = [(1, 1.0, first_delay)]
                if rng.random() < 0.10:
                    events.append((2, 0.5, first_delay + rng.randint(60, 1800)))

                for type_id, factor, delay in events:
                    postback_ts = visit_ts + timedelta(seconds=delay)
                    if postback_ts >= end_of_day:
                        continue  # simplificacao: o postback fica no dia da visita
                    original = round(payout * factor, 4)
                    revenue = round(original * _FX_TO_USD[currency], 4)
                    conversions.append(
                        {
                            "click_id": click_id, "campaign_id": campaign_id,
                            "traffic_source_id": ts_id, "offer_id": _uid("offer", offer_n),
                            "visit_timestamp": visit_ts, "postback_timestamp": postback_ts,
                            "revenue": revenue, "revenue_original_currency": original,
                            "conversion_type_id": type_id, "country_code": country,
                        }
                    )
                    day_revenue += revenue

        # --- daily control: o agregado diario (vem de OUTRO sistema) -------
        is_manual = rng.random() < 0.10
        if is_manual:
            # alguem corrigiu os numeros a mao: podem nao bater com os eventos
            day_revenue *= rng.uniform(0.9, 1.1)
            day_cost *= rng.uniform(0.9, 1.1)
        daily.append(
            {
                "date": day, "campaign_id": campaign_id,
                "revenue": round(day_revenue, 2), "investment": round(day_cost, 2),
                "is_manual": is_manual,
            }
        )

    costs.sort(key=lambda r: (r["datetime"], r["campaign_id"], r["investment_provider"]))
    conversions.sort(key=lambda r: (r["postback_timestamp"], r["click_id"], r["conversion_type_id"]))
    daily.sort(key=lambda r: r["campaign_id"])
    return {"costs": tuple(costs), "conversions": tuple(conversions), "daily": tuple(daily)}


# --------------------------------------------------------------------------
# Interface publica
# --------------------------------------------------------------------------

def _days_between(start: datetime, end: datetime) -> list[date]:
    """Dias UTC tocados por [start, end)."""
    if end <= start:
        return []
    last = (end - timedelta(microseconds=1)).date()
    return [start.date() + timedelta(days=k) for k in range((last - start.date()).days + 1)]


def _campaign_ts() -> dict[str, str]:
    return {c["campaign_id"]: c["traffic_source_id"] for c in CAMPAIGNS}


def _keep(row: dict[str, Any], campaign_id: Optional[str], traffic_source_id: Optional[str]) -> bool:
    if campaign_id is not None and row["campaign_id"] != campaign_id:
        return False
    if traffic_source_id is not None and _campaign_ts()[row["campaign_id"]] != traffic_source_id:
        return False
    return True


def list_conversions(seed, start, end, campaign_id=None, traffic_source_id=None) -> list[dict[str, Any]]:
    """Conversoes com start <= postback_timestamp < end (UTC)."""
    return [
        dict(r)
        for day in _days_between(start, end)
        for r in _day(seed, day)["conversions"]
        if start <= r["postback_timestamp"] < end and _keep(r, campaign_id, traffic_source_id)
    ]


def list_campaign_costs(seed, start, end, campaign_id=None, traffic_source_id=None) -> list[dict[str, Any]]:
    """Custo horario com start <= datetime < end (UTC)."""
    return [
        dict(r)
        for day in _days_between(start, end)
        for r in _day(seed, day)["costs"]
        if start <= r["datetime"] < end and _keep(r, campaign_id, traffic_source_id)
    ]


def list_daily_control(seed, start, end, campaign_id=None, traffic_source_id=None) -> list[dict[str, Any]]:
    """Daily control dos dias cuja meia-noite cai em [start, end)."""
    return [
        dict(r)
        for day in _days_between(start, end)
        for r in _day(seed, day)["daily"]
        if start <= datetime.combine(r["date"], time.min, tzinfo=UTC) < end
        and _keep(r, campaign_id, traffic_source_id)
    ]


def list_workspaces() -> list[dict[str, Any]]:
    return [dict(w) for w in WORKSPACES]


def list_traffic_sources() -> list[dict[str, Any]]:
    return [dict(s) for s in TRAFFIC_SOURCES]


def list_campaigns() -> list[dict[str, Any]]:
    return [dict(c) for c in CAMPAIGNS]


def list_offers() -> list[dict[str, Any]]:
    return [dict(o) for o in OFFERS]
