"""Cleaning pipeline: pure, testable functions (scrape batch -> production rows).

Policy summary:
- Outliers: >3 SD from trailing 7-day mean for route+window, or below floor price.
- Missing values: NEVER forward-fill volatile fares; mark no_data, exclude from index.
- Sold-out: excluded from averages, retained as availability metric.
- De-dup key: route+carrier+flight_date+window+source+scrape_date; keep latest.
"""
from __future__ import annotations

from statistics import mean, stdev
from typing import Any

FLOOR_PRICE = 500.0  # INR sanity floor: no genuine domestic fare is below this.
OUTLIER_SIGMA = 3.0


def is_outlier(price: float, history: list[float]) -> bool:
    """Flag statistically implausible fares.

    Args:
        price: candidate total fare.
        history: trailing fares for same route+window (need >= 2 for SD).
    """
    if price < FLOOR_PRICE:
        return True
    if len(history) < 2:
        return False
    mu, sd = mean(history), stdev(history)
    if sd == 0:
        return price != mu
    return abs(price - mu) > OUTLIER_SIGMA * sd


def remove_outliers(records: list[dict[str, Any]], history_by_key: dict[str, list[float]]) -> list[dict]:
    """Annotate each record with is_outlier; returns same list (mutated copies)."""
    out = []
    for rec in records:
        key = f"{rec['origin']}-{rec['destination']}-{rec['advance_purchase_window']}"
        price = rec.get("total_fare")
        flagged = price is not None and is_outlier(float(price), history_by_key.get(key, []))
        out.append({**rec, "is_outlier": flagged})
    return out


def handle_availability(records: list[dict[str, Any]]) -> tuple[list[dict], dict[str, int]]:
    """Split available fares from sold_out/no_data; count availability metric.

    Returns (priced_records, availability_counts).
    """
    priced: list[dict] = []
    counts: dict[str, int] = {}
    avail = priced
    for rec in records:
        status = rec.get("availability_status", "available")
        counts[status] = counts.get(status, 0) + 1
        if status == "available" and rec.get("total_fare") is not None and not rec.get("is_outlier"):
            avail.append(rec)
    return avail, counts


def decompose_fare(raw_payload: dict[str, Any]) -> dict[str, Any]:
    """Split raw payload into base/taxes/udf/convenience/total.

    Where breakdown is absent, total_fare only + decomposition_available=False.
    """
    if "total_fare" not in raw_payload:
        return {"total_fare": None, "decomposition_available": False}
    keys = ("base_fare", "taxes", "udf", "convenience_fee")
    present = all(k in raw_payload for k in keys)
    return {
        "base_fare": raw_payload.get("base_fare"),
        "taxes": raw_payload.get("taxes"),
        "udf": raw_payload.get("udf"),
        "convenience_fee": raw_payload.get("convenience_fee"),
        "total_fare": raw_payload["total_fare"],
        "decomposition_available": present,
    }


def deduplicate(records: list[dict[str, Any]]) -> tuple[list[dict], int]:
    """De-dup on route+carrier+flight_date+window+source+scrape_date; keep latest.

    Returns (deduped, n_discarded).
    """
    latest: dict[tuple, dict] = {}
    for rec in sorted(records, key=lambda r: r.get("scrape_timestamp", "")):
        key = (
            rec.get("origin"), rec.get("destination"), rec.get("carrier"),
            rec.get("flight_date"), rec.get("advance_purchase_window"),
            rec.get("source"), str(rec.get("scrape_timestamp", ""))[:10],
        )
        latest[key] = rec
    discarded = len(records) - len(latest)
    if discarded:
        import logging
        logging.getLogger(__name__).info("deduplicated %d rows", discarded)
    return list(latest.values()), discarded


def clean_batch(raw_rows: list[dict[str, Any]], history_by_key: dict[str, list[float]] | None = None) -> dict[str, Any]:
    """Full batch: decompose -> dedup -> outlier-flag -> availability split."""
    history_by_key = history_by_key or {}
    enriched = []
    for row in raw_rows:
        parts = decompose_fare(row.get("raw_payload", {}))
        status = row.get("status", "success")
        avail = "available" if status == "success" else ("sold_out" if status == "sold_out" else "no_data")
        enriched.append({**row, **parts, "availability_status": avail, "is_outlier": False})
    deduped, n_discarded = deduplicate(enriched)
    flagged = remove_outliers(deduped, history_by_key)
    priced, availability = handle_availability(flagged)
    return {
        "cleaned": flagged,
        "priced": priced,
        "availability": availability,
        "n_discarded": n_discarded,
    }
