"""Integration tests: end-to-end pipeline from raw data to index computation."""
import pytest

from index.compute import compute_daily_index, validate_weights
from pipeline.clean import clean_batch, get_data_quality_metrics


def test_end_to_end_pipeline():
    """Test full pipeline: raw data -> clean -> index computation."""
    raw_rows = [
        {"source": "test", "origin": "DEL", "destination": "BOM", "carrier": "6E",
         "advance_purchase_window": 7, "flight_date": "2026-09-01",
         "scrape_timestamp": "2026-08-25T02:00",
         "raw_payload": {"total_fare": 5000, "base_fare": 4000, "taxes": 800, "udf": 100, "convenience_fee": 100},
         "status": "success"},
        {"source": "test", "origin": "DEL", "destination": "BOM", "carrier": "6E",
         "advance_purchase_window": 7, "flight_date": "2026-09-01",
         "scrape_timestamp": "2026-08-25T02:00",
         "raw_payload": {"total_fare": 5200, "base_fare": 4200, "taxes": 800, "udf": 100, "convenience_fee": 100},
         "status": "success"},
        {"source": "test", "origin": "DEL", "destination": "BOM", "carrier": "6E",
         "advance_purchase_window": 7, "flight_date": "2026-09-08",
         "scrape_timestamp": "2026-08-25T02:00",
         "raw_payload": {"total_fare": 5500, "base_fare": 4500, "taxes": 800, "udf": 100, "convenience_fee": 100},
         "status": "success"},
    ]

    weights = {"DEL-BOM": 1.0}
    validate_weights(weights)

    result = clean_batch(raw_rows)
    assert result["data_quality"]["total_input"] == 3
    assert result["data_quality"]["valid_records"] == 3
    assert result["data_quality"]["priced_records"] == 3

    fares_by_route_day = {
        "DEL-BOM": {
            "2026-08-25": [5000.0, 5200.0],
            "2026-08-25": [5500.0],
        }
    }

    index = compute_daily_index(fares_by_route_day, ["2026-08-25"], weights)
    assert "2026-08-25" in index
    assert index["2026-08-25"] is not None


def test_data_quality_metrics_aggregation():
    """Test data quality metrics across multiple batches."""
    batch1 = clean_batch([
        {"source": "test", "origin": "DEL", "destination": "BOM", "carrier": "6E",
         "advance_purchase_window": 7, "flight_date": "2026-09-01",
         "scrape_timestamp": "2026-08-25T02:00",
         "raw_payload": {"total_fare": 5000}, "status": "success"},
    ])
    batch2 = clean_batch([
        {"source": "test", "origin": "DEL", "destination": "BOM", "carrier": "6E",
         "advance_purchase_window": 7, "flight_date": "2026-09-01",
         "scrape_timestamp": "2026-08-25T02:00",
         "raw_payload": {"total_fare": 100}, "status": "success"},
    ])

    metrics = get_data_quality_metrics([batch1, batch2])
    assert metrics["total_input"] == 2
    assert metrics["total_valid"] == 2
    assert metrics["total_outliers"] == 1
    assert metrics["outlier_rate"] == 0.5


def test_index_validation():
    """Test index value validation."""
    from index.compute import validate_index_value

    assert validate_index_value(100.0, "2026-01-01") == []
    assert len(validate_index_value(None, "2026-01-01")) == 1
    assert len(validate_index_value(-10.0, "2026-01-01")) == 1
    assert len(validate_index_value(2000.0, "2026-01-01")) == 1


def test_index_decomposition():
    """Test index change decomposition."""
    from index.compute import decompose_index_change

    relatives_t = {"A": 1.1, "B": 1.0}
    relatives_t1 = {"A": 1.0, "B": 1.0}
    weights = {"A": 0.5, "B": 0.5}

    contributions = decompose_index_change(relatives_t, relatives_t1, weights)
    assert "A" in contributions
    assert "B" in contributions
    assert contributions["A"] == pytest.approx(0.05)
    assert contributions["B"] == pytest.approx(0.0)


def test_sensitivity_analysis():
    """Test sensitivity analysis."""
    from index.compute import sensitivity_analysis

    relatives = {"A": 1.1, "B": 1.0}
    weights = {"A": 0.5, "B": 0.5}

    impacts = sensitivity_analysis(relatives, weights, shock_pct=10.0)
    assert "A" in impacts
    assert "B" in impacts
    assert impacts["A"] > 0
    assert impacts["B"] > 0


def test_index_rebalancing():
    """Test weight rebalancing."""
    from index.compute import check_index_rebalancing_needed, rebalance_weights

    current = {"A": 0.6, "B": 0.4}
    target = {"A": 0.5, "B": 0.5}

    assert check_index_rebalancing_needed(current, target, tolerance=0.05)
    new_weights = rebalance_weights(current, target, smoothing=0.5)
    assert abs(sum(new_weights.values()) - 1.0) < 1e-6
    assert new_weights["A"] == pytest.approx(0.55)
    assert new_weights["B"] == pytest.approx(0.45)
