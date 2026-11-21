"""Gera sql/04_seed_reference.sql: dimensao de campanhas e taxas de cambio USD->EUR.

As taxas vem de simulators.scenarios.fx_rate: o simulador (que cria o "mundo verdadeiro") e a base de dados
usam EXATAMENTE os mesmos valores. Correr: python scripts/generate_reference_seed.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from simulators.scenarios import VOLUUM_CAMPAIGNS, fx_rate  # noqa: E402

START, END = date(2026, 10, 20), date(2026, 12, 31)


def main() -> None:
    lines = [
        "-- GERADO por scripts/generate_reference_seed.py. Nao editar a mao.",
        "-- Referencia: campanhas (dimensao) e taxas de cambio (a normalizacao le daqui).",
        "",
        "INSERT INTO analytics.campaigns (campaign_id, name, geo, traffic_source, workspace_id, is_paused, created) VALUES",
    ]
    rows = []
    for cid, name, source, country, *_ in VOLUUM_CAMPAIGNS:
        rows.append(f"  ('{cid}', '{name}', '{country}', '{source}', 1, false, '2026-09-01T00:00:00Z')")
    lines.append(",\n".join(rows) + "\nON CONFLICT (campaign_id) DO NOTHING;\n")

    lines.append("INSERT INTO analytics.exchange_rate (date, source_currency, target_currency, rate) VALUES")
    rates = []
    d = START
    while d <= END:
        rates.append(f"  ('{d.isoformat()}', 'USD', 'EUR', {fx_rate(d)})")
        d += timedelta(days=1)
    lines.append(",\n".join(rates) + "\nON CONFLICT DO NOTHING;")
    (ROOT / "sql" / "04_seed_reference.sql").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote sql/04_seed_reference.sql ({len(rates)} exchange rates)")


if __name__ == "__main__":
    main()
