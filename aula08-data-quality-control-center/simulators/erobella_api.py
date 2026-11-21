"""Erobella simulada: totais por dia (UTC), custo e eCPM em EUR.

Problemas plantados (so no cenario `broken`):
  1. erobella_missing_day   -> o dia as_of-2 (11 Nov) nao vem na resposta
  2. erobella_null_clicks   -> clicks = NULL num dia
  3. erobella_schema_drift  -> `cost: {amount, currency}` em vez de `cost_eur`
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from simulators.scenarios import Scenario, envelope, erobella_truth


def fetch(as_of: date, days: int, scenario: Scenario, requested_at: datetime) -> dict:
    rows = erobella_truth(as_of, days)

    if scenario.has("erobella_missing_day"):
        missing = (as_of - timedelta(days=2)).isoformat()
        rows = [r for r in rows if r["day"] != missing]

    if scenario.has("erobella_null_clicks"):
        target = (as_of - timedelta(days=4)).isoformat()
        for r in rows:
            if r["day"] == target:
                r["clicks"] = None

    if scenario.has("erobella_schema_drift"):  # o provider mudou o contrato sem avisar
        for r in rows:
            r["cost"] = {"amount": r.pop("cost_eur"), "currency": "EUR"}

    return envelope("erobella", requested_at, rows)
