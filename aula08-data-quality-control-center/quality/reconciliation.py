"""Reconciliacao: o mesmo numero, contado em dois sitios, tem de dar o mesmo.

    Provider API  ->  Bronze  ->  Silver  ->  Gold        (e Silver vs daily_control, o sistema interno)

Considera moeda (TrafficJunky em USD, convertido com a tabela exchange_rate) e dados em falta.
Fusos horarios e dados tardios ficam documentados no README: aqui compara-se o mesmo conjunto de dias.
"""

from __future__ import annotations

from quality.context import CheckContext
from quality.models import CheckResult, pct_diff, status_from_abs_pct

BRONZE_COST_FIELD = {"erobella": "cost_eur", "trafficjunky": "cost", "voluum": "cost"}


def _compare(spec, ctx, metric, observed, expected, what, **extra) -> CheckResult:
    diff = pct_diff(observed, expected)
    status = status_from_abs_pct(abs(diff), spec.get("warn_pct"), spec.get("fail_pct"))
    return ctx.result(spec, status, observed=observed, expected=expected, threshold=spec.get("warn_pct"),
                      suffix=f"_{metric}", dimension="reconciliation",
                      message=f"{what} {metric}: {observed:,.2f} vs {expected:,.2f} ({diff:+.2f}%)",
                      metric=metric, diff_pct=round(diff, 4), **extra)


def reconcile_api_to_bronze(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """O que o provider diz ter devolvido == o que a Bronze guardou?"""
    run = ctx.api_run
    declared = run["total_rows"] if run and run["total_rows"] is not None else len(ctx.bronze_rows)
    return [_compare(spec, ctx, "row_count", len(ctx.bronze_rows), declared, "API vs Bronze")]


def reconcile_bronze_to_silver(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """A normalizacao preservou linhas, spend (em EUR), clicks e conversoes?"""
    bronze, silver = ctx.bronze_rows, ctx.silver_rows
    cost_field = BRONZE_COST_FIELD[ctx.provider]

    def bronze_spend() -> float:
        total = 0.0
        for r in bronze:
            fx = 1.0 if r["source_currency"] == "EUR" else ctx.fx_rates.get((r["day"].isoformat(), r["source_currency"]), 0.0)
            total += (r.get(cost_field) or 0.0) * fx
        return total

    def s(rows, col):
        return float(sum((r.get(col) or 0) for r in rows))

    pairs = {
        "row_count": (len(silver), len(bronze)),
        "spend": (s(silver, "cost"), bronze_spend()),
        "clicks": (s(silver, "clicks"), s(bronze, "clicks")),
        "conversions": (s(silver, "conversions"), s(bronze, "conversions")),
    }
    return [_compare(spec, ctx, m, *pairs[m], "Bronze vs Silver") for m in spec["metrics"]]


def reconcile_silver_to_gold(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """A camada semantica (formulas do semantic.yaml) devolve o que a Silver contem?"""
    rows = ctx.silver_rows
    out = []
    for metric in spec["metrics"]:
        column = {"spend": "cost"}.get(metric, metric)
        expected = float(sum((r.get(column) or 0) for r in rows))
        observed = float(ctx.semantic_value(metric) or 0)
        out.append(_compare(spec, ctx, metric, observed, expected, "Silver vs Gold"))
    return out


def reconcile_control(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """Silver vs daily_control (sistema interno, independente do provider): investimento e receita."""
    prefix = spec["campaign_prefix"]
    days = {d.isoformat() for d in ctx.expected_days}
    control = [r for r in ctx.control_rows if r["campaign_id"].startswith(prefix) and r["date"].isoformat() in days]
    silver = ctx.silver_rows
    out = []
    for metric in spec["metrics"]:
        s_col, c_col = ("cost", "investment") if metric == "spend" else ("revenue", "revenue")
        observed = float(sum((r.get(s_col) or 0) for r in silver))
        expected = float(sum((r.get(c_col) or 0) for r in control))
        silver_days = {str(r["date"]) for r in silver}
        out.append(_compare(spec, ctx, metric, observed, expected, "Silver vs daily_control",
                            days_in_silver=len(silver_days), days_in_control=len(days)))
    return out


CHECKS = {
    "reconcile_api_to_bronze": reconcile_api_to_bronze,
    "reconcile_bronze_to_silver": reconcile_bronze_to_silver,
    "reconcile_silver_to_gold": reconcile_silver_to_gold,
    "reconcile_control": reconcile_control,
}
