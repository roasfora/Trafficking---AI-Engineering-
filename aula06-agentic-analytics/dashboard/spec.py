"""DashboardSpec: o contrato Pydantic entre "o que o utilizador (ou o LLM) pede" e o SQL.

O LLM pode PROPOR uma spec em JSON. Nunca escreve SQL: o SQL sai daqui, de forma
deterministica, das expressoes do semantic.yaml. Spec invalida = erro de validacao.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from tools.metrics import load_semantic, one_line

Filter = Literal["date", "provider"]
ChartType = Literal["line", "bar", "table"]


class Chart(BaseModel):
    type: ChartType
    metric: str
    dimension: str


class DashboardSpec(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    filters: list[Filter] = []
    metrics: list[str] = Field(min_length=1)
    charts: list[Chart] = Field(min_length=1)
    date_from: str | None = None  # ISO, ex.: 2026-10-30
    date_to: str | None = None
    providers: list[str] | None = None

    @field_validator("date_from", "date_to")
    @classmethod
    def _iso_date(cls, value: str | None) -> str | None:
        if value is not None:
            date.fromisoformat(value)  # ValueError -> erro de validacao
        return value

    @field_validator("metrics")
    @classmethod
    def _known_metrics(cls, values: list[str]) -> list[str]:
        known = load_semantic()["metrics"]
        unknown = [m for m in values if m not in known]
        if unknown:
            raise ValueError(f"unknown metrics {unknown}; available: {list(known)}")
        return values

    @field_validator("providers")
    @classmethod
    def _known_providers(cls, values: list[str] | None) -> list[str] | None:
        allowed = load_semantic()["dimensions"]["provider"]["values"]
        if values is not None and not set(values) <= set(allowed):
            raise ValueError(f"unknown providers; allowed: {allowed}")
        return values

    @model_validator(mode="after")
    def _charts_consistent(self) -> "DashboardSpec":
        dimensions = load_semantic()["dimensions"]
        for chart in self.charts:
            if chart.metric not in self.metrics:
                raise ValueError(f"chart metric '{chart.metric}' is not in metrics")
            if chart.dimension not in dimensions:
                raise ValueError(f"unknown dimension '{chart.dimension}'; available: {list(dimensions)}")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from is after date_to")
        return self


def build_chart_queries(spec: DashboardSpec) -> list[tuple[Chart, str, tuple]]:
    """SQL de cada grafico, montado so com expressoes do semantic.yaml (valores em parametros)."""
    semantic = load_semantic()
    conditions, params = [], []
    if spec.date_from:
        conditions.append("date >= %s")
        params.append(spec.date_from)
    if spec.date_to:
        conditions.append("date <= %s")
        params.append(spec.date_to)
    if spec.providers:
        conditions.append("provider = ANY(%s)")
        params.append(spec.providers)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    queries = []
    for chart in spec.charts:
        expression = one_line(semantic["metrics"][chart.metric]["expression"])
        sql = (
            f"SELECT {chart.dimension}, {expression} AS {chart.metric} "
            f"FROM {semantic['dataset']}{where} GROUP BY 1 ORDER BY 1"
        )
        queries.append((chart, sql, tuple(params)))
    return queries


EXAMPLE_SPEC = {
    "title": "Provider Performance",
    "filters": ["date", "provider"],
    "metrics": ["spend", "cpc", "conversion_rate", "roas"],
    "charts": [
        {"type": "line", "metric": "conversion_rate", "dimension": "date"},
        {"type": "bar", "metric": "roas", "dimension": "provider"},
    ],
    "date_from": "2026-10-30",
    "date_to": "2026-11-05",
}
