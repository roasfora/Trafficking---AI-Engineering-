import pytest

from tools.metrics import get_metric_definition, normalize


@pytest.mark.parametrize("text,metric", [
    ("gastámos", "spend"),
    ("  GASTÁMOS ", "spend"),  # maiusculas e espacos
    ("investimento", "spend"),
    ("taxa de conversão", "conversion_rate"),
    ("Taxa  de   conversao", "conversion_rate"),
    ("CR", "conversion_rate"),
    ("cpc", "cpc"),
])
def test_synonyms_resolve(text, metric):
    assert get_metric_definition(text)["metric"] == metric


def test_accents_are_optional():
    assert get_metric_definition("gastamos")["metric"] == "spend"


def test_definition_shape():
    result = get_metric_definition("spend")
    assert result == {
        "metric": "spend",
        "label": "Spend",
        "description": "Total advertising spend.",
        "expression": "SUM(cost)",
        "unit": "EUR",
        "dataset": "marketing.campaign_performance_daily",
    }


def test_cpc_is_ratio_of_sums_and_has_never_list():
    result = get_metric_definition("cpc")
    assert result["expression"] == "SUM(cost) / NULLIF(SUM(clicks), 0)"
    assert "AVG(cost / clicks)" in result["never"]


def test_unknown_metric_lists_available():
    result = get_metric_definition("margem de lucro")
    assert result["error"] == "Unknown metric"
    assert "spend" in result["available_metrics"]


def test_normalize():
    assert normalize("  Taxa  de CONVERSÃO ") == "taxa de conversao"
