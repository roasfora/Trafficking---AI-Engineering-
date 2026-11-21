"""Deteccao de anomalias SIMPLES (sem ML). Uma anomalia nao e um erro: significa "vai investigar"."""

from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Sequence


def percentage_change(current: float, baseline: float) -> float | None:
    """Variacao relativa (fracao: -0.74 = -74%). None se a base for 0."""
    if baseline == 0:
        return None
    return (current - baseline) / abs(baseline)


def rolling_mean_change(values: Sequence[float], lookback: int = 7) -> tuple[float | None, float | None]:
    """Compara o ULTIMO valor com a media dos `lookback` anteriores. Devolve (variacao, media)."""
    if len(values) < 2:
        return None, None
    history = list(values[:-1])[-lookback:]
    baseline = mean(history)
    return percentage_change(values[-1], baseline), baseline


def rolling_std(values: Sequence[float], lookback: int = 7) -> float:
    history = list(values[:-1])[-lookback:]
    return pstdev(history) if len(history) > 1 else 0.0


def z_score(value: float, history: Sequence[float]) -> float | None:
    """Quantos desvios-padrao `value` esta da media do historico. None se o historico nao varia."""
    if len(history) < 2:
        return None
    sd = pstdev(history)
    return None if sd == 0 else (value - mean(history)) / sd


def iqr_bounds(history: Sequence[float], k: float = 1.5) -> tuple[float, float]:
    """Limites de Tukey: [Q1 - k*IQR, Q3 + k*IQR]."""
    data = sorted(history)
    q1, q3 = _quantile(data, 0.25), _quantile(data, 0.75)
    iqr = q3 - q1
    return q1 - k * iqr, q3 + k * iqr


def is_iqr_outlier(value: float, history: Sequence[float], k: float = 1.5) -> bool:
    low, high = iqr_bounds(history, k)
    return value < low or value > high


def _quantile(sorted_data: Sequence[float], q: float) -> float:
    if not sorted_data:
        return math.nan
    pos = (len(sorted_data) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (pos - lo)
