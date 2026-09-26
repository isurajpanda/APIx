"""Seed route basket (weights sum to 1.0)."""
import os
import sqlalchemy as sa
from sqlalchemy import text

ROUTES = [
    ("DEL", "BOM", 0.22), ("DEL", "BLR", 0.20), ("BOM", "BLR", 0.17),
    ("DEL", "CCU", 0.15), ("BLR", "HYD", 0.12), ("MAA", "DEL", 0.14),
]

if __name__ == "__main__":
    eng = sa.create_engine(os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/apix"))
    with eng.begin() as c:
        for o, d, w in ROUTES:
            c.execute(text(
                "INSERT INTO routes (origin, destination, weight) VALUES (:o,:d,:w) "
                "ON CONFLICT (origin, destination) DO UPDATE SET weight=EXCLUDED.weight"),
                {"o": o, "d": d, "w": w})
    print("seeded routes")
