"""BRONZE: guarda o que o provider disse, tal como o provider o disse.

NAO converte moeda, NAO renomeia metricas para nomes canonicos, NAO recalcula CPC, NAO corrige valores.
Se o provider mudar um campo (ex.: `cost_eur` -> `cost.amount`), a coluna tipada fica NULL e a linha original
fica intacta em `raw_payload`. Quem repara nisso e o check schema_diff, nao o loader.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from psycopg.types.json import Jsonb

SOURCE_CURRENCY = {"erobella": "EUR", "trafficjunky": "USD", "voluum": "EUR"}

# colunas tipadas = campos que o provider documenta (nomes do PROVIDER, nao os canonicos)
PROVIDER_COLUMNS = {
    "erobella": ("day", "impressions", "clicks", "ctr_pct", "cost_eur", "ecpm_eur", "rates", "updated_at"),
    "trafficjunky": ("day", "campaign_id", "campaign_name", "campaign_type", "impressions", "clicks",
                     "conversions", "ctr", "ecpm", "ecpc", "cost", "currency"),
    "voluum": ("day", "campaign_id", "campaign_name", "traffic_source", "country", "visits", "clicks",
               "conversions", "impressions", "revenue", "cost", "profit", "ctr", "cr", "cpc", "cpa"),
}
TABLES = {
    "erobella": "raw.erobella_daily_stats",
    "trafficjunky": "raw.trafficjunky_campaign_stats",
    "voluum": "raw.voluum_report",
}
CONVERSION_COLUMNS = ("click_id", "campaign_id", "visit_timestamp", "postback_timestamp", "revenue",
                      "revenue_original_currency", "conversion_type_id", "country_code", "offer_id", "traffic_source_id")


def payload_to_records(provider: str, payload: dict, run_id: str, as_of: date, scenario: str) -> dict[str, Any]:
    """Funcao pura: payload da API -> linhas Bronze + linha de api_runs. (testavel sem base de dados)"""
    rows = payload["rows"]
    meta = payload["meta"]
    fields = sorted({key for row in rows for key in row})
    days = [r["day"] for r in rows if r.get("day")]
    requested_at = datetime.fromisoformat(payload["requested_at"])
    common = {"run_id": run_id, "provider": provider, "request_date": as_of, "source_currency": SOURCE_CURRENCY[provider]}

    records = []
    for row in rows:
        rec = dict(common)
        for col in PROVIDER_COLUMNS[provider]:
            rec[col] = row.get(col)  # campo ausente (schema drift) -> None; o original fica em raw_payload
        rec["raw_payload"] = row
        records.append(rec)

    conversions = [dict(common, **{c: conv.get(c) for c in CONVERSION_COLUMNS}) for conv in payload.get("conversions", [])]

    api_run = {
        "run_id": run_id, "provider": provider, "request_date": as_of, "requested_at": requested_at,
        "scenario": scenario, "source_currency": SOURCE_CURRENCY[provider], "http_status": 200,
        "rows_received": len(rows), "total_rows": meta.get("total_rows"), "page_offset": meta.get("offset"),
        "page_limit": meta.get("limit"), "truncated": bool(meta.get("truncated")),
        "messages": meta.get("messages", []), "response_fields": fields,
        "latest_data_date": max(days) if days else None,
    }
    return {"api_run": api_run, "rows": records, "conversions": conversions}


def _jsonb(value: Any) -> Any:
    return Jsonb(value) if isinstance(value, (dict, list)) else value


def _insert(conn, table: str, records: list[dict]) -> None:
    if not records:
        return
    cols = list(records[0])
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
    with conn.cursor() as cur:
        cur.executemany(sql, [[_jsonb(r[c]) for c in cols] for r in records])


def load_bronze(conn, provider: str, payload: dict, run_id: str, as_of: date, scenario: str) -> dict[str, int]:
    """Grava o payload nas tabelas raw.* e regista a resposta em raw.api_runs. Devolve contagens."""
    parts = payload_to_records(provider, payload, run_id, as_of, scenario)
    _insert(conn, "raw.api_runs", [parts["api_run"]])
    _insert(conn, TABLES[provider], parts["rows"])
    if provider == "voluum":
        _insert(conn, "raw.voluum_conversions", parts["conversions"])
    conn.commit()
    return {"rows": len(parts["rows"]), "conversions": len(parts["conversions"])}


def load_control(conn, rows: list[dict]) -> int:
    """daily_control vem do sistema interno (independente dos providers). Upsert: e referencia, nao historico."""
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO analytics.daily_control (date, campaign_id, revenue, investment, is_manual)
               VALUES (%(date)s, %(campaign_id)s, %(revenue)s, %(investment)s, %(is_manual)s)
               ON CONFLICT (date, campaign_id) DO UPDATE
               SET revenue = EXCLUDED.revenue, investment = EXCLUDED.investment, is_manual = EXCLUDED.is_manual""",
            rows,
        )
    conn.commit()
    return len(rows)


def write_payload(path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def read_payload(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
