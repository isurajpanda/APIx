# APIx — Real-time Airfare Price Index (MoSPI prototype)

End-to-end system tracking Indian domestic airfares and computing a daily
Laspeyres-style price index that could augment CPI. See `METHODOLOGY.md`,
`SCRAPING_ETHICS.md`, `backtest_report.md`, `API.md`.

## Architecture

```
airlines/OTAs --> [scraper (Scrapy+Playwright) + APScheduler] --> raw_fare_quotes
raw_fare_quotes --> [pipeline/clean.py] --> fares (TimescaleDB hypertable)
fares --> [index/compute.py] --> daily_index --> [FastAPI + Memcached] --> [React dashboard]
```

## Native setup (no Docker)

```bash
# 1. PostgreSQL + TimescaleDB (Ubuntu)
sudo apt install postgresql-15 memcached
# install TimescaleDB per docs: https://docs.timescale.com/self-hosted/latest/install/
sudo -u postgres psql -c "CREATE DATABASE apix;"
sudo -u postgres psql -d apix -c "CREATE EXTENSION timescaledb;"
psql $DATABASE_URL -f db/schema.sql
python db/seed.py

# 2. Python env
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. Run (3 terminals, or honcho start / systemd units in deploy/)
uvicorn backend.main:app --port 8000
python -m scraper.scheduler --once   # one cycle; omit --once for daily daemon
cd dashboard && npm install && npm run dev

# 4. Tests
pytest -q
```

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
