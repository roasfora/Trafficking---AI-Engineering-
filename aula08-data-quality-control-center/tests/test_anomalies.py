"""Anomalias simples (sem ML). Anomalia != erro: significa 'investigar'."""

import pytest

from quality.anomalies import (is_iqr_outlier, iqr_bounds, percentage_change, rolling_mean_change, rolling_std,
                               z_score)


def test_percentage_change():
    assert percentage_change(50, 100) == pytest.approx(-0.5)
    assert percentage_change(150, 100) == pytest.approx(0.5)
    assert percentage_change(10, 0) is None


def test_rolling_mean_change_main_example_trafficjunky_spend_drop():
    history = [1250, 1270, 1240, 1280, 1255, 1265, 1262]   # media ~ 1260
    change, baseline = rolling_mean_change(history + [320], lookback=7)
    assert baseline == pytest.approx(1260, rel=0.01)
    assert change == pytest.approx(-0.746, abs=0.01)        # ~ -74%


def test_rolling_mean_uses_only_the_lookback_window():
    change, baseline = rolling_mean_change([1000] * 10 + [10, 10, 10, 10, 10, 10, 10, 100], lookback=7)
    assert baseline == 10 and change == pytest.approx(9.0)


def test_rolling_mean_needs_history():
    assert rolling_mean_change([5]) == (None, None)


def test_rolling_std_and_z_score():
    values = [10, 12, 11, 13, 12]
    assert rolling_std(values + [99]) > 0
    assert z_score(40, values) > 10
    assert z_score(12, [5, 5, 5]) is None   # historico sem variacao


def test_iqr_flags_outliers_only():
    history = [100, 102, 98, 101, 99, 103, 97]
    assert not is_iqr_outlier(101, history)
    assert is_iqr_outlier(300, history)
    low, high = iqr_bounds(history)
    assert low < 97 and high > 103
