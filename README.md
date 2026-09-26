# APIx — Real-time Airfare Price Index (MoSPI prototype)

End-to-end system tracking Indian domestic airfares and computing a daily
Laspeyres-style price index that could augment CPI. Docs: `METHODOLOGY.md`
(index theory), `SCRAPING_ETHICS.md` (scraping rules), `backtest_report.md`
(validation), `API.md` (endpoints), `LIVE_STATUS.md` (per-platform audit),
`WINDOWS.md` (Windows setup), `HANDOFF.md` (operator handoff).

## Architecture

```
airlines/OTAs --> [scraper (Playwright live + mock) + APScheduler] --> raw_fare_quotes
                                                                     (proxies table: 40x failover pool)
raw_fare_quotes --> [pipeline/clean.py] --> fares (TimescaleDB hypertable, plain-PG fallback)
fares --> [index/compute.py] --> daily_index --> [FastAPI + Memcached] --> [React dashboard at /]
```

Live status: EaseMyTrip genuinely live (form-driven); 1/11 platforms from a
datacenter IP — see `LIVE_STATUS.md`. DB holds a 45-day backfill + 3 live quotes.

## Native setup (no Docker, Ubuntu)

```bash
# 1. System: PostgreSQL + TimescaleDB + Memcached
sudo apt install postgresql memcached python3.12-venv
# TimescaleDB via packagecloud (see .github/workflows/ci.yml); then:
sudo -u postgres psql -c "CREATE DATABASE apix;"
psql $DATABASE_URL -f db/schema.sql   # Timescale parts auto-skip if absent

# 2. Python 3.12 env (3.14 cannot build pinned numpy/pandas)
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

# 3. Config + data
cp .env.example .env   # edit DATABASE_URL password; backend auto-loads it
python db/seed.py && python db/backfill.py --days 45

# 4. Run
./venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 443 \
  --ssl-keyfile deploy/apix.key --ssl-certfile deploy/apix.crt  # needs sudo; dashboard at /
python -m scraper.scheduler          # daily scrape + 3-hourly proxy refresh
python -m scraper.audit DEL BOM --window 7 [--with-proxies]  # live audit
cd dashboard && npm install && npm run build   # rebuild after frontend changes

# 5. Tests (22 passing)
pytest -q
```

Windows users: same program, native setup in `WINDOWS.md`.

Env vars: `DATABASE_URL`, `APIX_API_KEY` (default `dev-key`),
`MEMCACHED_SERVERS` (default `127.0.0.1:11211`), `SCRAPE_CRON` (default `0 2 * * *`),
`APIX_SCRAPER_MOCK` (`true` = deterministic mock fares for demo).
Proxy pool: `PROXY_LIST_URL` (default: proxifly IN list), `PROXY_REFRESH_HOURS`
(default `3`), `PROXY_CHECK_HOST` (default `checkip.amazonaws.com`),
`PROXY_CHECK_TIMEOUT` (default `8.0`s), `PROXY_CHECK_WORKERS` (default `20`).

Manual proxy refresh (fetch → check → store fastest-first):

```bash
python -m scraper.proxies                 # full refresh (~200 proxies)
python -m scraper.proxies --limit 10      # quick check of first 10 (testing)
```
