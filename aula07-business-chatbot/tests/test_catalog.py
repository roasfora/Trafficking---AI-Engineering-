import pytest

from tools.catalog import clear_cache, get_dataset_metadata

pytestmark = pytest.mark.usefixtures("pg")
DATASET = "analytics.campaign_performance_daily"


def test_allowed_dataset_has_table_and_column_comments():
    clear_cache()
    result = get_dataset_metadata(DATASET)
    assert result["dataset"] == DATASET
    assert result["description"].startswith("Daily advertising performance per provider and campaign")
    by_name = {c["name"]: c for c in result["columns"]}
    assert list(by_name) == [
        "date", "provider", "campaign_id", "campaign_name", "traffic_source", "country",
        "impressions", "visits", "clicks", "conversions", "cost", "revenue",
    ]
    assert by_name["cost"]["description"].startswith("Cost in EUR")
    assert "NULL" in by_name["revenue"]["description"]  # so o voluum reporta receita


def test_date_column_type_is_date():
    assert {c["name"]: c["type"] for c in get_dataset_metadata(DATASET)["columns"]}["date"] == "date"


def test_unknown_dataset_rejected():
    result = get_dataset_metadata("secret.users")
    assert result["error"] == "Dataset not allowed"
    assert result["allowed_datasets"] == [DATASET]


def test_result_is_cached_and_leaks_no_connection_info():
    clear_cache()
    first = get_dataset_metadata(DATASET)
    assert get_dataset_metadata(DATASET) is first
    text = str(first).lower()
    assert "password" not in text and "postgresql://" not in text
