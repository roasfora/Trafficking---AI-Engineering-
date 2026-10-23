from decimal import Decimal

import pytest

from pipeline.config import get_settings
from pipeline.window import resolve_day
from datetime import date, datetime, timezone

UTC = timezone.utc


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        get_settings()


def test_mock_mode_points_every_provider_to_the_mock_api(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("USE_MOCK_API", "true")
    monkeypatch.setenv("MOCK_API_BASE_URL", "http://mock:8000/")
    s = get_settings()
    assert s.use_mock_api
    assert s.trafficjunky.base_url == s.erobella.base_url == "http://mock:8000"
    assert s.trafficjunky.stats_path == "/mock/trafficjunky/stats"
    assert s.erobella.stats_path == "/mock/erobella/stats"
    assert s.trafficjunky.token is None  # a mock nao precisa de token


def test_real_mode_uses_urls_and_tokens_from_the_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("USE_MOCK_API", "false")
    monkeypatch.setenv("TRAFFICJUNKY_BASE_URL", "https://tj.example/")
    monkeypatch.setenv("TRAFFICJUNKY_BEARER_TOKEN", "tok-tj")
    monkeypatch.setenv("EROBELLA_BASE_URL", "https://eb.example")
    monkeypatch.setenv("EROBELLA_API_TOKEN", "tok-eb")
    s = get_settings()
    assert not s.use_mock_api
    assert (s.trafficjunky.base_url, s.trafficjunky.token) == ("https://tj.example", "tok-tj")
    assert (s.erobella.base_url, s.erobella.token) == ("https://eb.example", "tok-eb")
    assert s.erobella.stats_path == "/api/v1/stats"


def test_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    for var in ("USE_MOCK_API", "RECONCILE_TOLERANCE", "PIPELINE_PAGE_SIZE"):
        monkeypatch.delenv(var, raising=False)
    s = get_settings()
    assert s.use_mock_api and s.reconcile_tolerance == Decimal("0.01") and s.page_size == 5
    assert s.trafficjunky.currency == s.erobella.currency == "EUR"


def test_resolve_day():
    assert resolve_day(datetime(2026, 10, 3, tzinfo=UTC), datetime(2026, 10, 4, tzinfo=UTC), None) == date(2026, 10, 3)
    assert resolve_day(None, datetime(2026, 10, 11, 14, tzinfo=UTC), {}) == date(2026, 10, 10)
    assert resolve_day(datetime(2026, 10, 3, tzinfo=UTC), datetime(2026, 10, 4, tzinfo=UTC), {"date": "2026-10-07"}) == date(2026, 10, 7)
