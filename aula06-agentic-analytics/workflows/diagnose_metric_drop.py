"""Workflow controlado: porque e que uma metrica de taxa mudou?

NAO e um agente: os passos estao fixos no codigo, o SQL e de templates nossos e o
LLM, se for usado, so redige a explicacao no fim (0 ou 1 chamada, nunca um ciclo).

Passos
    1. resolver a metrica (semantic.yaml)
    2. comparar o periodo com o anterior; se nao mudou, parar
    3. decompor por provider e calcular a contribuicao de cada um
    4. escolher o provider que mais explica a mudanca
    5. decompor as campanhas desse provider
    6. (opcional) pedir ao LLM que explique os numeros

Metodo de contribuicao (para taxas = numerador / denominador, ex.: CR = conversoes / cliques)
    taxa_total = soma_i( peso_i * taxa_i ),  peso_i = denominador_i / denominador_total
    contribuicao_i = peso_atual_i * taxa_atual_i  -  peso_anterior_i * taxa_anterior_i
    As contribuicoes SOMAM EXATAMENTE a variacao da taxa total (em pontos percentuais).
    Cada uma divide-se em:
        efeito taxa = peso_atual_i * (taxa_atual_i - taxa_anterior_i)   o segmento converteu pior/melhor
        efeito mix  = (peso_atual_i - peso_anterior_i) * taxa_anterior_i   o segmento ganhou/perdeu trafego
    Assim um segmento pequeno com uma queda enorme nao ganha por "maior queda %":
    conta o peso que tem. Para campanhas usamos o peso face ao TOTAL, logo as
    contribuicoes das campanhas de um provider somam a contribuicao desse provider.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from config import Settings, get_settings
from tools.metrics import load_semantic, resolve_metric
from tools.postgres import execute

NO_CHANGE_PP = 0.05  # abaixo disto (pontos percentuais) nao ha o que diagnosticar


def diagnose_metric_drop(metric_name: str, day: date, period_days: int = 1, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    semantic = load_semantic()

    # 1. resolver a metrica; so metricas de taxa com drilldowns declarados
    key = resolve_metric(metric_name)
    supported = [k for k, m in semantic["metrics"].items() if "numerator" in m and "drilldowns" in m]
    if key not in supported:
        return {"error": f"Metric not supported by this workflow: {metric_name}", "supported_metrics": supported}
    metric = semantic["metrics"][key]
    provider_dim, campaign_dim = metric["drilldowns"]  # provider -> campaign_name

    current = (day - timedelta(days=period_days - 1), day)
    previous = (current[0] - timedelta(days=period_days), current[0] - timedelta(days=1))

    # 2. confirmar a mudanca
    total_now, total_before = _rate(settings, metric, None, current), _rate(settings, metric, None, previous)
    change = round(total_now[2] - total_before[2], 2)
    result: dict[str, Any] = {
        "metric": key,
        "unit": metric["unit"],
        "current_period": [d.isoformat() for d in current],
        "previous_period": [d.isoformat() for d in previous],
        "previous_value": round(total_before[2], 2),
        "current_value": round(total_now[2], 2),
        "change_pp": change,
        "direction": "drop" if change < 0 else "rise",
        "providers": [],
        "top_provider": None,
        "campaigns": [],
    }
    if abs(change) < NO_CHANGE_PP:
        result["direction"] = "no_change"
        return result

    # 3-4. provider: contribuicao e escolha do que mais explica a mudanca
    result["providers"] = _contributions(settings, metric, provider_dim, None, current, previous, total_now[1], total_before[1])
    pick = min if change < 0 else max
    top = pick(result["providers"], key=lambda s: s["contribution_pp"])
    result["top_provider"] = top["segment"]

    # 5. campanhas do provider escolhido (pesos face ao total geral)
    result["campaigns"] = _contributions(
        settings, metric, campaign_dim, top["segment"], current, previous, total_now[1], total_before[1]
    )
    return result


def _rate(settings, metric, provider, period) -> tuple[float, float, float]:
    """(numerador, denominador, taxa em %) do periodo. Template fixo, valores em parametros."""
    where, params = _where(provider, period)
    sql = (
        f"SELECT {metric['numerator']}, {metric['denominator']} "
        f"FROM {load_semantic()['dataset']} WHERE {where}"
    )
    _, rows = execute(sql, params, settings)
    n, d = float(rows[0][0] or 0), float(rows[0][1] or 0)
    return n, d, (100.0 * n / d if d else 0.0)


def _where(provider: str | None, period: tuple[date, date]) -> tuple[str, tuple]:
    where, params = "date BETWEEN %s AND %s", (period[0], period[1])
    if provider is not None:
        where, params = where + " AND provider = %s", params + (provider,)
    return where, params


def _segments(settings, metric, dimension, provider, period) -> dict[str, tuple[float, float]]:
    # `dimension` vem de metric["drilldowns"] no semantic.yaml, nunca do utilizador nem do LLM.
    where, params = _where(provider, period)
    sql = (
        f"SELECT {dimension}, {metric['numerator']}, {metric['denominator']} "
        f"FROM {load_semantic()['dataset']} WHERE {where} GROUP BY 1"
    )
    _, rows = execute(sql, params, settings)
    return {r[0]: (float(r[1]), float(r[2])) for r in rows}


def _contributions(settings, metric, dimension, provider, current, previous, den_now, den_before) -> list[dict]:
    now = _segments(settings, metric, dimension, provider, current)
    before = _segments(settings, metric, dimension, provider, previous)
    out = []
    for segment in sorted(set(now) | set(before)):
        n1, d1 = now.get(segment, (0.0, 0.0))
        n0, d0 = before.get(segment, (0.0, 0.0))
        r1 = 100.0 * n1 / d1 if d1 else 0.0
        r0 = 100.0 * n0 / d0 if d0 else 0.0
        w1, w0 = d1 / den_now, d0 / den_before
        out.append({
            "segment": segment,
            "previous_value": round(r0, 2),
            "current_value": round(r1, 2),
            "weight_current": round(w1, 4),
            "contribution_pp": round(w1 * r1 - w0 * r0, 3),
            "rate_effect_pp": round(w1 * (r1 - r0), 3),
            "mix_effect_pp": round((w1 - w0) * r0, 3),
        })
    return sorted(out, key=lambda s: s["contribution_pp"])


def format_report(result: dict[str, Any]) -> str:
    if "error" in result:
        return f"{result['error']}\nSuportadas: {', '.join(result['supported_metrics'])}"
    lines = [
        f"{result['metric']} {result['previous_period'][1]} -> {result['current_period'][1]}: "
        f"{result['previous_value']}{result['unit']} -> {result['current_value']}{result['unit']} "
        f"({result['change_pp']:+.2f} pp)"
    ]
    if result["direction"] == "no_change":
        return lines[0] + "\nSem variacao relevante: nada a diagnosticar."
    for title, rows in (("Por provider", result["providers"]), (f"Campanhas de {result['top_provider']}", result["campaigns"])):
        lines += ["", title + "  (contribuicao em pp = efeito taxa + efeito mix)"]
        for s in rows:
            lines.append(
                f"  {s['segment']:<26} {s['previous_value']:>6.2f} -> {s['current_value']:>6.2f}   "
                f"contribuicao {s['contribution_pp']:+.3f} pp  (taxa {s['rate_effect_pp']:+.3f}, mix {s['mix_effect_pp']:+.3f})"
            )
    return "\n".join(lines)


def explain(result: dict[str, Any], settings: Settings | None = None, llm: Any = None) -> str:
    """Passo opcional: UMA chamada ao LLM, sem tools, so a redigir os numeros ja calculados."""
    from providers import get_llm

    settings = settings or get_settings()
    llm = llm or get_llm(settings.llm_provider, settings.model_name, settings)
    prompt = (
        "Explica em portugues, em 3 frases, porque mudou a metrica. Usa APENAS os numeros "
        "abaixo (contribuicao em pontos percentuais), sem inventar causas.\n\n" + format_report(result)
    )
    return llm.invoke(prompt).content
