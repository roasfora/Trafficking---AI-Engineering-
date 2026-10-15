import pytest
from fastapi.testclient import TestClient

from api import faults
from api.main import app
from pipeline.validate import validate_records

client = TestClient(app)
DAY = {"start_date": "2026-10-01", "end_date": "2026-10-02", "limit": 1000}


@pytest.fixture(autouse=True)
def reset_mode():
    faults.STATE.set(faults.Mode.healthy)
    yield
    faults.STATE.set(faults.Mode.healthy)


def set_mode(mode, **params):
    r = client.post(f"/admin/mode/{mode}", params=params)
    assert r.status_code == 200
    return r.json()


def test_default_mode_is_healthy():
    assert client.get("/admin/mode").json()["mode"] == "healthy"


def test_unknown_mode_is_rejected():
    assert client.post("/admin/mode/chaos_monkey").status_code == 422


def test_http_500_breaks_everything_but_admin():
    set_mode("http_500")
    assert client.get("/health").status_code == 500
    assert client.get("/conversions", params=DAY).status_code == 500
    assert client.get("/admin/mode").status_code == 200  # tens de poder curar
    set_mode("healthy")
    assert client.get("/health").status_code == 200


def test_rate_limit_fails_n_times_then_recovers():
    set_mode("rate_limit", fail_times=2)
    r = client.get("/health")
    assert r.status_code == 429 and r.headers["Retry-After"] == "5"
    assert client.get("/health").status_code == 429
    assert client.get("/health").status_code == 200  # recuperou


def test_slow_only_slows_data_endpoints(monkeypatch):
    delays = []

    async def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(faults.asyncio, "sleep", fake_sleep)
    set_mode("slow")
    client.get("/health")
    assert delays == []
    client.get("/conversions", params=DAY)
    assert delays == [20.0]


def test_schema_drift_renames_a_field_and_fails_the_contract():
    set_mode("schema_drift")
    convs = client.get("/conversions", params=DAY).json()["data"]
    costs = client.get("/campaign-costs", params=DAY).json()["data"]
    assert "revenue_amount" in convs[0] and "revenue" not in convs[0]
    assert "cost_amount" in costs[0] and "cost" not in costs[0]
    problems = validate_records("conversions", convs)
    assert problems.pop("__invalid_records__") == len(convs)  # TODOS os registos
    assert ("revenue", "missing") in problems and ("revenue_amount", "extra_forbidden") in problems


def test_invalid_payload_corrupts_some_records():
    set_mode("invalid_payload")
    convs = client.get("/conversions", params=DAY).json()["data"]
    problems = validate_records("conversions", convs)
    invalid = problems.pop("__invalid_records__")
    assert 0 < invalid < len(convs)
    assert {f for f, _ in problems} == {"revenue", "country_code"}
    costs = client.get("/campaign-costs", params=DAY).json()["data"]
    cost_problems = validate_records("campaign_costs", costs)
    cost_problems.pop("__invalid_records__")
    assert {f for f, _ in cost_problems} == {"cost", "clicks"}


def test_dimensions_and_daily_control_are_not_corrupted():
    set_mode("schema_drift")
    assert "currency_code" in client.get("/traffic-sources").json()["data"][0]
    assert "investment" in client.get("/daily-control", params=DAY).json()["data"][0]


def test_healthy_again_after_faults():
    set_mode("schema_drift")
    set_mode("healthy")
    problems = validate_records("conversions", client.get("/conversions", params=DAY).json()["data"])
    assert problems.pop("__invalid_records__") == 0
