"""Checks da BRONZE. Pergunta: "recebemos os dados corretamente?"

Sao so funcoes: `check(spec, ctx) -> list[CheckResult]`. Os parametros (limites, colunas) vem do
config/quality_checks.yaml: checks are configuration, not DAG logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quality.context import CheckContext
from quality.models import CheckResult, pct_diff, status_from_abs_pct


def freshness(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """Ha quantas horas terminou o dia mais recente que recebemos?"""
    run = ctx.api_run
    max_delay = float(spec["max_delay_hours"])
    if run is None or run["latest_data_date"] is None:
        return [ctx.result(spec, "FAIL", expected=max_delay, threshold=max_delay, message="no data received")]
    latest = run["latest_data_date"]
    end_of_latest_day = datetime.combine(latest + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    lag_hours = (run["requested_at"] - end_of_latest_day).total_seconds() / 3600
    status = "FAIL" if lag_hours > max_delay else "WARN" if lag_hours > 0.8 * max_delay else "PASS"
    return [ctx.result(spec, status, observed=lag_hours, expected=0, threshold=max_delay,
                       message=f"latest data day {latest.isoformat()} is {lag_hours:.0f}h old (max {max_delay:.0f}h)",
                       latest_data_date=latest.isoformat())]


def schema_diff(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """Os campos da resposta sao os que o contrato diz? Campo em falta = FAIL; campo novo = WARN."""
    run = ctx.api_run
    expected = set(spec["expected_fields"])
    observed = set(run["response_fields"]) if run else set()
    missing, unexpected = sorted(expected - observed), sorted(observed - expected)
    status = "FAIL" if missing else "WARN" if unexpected else "PASS"
    return [ctx.result(spec, status, observed=len(missing) + len(unexpected), expected=0, threshold=0,
                       message=(f"schema drift: missing {missing}, unexpected {unexpected}" if status != "PASS"
                                else "schema matches the contract"),
                       missing_fields=missing, unexpected_fields=unexpected)]


def row_count(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """Temos as linhas que esperamos? Esperado = dias da janela x entidades por dia (chaves distintas)."""
    keys = spec["keys"]
    rows = ctx.bronze_rows
    distinct = {tuple(r.get(k) for k in keys) for r in rows}
    expected = len(ctx.expected_days) * int(spec["entities_per_day"])
    diff = pct_diff(len(distinct), expected)
    status = status_from_abs_pct(abs(diff), spec.get("warn_pct"), spec.get("fail_pct"))
    days_present = {r["day"] for r in rows if r.get("day")}
    missing_dates = [d.isoformat() for d in ctx.expected_days if d not in days_present]
    msg = f"{len(distinct)} of {expected} expected rows ({diff:+.1f}%)"
    if missing_dates:
        msg += f"; missing days: {', '.join(missing_dates)}"
    return [ctx.result(spec, status, observed=len(distinct), expected=expected, threshold=spec.get("fail_pct"),
                       message=msg, diff_pct=round(diff, 2), missing_dates=missing_dates)]


def null_rate(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """Que fraccao das linhas tem NULL nas colunas vigiadas? O pior caso decide o estado."""
    rows = ctx.bronze_rows
    total = len(rows) or 1
    rates = {c: sum(1 for r in rows if r.get(c) is None) / total for c in spec["columns"]}
    column, worst_rate = max(rates.items(), key=lambda kv: kv[1])
    status = status_from_abs_pct(worst_rate * 100, spec.get("warn_pct"), spec.get("fail_pct"))
    return [ctx.result(spec, status, observed=worst_rate, expected=0, threshold=(spec.get("warn_pct") or 0) / 100,
                       message=f"{column} is NULL in {worst_rate:.1%} of rows",
                       null_rates={c: round(v, 4) for c, v in rates.items()}, worst_column=column)]


def duplicate_rows(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """Ha chaves repetidas? A Bronze guarda-as; o check avisa."""
    keys = spec["keys"]
    seen: dict[tuple, int] = {}
    for r in ctx.bronze_rows:
        k = tuple(r.get(c) for c in keys)
        seen[k] = seen.get(k, 0) + 1
    dups = {k: n for k, n in seen.items() if n > 1}
    extra = sum(n - 1 for n in dups.values())
    sample = [dict(zip(keys, (str(v) for v in k)), times=n) for k, n in list(dups.items())[:5]]
    return [ctx.result(spec, "FAIL" if extra else "PASS", observed=extra, expected=0, threshold=0,
                       message=(f"{extra} duplicated row(s) on key {keys}" if extra else f"key {keys} is unique"),
                       duplicates=sample)]


def pagination_complete(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """Recebemos TODAS as linhas que o provider diz ter? (total_rows declarado vs linhas carregadas)"""
    run = ctx.api_run
    loaded = len(ctx.bronze_rows)
    total = run["total_rows"] if run and run["total_rows"] is not None else loaded
    status = "FAIL" if loaded < total else "PASS"
    return [ctx.result(spec, status, observed=loaded, expected=total, threshold=total,
                       message=(f"loaded {loaded} of {total} rows: pagination incomplete" if status == "FAIL"
                                else f"all {total} rows loaded"),
                       diff_pct=round(pct_diff(loaded, total), 2))]


def truncated_response(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """O provider avisou que a resposta foi truncada?"""
    run = ctx.api_run
    truncated = bool(run and run["truncated"])
    return [ctx.result(spec, "FAIL" if truncated else "PASS", observed=1 if truncated else 0, expected=0, threshold=0,
                       message=("provider flagged the response as truncated" if truncated else "response not truncated"),
                       provider_messages=(run or {}).get("messages", []))]


CHECKS = {
    "freshness": freshness,
    "schema_diff": schema_diff,
    "row_count": row_count,
    "null_rate": null_rate,
    "duplicate_rows": duplicate_rows,
    "pagination_complete": pagination_complete,
    "truncated_response": truncated_response,
}
