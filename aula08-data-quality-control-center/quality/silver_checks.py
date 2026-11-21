"""Checks da SILVER. Pergunta: "os dados normalizados fazem sentido?"

A Silver e onde os dados sao interpretados (EUR, nomes canonicos, grain). Aqui verificam-se
a forma (nulos, tipos, valores permitidos) e as invariantes de negocio (clicks <= impressions...).
"""

from __future__ import annotations

import re

from quality.anomalies import rolling_mean_change
from quality.context import CheckContext
from quality.models import CheckResult, status_from_abs_pct

ISO2 = re.compile(r"^[A-Z]{2}$")


def _count_result(spec, ctx, total, bad, what, sample=None, **extra):
    """Resultado para checks do tipo "N linhas violam uma regra": taxa de violacao vs limites do yaml."""
    rate = bad / total if total else 0.0
    warn, fail = spec.get("warn_pct", 0), spec.get("fail_pct", 0)
    status = status_from_abs_pct(rate * 100, warn, fail) if bad else "PASS"
    msg = f"{bad} of {total} rows {what}" if bad else f"no rows {what}"
    return [ctx.result(spec, status, observed=bad, expected=0, threshold=warn / 100 if warn is not None else None,
                       message=msg, violation_rate=round(rate, 4), sample=(sample or [])[:5], **extra)]


def _ident(r):
    return {"date": str(r["date"]), "campaign_id": r["campaign_id"]}


def not_null(spec, ctx):
    rows = ctx.silver_rows
    bad = [r for r in rows if any(r.get(c) is None for c in spec["columns"])]
    nulls = {c: sum(1 for r in rows if r.get(c) is None) for c in spec["columns"]}
    with_nulls = ", ".join(f"{c} ({n})" for c, n in nulls.items() if n) or "none"
    return _count_result(spec, ctx, len(rows), len(bad), f"have NULL in: {with_nulls}",
                         [_ident(r) for r in bad], null_counts=nulls)


def min_value(spec, ctx):
    rows, minimum = ctx.silver_rows, spec.get("min", 0)
    bad = [r for r in rows if any(r.get(c) is not None and r[c] < minimum for c in spec["columns"])]
    return _count_result(spec, ctx, len(rows), len(bad), f"below {minimum} in {spec['columns']}", [_ident(r) for r in bad])


def allowed_values(spec, ctx):
    rows, col, allowed = ctx.silver_rows, spec["column"], set(spec["allowed"])
    bad = [r for r in rows if r.get(col) not in allowed]
    return _count_result(spec, ctx, len(rows), len(bad), f"have {col} outside {sorted(allowed)}", [_ident(r) for r in bad])


def unique_grain(spec, ctx):
    keys = spec["keys"]
    seen: dict[tuple, int] = {}
    for r in ctx.silver_rows:
        k = tuple(str(r.get(c)) for c in keys)
        seen[k] = seen.get(k, 0) + 1
    dups = {k: n for k, n in seen.items() if n > 1}
    extra = sum(n - 1 for n in dups.values())
    sample = [dict(zip(keys, k), times=n) for k, n in list(dups.items())[:5]]
    return [ctx.result(spec, "FAIL" if extra else "PASS", observed=extra, expected=0, threshold=0,
                       message=(f"{extra} row(s) break the grain {keys}" if extra else f"grain {keys} is unique"),
                       duplicates=sample)]


def country_iso2(spec, ctx):
    rows = ctx.silver_rows
    bad = [r for r in rows if r.get("country") is not None and not ISO2.match(str(r["country"]))]
    return _count_result(spec, ctx, len(rows), len(bad), "have a country that is not ISO-3166 alpha-2", [_ident(r) for r in bad])


def currency_is_eur(spec, ctx):
    rows = ctx.silver_rows
    bad = [r for r in rows if r.get("currency") != "EUR"]
    return _count_result(spec, ctx, len(rows), len(bad), "are not in EUR", [_ident(r) for r in bad])


