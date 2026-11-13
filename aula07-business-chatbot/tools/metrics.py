"""Tool 2: get_metric_definition. Le SO o semantic.yaml (sem PostgreSQL, sem LLM)."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

SEMANTIC_PATH = Path(__file__).resolve().parent.parent / "semantic.yaml"


@lru_cache(maxsize=1)
def load_semantic() -> dict[str, Any]:
    return yaml.safe_load(SEMANTIC_PATH.read_text(encoding="utf-8"))


def one_line(text: str) -> str:
    """Os blocos `>` do YAML trazem quebras de linha: o SQL fica numa linha."""
    return " ".join(text.split())


def normalize(text: str) -> str:
    """minusculas, sem acentos, espacos colapsados: 'Gastámos ' -> 'gastamos'."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def resolve_metric(name: str) -> str | None:
    """Nome ou sinonimo -> chave da metrica no semantic.yaml (ou None)."""
    wanted = normalize(name)
    for key, metric in load_semantic()["metrics"].items():
        names = [key, metric.get("label", "")] + metric.get("synonyms", [])
        if wanted in {normalize(n) for n in names}:
            return key
    return None


def get_metric_definition(metric_name: str) -> dict[str, Any]:
    """Return the governed business definition of a metric (SQL expression, unit, rules).

    ALWAYS use this instead of inventing a formula. Accepts the metric name or a
    synonym in Portuguese or English (e.g. 'gastámos', 'taxa de conversão', 'cpc').
    The 'expression' is a PostgreSQL aggregate to use inside a SELECT.
    If the metric is unknown the result lists the available metrics.
    """
    semantic = load_semantic()
    key = resolve_metric(metric_name)
    if key is None:
        return {"error": "Unknown metric", "available_metrics": list(semantic["metrics"])}
    metric = semantic["metrics"][key]
    result = {
        "metric": key,
        "label": metric["label"],
        "description": metric["description"],
        "expression": one_line(metric["expression"]),
        "unit": metric["unit"],
        "dataset": semantic["dataset"],
    }
    if "never" in metric:
        result["never"] = metric["never"]
    return result
