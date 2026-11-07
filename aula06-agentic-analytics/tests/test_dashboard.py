import pytest
from pydantic import ValidationError

from dashboard.spec import EXAMPLE_SPEC, DashboardSpec, build_chart_queries
from tools.postgres import execute


def spec(**changes):
    return DashboardSpec.model_validate({**EXAMPLE_SPEC, **changes})


def test_valid_spec():
    assert spec().title == "Provider Performance"


@pytest.mark.parametrize("changes", [
    {"metrics": ["spend", "magic_metric"]},
    {"filters": ["date", "campaign_name"]},                       # filtro fora da allowlist
    {"charts": [{"type": "pie", "metric": "spend", "dimension": "provider"}]},
    {"metrics": ["spend"], "charts": [{"type": "bar", "metric": "spend", "dimension": "salary"}]},
    {"charts": [{"type": "bar", "metric": "roas", "dimension": "provider"}], "metrics": ["spend"]},
    {"date_from": "05/11/2026"},
    {"date_to": "2026-13-45"},
    {"date_from": "2026-11-05", "date_to": "2026-10-01"},
    {"providers": ["trafficjunky", "evil"]},
    {"charts": []},
])
def test_invalid_specs_are_rejected(changes):
    with pytest.raises(ValidationError):
        spec(**changes)


def test_sql_comes_from_semantic_layer_and_values_are_parameters():
    s = spec(providers=["erobella"])
    queries = {c.metric: (sql, params) for c, sql, params in build_chart_queries(s)}
    sql, params = queries["roas"]
    assert "SUM(revenue) / NULLIF(SUM(cost), 0) AS roas" in sql
    assert "erobella" not in sql and "2026" not in sql
    assert params == ("2026-10-30", "2026-11-05", ["erobella"])


def test_injection_in_values_cannot_reach_sql():
    with pytest.raises(ValidationError):
        spec(providers=["x'; DROP TABLE marketing.campaign_performance_daily; --"])


@pytest.mark.usefixtures("pg")
def test_dashboard_queries_run():
    for chart, sql, params in build_chart_queries(spec()):
        columns, rows = execute(sql, params)
        assert columns == [chart.dimension, chart.metric] and rows
