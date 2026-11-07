"""Exporta as tabelas de INPUT (o que a API entrega a pipeline) para CSV.

Serve para mostrar aos alunos os dados "em bruto", antes do validate/transform:
exatamente os registos que o extract descarrega, um CSV por dataset.

    python -m scripts.export_sample_csv                 # dia 2026-10-01
    python -m scripts.export_sample_csv 2026-10-03      # outro dia

Escreve em sample-data/<dia>/. Inclui ainda sample-data/<dia>/faults/ com as
versoes ADULTERADAS de conversions e campaign_costs (modos schema_drift e
invalid_payload), para mostrar o que o `validate` rejeita.

Nao precisa de Docker nem de base de dados: usa o gerador diretamente.
"""

from __future__ import annotations

import csv
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from api import faults, generator
from api.config import get_api_settings

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def cell(value: Any) -> str:
    """Valor -> texto, como a API o serializaria (ISO 8601; NULL = vazio)."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = columns or list(rows[0])
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([cell(row.get(c)) for c in columns])


def main() -> None:
    day = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2026, 10, 1)
    start = datetime.combine(day, time.min, tzinfo=UTC)
    end = start + timedelta(days=1)
    seed = get_api_settings().seed
    out = ROOT / "sample-data" / day.isoformat()

    datasets = {
        "workspaces": generator.list_workspaces(),
        "traffic_sources": generator.list_traffic_sources(),
        "campaigns": generator.list_campaigns(),
        "offers": generator.list_offers(),
        "conversions": generator.list_conversions(seed, start, end),
        "campaign_costs": generator.list_campaign_costs(seed, start, end),
        "daily_control": generator.list_daily_control(seed, start, end),
    }
    for name, rows in datasets.items():
        write_csv(out / f"{name}.csv", rows)
        print(f"{name:16} {len(rows):5} linhas")

    # versoes adulteradas (o que a API devolve nos modos de falha)
    for mode in (faults.Mode.schema_drift, faults.Mode.invalid_payload):
        faults.STATE.set(mode)
        for name in ("conversions", "campaign_costs"):
            rows = faults.corrupt(name, datasets[name])
            columns = list(rows[0])
            if mode is faults.Mode.invalid_payload:
                columns = list(datasets[name][0])
            write_csv(out / "faults" / f"{name}__{mode.value}.csv", rows, columns)
    faults.STATE.set(faults.Mode.healthy)
    print(f"\nEscrito em {out.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
