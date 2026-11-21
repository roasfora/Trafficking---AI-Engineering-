"""TrafficJunky simulada: por dia e campanha, custo em USD, ratios do provider (ctr, ecpm, ecpc).

Problemas plantados (so no cenario `broken`):
  4. trafficjunky_duplicate_campaign -> a mesma campanha/dia aparece duas vezes
  5. trafficjunky_spend_drop         -> spend do ultimo dia ~74% abaixo da media (vem do "mundo verdadeiro")
  6. trafficjunky_ecpc_mismatch      -> o ecpc que o provider reporta nao bate com cost/clicks
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from simulators.scenarios import Scenario, envelope, trafficjunky_truth


def fetch(as_of: date, days: int, scenario: Scenario, requested_at: datetime) -> dict:
    rows = trafficjunky_truth(as_of, days, spend_drop=scenario.has("trafficjunky_spend_drop"))

    if scenario.has("trafficjunky_ecpc_mismatch"):
        for r in rows:
            if r["campaign_id"] == "tj-2002":  # TJ-Native-FR: o provider calcula o ecpc de outra forma
                r["ecpc"] = round(r["ecpc"] * 1.06, 4)

    if scenario.has("trafficjunky_duplicate_campaign"):
        day = (as_of - timedelta(days=1)).isoformat()
        dup = next(dict(r) for r in rows if r["day"] == day and r["campaign_id"] == "tj-2001")
        rows.append(dup)

    return envelope("trafficjunky", requested_at, rows)
