"""Que janela de tempo processa esta run?  [start, end), sempre em UTC.

Tres origens, por ordem de prioridade:

1. conf {"date": "2026-10-03"}   quem dispara a run manualmente escolhe o dia
2. data interval                 runs AGENDADAS e backfills: o Airflow decide
3. o dia anterior (UTC)          run manual sem mais informacao

Porque e que o 3 existe: no Airflow 3, uma run disparada manualmente NAO tem
data interval (nem logical_date). O data interval pertence a runs agendadas.
Sem este fallback, um "Trigger DAG" na UI nao saberia que dia processar.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

UTC = timezone.utc


def resolve_window(
    data_interval_start: datetime | None,
    data_interval_end: datetime | None,
    run_after: datetime,
    conf: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Devolve (interval_start, interval_end) em ISO 8601."""
    if conf and conf.get("date"):
        day = datetime.combine(datetime.fromisoformat(conf["date"]).date(), time.min, tzinfo=UTC)
        return day.isoformat(), (day + timedelta(days=1)).isoformat()

    if data_interval_start is not None and data_interval_end is not None:
        return data_interval_start.isoformat(), data_interval_end.isoformat()

    today = datetime.combine(run_after.astimezone(UTC).date(), time.min, tzinfo=UTC)
    return (today - timedelta(days=1)).isoformat(), today.isoformat()
