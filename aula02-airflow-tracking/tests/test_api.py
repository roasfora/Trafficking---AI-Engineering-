from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)
DAY = {"start_date": "2026-10-01", "end_date": "2026-10-02"}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_dimension_endpoints_use_the_envelope():
    for path, n in [("/workspaces", 2), ("/traffic-sources", 6), ("/campaigns", 8), ("/offers", 7)]:
        body = client.get(path).json()
        assert body["total"] == n and body["count"] == n
        assert set(body) == {"data", "count", "total", "limit", "offset"}


def test_optional_fields_can_be_null():
    offers = client.get("/offers").json()["data"]
    assert any(o["country_code"] is None for o in offers)


def test_fact_endpoints_return_data():
    for path in ("/conversions", "/campaign-costs", "/daily-control"):
        body = client.get(path, params={**DAY, "limit": 1000}).json()
        assert body["total"] > 0 and body["count"] == body["total"]


def test_pagination_covers_everything_without_overlap():
    full = client.get("/campaign-costs", params={**DAY, "limit": 1000}).json()
    assert full["total"] > 100
    page1 = client.get("/campaign-costs", params={**DAY, "limit": 100, "offset": 0}).json()
    page2 = client.get("/campaign-costs", params={**DAY, "limit": 100, "offset": 100}).json()
    assert page1["count"] == 100 and page1["total"] == full["total"]
    assert page1["data"] + page2["data"] == full["data"][:200]


def test_deterministic_across_calls():
    a = client.get("/conversions", params={**DAY, "limit": 50}).json()
    assert a == client.get("/conversions", params={**DAY, "limit": 50}).json()


def test_filters():
    camp = client.get("/campaigns").json()["data"][0]["campaign_id"]
    r = client.get("/conversions", params={**DAY, "campaign_id": camp, "limit": 1000}).json()
    assert r["total"] > 0 and all(c["campaign_id"] == camp for c in r["data"])
    r = client.get("/conversions", params={**DAY, "traffic_source_id": "nao-existe"}).json()
    assert r["total"] == 0 and r["data"] == []


def test_end_date_is_exclusive():
    r = client.get(
        "/campaign-costs",
        params={"start_date": "2026-10-01T00:00:00", "end_date": "2026-10-01T06:00:00", "limit": 1000},
    ).json()
    assert r["total"] > 0
    assert all(c["datetime"] < "2026-10-01T06:00:00" for c in r["data"])


def test_bad_requests_are_422():
    assert client.get("/conversions", params={"start_date": "2026-10-02", "end_date": "2026-10-01"}).status_code == 422
    assert client.get("/conversions", params={"start_date": "2026-01-01", "end_date": "2026-06-01"}).status_code == 422
    assert client.get("/conversions", params={"limit": 0}).status_code == 422
    assert client.get("/conversions", params={"limit": 5000}).status_code == 422
