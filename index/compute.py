"""Index-construction module (Laspeyres-style APIx). Decoupled + unit-testable.

Index(t) = 100 * sum_i weight(i) * avg_fare(i,t) / avg_fare(i, base_period)
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean


def route_average(fares: list[float]) -> float | None:
    """Mean fare for a route-day; None when no priced data (never fabricate)."""
    valid = [f for f in fares if f is not None]
    return mean(valid) if valid else None


def price_relative(avg_t: float | None, avg_base: float | None) -> float | None:
    """Route price relative; None if either leg missing."""
    if avg_t is None or avg_base is None or avg_base == 0:
        return None
    return avg_t / avg_base


def laspeyres_index(relatives: dict[str, float | None], weights: dict[str, float]) -> float | None:
    """Weighted Laspeyres index (x100). Routes with missing relatives are excluded
    and remaining weights renormalized (documented in METHODOLOGY.md)."""
    pairs = [(weights[k], r) for k, r in relatives.items() if r is not None and k in weights]
    if not pairs:
        return None
    wsum = sum(w for w, _ in pairs)
    return 100.0 * sum(w * r for w, r in pairs) / wsum


def compute_daily_index(
    fares_by_route_day: dict[str, dict[str, list[float]]],
    base_dates: list[str],
    weights: dict[str, float],
) -> dict[str, float | None]:
    """Compute index per day given {route: {date: [fares]}} and base-period dates."""
    base_avg = {r: route_average([f for d in base_dates for f in days.get(d, [])]) for r, days in fares_by_route_day.items()}
    all_dates = sorted({d for days in fares_by_route_day.values() for d in days})
    result = {}
    for d in all_dates:
        rels = {r: price_relative(route_average(days.get(d, [])), base_avg[r]) for r, days in fares_by_route_day.items()}
        result[d] = laspeyres_index(rels, weights)
    return result


def rolling_average(series: dict[str, float | None], window: int) -> dict[str, float | None]:
    """N-day rolling mean over a date-sorted index series (7d weekly / 30d monthly)."""
    dates = sorted(series)
    out: dict[str, float | None] = {}
    for i, d in enumerate(dates):
        win = [series[dates[j]] for j in range(max(0, i - window + 1), i + 1)]
        valid = [v for v in win if v is not None]
        out[d] = sum(valid) / len(valid) if valid else None
    return out


def elasticity_curve(fares_by_window: dict[int, list[float]]) -> dict[int, float | None]:
    """Per-window mean fare (T+1..T+45) for the dashboard elasticity view."""
    return {w: (mean(v) if v else None) for w, v in fares_by_window.items()}


def validate_weights(weights: dict[str, float]) -> None:
    """Weights must sum to 1.0 (tolerance 1e-6)."""
    if abs(sum(weights.values()) - 1.0) > 1e-6:
        raise ValueError(f"weights must sum to 1.0, got {sum(weights.values())}")
