"""Que DIA processa esta run?

Tres origens, por ordem de prioridade:

1. conf {"date": "2026-10-03"}   quem dispara a run a mao escolhe o dia
2. data interval                 runs AGENDADAS e backfills: o Airflow decide
3. o dia anterior (UTC)          run manual sem mais informacao

No Airflow 3 uma run disparada a mao NAO tem data interval; sem o fallback, um
"Trigger DAG" na UI nao saberia que dia processar.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

UTC = timezone.utc


def resolve_day(
    data_interval_start: datetime | None,
    run_after: datetime,
    conf: dict[str, Any] | None = None,
) -> date:
    if conf and conf.get("date"):
        return date.fromisoformat(conf["date"])
    if data_interval_start is not None:
        return data_interval_start.astimezone(UTC).date()
    return run_after.astimezone(UTC).date() - timedelta(days=1)
