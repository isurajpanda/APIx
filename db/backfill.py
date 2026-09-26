"""Backfill: run the full pipeline (generate -> raw -> clean -> fares -> index) for N days.

Uses the same mock fare generator as the scrapers (deterministic per
date/route/window/source) so the whole chain is exercised end-to-end and the
API/dashboard serve database-backed data instead of hardcoded demo series.
Swap `mock_quote` for live spider output when running against real sites.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlalchemy as sa
from sqlalchemy import text

from index.compute import compute_daily_index, validate_weights
from pipeline.clean import clean_batch
from scraper.spiders import BASE_FARES as BASE_FARE, CARRIERS

SOURCES = list(CARRIERS.keys())
WINDOWS = [1, 7, 15, 30, 45]
MARKUP = {1: 1.45, 7: 1.25, 15: 1.10, 30: 1.0, 45: 0.92}


def fare_for(day_idx: int, total_days: int, origin: str, destination: str,
             window: int, source: str) -> float:
    """Deterministic fare with seasonal drift + hash jitter (INR)."""
    base = BASE_FARE.get((origin, destination), 5000)
    drift = 1 + 0.06 * __import__("math").sin(day_idx / 5.0) + 0.002 * day_idx
    seed = int(hashlib.md5(f"{day_idx}{origin}{destination}{window}{source}".encode()).hexdigest()[:8], 16)
    jitter = 0.95 + (seed % 100) / 1000.0
    return round(base * MARKUP[window] * drift * jitter, 2)


def backfill(database_url: str | None = None, days: int = 45) -> dict:
    url = database_url or os.environ.get("DATABASE_URL",
          "postgresql+psycopg://postgres:postgres@localhost:5432/apix")
    eng = sa.create_engine(url)
    today = date.today()
    base_date = today - timedelta(days=days - 1)

    with eng.connect() as c:
        routes = [(r.origin, r.destination, float(r.weight))
                  for r in c.execute(text("SELECT origin, destination, weight FROM routes WHERE active")).all()]
    weights = {f"{o}-{d}": w for o, d, w in routes}
    validate_weights(weights)

    n_raw = n_fares = 0
    with eng.begin() as conn:
        for day_idx in range(days):
            scrape_date = base_date + timedelta(days=day_idx)
            scrape_ts = datetime(scrape_date.year, scrape_date.month, scrape_date.day, 2, 0, tzinfo=timezone.utc)
            raw_rows: list[dict] = []
            for origin, destination, _ in routes:
                for window in WINDOWS:
                    flight_date = scrape_date + timedelta(days=window)
                    for source in SOURCES:
                        # ~2% sold-out (deterministic) to exercise availability handling.
                        sold = (int(hashlib.md5(f"sold{day_idx}{origin}{window}{source}".encode()).hexdigest()[:4], 16) % 50) == 0
                        if sold:
                            raw_rows.append({
                                "source": source, "origin": origin, "destination": destination,
                                "carrier": CARRIERS[source], "advance_purchase_window": window,
                                "flight_date": flight_date, "scrape_timestamp": scrape_ts,
                                "raw_payload": {}, "status": "sold_out",
                            })
                            continue
                        total = fare_for(day_idx, days, origin, destination, window, source)
                        taxes = round(total * 0.18, 2)
                        raw_rows.append({
                            "source": source, "origin": origin, "destination": destination,
                            "carrier": CARRIERS[source], "advance_purchase_window": window,
                            "flight_date": flight_date, "scrape_timestamp": scrape_ts,
                            "raw_payload": {
                                "total_fare": total, "base_fare": round(total - taxes - 300, 2),
                                "taxes": taxes, "udf": 200.0, "convenience_fee": 100.0,
                                "currency": "INR", "mock": True,
                            },
                            "status": "success",
                        })
            conn.execute(text(
                """INSERT INTO raw_fare_quotes
                (source, origin, destination, carrier, advance_purchase_window,
                 scrape_timestamp, raw_payload, status)
                VALUES (:source, :origin, :destination, :carrier, :advance_purchase_window,
                 :scrape_timestamp, CAST(:raw AS JSONB), :status)"""),
                [{**r, "raw": json.dumps(r["raw_payload"])} for r in raw_rows])
            n_raw += len(raw_rows)

            key = lambda r: f"{r['origin']}-{r['destination']}-{r['advance_purchase_window']}"  # noqa: E731
            hist = {k: [fare_for(max(0, day_idx - i), days, r["origin"], r["destination"],
                                 r["advance_purchase_window"], r["source"])
                        for i in range(1, 8)] for r in raw_rows for k in [key(r)]}
            res = clean_batch(raw_rows, hist)
            fare_rows = [{
                "scrape_timestamp": r["scrape_timestamp"], "flight_date": r["flight_date"],
                "origin": r["origin"], "destination": r["destination"], "carrier": r["carrier"],
                "advance_purchase_window": r["advance_purchase_window"],
                "base_fare": r.get("base_fare"), "taxes": r.get("taxes"), "udf": r.get("udf"),
                "convenience_fee": r.get("convenience_fee"), "total_fare": r["total_fare"],
                "source": r["source"], "decomposition_available": r.get("decomposition_available", False),
                "is_outlier": r.get("is_outlier", False), "availability_status": r["availability_status"],
            } for r in res["cleaned"] if r.get("total_fare") is not None]
            if fare_rows:
                conn.execute(text(
                    """INSERT INTO fares
                    (scrape_timestamp, flight_date, origin, destination, carrier,
                     advance_purchase_window, base_fare, taxes, udf, convenience_fee,
                     total_fare, source, decomposition_available, is_outlier, availability_status)
                    VALUES (:scrape_timestamp, :flight_date, :origin, :destination, :carrier,
                     :advance_purchase_window, :base_fare, :taxes, :udf, :convenience_fee,
                     :total_fare, :source, :decomposition_available, :is_outlier, :availability_status)"""),
                    fare_rows)
                n_fares += len(fare_rows)

        # Recompute the daily index from stored fares (base = first 7 days).
        rows = conn.execute(text(
            """SELECT origin, destination, scrape_timestamp::date AS d, AVG(total_fare) AS avg_f
            FROM fares WHERE availability_status='available' AND NOT is_outlier
            GROUP BY 1, 2, 3 ORDER BY 3""")).all()
        by_route: dict[str, dict[str, list[float]]] = {}
        for o, d, day, avg in rows:
            by_route.setdefault(f"{o}-{d}", {}).setdefault(str(day), []).append(float(avg))
        all_dates = sorted({str(r[2]) for r in rows})
        series = compute_daily_index(by_route, all_dates[:7], weights)
        for day, val in series.items():
            if val is None:
                continue
            conn.execute(text(
                """INSERT INTO daily_index (index_date, index_value, methodology_version, base_period)
                VALUES (CAST(:d AS DATE), :v, 'v1.0', CAST(:b AS DATE))
                ON CONFLICT (index_date) DO UPDATE SET index_value = EXCLUDED.index_value,
                    methodology_version = EXCLUDED.methodology_version,
                    base_period = EXCLUDED.base_period, computed_at = now()"""),
                {"d": day, "v": round(val, 2), "b": all_dates[0]})
    eng.dispose()
    return {"raw": n_raw, "fares": n_fares, "index_days": len(series), "base_period": all_dates[0]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Backfill N days of pipeline data.")
    ap.add_argument("--days", type=int, default=45)
    args = ap.parse_args(argv)
    print(backfill(days=args.days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
