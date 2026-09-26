"""FastAPI backend: APIx index, fares, routes, health. Memcached caching, API-key auth."""
from __future__ import annotations

import os

try:  # load /workspaces/APIx/.env so DATABASE_URL etc. persist outside the shell
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import time
from datetime import date, timedelta

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

API_KEY = os.environ.get("APIX_API_KEY", "dev-key")
MEMCACHED_SERVERS = os.environ.get("MEMCACHED_SERVERS", "127.0.0.1:11211")
CACHE_TTL = int(os.environ.get("APIX_CACHE_TTL", "300"))

app = FastAPI(title="APIx — Airfare Price Index", version="1.0.0",
              description="Real-time domestic airfare price index for MoSPI/NSO/RBI consumption.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- simple cache: Memcached if reachable, else in-process dict fallback ---
_memc = None
_memc_failed = False


def _memc_client():
    """Lazily connect to Memcached; permanently fall back on first failure."""
    global _memc, _memc_failed
    if _memc_failed:
        return None
    if _memc is None:
        try:
            from pymemcache.client.base import Client
            _memc = Client(MEMCACHED_SERVERS, connect_timeout=0.2, timeout=0.2)
            _memc.get(b"__ping__")
        except Exception:
            _memc = None
            _memc_failed = True
    return _memc
_fallback: dict[str, tuple[float, object]] = {}


def cache_get(key: str):
    mc = _memc_client()
    if mc is not None:
        try:
            import json
            raw = mc.get(key.encode())
            return json.loads(raw) if raw else None
        except Exception:
            pass
    item = _fallback.get(key)
    if item and time.time() - item[0] < CACHE_TTL:
        return item[1]
    return None


def cache_set(key: str, value) -> None:
    mc = _memc_client()
    if mc is not None:
        try:
            import json
            mc.set(key.encode(), json.dumps(value, default=str).encode(), expire=CACHE_TTL)
            return
        except Exception:
            pass
    _fallback[key] = (time.time(), value)


def require_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid API key")


# --- deterministic demo dataset (used when DB is empty/unreachable) ---
BASE = date(2026, 8, 1)
ROUTES = [
    {"route_id": 1, "origin": "DEL", "destination": "BOM", "weight": 0.22},
    {"route_id": 2, "origin": "DEL", "destination": "BLR", "weight": 0.20},
    {"route_id": 3, "origin": "BOM", "destination": "BLR", "weight": 0.17},
    {"route_id": 4, "origin": "DEL", "destination": "CCU", "weight": 0.15},
    {"route_id": 5, "origin": "BLR", "destination": "HYD", "weight": 0.12},
    {"route_id": 6, "origin": "MAA", "destination": "DEL", "weight": 0.14},
]
BASE_FARE = {"DEL-BOM": 5500, "DEL-BLR": 6200, "BOM-BLR": 4200, "DEL-CCU": 5800, "BLR-HYD": 3200, "MAA-DEL": 6400}


def demo_index_series(n: int = 60) -> list[dict]:
    import math
    out = []
    for i in range(n):
        d = BASE + timedelta(days=i)
        val = 100 * (1 + 0.06 * math.sin(i / 5.0) + 0.002 * i)
        out.append({"index_date": d.isoformat(), "index_value": round(val, 2),
                    "methodology_version": "v1.0", "base_period": BASE.isoformat()})
    return out


class IndexPoint(BaseModel):
    index_date: str
    index_value: float
    methodology_version: str = "v1.0"
    base_period: str = BASE.isoformat()


def _db_rows(query: str, params: dict):
    import sqlalchemy as sa
    from sqlalchemy import text
    eng = sa.create_engine(os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/apix"))
    with eng.connect() as c:
        return [dict(r._mapping) for r in c.execute(text(query), params)]


def get_index_series(granularity: str, start: str | None, end: str | None) -> list[dict]:
    """DB-backed series with demo fallback (keeps system demoable pre-scrape)."""
    key = f"index:{granularity}:{start}:{end}"
    hit = cache_get(key)
    if hit is not None:
        return hit
    try:
        rows = _db_rows(
            "SELECT index_date, index_value, methodology_version, base_period FROM daily_index "
            "WHERE (:s IS NULL OR index_date >= CAST(:s AS DATE)) AND (:e IS NULL OR index_date <= CAST(:e AS DATE)) "
            "ORDER BY index_date",
            {"s": start, "e": end},
        )
        if rows:
            from index.compute import rolling_average
            daily = {str(r["index_date"]): float(r["index_value"]) for r in rows}
            meta = {str(r["index_date"]): (r["methodology_version"], str(r["base_period"])) for r in rows}
            if granularity == "weekly":
                daily = rolling_average(daily, 7)
            elif granularity == "monthly":
                daily = rolling_average(daily, 30)
            vals = [{"index_date": d, "index_value": round(v, 2),
                     "methodology_version": meta[d][0], "base_period": meta[d][1]}
                    for d, v in daily.items() if v is not None]
            cache_set(key, vals)
            return vals
    except Exception:
        pass
    series = demo_index_series()
    if start:
        series = [p for p in series if p["index_date"] >= start]
    if end:
        series = [p for p in series if p["index_date"] <= end]
    if granularity == "weekly":
        series = series[::7]
    elif granularity == "monthly":
        series = series[::30]
    cache_set(key, series)
    return series


@app.get("/api/v1/health")
def health():
    """Health check: DB connectivity + last successful scrape timestamp."""
    try:
        rows = _db_rows("SELECT MAX(scrape_timestamp) AS last_scrape FROM raw_fare_quotes", {})
        return {"status": "ok", "db": "connected", "last_scrape": str(rows[0]["last_scrape"])}
    except Exception as exc:
        return {"status": "degraded", "db": "unreachable", "detail": str(exc)[:200], "last_scrape": None}


@app.get("/api/v1/index/daily", dependencies=[Depends(require_key)])
def daily(start: str | None = Query(default=None), end: str | None = Query(default=None)):
    return {"granularity": "daily", "series": get_index_series("daily", start, end)}


@app.get("/api/v1/index/weekly", dependencies=[Depends(require_key)])
def weekly(start: str | None = Query(default=None), end: str | None = Query(default=None)):
    return {"granularity": "weekly", "series": get_index_series("weekly", start, end)}


@app.get("/api/v1/index/monthly", dependencies=[Depends(require_key)])
def monthly(start: str | None = Query(default=None), end: str | None = Query(default=None)):
    return {"granularity": "monthly", "series": get_index_series("monthly", start, end)}


@app.get("/api/v1/routes", dependencies=[Depends(require_key)])
def routes():
    try:
        return {"routes": _db_rows("SELECT route_id, origin, destination, weight FROM routes WHERE active ORDER BY 1", {})}
    except Exception:
        return {"routes": ROUTES, "source": "demo"}


@app.get("/api/v1/fares/heatmap", dependencies=[Depends(require_key)])
def heatmap():
    key = "heatmap"
    hit = cache_get(key)
    if hit is not None:
        return {"heatmap": hit, "source": "db"}
    try:
        rows = _db_rows(
            """WITH latest AS (SELECT MAX(scrape_timestamp)::date AS d FROM fares),
            base AS (SELECT origin, destination, AVG(total_fare) AS base_fare
                     FROM fares WHERE scrape_timestamp::date IN
                        (SELECT DISTINCT scrape_timestamp::date FROM fares ORDER BY 1 LIMIT 7)
                     AND availability_status='available' AND NOT is_outlier
                     GROUP BY 1, 2)
            SELECT f.origin, f.destination, AVG(f.total_fare) AS avg_fare,
                   MAX(b.base_fare) AS base_fare
            FROM fares f JOIN latest ON f.scrape_timestamp::date = latest.d
            LEFT JOIN base b ON b.origin=f.origin AND b.destination=f.destination
            WHERE f.availability_status='available' AND NOT f.is_outlier
            GROUP BY 1, 2 ORDER BY 1, 2""", {})
        if rows:
            cells = [{"origin": r["origin"], "destination": r["destination"],
                      "avg_fare": round(float(r["avg_fare"]), 2),
                      "relative": round(float(r["avg_fare"]) / float(r["base_fare"]), 4)
                      if r["base_fare"] else 1.0} for r in rows]
            cache_set(key, cells)
            return {"heatmap": cells, "source": "db"}
    except Exception:
        pass
    cells = [{"origin": r["origin"], "destination": r["destination"],
              "avg_fare": BASE_FARE[f"{r['origin']}-{r['destination']}"],
              "relative": 1.0} for r in ROUTES]
    cache_set(key, cells)
    return {"heatmap": cells, "source": "demo"}


@app.get("/api/v1/fares/elasticity/{route_id}", dependencies=[Depends(require_key)])
def elasticity(route_id: int):
    route = next((r for r in ROUTES if r["route_id"] == route_id), None)
    if route is None:
        raise HTTPException(404, "unknown route")
    try:
        rows = _db_rows(
            """SELECT advance_purchase_window AS window, AVG(total_fare) AS avg_fare
            FROM fares WHERE origin=:o AND destination=:d
            AND availability_status='available' AND NOT is_outlier
            AND scrape_timestamp >= now() - INTERVAL '30 days'
            GROUP BY 1 ORDER BY 1""",
            {"o": route["origin"], "d": route["destination"]})
        if rows:
            return {"route_id": route_id, "source": "db",
                    "curve": [{"window": int(r["window"]), "avg_fare": round(float(r["avg_fare"]), 2)}
                              for r in rows]}
    except Exception:
        pass
    base = BASE_FARE[f"{route['origin']}-{route['destination']}"]
    curve = [{"window": w, "avg_fare": round(base * m, 2)}
             for w, m in [(1, 1.45), (7, 1.25), (15, 1.10), (30, 1.0), (45, 0.92)]]
    return {"route_id": route_id, "curve": curve, "source": "demo"}


# --- dashboard (React build) served at / so one server handles UI + API ---
_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="dashboard")
