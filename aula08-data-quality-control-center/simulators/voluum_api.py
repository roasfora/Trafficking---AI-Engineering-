"""Voluum simulada: GET /report (por dia e campanha) + conversoes individuais, com paginacao.

Problemas plantados (so no cenario `broken`):
  7. voluum_incomplete_pagination      -> limit=50 mas total_rows=60; truncated=true
  8. voluum_stale_data                 -> os 2 ultimos dias ainda nao existem (2 dias de atraso)
  9. voluum_revenue_without_conversions -> revenue > 0 com conversions = 0 (postbacks perdidos)
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

from simulators.scenarios import Scenario, envelope, fx_rate, voluum_truth, VOLUUM_CAMPAIGNS

DEFAULT_LIMIT = 1000
SHORT_LIMIT = 50  # no cenario broken a API devolve so 50 linhas


def fetch(as_of: date, days: int, scenario: Scenario, requested_at: datetime) -> dict:
    rows = voluum_truth(as_of, days)

    if scenario.has("voluum_stale_data"):
        cutoff = (as_of - timedelta(days=2)).isoformat()
        rows = [r for r in rows if r["day"] <= cutoff]

    if scenario.has("voluum_revenue_without_conversions"):
        targets = {(as_of - timedelta(days=5)).isoformat(), (as_of - timedelta(days=4)).isoformat()}
        for r in rows:
            if r["campaign_id"] == "vl-1002" and r["day"] in targets:
                r["conversions"], r["cr"], r["cpa"] = 0, 0.0, 0.0  # revenue fica > 0

    rows.sort(key=lambda r: (r["day"], r["campaign_id"]), reverse=True)  # mais recentes primeiro
    total = len(rows)
    limit = SHORT_LIMIT if scenario.has("voluum_incomplete_pagination") else DEFAULT_LIMIT
    page = rows[:limit]
    truncated = total > limit
    messages = [f"Result truncated: {len(page)} of {total} rows. Use offset to fetch the next page."] if truncated else []

    return envelope("voluum", requested_at, page, total_rows=total, offset=0, limit=limit,
                    truncated=truncated, messages=messages, conversions=conversions_for(page))


def conversions_for(report_rows: list[dict]) -> list[dict]:
    """Uma linha por conversao, coerente com as linhas do report que a API devolveu."""
    geo = {c[0]: c[3] for c in VOLUUM_CAMPAIGNS}
    source_ids = {"TrafficJunky": "ts-tj", "Erobella": "ts-eb", "Other": "ts-ot"}
    out = []
    for r in report_rows:
        n = r["conversions"]
        if not n:
            continue
        day = date.fromisoformat(r["day"])
        rng = random.Random(f"conv-{r['day']}-{r['campaign_id']}")
        per_conv_eur = r["revenue"] / n
        for i in range(n):
            visit = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(seconds=rng.randint(0, 86_399))
            out.append({
                "click_id": f"{r['campaign_id']}-{r['day']}-{i:03d}",
                "campaign_id": r["campaign_id"],
                "visit_timestamp": visit.isoformat(),
                "postback_timestamp": (visit + timedelta(minutes=rng.randint(5, 180))).isoformat(),
                "revenue": round(per_conv_eur / fx_rate(day), 4),         # USD
                "revenue_original_currency": round(per_conv_eur, 4),      # EUR (moeda da fonte)
                "conversion_type_id": 1,
                "country_code": geo[r["campaign_id"]],
                "offer_id": f"offer-{(i % 3) + 1}",
                "traffic_source_id": source_ids[r["traffic_source"]],
            })
    return out
