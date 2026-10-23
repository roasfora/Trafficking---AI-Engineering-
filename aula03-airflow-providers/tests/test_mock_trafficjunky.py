from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from mock_api import datasets, faults
from mock_api.main import app

client = TestClient(app)
DAY = {"startDate": "20/10/2026", "endDate": "20/10/2026"}
TJ = "trafficjunky"


@pytest.fixture(autouse=True)
def healthy():
    client.post("/admin/reset")
    yield
    client.post("/admin/reset")


def mode(provider, name, **params):
    assert client.post(f"/admin/{provider}/mode/{name}", params=params).status_code == 200


def stats(**params):
    return client.get("/mock/trafficjunky/stats", params={**DAY, "limit": 1000, **params})


def test_campaign_names_come_from_the_shared_csv():
    names = datasets.campaign_ids()
    assert all(n in names for n in datasets.TJ_NAMES) and datasets.TJ_UNMAPPED not in names


def test_deterministic():
    assert stats().json() == stats().json()
    assert stats().json() != client.get("/mock/trafficjunky/stats",
                                        params={"startDate": "21/10/2026", "endDate": "21/10/2026"}).json()


def test_dataset_has_the_cases_the_lesson_needs():
    rows = stats().json()["data"]
    assert any(r["campaign_type"] == "deal" for r in rows)  # a ignorar
    names = [r["campaign_name"] for r in rows if r["campaign_type"] != "deal"]
    assert len(names) != len(set(names))  # nomes duplicados (a agregar)
    assert set(names) <= set(datasets.campaign_ids())  # todos mapeaveis (healthy)


def test_paginates_with_limit_and_offset():
    full = stats().json()
    p1 = stats(limit=5, offset=0).json()
    p2 = stats(limit=5, offset=5).json()
    assert full["total"] == p1["total"] == p2["total"] == 7
    assert p1["data"] + p2["data"] == full["data"]


def test_provider_reported_ratios_differ_from_recomputed_ones():
    r = next(r for r in stats().json()["data"] if r["campaign_type"] != "deal")
    assert Decimal(str(r["ecpc"])) != Decimal(str(r["cost"])) / r["clicks"]  # arredondado a 2 casas


def test_date_format_is_dd_mm_yyyy():
    assert client.get("/mock/trafficjunky/stats", params={"startDate": "2026-10-20", "endDate": "2026-10-20"}).status_code == 422
    assert client.get("/mock/trafficjunky/stats", params={"startDate": "20/10/2026", "endDate": "21/10/2026"}).status_code == 422


def test_total_is_the_sum_of_non_deal_costs():
    rows = stats().json()["data"]
    expected = sum(Decimal(str(r["cost"])) for r in rows if r["campaign_type"] != "deal")
    total = client.get("/mock/trafficjunky/total", params={"date": "2026-10-20"}).json()
    assert Decimal(str(total["total_cost"])) == expected and total["currency"] == "EUR"


def test_http_500_breaks_every_trafficjunky_endpoint_but_not_admin():
    mode(TJ, "http_500")
    for path in ("/mock/trafficjunky/health", "/mock/trafficjunky/total?date=2026-10-20"):
        assert client.get(path).status_code == 500
    assert stats().status_code == 500
    assert client.get("/admin/state").status_code == 200


def test_rate_limit_fails_n_times_then_recovers():
    mode(TJ, "rate_limit", fail_times=2)
    r = client.get("/mock/trafficjunky/health")
    assert r.status_code == 429 and r.headers["Retry-After"] == "5"
    assert client.get("/mock/trafficjunky/health").status_code == 429
    assert client.get("/mock/trafficjunky/health").status_code == 200


def test_timeout_only_slows_data_endpoints(monkeypatch):
    delays = []

    async def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(faults.asyncio, "sleep", fake_sleep)
    mode(TJ, "timeout")
    client.get("/mock/trafficjunky/health")
    assert delays == []
    stats()
    assert delays == [20.0]


def test_schema_drift_renames_a_consumed_field():
    mode(TJ, "schema_drift")
    row = stats().json()["data"][0]
    assert "spend" in row and "cost" not in row


def test_partial_data_truncates_the_detail_but_not_the_control_total():
    healthy_rows = stats().json()
    healthy_total = client.get("/mock/trafficjunky/total", params={"date": "2026-10-20"}).json()
    mode(TJ, "partial_data")
    partial = stats().json()
    assert partial["total"] < healthy_rows["total"]  # detalhe incompleto...
    assert partial["total"] == len(partial["data"])  # ...mas internamente coerente (paginacao nao o apanha)
    assert client.get("/mock/trafficjunky/total", params={"date": "2026-10-20"}).json() == healthy_total


def test_dirty_data_adds_an_unmappable_campaign_and_counts_it_in_the_total():
    healthy_total = client.get("/mock/trafficjunky/total", params={"date": "2026-10-20"}).json()["total_cost"]
    mode(TJ, "dirty_data")
    names = [r["campaign_name"] for r in stats().json()["data"]]
    assert datasets.TJ_UNMAPPED in names
    assert client.get("/mock/trafficjunky/total", params={"date": "2026-10-20"}).json()["total_cost"] > healthy_total


def test_unknown_mode_and_provider_are_rejected():
    assert client.post("/admin/trafficjunky/mode/chaos").status_code == 422
    assert client.post("/admin/google/mode/healthy").status_code == 422


def test_reset_heals_everything():
    mode(TJ, "http_500")
    client.post("/admin/reset")
    assert client.get("/admin/state").json()[TJ]["mode"] == "healthy"
