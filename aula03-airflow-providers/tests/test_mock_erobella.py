from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from mock_api import datasets
from mock_api.main import app

client = TestClient(app)
DAY = {"start_date": "2026-10-20", "end_date": "2026-10-20"}


@pytest.fixture(autouse=True)
def healthy():
    client.post("/admin/reset")
    yield
    client.post("/admin/reset")


def stats(**params):
    return client.get("/mock/erobella/stats", params={**DAY, **params})


def mode(name, **params):
    assert client.post(f"/admin/erobella/mode/{name}", params=params).status_code == 200


def test_response_has_the_three_parts_and_the_campaign_is_only_in_the_link():
    body = stats().json()
    assert set(body) == {"by_day_creative", "by_creative", "by_day"}
    assert "campaign_id" not in body["by_day_creative"][0]  # o desempenho nao traz campanha
    assert "https://" in body["by_creative"][0]["link"]


def test_links_use_both_formats_and_resolve_to_our_campaigns():
    from providers.erobella import extract_campaign_id
    links = [c["link"] for c in stats().json()["by_creative"]]
    assert any("vcid=" in l for l in links) and any("vcid=" not in l for l in links)
    ours = set(datasets.campaign_ids().values())
    assert {str(extract_campaign_id(l)) for l in links} <= ours


def test_deterministic():
    assert stats().json() == stats().json()


def test_by_day_is_the_sum_of_the_creatives():
    body = stats().json()
    total = sum(Decimal(str(r["cost_eur"])) for r in body["by_day_creative"])
    assert Decimal(str(body["by_day"][0]["cost_eur"])) == total


def test_a_range_returns_one_by_day_entry_per_day():
    body = client.get("/mock/erobella/stats", params={"start_date": "2026-10-20", "end_date": "2026-10-22"}).json()
    assert [d["date"] for d in body["by_day"]] == ["2026-10-20", "2026-10-21", "2026-10-22"]
    assert client.get("/mock/erobella/stats", params={"start_date": "2026-10-20", "end_date": "2026-10-30"}).status_code == 422


def test_faults_are_independent_per_provider():
    client.post("/admin/trafficjunky/mode/http_500")
    assert stats().status_code == 200
    assert client.get("/mock/trafficjunky/health").status_code == 500
    client.post("/admin/reset")
    mode("http_500")
    assert client.get("/mock/trafficjunky/health").status_code == 200
    assert client.get("/mock/erobella/health").status_code == 500


def test_rate_limit_and_timeout(monkeypatch):
    from mock_api import faults
    mode("rate_limit", fail_times=1)
    assert client.get("/mock/erobella/health").status_code == 429
    assert client.get("/mock/erobella/health").status_code == 200
    delays = []

    async def fake_sleep(s):
        delays.append(s)

    monkeypatch.setattr(faults.asyncio, "sleep", fake_sleep)
    mode("timeout")
    client.get("/mock/erobella/health")
    assert delays == []
    stats()
    assert delays == [20.0]


def test_schema_drift_renames_a_consumed_field():
    mode("schema_drift")
    row = stats().json()["by_day_creative"][0]
    assert "spend_eur" in row and "cost_eur" not in row


def test_partial_data_truncates_the_detail_but_not_by_day():
    healthy = stats().json()
    mode("partial_data")
    partial = stats().json()
    assert len(partial["by_day_creative"]) < len(healthy["by_day_creative"])
    assert partial["by_day"] == healthy["by_day"]  # o total de controlo continua correto


def test_dirty_data_adds_a_creative_without_link_and_one_without_uuid():
    mode("dirty_data")
    body = stats().json()
    links = {c["label"]: c["link"] for c in body["by_creative"]}
    assert links[datasets.EROBELLA_NO_LINK] is None
    assert "landing" in links[datasets.EROBELLA_BAD_LINK]
    total = sum(Decimal(str(r["cost_eur"])) for r in body["by_day_creative"])
    assert Decimal(str(body["by_day"][0]["cost_eur"])) == total  # o total INCLUI o custo desses creatives
