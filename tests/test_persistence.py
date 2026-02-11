import math

import pytest

from core.forecast_models.persistence import PersistenceConfig, PersistenceForecast


def test_requires_nonempty_measured():
    m = PersistenceForecast()
    with pytest.raises(ValueError):
        m.forecast([], horizon=1)


def test_requires_positive_horizon():
    m = PersistenceForecast()
    with pytest.raises(ValueError):
        m.forecast([1, 2], horizon=0)


def test_rejects_nulls_by_default_none():
    m = PersistenceForecast(PersistenceConfig(reject_nulls=True))
    with pytest.raises(ValueError):
        m.forecast([1.0, None], horizon=1)


def test_rejects_nulls_by_default_nan():
    m = PersistenceForecast(PersistenceConfig(reject_nulls=True))
    with pytest.raises(ValueError):
        m.forecast([1.0, float("nan")], horizon=1)


def test_filters_nulls_when_configured():
    m = PersistenceForecast(PersistenceConfig(reject_nulls=False, noise_frac=0.0, connect_last_measured=False))
    y = m.forecast([None, 1.0, float("nan"), 2.0], horizon=2, seed=0)
    assert y == [2.0, 2.0]


def test_persistence_no_noise_connect_true_float():
    m = PersistenceForecast(PersistenceConfig(noise_frac=0.0, connect_last_measured=True))
    y = m.forecast([10.0, 12.5, 13.0], horizon=3)
    assert y == [13.0, 13.0, 13.0, 13.0]


def test_persistence_no_noise_connect_false_float():
    m = PersistenceForecast(PersistenceConfig(noise_frac=0.0, connect_last_measured=False))
    y = m.forecast([10.0, 12.5, 13.0], horizon=3)
    assert y == [13.0, 13.0, 13.0]


def test_preserve_integers_if_series_integer():
    m = PersistenceForecast(PersistenceConfig(noise_frac=0.0, connect_last_measured=True))
    y = m.forecast([10, 11, 12], horizon=2)
    assert y == [12, 12, 12]
    assert all(isinstance(v, int) for v in y)


def test_integer_series_with_noise_stays_integer():
    m = PersistenceForecast(PersistenceConfig(noise_frac=0.2, connect_last_measured=True))
    y = m.forecast([20, 21, 22], horizon=3, seed=123)
    assert all(isinstance(v, int) for v in y)


def test_negative_noise_frac_rejected():
    m = PersistenceForecast(PersistenceConfig(noise_frac=-0.1))
    with pytest.raises(ValueError):
        m.forecast([1.0, 2.0], horizon=1)


def test_forecast_with_pi_shapes_and_order():
    m = PersistenceForecast(PersistenceConfig(noise_frac=0.0, connect_last_measured=True))
    y_hat, lo, hi = m.forecast_with_pi([5.0, 6.0], horizon=4, level=0.9, seed=0)
    assert len(y_hat) == 5  # connect_last_measured adds one
    assert len(lo) == 4
    assert len(hi) == 4
    for a, b in zip(lo, hi):
        assert a <= b


def test_forecast_with_pi_level_validation():
    m = PersistenceForecast()
    with pytest.raises(ValueError):
        m.forecast_with_pi([1.0], horizon=1, level=1.0)
