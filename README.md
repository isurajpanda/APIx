# APIx | Airfare Price Index

**Data engineering and statistical price-index prototype for Indian domestic airfares.**

APIx collects fare observations, normalizes them and computes a daily Laspeyres-style index for analysis. This is a MoSPI-oriented prototype, not an official CPI product.

## Architecture

```mermaid
flowchart LR
  A[Airlines and fare sources] --> B[Scheduled collection]
  B --> C[Raw observations]
  C --> D[Cleaning pipeline]
  D --> E[(PostgreSQL / TimescaleDB)]
  E --> F[Index computation]
  F --> G[FastAPI and cache]
  G --> H[React dashboard]
```

**Stack:** Python · FastAPI · PostgreSQL · TimescaleDB · Memcached · Playwright · React

## Project structure

| Directory | Purpose |
|---|---|
| `scraper/` | Collection and scheduling |
| `pipeline/` | Data cleaning |
| `db/` | Schema and seed data |
| `index/` | Statistical index computation |
| `backend/` | API and caching |
| `dashboard/` | User interface |
| `tests/` | Automated tests |

## Documentation

- [Methodology](METHODOLOGY.md) and [backtesting](backtest_report.md)
- [API reference](API.md)
- [Live source status](LIVE_STATUS.md) and [collection checklist](SCRAPE_CHECKLIST.md)
- [Collection ethics](SCRAPING_ETHICS.md)
- [Windows setup](WINDOWS.md) and [operator handoff](HANDOFF.md)

## Data and limitations

The repository supports mock and live collection. Source availability varies, and historical backfills must not be confused with verified live observations. Consult the dated source audit before interpreting results. Use authorized data sources and respect access restrictions.

## Quickstart (Ubuntu, native setup)

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

# 5. Run tests
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
