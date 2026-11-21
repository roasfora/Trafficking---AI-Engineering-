"""Cenarios (healthy | broken) e o "mundo verdadeiro" que os simuladores de API descrevem.

Ideia central: primeiro gera-se a VERDADE (o que realmente aconteceu em cada campanha/dia).
Cada simulador de API reporta essa verdade; no cenario `broken` o provider reporta-a com defeitos.
O `daily_control` (sistema interno) guarda a verdade: e a segunda opiniao da reconciliacao.

    load_scenario("broken")  ->  Scenario(name="broken", faults={9 problemas...})
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

PROVIDERS = ("erobella", "trafficjunky", "voluum")

# Os 9 problemas plantados: fault_id -> (provider, o que acontece, check que o apanha)
FAULTS: dict[str, tuple[str, str, str]] = {
    "erobella_missing_day": ("erobella", "dia 11 Nov ausente na resposta", "erobella_coverage (FAIL)"),
    "erobella_null_clicks": ("erobella", "clicks = NULL num dia", "erobella_clicks_null_rate (WARN)"),
    "erobella_schema_drift": ("erobella", "cost.amount em vez de cost_eur", "erobella_schema (FAIL)"),
    "trafficjunky_duplicate_campaign": ("trafficjunky", "mesma campanha/dia duas vezes", "trafficjunky_duplicates (FAIL) + silver_unique_grain"),
    "trafficjunky_spend_drop": ("trafficjunky", "spend do ultimo dia ~75% abaixo da media de 7 dias", "daily_volume_change (WARN)"),
    "trafficjunky_ecpc_mismatch": ("trafficjunky", "ecpc do provider ~6% acima do CPC canonico", "trafficjunky_cpc_reconciliation (WARN)"),
    "voluum_incomplete_pagination": ("voluum", "total_rows > linhas devolvidas, truncated=true", "voluum_pagination (FAIL)"),
    "voluum_stale_data": ("voluum", "dados com 2 dias de atraso", "voluum_freshness (FAIL)"),
    "voluum_revenue_without_conversions": ("voluum", "revenue > 0 com conversions = 0", "revenue_without_conversions (WARN)"),
}


@dataclass(frozen=True)
class Scenario:
    name: str
    providers: tuple
    faults: frozenset

    def has(self, fault_id: str) -> bool:
        return fault_id in self.faults


def load_scenario(name: str = "healthy", providers: tuple | list | None = None) -> Scenario:
    """`healthy` nao tem defeitos. `broken` ativa os 9 (so os dos providers escolhidos)."""
    name = (name or "healthy").lower()
    if name not in ("healthy", "broken"):
        raise ValueError(f"unknown scenario {name!r} (healthy | broken)")
    chosen = tuple(providers) if providers else PROVIDERS
    unknown = set(chosen) - set(PROVIDERS)
    if unknown:
        raise ValueError(f"unknown provider(s): {sorted(unknown)}")
    faults = frozenset(f for f, (prov, _, _) in FAULTS.items() if prov in chosen) if name == "broken" else frozenset()
    return Scenario(name=name, providers=chosen, faults=faults)


# --------------------------------------------------------------------------- tempo e cambio
def window_days(as_of: date, days: int) -> list[date]:
    return [as_of - timedelta(days=days - 1 - i) for i in range(days)]


def simulated_now(as_of: date) -> datetime:
    """"Agora" da simulacao: 06:00 UTC da manha seguinte ao ultimo dia esperado (determinista)."""
    return datetime.combine(as_of + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=6)


def fx_rate(day: date) -> float:
    """USD->EUR do dia. Os mesmos valores sao gravados em analytics.exchange_rate (scripts/generate_reference_seed.py)."""
    return round(0.92 + 0.01 * math.sin(day.toordinal() / 3.0), 4)


def _rng(*parts: Any) -> random.Random:
    return random.Random("-".join(str(p) for p in parts))  # seed por string: determinista entre runs


# --------------------------------------------------------------------------- verdade
EROBELLA_ID = "erobella-total"

TJ_CAMPAIGNS = [  # id, nome, tipo, quota do spend, CPM (USD), CTR (%), CR (%)
    ("tj-2001", "TJ-Banner-DE", "banner", 0.35, 3.1, 0.55, 1.5),
    ("tj-2002", "TJ-Native-FR", "native", 0.25, 2.6, 0.80, 0.6),
    ("tj-2003", "TJ-Pop-ES", "pop", 0.22, 1.8, 1.10, 0.9),
    ("tj-2004", "TJ-Video-IT", "video", 0.18, 4.2, 0.45, 1.2),
]
TJ_DAILY_USD = 1370.0  # ~1260 EUR por dia

VOLUUM_CAMPAIGNS = [  # id, nome, traffic source, pais, custo base/dia (EUR), CPC, CR (% de visits), payout (EUR)
    ("vl-1001", "VL-HEALTH-FR", "TrafficJunky", "FR", 520, 0.42, 1.10, 50),
    ("vl-1002", "VL-VPN-UK", "Erobella", "GB", 480, 0.46, 0.90, 42),
    ("vl-1003", "VL-GAMING-DE", "TrafficJunky", "DE", 610, 0.44, 1.00, 49),
    ("vl-1004", "VL-DATING-ES", "Other", "ES", 430, 0.43, 0.95, 47),
    ("vl-1005", "VL-FINANCE-IT", "Other", "IT", 390, 0.45, 1.05, 50),
]

SPEND_DROP_FACTOR = 0.254  # ~ -74% vs media


def erobella_truth(as_of: date, days: int) -> list[dict]:
    rows = []
    for d in window_days(as_of, days):
        r = _rng("erobella", d)
        impressions = int(r.uniform(170_000, 195_000))
        clicks = int(impressions * r.uniform(0.0085, 0.0095))
        cost = round(impressions / 1000 * 2.40 * r.uniform(0.98, 1.02), 4)
        rows.append({
            "day": d.isoformat(), "impressions": impressions, "clicks": clicks,
            "ctr_pct": round(clicks / impressions * 100, 4), "cost_eur": cost,
            "ecpm_eur": round(cost / impressions * 1000, 4),
            "rates": [{"model": "cpm", "price_eur": 2.4}],
            "updated_at": datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
            .replace(hour=2).isoformat(),
        })
    return rows


def trafficjunky_truth(as_of: date, days: int, spend_drop: bool = False) -> list[dict]:
    rows = []
    for d in window_days(as_of, days):
        total = TJ_DAILY_USD * _rng("tj-total", d).uniform(0.96, 1.04)
        for cid, name, ctype, share, cpm, ctr, cr in TJ_CAMPAIGNS:
            r = _rng("tj", d, cid)
            factor = SPEND_DROP_FACTOR if (spend_drop and d == as_of) else 1.0
            cost = round(total * share * r.uniform(0.95, 1.05) * factor, 4)
            impressions = int(cost / cpm * 1000)
            clicks = int(impressions * ctr / 100 * r.uniform(0.95, 1.05))
            conversions = int(clicks * cr / 100 * r.uniform(0.9, 1.1))
            rows.append({
                "day": d.isoformat(), "campaign_id": cid, "campaign_name": name, "campaign_type": ctype,
                "impressions": impressions, "clicks": clicks, "conversions": conversions,
                "ctr": round(clicks / impressions * 100, 4), "ecpm": round(cost / impressions * 1000, 4),
                "ecpc": round(cost / clicks, 4), "cost": cost, "currency": "USD",
            })
    return rows


def voluum_truth(as_of: date, days: int) -> list[dict]:
    rows = []
    for d in window_days(as_of, days):
        for cid, name, source, country, base, cpc, cr, payout in VOLUUM_CAMPAIGNS:
            r = _rng("vl", d, cid)
            cost = round(base * r.uniform(0.92, 1.08), 4)
            clicks = int(cost / cpc)
            visits = int(clicks * r.uniform(1.0, 1.05))
            impressions = int(clicks / r.uniform(0.010, 0.014))
            conversions = max(1, int(visits * cr / 100 * r.uniform(0.9, 1.1)))
            revenue = round(conversions * payout * r.uniform(0.97, 1.03), 4)
            rows.append({
                "day": d.isoformat(), "campaign_id": cid, "campaign_name": name, "traffic_source": source,
                "country": country, "visits": visits, "clicks": clicks, "conversions": conversions,
                "impressions": impressions, "revenue": revenue, "cost": cost,
                "profit": round(revenue - cost, 4), "ctr": round(clicks / impressions * 100, 4),
                "cr": round(conversions / visits * 100, 4), "cpc": round(cost / clicks, 4),
                "cpa": round(cost / conversions, 4),
            })
    return rows


def control_rows(as_of: date, days: int, scenario: Scenario) -> list[dict]:
    """daily_control: investimento e receita VERDADEIROS (EUR), independentes das APIs dos providers.

    O spend drop do TrafficJunky e REAL (o controlo interno tambem o regista): uma anomalia nao e um erro.
    """
    out = []
    for r in erobella_truth(as_of, days):
        out.append({"date": r["day"], "campaign_id": EROBELLA_ID, "revenue": None,
                    "investment": r["cost_eur"], "is_manual": False})
    for r in trafficjunky_truth(as_of, days, spend_drop=scenario.has("trafficjunky_spend_drop")):
        fx = fx_rate(date.fromisoformat(r["day"]))
        out.append({"date": r["day"], "campaign_id": r["campaign_id"], "revenue": None,
                    "investment": round(r["cost"] * fx, 4), "is_manual": False})
    for r in voluum_truth(as_of, days):
        out.append({"date": r["day"], "campaign_id": r["campaign_id"], "revenue": r["revenue"],
                    "investment": r["cost"], "is_manual": False})
    return out


def envelope(provider: str, requested_at: datetime, rows: list[dict], total_rows: int | None = None,
             offset: int = 0, limit: int | None = None, truncated: bool = False,
             messages: list[str] | None = None, **extra: Any) -> dict:
    """Formato comum da resposta simulada: linhas + metadata de paginacao."""
    return {
        "provider": provider,
        "requested_at": requested_at.isoformat(),
        "rows": rows,
        "meta": {"total_rows": len(rows) if total_rows is None else total_rows, "offset": offset,
                 "limit": limit, "truncated": truncated, "messages": messages or []},
        **extra,
    }
