"""Back-test module: DGCA CSV parsing, monthly aggregation, comparison, honesty."""
import os

from dgca.backtest import compare, load_dgca_csv, write_report


def test_load_dgca_csv(tmp_path):
    p = tmp_path / "dgca.csv"
    p.write_text("month,avg_fare_inr\n2026-01,5000.0\n2026-02,5200.0\n", encoding="utf-8")
    s = load_dgca_csv(str(p))
    assert s == {"2026-01": 5000.0, "2026-02": 5200.0}


def test_load_dgca_csv_skips_bad_rows(tmp_path):
    p = tmp_path / "dgca.csv"
    p.write_text("month,avg_fare_inr\n2026-01,5000.0\nbad,row\n2026-02,abc\n", encoding="utf-8")
    s = load_dgca_csv(str(p))
    assert s == {"2026-01": 5000.0}


def test_compare_aligns_and_scores():
    apix = {"2026-01": 100.0, "2026-02": 110.0, "2026-03": 105.0}
    dgca = {"2026-01": 5000.0, "2026-02": 5500.0, "2026-04": 9999.0}
    res = compare(apix, dgca)
    assert res["overlap_months"] == 2
    assert res["r"] is not None and res["r"] > 0.99
    assert res["pairs"][0]["dgca_rebased"] == 100.0  # rebased to APIx base


def test_compare_no_overlap():
    res = compare({"2026-01": 100.0}, {"2025-01": 5000.0})
    assert res["overlap_months"] == 0
    assert res["r"] is None


def test_report_is_honest_without_benchmark(tmp_path):
    write_report({"overlap_months": 0, "r": None, "rmse": None, "mae": None, "pairs": []},
                 "missing.csv", 44, report_path=str(tmp_path / "backtest_report.md"))
    text = (tmp_path / "backtest_report.md").read_text(encoding="utf-8")
    assert "NOT FOUND OR EMPTY" in text
    assert "no correlation quoted" in text
    assert "synthetic stand-in" in text


def test_report_quotes_correlation_with_benchmark(tmp_path):
    result = {
        "overlap_months": 2, "r": 0.97, "rmse": 1.2, "mae": 0.9,
        "pairs": [{"month": "2026-01", "apix": 100.0, "dgca_published": 5000.0, "dgca_rebased": 100.0}],
    }
    write_report(result, "dgca.csv", 60, report_path=str(tmp_path / "backtest_report.md"))
    text = (tmp_path / "backtest_report.md").read_text(encoding="utf-8")
    assert "0.970" in text
    assert "REAL published figures" in text
    assert "| 2026-01 |" in text
