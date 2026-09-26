"""DB writer: raw quotes -> raw_fare_quotes staging table."""
from __future__ import annotations

import json
import logging
import os

import sqlalchemy as sa
from sqlalchemy import text

log = logging.getLogger(__name__)


def get_engine(url: str | None = None) -> sa.Engine:
    return sa.create_engine(url or os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/apix"))


def write_raw_quotes(engine: sa.Engine, quotes: list) -> int:
    """Insert raw quotes into staging. Returns rows written."""
    rows = [
        {
            "source": q.source,
            "origin": q.origin,
            "destination": q.destination,
            "carrier": q.carrier,
            "advance_purchase_window": q.advance_purchase_window,
            "scrape_timestamp": q.scrape_timestamp,
            "raw_payload": json.dumps(q.raw_payload),
            "status": q.status,
        }
        for q in quotes
    ]
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO raw_fare_quotes
                (source, origin, destination, carrier, advance_purchase_window,
                 scrape_timestamp, raw_payload, status)
                VALUES (:source, :origin, :destination, :carrier, :advance_purchase_window,
                 :scrape_timestamp, CAST(:raw_payload AS JSONB), :status)"""
            ),
            rows,
        )
    log.info("wrote %d raw quotes", len(rows))
    return len(rows)
