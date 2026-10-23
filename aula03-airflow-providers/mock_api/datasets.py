"""Dados sinteticos dos providers, DETERMINISTICOS (mesma seed + mesmo dia = mesmos dados).

ATENCAO: estes formatos sao REPRESENTACOES PEDAGOGICAS inferidas dos tickets. Os
tickets descrevem o comportamento e os campos relevantes, mas nao os payloads
completos das APIs reais. Preservam as DIFERENCAS ESTRUTURAIS que importam
(TrafficJunky: uma linha por campanha, paginada; Erobella: uma linha por creative
e a campanha escondida num link), nao copiam o formato exato.

Os nomes de campanha vem de data/campaigns.csv: o mesmo ficheiro que a pipeline
carrega em dim_campaign. Assim o match por nome funciona.
"""

from __future__ import annotations

import csv
import random
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from mock_api.config import CAMPAIGNS_CSV

TWO = Decimal("0.01")

TJ_NAMES = ["TJ PT Casino Desktop", "TJ ES Sports Mobile", "TJ DE Loans", "TJ FR Dating", "TJ BR Keto"]
TJ_DEAL = "TJ Private Deal Q4"
TJ_SPLIT = "TJ DE Loans"  # aparece como DUAS campanhas do provider com o mesmo nome
TJ_UNMAPPED = "TJ Unmapped Campaign Test"  # nao existe em dim_campaign


def campaign_ids() -> dict[str, str]:
    """{nome: campaign_id} lido de data/campaigns.csv."""
    with CAMPAIGNS_CSV.open() as f:
        return {r["campaign_name"]: r["campaign_id"] for r in csv.DictReader(f)}


