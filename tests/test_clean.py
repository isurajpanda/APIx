"""Unit tests: cleaning pipeline."""
from pipeline.clean import (
    clean_batch, decompose_fare, deduplicate, handle_availability, is_outlier,
)


def test_is_outlier_floor():
    assert is_outlier(100.0, [5000.0, 5100.0]) is True


def test_is_outlier_sigma():
    hist = [5000.0] * 6 + [5050.0]
    assert is_outlier(9000.0, hist) is True
    assert is_outlier(5020.0, hist) is False


def test_is_outlier_needs_history():
    assert is_outlier(99999.0, [5000.0]) is False


def test_decompose_full_and_partial():
    full = decompose_fare({"total_fare": 6000, "base_fare": 4500, "taxes": 1100, "udf": 200, "convenience_fee": 200})
    assert full["decomposition_available"] is True
    part = decompose_fare({"total_fare": 6000})
    assert part["decomposition_available"] is False and part["base_fare"] is None


def test_deduplicate_keeps_latest():
    recs = [
        {"origin": "DEL", "destination": "BOM", "carrier": "6E", "flight_date": "2026-09-01",
         "advance_purchase_window": 7, "source": "m", "scrape_timestamp": "2026-08-01T01:00", "v": 1},
        {"origin": "DEL", "destination": "BOM", "carrier": "6E", "flight_date": "2026-09-01",
         "advance_purchase_window": 7, "source": "m", "scrape_timestamp": "2026-08-01T02:00", "v": 2},
    ]
    out, dropped = deduplicate(recs)
    assert len(out) == 1 and out[0]["v"] == 2 and dropped == 1


def test_handle_availability_excludes_soldout():
    recs = [
        {"total_fare": 5000, "availability_status": "available"},
        {"total_fare": 5200, "availability_status": "sold_out"},
        {"total_fare": None, "availability_status": "no_data"},
    ]
    priced, counts = handle_availability(recs)
    assert len(priced) == 1 and counts["sold_out"] == 1


def test_clean_batch_end_to_end():
    raw = [
        {"source": "m", "origin": "DEL", "destination": "BOM", "carrier": "6E",
         "advance_purchase_window": 7, "flight_date": "2026-09-01",
         "scrape_timestamp": "2026-08-01T02:00",
         "raw_payload": {"total_fare": 6000, "base_fare": 4500, "taxes": 1100, "udf": 200, "convenience_fee": 200},
         "status": "success"},
        {"source": "m", "origin": "DEL", "destination": "BOM", "carrier": "6E",
         "advance_purchase_window": 7, "flight_date": "2026-09-02",
         "scrape_timestamp": "2026-08-01T02:00", "raw_payload": {}, "status": "sold_out"},
    ]
    res = clean_batch(raw, {"DEL-BOM-7": [5900.0, 6000.0, 5950.0]})
    assert len(res["priced"]) == 1 and res["availability"]["sold_out"] == 1
