from datetime import datetime, timezone

from pipeline.window import resolve_window

UTC = timezone.utc
D = lambda d, h=0: datetime(2026, 10, d, h, tzinfo=UTC)  # noqa: E731


def test_scheduled_run_uses_its_data_interval():
    assert resolve_window(D(3), D(4), D(4), None) == (D(3).isoformat(), D(4).isoformat())


def test_manual_run_without_interval_processes_yesterday():
    assert resolve_window(None, None, D(11, 14), {}) == (D(10).isoformat(), D(11).isoformat())


def test_conf_date_overrides_everything():
    assert resolve_window(D(3), D(4), D(4), {"date": "2026-10-07"}) == (D(7).isoformat(), D(8).isoformat())
    assert resolve_window(None, None, D(11), {"date": "2026-10-07"}) == (D(7).isoformat(), D(8).isoformat())