def clicks_le_impressions(spec, ctx):
    rows = ctx.silver_rows
    bad = [r for r in rows if r["clicks"] is not None and r["impressions"] is not None and r["clicks"] > r["impressions"]]
    return _count_result(spec, ctx, len(rows), len(bad), "have more clicks than impressions", [_ident(r) for r in bad])


def conversions_le_clicks(spec, ctx):
    rows = ctx.silver_rows
    bad = [r for r in rows if r["conversions"] is not None and r["clicks"] is not None and r["conversions"] > r["clicks"]]
    return _count_result(spec, ctx, len(rows), len(bad), "have more conversions than clicks", [_ident(r) for r in bad])


def revenue_without_conversions(spec, ctx):
    rows = ctx.silver_rows
    bad = [r for r in rows if (r["revenue"] or 0) > 0 and r["conversions"] == 0]
    return _count_result(spec, ctx, len(rows), len(bad), "have revenue > 0 with 0 conversions",
                         [dict(_ident(r), revenue=r["revenue"]) for r in bad])


def cost_without_impressions(spec, ctx):
    rows = ctx.silver_rows
    bad = [r for r in rows if (r["cost"] or 0) > 0 and r["impressions"] == 0]
    return _count_result(spec, ctx, len(rows), len(bad), "have cost > 0 with 0 impressions", [_ident(r) for r in bad])


def known_campaign(spec, ctx):
    rows = ctx.silver_rows
    known = ctx.known_campaigns
    bad = [r for r in rows if r["campaign_id"] not in known]
    return _count_result(spec, ctx, len(rows), len(bad), "belong to a campaign missing from analytics.campaigns",
                         [_ident(r) for r in bad])


def rolling_avg_change(spec, ctx):
    """Anomalia: o ultimo dia vs a media dos `lookback_days` anteriores (totais do provider). Anomalia != erro."""
    metric = spec["metric"]
    per_day: dict = {}
    for r in ctx.silver_rows:
        if r.get(metric) is not None:
            per_day[r["date"]] = per_day.get(r["date"], 0.0) + r[metric]
    days = sorted(per_day)
    if len(days) < 2:
        return [ctx.result(spec, "FAIL", message="not enough history for a rolling average", days=len(days))]
    change, baseline = rolling_mean_change([per_day[d] for d in days], int(spec.get("lookback_days", 7)))
    latest = per_day[days[-1]]
    if change is None:
        return [ctx.result(spec, "PASS", observed=latest, message="baseline is 0: nothing to compare")]
    warn, fail = spec.get("warn_pct"), spec.get("fail_pct")
    status = status_from_abs_pct(abs(change) * 100, warn, fail)
    direction = "drop" if change < 0 else "rise"
    return [ctx.result(spec, status, observed=change, expected=baseline,
                       threshold=-(warn or 0) / 100 if change < 0 else (warn or 0) / 100,
                       message=(f"{provider_label(ctx)} {metric} on {days[-1]} is {latest:.0f} vs 7-day avg "
                                f"{baseline:.0f} ({change:+.0%}): {direction} worth investigating"),
                       latest_day=str(days[-1]), latest_value=round(latest, 2), baseline_avg=round(baseline, 2),
                       change_pct=round(change * 100, 1))]


def provider_label(ctx: CheckContext) -> str:
    return ctx.provider


CHECKS = {
    "not_null": not_null,
    "min_value": min_value,
    "allowed_values": allowed_values,
    "unique_grain": unique_grain,
    "country_iso2": country_iso2,
    "currency_is_eur": currency_is_eur,
    "clicks_le_impressions": clicks_le_impressions,
    "conversions_le_clicks": conversions_le_clicks,
    "revenue_without_conversions": revenue_without_conversions,
    "cost_without_impressions": cost_without_impressions,
    "known_campaign": known_campaign,
    "rolling_avg_change": rolling_avg_change,
}
