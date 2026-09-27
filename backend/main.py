"""FastAPI backend: APIx index, fares, routes, health. Memcached caching."""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import sqlalchemy as sa
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("apix")

MEMCACHED_SERVERS = os.environ.get("MEMCACHED_SERVERS", "127.0.0.1:11211")
CACHE_TTL = int(os.environ.get("APIX_CACHE_TTL", "300"))
DB_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/apix")
MAX_DB_RETRIES = 3
DB_RETRY_DELAY = 0.5
QUERY_TIMEOUT = 30
MAX_PAGE_SIZE = 365
DEFAULT_PAGE_SIZE = 90

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = sa.create_engine(
            DB_URL,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_recycle=3600,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10, "options": f"-c statement_timeout={QUERY_TIMEOUT * 1000}"},
        )
    return _engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    _get_engine()
    logger.info("APIx backend starting up")
    yield
    if _engine:
        _engine.dispose()
    logger.info("APIx backend shutting down")


app = FastAPI(
    title="APIx — Airfare Price Index",
    version="1.0.0",
    description="Real-time domestic airfare price index for MoSPI/NSO/RBI consumption.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.monotonic()
    response = await call_next(request)
    elapsed = time.monotonic() - start
    response.headers["X-Request-ID"] = request_id
    logger.info("%s %s %d %.3fms", request.method, request.url.path, response.status_code, elapsed * 1000)
    return response


_memc = None
_memc_failed = False


def _memc_client():
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


def _sanitize_cache_key(key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9:_\-.]", "_", key)


class IndexPoint(BaseModel):
    index_date: str
    index_value: float
    methodology_version: str = "v1.0"
    base_period: str = ""


AIRPORTS = [
    {"code": "DEL", "city": "New Delhi", "name": "Indira Gandhi Intl", "lat": 28.5562, "lon": 77.1000},
    {"code": "BOM", "city": "Mumbai", "name": "Chhatrapati Shivaji Intl", "lat": 19.0896, "lon": 72.8656},
    {"code": "BLR", "city": "Bengaluru", "name": "Kempegowda Intl", "lat": 13.1986, "lon": 77.7066},
    {"code": "CCU", "city": "Kolkata", "name": "Netaji Subhas Chandra Bose Intl", "lat": 22.6547, "lon": 88.4467},
    {"code": "HYD", "city": "Hyderabad", "name": "Rajiv Gandhi Intl", "lat": 17.2403, "lon": 78.4294},
    {"code": "MAA", "city": "Chennai", "name": "Chennai Intl", "lat": 12.9941, "lon": 80.1709},
    {"code": "GOI", "city": "Goa", "name": "Manohar Intl", "lat": 15.3808, "lon": 73.8314},
    {"code": "AMD", "city": "Ahmedabad", "name": "Sardar Vallabhbhai Patel Intl", "lat": 23.0772, "lon": 72.6347},
    {"code": "PNQ", "city": "Pune", "name": "Pune Airport", "lat": 18.5822, "lon": 73.9197},
    {"code": "LKO", "city": "Lucknow", "name": "Chaudhary Charan Singh Intl", "lat": 26.7606, "lon": 80.8893},
    {"code": "ATQ", "city": "Amritsar", "name": "Sri Guru Ram Dass Jee Intl", "lat": 31.7096, "lon": 74.7973},
    {"code": "SXR", "city": "Srinagar", "name": "Sheikh ul-Alam Intl", "lat": 33.9871, "lon": 74.7742},
    {"code": "IXC", "city": "Chandigarh", "name": "Shaheed Bhagat Singh Intl", "lat": 30.6735, "lon": 76.7885},
    {"code": "BBI", "city": "Bhubaneswar", "name": "Biju Patnaik Intl", "lat": 20.2444, "lon": 85.8178},
    {"code": "GAU", "city": "Guwahati", "name": "Lokpriya Gopinath Bordoloi Intl", "lat": 26.1061, "lon": 91.5859},
    {"code": "IMF", "city": "Imphal", "name": "Imphal Intl", "lat": 24.7600, "lon": 93.8967},
    {"code": "IXA", "city": "Agartala", "name": "Maharaja Bir Bikram", "lat": 23.8869, "lon": 91.2404},
    {"code": "DIB", "city": "Dibrugarh", "name": "Dibrugarh Airport", "lat": 27.4839, "lon": 95.0169},
    {"code": "AJL", "city": "Aizawl", "name": "Lengpui Airport", "lat": 23.7466, "lon": 92.8028},
    {"code": "SHL", "city": "Shillong", "name": "Shillong Airport", "lat": 25.7036, "lon": 91.9787},
    {"code": "IXM", "city": "Madurai", "name": "Madurai Airport", "lat": 9.8345, "lon": 78.0934},
    {"code": "TRV", "city": "Thiruvananthapuram", "name": "Thiruvananthapuram Intl", "lat": 8.4821, "lon": 76.9201},
    {"code": "COK", "city": "Kochi", "name": "Cochin Intl", "lat": 10.1520, "lon": 76.4019},
    {"code": "CJB", "city": "Coimbatore", "name": "Coimbatore Intl", "lat": 11.0300, "lon": 77.0434},
    {"code": "IXE", "city": "Mangaluru", "name": "Mangaluru Intl", "lat": 12.9613, "lon": 74.8900},
    {"code": "VTZ", "city": "Visakhapatnam", "name": "Visakhapatnam Intl", "lat": 17.7212, "lon": 83.2245},
    {"code": "RJA", "city": "Rajahmundry", "name": "Rajahmundry Airport", "lat": 17.1104, "lon": 81.8182},
    {"code": "TIR", "city": "Tirupati", "name": "Tirupati Airport", "lat": 13.6325, "lon": 79.5438},
    {"code": "UDR", "city": "Udaipur", "name": "Maharana Pratap", "lat": 24.6177, "lon": 73.8961},
    {"code": "JAI", "city": "Jaipur", "name": "Jaipur Intl", "lat": 26.8247, "lon": 75.8127},
    {"code": "JDH", "city": "Jodhpur", "name": "Jodhpur Airport", "lat": 26.2511, "lon": 73.0489},
    {"code": "BHO", "city": "Bhopal", "name": "Raja Bhoj", "lat": 23.2875, "lon": 77.3375},
    {"code": "IDR", "city": "Indore", "name": "Devi Ahilya Bai Holkar", "lat": 22.7217, "lon": 75.8011},
    {"code": "NAG", "city": "Nagpur", "name": "Dr. Babasaheb Ambedkar Intl", "lat": 21.0922, "lon": 79.0472},
    {"code": "RPR", "city": "Raipur", "name": "Swami Vivekananda", "lat": 21.1804, "lon": 81.7388},
    {"code": "PAT", "city": "Patna", "name": "Jay Prakash Narayan Intl", "lat": 25.5913, "lon": 85.0880},
    {"code": "GAY", "city": "Gaya", "name": "Gaya Airport", "lat": 24.7443, "lon": 84.9512},
    {"code": "DHM", "city": "Dharamshala", "name": "Gaggal Airport", "lat": 32.1650, "lon": 76.2634},
    {"code": "KUU", "city": "Kullu", "name": "Bhuntar Airport", "lat": 31.8767, "lon": 77.1543},
    {"code": "SLV", "city": "Shimla", "name": "Shimla Airport", "lat": 31.0819, "lon": 77.0680},
    {"code": "PNY", "city": "Puducherry", "name": "Puducherry Airport", "lat": 11.9680, "lon": 79.8125},
    {"code": "AGX", "city": "Agatti", "name": "Agatti Island", "lat": 10.8237, "lon": 72.1760},
    {"code": "DED", "city": "Dehradun", "name": "Jolly Grant", "lat": 30.1872, "lon": 78.1800},
    {"code": "PBD", "city": "Porbandar", "name": "Porbandar Airport", "lat": 21.6487, "lon": 69.6572},
    {"code": "BHJ", "city": "Bhuj", "name": "Bhuj Airport", "lat": 23.2878, "lon": 69.6700},
    {"code": "RAJ", "city": "Rajkot", "name": "Rajkot Airport", "lat": 22.3092, "lon": 70.7800},
    {"code": "STV", "city": "Surat", "name": "Surat Airport", "lat": 21.1142, "lon": 72.7420},
    {"code": "VNS", "city": "Varanasi", "name": "Lal Bahadur Shastri", "lat": 25.4524, "lon": 82.8593},
    {"code": "LDH", "city": "Ludhiana", "name": "Ludhiana Airport", "lat": 30.8547, "lon": 75.9525},
    {"code": "IXJ", "city": "Jammu", "name": "Jammu Airport", "lat": 32.6891, "lon": 74.8374},
    {"code": "GWL", "city": "Gwalior", "name": "Gwalior Airport", "lat": 26.2933, "lon": 78.2278},
    {"code": "KNU", "city": "Kanpur", "name": "Kanpur Airport", "lat": 26.4043, "lon": 80.4101},
    {"code": "IXR", "city": "Ranchi", "name": "Birsa Munda", "lat": 23.3143, "lon": 85.3217},
    {"code": "IXW", "city": "Jamshedpur", "name": "Sonari Airport", "lat": 22.8136, "lon": 86.1688},
    {"code": "HJR", "city": "Khajuraho", "name": "Khajuraho Airport", "lat": 24.8177, "lon": 79.9197},
    {"code": "JLR", "city": "Jabalpur", "name": "Jabalpur Airport", "lat": 23.1778, "lon": 80.0520},
    {"code": "IXL", "city": "Leh", "name": "Kushok Bakula Rimpochee", "lat": 34.1359, "lon": 77.5465},
    {"code": "RDP", "city": "Durgapur", "name": "Kazi Nazrul Islam", "lat": 23.6225, "lon": 87.2430},
    {"code": "COJ", "city": "Cooch Behar", "name": "Cooch Behar Airport", "lat": 26.3304, "lon": 89.4672},
    {"code": "DBD", "city": "Dhanbad", "name": "Dhanbad Airport", "lat": 23.8145, "lon": 86.4280},
    {"code": "HSS", "city": "Hisar", "name": "Hisar Airport", "lat": 29.1492, "lon": 75.7216},
    {"code": "BUP", "city": "Bathinda", "name": "Bathinda Airport", "lat": 30.2000, "lon": 74.9500},
    {"code": "RUP", "city": "Rupnagar", "name": "Rupnagar Airport", "lat": 30.9660, "lon": 76.5330},
]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(date_str: str | None, param_name: str) -> None:
    if date_str is not None and not _DATE_RE.match(date_str):
        raise HTTPException(400, f"Invalid {param_name} format. Expected YYYY-MM-DD, got: {date_str}")


def _db_rows(query: str, params: dict):
    from sqlalchemy import text
    eng = _get_engine()
    last_exc = None
    for attempt in range(MAX_DB_RETRIES):
        try:
            with eng.connect() as c:
                return [dict(r._mapping) for r in c.execute(text(query), params)]
        except Exception as exc:
            last_exc = exc
            logger.warning("DB query failed (attempt %d/%d): %s", attempt + 1, MAX_DB_RETRIES, str(exc)[:200])
            if attempt < MAX_DB_RETRIES - 1:
                time.sleep(DB_RETRY_DELAY * (2 ** attempt))
    logger.error("DB query failed after %d attempts: %s", MAX_DB_RETRIES, str(last_exc)[:200])
    raise HTTPException(503, "Database unavailable")


def get_index_series(granularity: str, start: str | None, end: str | None, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> dict:
    _validate_date(start, "start")
    _validate_date(end, "end")
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)
    offset = (page - 1) * page_size
    key = _sanitize_cache_key(f"index:{granularity}:{start}:{end}:{page}:{page_size}")
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
            total = len(vals)
            paginated = vals[offset:offset + page_size]
            result = {
                "granularity": granularity,
                "series": paginated,
                "pagination": {"page": page, "page_size": page_size, "total": total, "total_pages": (total + page_size - 1) // page_size},
            }
            cache_set(key, result)
            return result
    except HTTPException:
        pass
    except Exception as exc:
        logger.error("Error computing index series: %s", str(exc)[:200])
    return {"granularity": granularity, "series": [], "pagination": {"page": page, "page_size": page_size, "total": 0, "total_pages": 0}}


@app.get("/api/v1/health")
def health():
    db_status = "unreachable"
    last_scrape = None
    try:
        rows = _db_rows("SELECT MAX(scrape_timestamp) AS last_scrape FROM raw_fare_quotes", {})
        db_status = "connected"
        last_scrape = str(rows[0]["last_scrape"]) if rows and rows[0]["last_scrape"] else None
    except HTTPException:
        db_status = "unreachable"
    except Exception as exc:
        logger.error("Health check DB error: %s", str(exc)[:200])
        db_status = "unreachable"

    cache_status = "unavailable"
    mc = _memc_client()
    if mc is not None:
        try:
            mc.get(b"__health__")
            cache_status = "connected"
        except Exception:
            cache_status = "unavailable"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "db": db_status,
        "cache": cache_status,
        "last_scrape": last_scrape,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/index/daily")
def daily(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    return get_index_series("daily", start, end, page, page_size)


@app.get("/api/v1/index/weekly")
def weekly(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    return get_index_series("weekly", start, end, page, page_size)


@app.get("/api/v1/index/monthly")
def monthly(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    return get_index_series("monthly", start, end, page, page_size)


@app.get("/api/v1/routes")
def routes():
    try:
        return {"routes": _db_rows("SELECT route_id, origin, destination, weight FROM routes WHERE active ORDER BY 1", {})}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching routes: %s", str(exc)[:200])
        return {"routes": [], "source": "error"}


@app.get("/api/v1/airports")
def airports():
    return {"airports": AIRPORTS}


@app.get("/api/v1/fares/route")
def route_fare(origin: str = Query(...), destination: str = Query(...)):
    key = _sanitize_cache_key(f"route_fare:{origin}:{destination}")
    hit = cache_get(key)
    if hit is not None:
        return hit
    try:
        rows = _db_rows(
            """WITH latest AS (SELECT MAX(scrape_timestamp)::date AS d FROM fares)
            SELECT AVG(f.total_fare) AS avg_fare, COUNT(*) AS count
            FROM fares f JOIN latest ON f.scrape_timestamp::date = latest.d
            WHERE f.origin = :o AND f.destination = :d
            AND f.availability_status = 'available' AND NOT f.is_outlier""",
            {"o": origin, "d": destination},
        )
        if rows and rows[0]["count"] > 0:
            result = {
                "origin": origin,
                "destination": destination,
                "avg_fare": round(float(rows[0]["avg_fare"]), 2),
                "observations": int(rows[0]["count"]),
                "source": "db",
            }
            cache_set(key, result)
            return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching route fare: %s", str(exc)[:200])
    return {"origin": origin, "destination": destination, "avg_fare": None, "observations": 0, "source": "no_data"}


@app.get("/api/v1/fares/heatmap")
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
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching heatmap: %s", str(exc)[:200])
    return {"heatmap": [], "source": "no_data"}


@app.get("/api/v1/fares/elasticity/{route_id}")
def elasticity(route_id: int):
    try:
        route = _db_rows(
            "SELECT origin, destination FROM routes WHERE route_id = :id", {"id": route_id})
        if not route:
            raise HTTPException(404, "unknown route")
        origin, destination = route[0]["origin"], route[0]["destination"]
        rows = _db_rows(
            """SELECT advance_purchase_window AS window, AVG(total_fare) AS avg_fare
            FROM fares WHERE origin=:o AND destination=:d
            AND availability_status='available' AND NOT is_outlier
            AND scrape_timestamp >= now() - INTERVAL '30 days'
            GROUP BY 1 ORDER BY 1""",
            {"o": origin, "d": destination})
        if rows:
            return {"route_id": route_id, "source": "db",
                    "curve": [{"window": int(r["window"]), "avg_fare": round(float(r["avg_fare"]), 2)}
                              for r in rows]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching elasticity: %s", str(exc)[:200])
    return {"route_id": route_id, "curve": [], "source": "no_data"}


@app.get("/api/v1/fares/sources")
def fare_sources(origin: str = Query(...), destination: str = Query(...)):
    """Get price sources/platforms for a route."""
    try:
        rows = _db_rows(
            """SELECT source, carrier, COUNT(*) AS count, AVG(total_fare) AS avg_fare,
                      MIN(total_fare) AS min_fare, MAX(total_fare) AS max_fare
            FROM fares WHERE origin = :o AND destination = :d
            AND availability_status = 'available' AND NOT is_outlier
            GROUP BY source, carrier ORDER BY avg_fare""",
            {"o": origin, "d": destination},
        )
        if rows:
            return {
                "origin": origin,
                "destination": destination,
                "sources": [{
                    "source": r["source"],
                    "carrier": r["carrier"],
                    "count": int(r["count"]),
                    "avg_fare": round(float(r["avg_fare"]), 2),
                    "min_fare": round(float(r["min_fare"]), 2),
                    "max_fare": round(float(r["max_fare"]), 2),
                } for r in rows],
                "source": "db",
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching fare sources: %s", str(exc)[:200])
    return {"origin": origin, "destination": destination, "sources": [], "source": "no_data"}


@app.get("/api/v1/fares/by-date")
def fares_by_date(origin: str = Query(...), destination: str = Query(...)):
    """Get date-to-price data for a route."""
    try:
        rows = _db_rows(
            """SELECT flight_date, AVG(total_fare) AS avg_fare, COUNT(*) AS count,
                      MIN(total_fare) AS min_fare, MAX(total_fare) AS max_fare
            FROM fares WHERE origin = :o AND destination = :d
            AND availability_status = 'available' AND NOT is_outlier
            GROUP BY flight_date ORDER BY flight_date""",
            {"o": origin, "d": destination},
        )
        if rows:
            return {
                "origin": origin,
                "destination": destination,
                "dates": [{
                    "flight_date": str(r["flight_date"]),
                    "avg_fare": round(float(r["avg_fare"]), 2),
                    "count": int(r["count"]),
                    "min_fare": round(float(r["min_fare"]), 2),
                    "max_fare": round(float(r["max_fare"]), 2),
                } for r in rows],
                "source": "db",
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching fares by date: %s", str(exc)[:200])
    return {"origin": origin, "destination": destination, "dates": [], "source": "no_data"}


@app.post("/api/v1/refresh")
def refresh_data():
    logs = []
    now = datetime.now(timezone.utc).isoformat()

    logs.append({"ts": now, "level": "INFO", "msg": "Refresh initiated"})

    global _fallback
    _fallback.clear()
    logs.append({"ts": now, "level": "INFO", "msg": "Cache cleared"})

    mc = _memc_client()
    if mc is not None:
        try:
            mc.flush_all()
            logs.append({"ts": now, "level": "INFO", "msg": "Memcached flushed"})
        except Exception as e:
            logs.append({"ts": now, "level": "WARN", "msg": f"Memcached flush failed: {str(e)[:100]}"})
    else:
        logs.append({"ts": now, "level": "INFO", "msg": "Memcached not available, using in-process cache"})

    try:
        rows = _db_rows("SELECT COUNT(*) AS cnt FROM fares", {})
        count = rows[0]["cnt"] if rows else 0
        logs.append({"ts": now, "level": "INFO", "msg": f"DB connected — {count} fare records"})
    except Exception as e:
        logs.append({"ts": now, "level": "ERROR", "msg": f"DB unreachable: {str(e)[:200]}"})

    try:
        rows = _db_rows("SELECT COUNT(*) AS cnt FROM daily_index", {})
        count = rows[0]["cnt"] if rows else 0
        logs.append({"ts": now, "level": "INFO", "msg": f"Index table — {count} records"})
    except Exception as e:
        logs.append({"ts": now, "level": "ERROR", "msg": f"Index table error: {str(e)[:200]}"})

    try:
        rows = _db_rows("SELECT COUNT(*) AS cnt FROM routes WHERE active", {})
        count = rows[0]["cnt"] if rows else 0
        logs.append({"ts": now, "level": "INFO", "msg": f"Active routes — {count}"})
    except Exception as e:
        logs.append({"ts": now, "level": "ERROR", "msg": f"Routes table error: {str(e)[:200]}"})

    logs.append({"ts": now, "level": "INFO", "msg": "Refresh complete"})

    return {"status": "ok", "refreshed_at": now, "logs": logs}


@app.get("/api/v1/metrics")
def metrics():
    """Basic operational metrics."""
    try:
        fares_count = _db_rows("SELECT COUNT(*) AS cnt FROM fares", {})[0]["cnt"]
        index_count = _db_rows("SELECT COUNT(*) AS cnt FROM daily_index", {})[0]["cnt"]
        routes_count = _db_rows("SELECT COUNT(*) AS cnt FROM routes WHERE active", {})[0]["cnt"]
        raw_count = _db_rows("SELECT COUNT(*) AS cnt FROM raw_fare_quotes", {})[0]["cnt"]
        return {
            "fares": fares_count,
            "index_days": index_count,
            "active_routes": routes_count,
            "raw_quotes": raw_count,
            "cache_fallback_size": len(_fallback),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error("Error fetching metrics: %s", str(exc)[:200])
        return {"error": str(exc)[:200]}


_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="dashboard")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=443)