def _money(value: float | Decimal) -> Decimal:
    return Decimal(value).quantize(TWO, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------
# TrafficJunky: uma linha por campanha e dia
# --------------------------------------------------------------------------

def _tj_stat(rng: random.Random, external_id: int, name: str, kind: str, scale: float = 1.0) -> dict[str, Any]:
    impressions = int(rng.randint(8_000, 60_000) * scale)
    clicks = int(impressions * rng.uniform(0.005, 0.03))
    cost = _money(clicks * rng.uniform(0.08, 0.45))
    return {
        "campaign_id": external_id,  # id do PROVIDER (nao e o nosso campaign_id)
        "campaign_name": name,
        "campaign_type": kind,
        "impressions": impressions,
        "clicks": clicks,
        "cost": float(cost),
        # racios REPORTADOS pelo provider: arredondados, ctr em percentagem.
        # Nao os guardamos: recalculam-se a partir das metricas base.
        "ecpc": float(_money(cost / clicks)) if clicks else 0.0,
        "ecpm": float(_money(cost / impressions * 1000)),
        "ctr": float(_money(Decimal(clicks) / impressions * 100)),
    }


def trafficjunky_full(seed: int, day: date, dirty: bool = False) -> list[dict[str, Any]]:
    """Todas as linhas que o provider tem para o dia (antes de qualquer falha)."""
    rng = random.Random(f"{seed}:trafficjunky:{day.isoformat()}")
    rows: list[dict[str, Any]] = []
    ext = 5000
    for name in TJ_NAMES:
        if name == TJ_SPLIT:  # duas campanhas do provider com o mesmo nome: vao ser agregadas
            rows.append(_tj_stat(rng, ext, name, "standard", 0.6)); ext += 1
            rows.append(_tj_stat(rng, ext, name, "standard", 0.4)); ext += 1
        else:
            rows.append(_tj_stat(rng, ext, name, "standard")); ext += 1
    rows.append(_tj_stat(rng, ext, TJ_DEAL, "deal")); ext += 1  # deals: ignorados pelo transform
    if dirty:
        rows.append(_tj_stat(rng, ext, TJ_UNMAPPED, "standard")); ext += 1
    return rows


def trafficjunky_total(seed: int, day: date, dirty: bool = False) -> Decimal:
    """Total de CONTROLO: custo de todas as campanhas nao-deal (o investimento real).

    Calculado sobre o dataset COMPLETO, independentemente de qualquer truncagem do
    endpoint de detalhe: e o que permite a reconciliacao apanhar dados em falta.
    """
    rows = trafficjunky_full(seed, day, dirty)
    return sum((_money(r["cost"]) for r in rows if r["campaign_type"] != "deal"), Decimal("0"))


# --------------------------------------------------------------------------
# Erobella: uma linha por CREATIVE e dia; a campanha esta escondida num link
# --------------------------------------------------------------------------

# (label, nome da campanha, formato do link)
EROBELLA_CREATIVES = [
    ("pt-casino-a", "EB PT Casino Native", "path"),
    ("pt-casino-b", "EB PT Casino Native", "vcid"),
    ("pt-casino-c", "EB PT Casino Native", "path"),
    ("es-sports-a", "EB ES Sports Native", "vcid"),
    ("es-sports-b", "EB ES Sports Native", "path"),
    ("br-keto-a", "EB BR Keto Native", "path"),
    ("br-keto-b", "EB BR Keto Native", "vcid"),
]
EROBELLA_NO_LINK = "orphan-no-link"  # creative sem link
EROBELLA_BAD_LINK = "bad-link"  # link sem UUID de campanha


def _eb_link(campaign_id: str, label: str, style: str) -> str:
    """O link do creative e o URL da campanha de tracking: o UUID vem la dentro.

    Dois formatos, como nos dados reais: `/<uuid>?...` e `...?vcid=<uuid>`.
    """
    if style == "path":
        return f"https://trk.example.test/{campaign_id}?creative={label}"
    return f"https://trk.example.test/click?vcid={campaign_id}&creative={label}"


def erobella_creatives(dirty: bool = False) -> list[dict[str, Any]]:
    """by_creative: uma linha por creative (label, link, ...)."""
    ids = campaign_ids()
    rows = [
        {"label": label, "partner": "EroPartner", "headline": f"Headline {label}",
         "text": f"Texto do creative {label}", "tag": "native", "image": f"https://img.example.test/{label}.png",
         "link": _eb_link(ids[campaign], label, style)}
        for label, campaign, style in EROBELLA_CREATIVES
    ]
    if dirty:
        rows.append({"label": EROBELLA_NO_LINK, "partner": "EroPartner", "headline": "Sem link",
                     "text": "", "tag": "native", "image": None, "link": None})
        rows.append({"label": EROBELLA_BAD_LINK, "partner": "EroPartner", "headline": "Link sem campanha",
                     "text": "", "tag": "native", "image": None,
                     "link": f"https://trk.example.test/landing?creative={EROBELLA_BAD_LINK}"})
    return rows


def erobella_day_creative(seed: int, day: date, dirty: bool = False) -> list[dict[str, Any]]:
    """by_day_creative: desempenho de cada creative nesse dia."""
    rng = random.Random(f"{seed}:erobella:{day.isoformat()}")
    labels = [c[0] for c in EROBELLA_CREATIVES] + ([EROBELLA_NO_LINK, EROBELLA_BAD_LINK] if dirty else [])
    rows = []
    for label in labels:
        impressions = rng.randint(5_000, 40_000)
        clicks = int(impressions * rng.uniform(0.01, 0.04))
        cost = _money(clicks * rng.uniform(0.10, 0.40))
        rows.append({
            "date": day.isoformat(), "label": label, "impressions": impressions, "clicks": clicks,
            "ctr_pct": float(_money(Decimal(clicks) / impressions * 100)),  # percentagem
            "cost_eur": float(cost),
            "ecpm_eur": float(_money(cost / impressions * 1000)),
        })
    return rows


def erobella_by_day(seed: int, day: date, dirty: bool = False) -> list[dict[str, Any]]:
    """by_day: o TOTAL do dia, calculado sobre TODOS os creatives (nunca truncado)."""
    rows = erobella_day_creative(seed, day, dirty)
    cost = sum((_money(r["cost_eur"]) for r in rows), Decimal("0"))
    impressions = sum(r["impressions"] for r in rows)
    clicks = sum(r["clicks"] for r in rows)
    return [{
        "date": day.isoformat(), "impressions": impressions, "clicks": clicks,
        "cost_eur": float(cost),
        "ecpm_eur": float(_money(cost / impressions * 1000)) if impressions else 0.0,
        "ctr_pct": float(_money(Decimal(clicks) / impressions * 100)) if impressions else 0.0,
    }]
