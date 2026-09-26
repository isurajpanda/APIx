# HANDOFF — APIx operator notes (this machine, 2026-09-26)

## Environment specifics (deviations from stock Ubuntu)
- System Python is 3.14, but the venv **must be Python 3.12**
  (`/usr/bin/python3.12`): pinned `numpy==1.26`/`pandas==2.2` have no 3.14
  wheels and pip hangs building from source. Always use `./venv/bin/...`.
- `sudo -u postgres` is restricted here; use `sudo -n su postgres -c "..."`
  for DB superuser work. Plain `sudo -n` (as root) works for apt/services.
- PostgreSQL 16 + TimescaleDB 2.30 (shared_preload_libraries set), Memcached —
  all running as system services. Postgres superuser password: `postgres`.

## What's running right now
- FastAPI + dashboard on **https://localhost:443** (self-signed
  `deploy/apix.crt`, background task; restart:
  `sudo -n ./venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 443 --ssl-keyfile deploy/apix.key --ssl-certfile deploy/apix.crt`,
  stop: `sudo -n pkill -f "[u]vicorn backend.main"` — bracket pattern avoids
  killing your own shell).
- Scheduler daemon is **not** running (run `python -m scraper.scheduler` when
  wanted; mock mode by default so it's DB-safe).

## Data state (`apix` DB)
- 6 routes seeded; 45-day backfill: 14,850 raw → 14,549 fares → 44 index days
  (2026-08-14 … 2026-09-27, base 2026-08-14). Re-run `python db/backfill.py --days 45`
  after truncating.
- 330 mock quotes from `python -m scraper.scheduler --once` (2026-09-27).
- DGCA benchmark: NOT yet loaded — download the published monthly average-fare
  series into `dgca_data/dgca_monthly_avg_fare.csv` (see `dgca_data/README.md`),
  then `python -m dgca.backtest` writes the real comparison to `backtest_report.md`.
- `proxies` table populated on demand (`python -m scraper.proxies`); empty by default.
- Test DB `test_apix` exists (conftest recreates it per session).

## Live scraping reality (see LIVE_STATUS.md)
- Only EaseMyTrip works live (1/11); rest blocked (PerimeterX/reCAPTCHA/403).
- Default `APIX_SCRAPER_MOCK=true` keeps everything demo-safe.
- Never attempt CAPTCHA solving (Ixigo, Air India Express are parked).

## Known quirks
- `dashboard/dist/` is served from disk — rebuild after frontend edits, no
  server restart needed.
- `.env` (gitignored) + `.env.example` (tracked) must stay in sync.
- `deploy/apix.key` is gitignored; regenerate with
  `openssl req -x509 -newkey rsa:2048 -keyout deploy/apix.key -out deploy/apix.crt -days 365 -nodes -subj "/CN=localhost"`.

## Suggested next steps
1. Residential proxies or NDC/affiliate APIs to lift live coverage past 1/11.
2. EMT-style form flows for IndiGo/SpiceJet (parked probes documented in chat).
3. **Download the real DGCA monthly average-fare series** into
   `dgca_data/dgca_monthly_avg_fare.csv` (schema in `dgca_data/README.md`) and
   run `python -m dgca.backtest` — the backtest currently reports 0 overlap
   honestly rather than quoting the old synthetic r ≈ 0.93.
4. Exact DGCA traffic shares into `routes.weight` before official use.
5. `git init` was re-run (original `.git/` vanished); nothing committed yet.
