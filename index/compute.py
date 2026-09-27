"""Index-construction module (Laspeyres-style APIx). Decoupled + unit-testable.

Index(t) = 100 * sum_i weight(i) * avg_fare(i,t) / avg_fare(i, base_period)
"""
from __future__ import annotations

import logging
from collections import defaultdict
from statistics import mean

logger = logging.getLogger(__name__)


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


def validate_index_value(value: float | None, date: str) -> list[str]:
    """Validate a single index value, returning list of validation errors."""
    errors = []
    if value is None:
        errors.append(f"index value is None for {date}")
    elif value < 0:
        errors.append(f"negative index value {value} for {date}")
    elif value > 1000:
        errors.append(f"suspiciously high index value {value} for {date}")
    elif value < 1:
        errors.append(f"suspiciously low index value {value} for {date}")
    return errors


def decompose_index_change(
    relatives_t: dict[str, float | None],
    relatives_t1: dict[str, float | None],
    weights: dict[str, float],
) -> dict[str, float]:
    """Decompose index change into per-route contributions.

    Returns {route: contribution} where contribution = weight * (rel_t - rel_t1).
    """
    contributions = {}
    for route in weights:
        rt = relatives_t.get(route)
        rt1 = relatives_t1.get(route)
        if rt is not None and rt1 is not None:
            contributions[route] = weights[route] * (rt - rt1)
    return contributions


def attribute_index_change(
    index_t: float,
    index_t1: float,
    relatives_t: dict[str, float | None],
    relatives_t1: dict[str, float | None],
    weights: dict[str, float],
) -> dict[str, Any]:
    """Attribute index change to routes with percentage contributions."""
    total_change = index_t - index_t1
    contributions = decompose_index_change(relatives_t, relatives_t1, weights)
    attribution = {}
    for route, contrib in contributions.items():
        pct = (contrib / total_change * 100) if total_change != 0 else 0
        attribution[route] = {
            "contribution": round(contrib, 4),
            "percentage": round(pct, 2),
        }
    return {
        "total_change": round(total_change, 4),
        "attribution": attribution,
    }


def sensitivity_analysis(
    relatives: dict[str, float | None],
    weights: dict[str, float],
    shock_pct: float = 10.0,
) -> dict[str, float]:
    """Compute index impact of a uniform shock to each route.

    Returns {route: index_impact} showing how much the index would change
    if that route's fares increased by shock_pct.
    """
    base_index = laspeyres_index(relatives, weights)
    if base_index is None:
        return {}
    impacts = {}
    for route in relatives:
        if relatives[route] is None:
            continue
        shocked = dict(relatives)
        shocked[route] = relatives[route] * (1 + shock_pct / 100)
        new_index = laspeyres_index(shocked, weights)
        if new_index is not None:
            impacts[route] = round(new_index - base_index, 4)
    return impacts


def compute_index_quality_metrics(
    series: dict[str, float | None],
    weights: dict[str, float],
) -> dict[str, Any]:
    """Compute quality metrics for the index series."""
    values = [v for v in series.values() if v is not None]
    if not values:
        return {"error": "no valid values"}
    return {
        "count": len(values),
        "mean": round(mean(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "std": round(stdev(values), 4) if len(values) > 1 else 0,
        "coverage": len(values) / len(series) if series else 0,
        "weight_count": len(weights),
    }


def check_index_rebalancing_needed(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    tolerance: float = 0.01,
) -> bool:
    """Check if weights need rebalancing (any route differs by more than tolerance)."""
    for route in set(current_weights) | set(target_weights):
        current = current_weights.get(route, 0)
        target = target_weights.get(route, 0)
        if abs(current - target) > tolerance:
            return True
    return False


def rebalance_weights(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    smoothing: float = 0.1,
) -> dict[str, float]:
    """Smoothly rebalance weights toward target using exponential smoothing."""
    new_weights = {}
    for route in set(current_weights) | set(target_weights):
        current = current_weights.get(route, 0)
        target = target_weights.get(route, 0)
        new_weights[route] = current + smoothing * (target - current)
    total = sum(new_weights.values())
    return {k: v / total for k, v in new_weights.items()}
