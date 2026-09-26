# Running APIx on Windows (10/11, 64-bit)

Yes — the whole stack runs natively on Windows. Only the *process-management*
layer differs (Task Scheduler instead of systemd/cron); everything else is the
same code. Two features degrade gracefully by design:

| Dependency | Linux | Windows | Impact |
|---|---|---|---|
| TimescaleDB | ✅ apt package | ❌ no official build | Schema auto-skips hypertables/continuous aggregates (verified); app queries plain tables, unaffected |
| Memcached | ✅ apt package | ❌ no maintained build | Backend auto-falls back to in-process cache; nothing to install |

## 1. Prerequisites (install once)

- **Python 3.12** from python.org (tick *Add python.exe to PATH*)
- **PostgreSQL 16** from postgresql.org/download/windows (EDB installer;
  remember the `postgres` superuser password you set)
- **Node.js 20 LTS** from nodejs.org (includes npm)

## 2. Setup (PowerShell)

```powershell
cd C:\path\to\APIx
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\venv\Scripts\python -m playwright install chromium
cd dashboard; npm install; npm run build; cd ..
```

Create the database (password prompt = the one from the EDB installer):

```powershell
$env:PGPASSWORD = "your-postgres-password"
psql -U postgres -h localhost -c "CREATE DATABASE apix;"
psql -U postgres -h localhost -d apix -f db/schema.sql
.\venv\Scripts\python db/seed.py
```

## 3. Configure

Copy `.env.example` to `.env` and edit (the backend loads it automatically —
no `export`/`source` needed on any OS):

```
DATABASE_URL=postgresql+psycopg://postgres:your-postgres-password@localhost:5432/apix
APIX_API_KEY=dev-key
```

## 4. Run

```powershell
# API + dashboard (http://localhost:8000, docs at /docs)
.\venv\Scripts\uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Scraper: one cycle, or daily daemon (second terminal)
.\venv\Scripts\python -m scraper.scheduler --once
.\venv\Scripts\python -m scraper.scheduler

# Tests
.\venv\Scripts\python -m pytest tests/ -q
```

For autostart on boot, wrap the daemon command in Task Scheduler
(`schtasks /create /tn APIxScheduler /tr "C:\path\to\APIx\venv\Scripts\python.exe -m scraper.scheduler" /sc daily /st 02:00`)
instead of the systemd units in `deploy/` (Linux-only).

## Notes

- Port 443 + HTTPS on Windows needs an admin shell and a cert; for local use
  plain port 8000 is fine. (Linux guide uses a self-signed `deploy/apix.crt`.)
- Playwright browsers install to `%USERPROFILE%\AppData\Local\ms-playwright`.
- If `Activate.ps1` is blocked, run
  `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` once.
