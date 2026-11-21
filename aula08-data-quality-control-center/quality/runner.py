"""Runner: carrega a config, executa os checks, persiste os resultados e calcula a quality gate.

    results = run_quality_gate(layer="bronze", provider="trafficjunky", run_id=run_id)

    PASS -> segue, sem notificacao
    WARN -> persiste, notifica, segue
    FAIL -> persiste, notifica, BLOQUEIA o publish (nunca apaga Bronze nem Silver)

O Airflow chama isto; o Airflow nao e o sistema de Data Quality.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import yaml
from psycopg.types.json import Jsonb

from config import PROVIDERS, get_settings
from db import connect
from quality import bronze_checks, reconciliation, semantic_checks, silver_checks
from quality.context import CheckContext
from quality.models import CheckResult, GateResult, worst
from quality.notifier import get_notifier

REGISTRY = {**bronze_checks.CHECKS, **silver_checks.CHECKS, **semantic_checks.CHECKS, **reconciliation.CHECKS}

TYPE_DIMENSION = {
    "freshness": "freshness", "schema_diff": "schema", "row_count": "completeness", "null_rate": "completeness",
    "duplicate_rows": "uniqueness", "pagination_complete": "completeness", "truncated_response": "completeness",
    "not_null": "completeness", "min_value": "validity", "allowed_values": "validity", "unique_grain": "uniqueness",
    "country_iso2": "validity", "currency_is_eur": "validity", "clicks_le_impressions": "consistency",
    "conversions_le_clicks": "consistency", "revenue_without_conversions": "consistency",
    "cost_without_impressions": "consistency", "known_campaign": "consistency", "rolling_avg_change": "volume",
    "ratio_bounds": "validity", "ratio_of_sums": "consistency", "metric_vs_provider": "accuracy",
    "metric_availability": "consistency", "no_avg_of_ratios": "consistency", "additivity": "consistency",
    "reconcile_api_to_bronze": "reconciliation", "reconcile_bronze_to_silver": "reconciliation",
    "reconcile_silver_to_gold": "reconciliation", "reconcile_control": "reconciliation",
}


def load_checks(path=None) -> list[dict]:
    with open(path or get_settings().checks_file, encoding="utf-8") as fh:
        specs = yaml.safe_load(fh)["checks"]
    names = [(s["name"], s["provider"], s["layer"]) for s in specs]
    if len(names) != len(set(names)):
        raise ValueError("duplicate (name, provider, layer) in quality_checks.yaml")
    for s in specs:
        if s["type"] not in REGISTRY:
            raise ValueError(f"check {s['name']!r}: unknown type {s['type']!r}")
    return specs


def _apply_spec_metadata(spec: dict, result: CheckResult) -> CheckResult:
    """Severity (warning = nunca FAIL) + metadata do check (para o dashboard explicar 'why it matters')."""
    severity = spec.get("severity", "critical")
    if severity == "warning" and result.status == "FAIL":
        result.status = "WARN"
        result.details["capped_by_severity"] = True
    result.details.update({"severity": severity, "check_type": spec["type"],
                           "why_it_matters": spec.get("why", ""), "description": spec.get("description", "")})
    return result


def _run_one(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    spec = {**spec, "dimension": spec.get("dimension") or TYPE_DIMENSION[spec["type"]]}
    try:
        results = REGISTRY[spec["type"]](spec, ctx)
    except Exception as exc:  # um check que nao consegue correr NAO e um PASS
        results = [ctx.result(spec, "FAIL", message=f"check could not run: {type(exc).__name__}: {exc}",
                              error=f"{type(exc).__name__}: {exc}")]
    return [_apply_spec_metadata(spec, r) for r in results]


def _persist(conn, results: list[CheckResult]) -> None:
    if not results:
        return
    sql = """INSERT INTO data_quality.check_results
             (run_id, checked_at, provider, dataset, layer, check_name, dimension, status,
              observed_value, expected_value, threshold, details)
             VALUES (%(run_id)s, %(checked_at)s, %(provider)s, %(dataset)s, %(layer)s, %(check_name)s, %(dimension)s,
                     %(status)s, %(observed_value)s, %(expected_value)s, %(threshold)s, %(details)s)"""
    rows = [{**r.to_row(), "details": Jsonb(r.details, dumps=lambda o: json.dumps(o, default=str))} for r in results]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()


def run_quality_gate(layer: str, run_id: str, provider: str | None = None, conn=None, providers: tuple | None = None,
                     notifier: Any = None, persist: bool = True, checks: list[dict] | None = None,
                     checked_at: datetime | None = None, **context_overrides: Any) -> GateResult:
    """Executa os checks de UMA camada. `provider=None` = todos os providers + checks `platform`."""
    own_conn = conn is None
    conn = conn or connect()
    try:
        checks = checks if checks is not None else load_checks()
        checked_at = checked_at or datetime.now(timezone.utc)
        targets = [provider] if provider and provider != "all" else list(providers or get_settings().providers)
        unknown = set(targets) - set(PROVIDERS)
        if unknown:
            raise ValueError(f"unknown provider(s): {sorted(unknown)}")
        notifier = notifier if notifier is not None else get_notifier(conn)

        results: list[CheckResult] = []
        for spec in (s for s in checks if s["layer"] == layer):
            scopes = targets if spec["provider"] == "all" else \
                ([spec["provider"]] if spec["provider"] in targets else
                 (["platform"] if spec["provider"] == "platform" and not (provider and provider != "all") else []))
            for scope in scopes:
                ctx = CheckContext(run_id, scope, layer, conn=conn, checked_at=checked_at, **context_overrides)
                results.extend(_run_one(spec, ctx))

        if persist:
            _persist(conn, results)
        for r in results:
            if r.status != "PASS":
                notifier.notify(r)

        status = worst(r.status for r in results)
        return GateResult(layer=layer, run_id=run_id, provider=provider or "all", status=status,
                          publish_allowed=status != "FAIL", results=results)
    finally:
        if own_conn:
            conn.close()
