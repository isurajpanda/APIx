"""Unit tests: index computation with hand-calculated expectations."""
import pytest

from index.compute import (
    compute_daily_index, elasticity_curve, laspeyres_index,
    price_relative, rolling_average, route_average, validate_weights,
)


def test_hand_calculated_laspeyres():
    # Two routes: A base 1000 -> 1100 (rel 1.1), B base 2000 -> 2000 (rel 1.0).
    # weights 0.5/0.5 -> Index = 100*(0.5*1.1 + 0.5*1.0) = 105.0
    assert laspeyres_index({"A": 1.1, "B": 1.0}, {"A": 0.5, "B": 0.5}) == pytest.approx(105.0)


def test_missing_route_renormalizes():
    # Only A present: renormalized weight -> 100*1.1 = 110.0
    assert laspeyres_index({"A": 1.1, "B": None}, {"A": 0.5, "B": 0.5}) == pytest.approx(110.0)
    assert laspeyres_index({"A": None}, {"A": 1.0}) is None


def test_price_relative_edge():
    assert price_relative(110.0, 100.0) == pytest.approx(1.1)
    assert price_relative(None, 100.0) is None
    assert price_relative(100.0, 0) is None
    assert route_average([]) is None


def test_compute_daily_index_hand_calc():
    fares = {
        "A": {"2026-08-01": [1000.0], "2026-08-02": [1100.0]},
        "B": {"2026-08-01": [2000.0], "2026-08-02": [2000.0]},
    }
    out = compute_daily_index(fares, ["2026-08-01"], {"A": 0.5, "B": 0.5})
    assert out["2026-08-01"] == pytest.approx(100.0)
    assert out["2026-08-02"] == pytest.approx(105.0)


def test_rolling_average():
    s = {"d1": 100.0, "d2": 110.0, "d3": None, "d4": 120.0}
    r = rolling_average(s, 2)
    assert r["d1"] == pytest.approx(100.0)
    assert r["d2"] == pytest.approx(105.0)
    assert r["d3"] == pytest.approx(110.0)  # None skipped
    assert r["d4"] == pytest.approx(120.0)


def test_elasticity_and_weights():
    assert elasticity_curve({1: [6000.0, 6200.0], 45: []}) == {1: 6100.0, 45: None}
    validate_weights({"A": 0.6, "B": 0.4})
    with pytest.raises(ValueError):
        validate_weights({"A": 0.5, "B": 0.4})
