"""Checks da camada SEMANTICA (Gold). Pergunta: "as metricas publicadas merecem confianca?"

As formulas vem do semantic.yaml (nunca duplicadas aqui). Estes checks verificam se as metricas se
comportam como metricas: rácios dentro de limites, "ratio of sums", sem AVG de rácios, aditividade,
e se o que o provider reporta bate com o nosso calculo canonico.
"""

from __future__ import annotations

import re

from quality.context import CheckContext, fetch_rows
from quality.models import CheckResult, pct_diff, status_from_abs_pct

AVG_RE = re.compile(r"\bAVG\s*\(", re.IGNORECASE)
VIEWS = ("analytics.v_metrics_provider_daily", "analytics.v_metrics_campaign_daily")
REL_TOL = 1e-9


def _sum(rows, col):
    values = [r[col] for r in rows if r.get(col) is not None]
    return sum(values) if values else None


def ratio_bounds(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """CTR e CR (em %) tem de estar em [0, 100]. Fora disto, o numerador ou o denominador estao errados."""
    defs = {"ctr": ("clicks", "impressions"), "cr": ("conversions", "clicks")}
    bad, worst_seen = [], 0.0
    for metric, (low, high) in spec["bounds"].items():
        num, den = defs[metric]
        for r in ctx.silver_rows:
            if r.get(num) is None or not r.get(den):
                continue
            value = 100.0 * r[num] / r[den]
            worst_seen = max(worst_seen, value)
            if value < low or value > high:
                bad.append({"metric": metric, "date": str(r["date"]), "campaign_id": r["campaign_id"], "value": round(value, 2)})
    return [ctx.result(spec, "FAIL" if bad else "PASS", observed=worst_seen, expected=100, threshold=100,
                       message=(f"{len(bad)} ratio(s) outside bounds" if bad else "all ratios within [0, 100]"),
                       violations=bad[:5])]


def ratio_of_sums(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """A expressao do semantic.yaml tem de dar o mesmo que SUM(numerador)/SUM(denominador) calculado a parte."""
    out = []
    rows = ctx.silver_rows
    for metric, parts in spec["metrics"].items():
        num, den, scale = _sum(rows, parts["numerator"]), _sum(rows, parts["denominator"]), parts.get("scale", 1)
        expected = None if not num or not den else scale * num / den
        observed = ctx.semantic_value(metric)
        if observed is None or expected is None:
            ok = observed is None and expected is None
            diff = 0.0 if ok else 1.0
        else:
            diff = abs(observed - expected) / max(abs(expected), 1e-12)
            ok = diff <= REL_TOL
        out.append(ctx.result(spec, "PASS" if ok else "FAIL", observed=observed, expected=expected, threshold=REL_TOL,
                              suffix=f"_{metric}", message=(f"{metric} is a ratio of sums" if ok else
                                                            f"{metric} does not equal SUM(num)/SUM(den): wrong aggregation?"),
                              metric=metric, relative_diff=diff))
    return out


def metric_vs_provider(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """O que o provider reporta (ecpc, ecpm, cpc) bate com o nosso calculo canonico (mesma moeda)?"""
    metric, field = spec["metric"], spec["provider_field"]
    weight, scale = ("clicks", 1) if metric == "cpc" else ("impressions", 1000)

    canonical: dict = {}
    for r in ctx.silver_rows:
        c = canonical.setdefault(r["campaign_id"], [0.0, 0.0])
        c[0] += r["cost"] or 0.0
        c[1] += r[weight] or 0
    provider: dict = {}
    for r in ctx.bronze_rows:
        w, value = r.get(weight) or 0, r.get(field)
        if value is None or not w:
            continue
        currency = r["source_currency"]
        fx = 1.0 if currency == "EUR" else ctx.fx_rates.get((r["day"].isoformat(), currency))
        cid = r.get("campaign_id") or "erobella-total"
        p = provider.setdefault(cid, [0.0, 0.0])
        p[0] += value * (fx or 0.0) * w
        p[1] += w

    per_campaign, worst_diff = {}, 0.0
    for cid, (cost, w) in canonical.items():
        if cid not in provider or not w or not provider[cid][1]:
            continue
        canon = scale * cost / w
        theirs = provider[cid][0] / provider[cid][1]
        diff = pct_diff(theirs, canon)
        per_campaign[cid] = {"provider": round(theirs, 4), "canonical": round(canon, 4), "diff_pct": round(diff, 2)}
        worst_diff = max(worst_diff, abs(diff))
    if not per_campaign:
        return [ctx.result(spec, "FAIL", message=f"cannot compare {metric} with the provider: no comparable rows")]
    status = status_from_abs_pct(worst_diff, spec.get("warn_pct"), spec.get("fail_pct"))
    worst_cid = max(per_campaign, key=lambda k: abs(per_campaign[k]["diff_pct"]))
    return [ctx.result(spec, status, observed=worst_diff / 100, expected=0, threshold=(spec.get("warn_pct") or 0) / 100,
                       message=(f"provider {field} differs from canonical {metric} by up to {worst_diff:.1f}% "
                                f"({worst_cid})"), metric=metric, provider_field=field, per_campaign=per_campaign)]


def metric_availability(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """ROAS so existe onde ha receita. Sem revenue, o ROAS tem de ser NULL (nunca 0, nunca inventado)."""
    metric, requires = spec["metric"], spec["requires"]
    has_inputs = all(any(r.get(c) is not None for r in ctx.silver_rows) for c in requires)
    value = ctx.semantic_value(metric)
    ok = (value is not None) if has_inputs else (value is None)
    return [ctx.result(spec, "PASS" if ok else "FAIL", observed=None if value is None else value,
                       expected=None, message=(f"{metric} is {'available' if has_inputs else 'NULL'}, as expected"
                                               if ok else f"{metric} should be {'available' if has_inputs else 'NULL'} "
                                                          f"when the provider {'reports' if has_inputs else 'does not report'} {requires}"),
                       metric=metric, requires=requires, provider_reports_inputs=has_inputs)]


def no_avg_of_ratios(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """Varredura estatica: nenhuma metrica (nem view) pode usar AVG(...) sobre rácios."""
    offenders = [name for name, m in ctx.semantic["metrics"].items() if AVG_RE.search(m["expression"])]
    if ctx.conn is not None:
        for view in VIEWS:
            definition = fetch_rows(ctx.conn, "SELECT pg_get_viewdef(%s::regclass) AS d", (view,))[0]["d"]
            if AVG_RE.search(definition):
                offenders.append(view)
    return [ctx.result(spec, "FAIL" if offenders else "PASS", observed=len(offenders), expected=0, threshold=0,
                       message=(f"AVG() found in: {offenders}" if offenders else "no AVG() of ratios in metrics or views"),
                       offenders=offenders)]


def additivity(spec: dict, ctx: CheckContext) -> list[CheckResult]:
    """Metricas aditivas: soma por campanha == total do provider (os dois calculados pelas formulas do yaml)."""
    out = []
    for metric in spec["metrics"]:
        total = ctx.semantic_value(metric)
        per_campaign = ctx.semantic_value(metric, group_by="campaign_id")
        parts = [r["value"] for r in per_campaign if r["value"] is not None]
        summed = sum(parts) if parts else None
        if total is None or summed is None:
            ok, diff = total is None and summed is None, 0.0
        else:
            diff = abs(total - summed) / max(abs(total), 1e-12)
            ok = diff <= REL_TOL
        out.append(ctx.result(spec, "PASS" if ok else "FAIL", observed=summed, expected=total, threshold=REL_TOL,
                              suffix=f"_{metric}", message=(f"{metric}: campaigns add up to the provider total" if ok
                                                            else f"{metric}: campaigns do not add up to the total"),
                              metric=metric, relative_diff=diff))
    return out


CHECKS = {
    "ratio_bounds": ratio_bounds,
    "ratio_of_sums": ratio_of_sums,
    "metric_vs_provider": metric_vs_provider,
    "metric_availability": metric_availability,
    "no_avg_of_ratios": no_avg_of_ratios,
    "additivity": additivity,
}
