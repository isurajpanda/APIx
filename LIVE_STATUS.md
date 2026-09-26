# LIVE SCRAPING STATUS (audited 2026-09-26, `python -m scraper.audit`)

All 6 basket routes (DEL-BOM, DEL-BLR, BOM-BLR, DEL-CCU, BLR-HYD, MAA-DEL) and
all 11 sources are wired into the scheduler. Live reachability from this
datacenter IP, one quote per source (DEL-BOM T+7):

| Source | Status | Detail |
|---|---|---|
| EaseMyTrip | ✅ SUCCESS | Form-driven flow (`scraper/emt.py`); genuine fares in DB (BLR-HYD T+7 ₹3,759; DEL-BOM T+15 ₹6,090) |
| IndiGo / Air India Express / SpiceJet | ⚠️ pages load, no prices | JS apps / idle shells; need form automation as done for EMT |
| Air India | ❌ blocked | Navigation timeouts (bot detection stalling loads) |
| Akasa Air / Cleartrip | ❌ 403 | Direct + free-proxy failover both refused |
| MakeMyTrip / Yatra / Goibibo | ❌ blocked | HTTP/2 resets, timeouts, PerimeterX challenge |
| Ixigo | ⚠️ loads, reports no flights | Wall or wrong guessed search URL; needs calibration |

## What this means
- Framework (spiders, scheduling, proxy failover, audit) covers all 11.
- Genuinely live today: **EaseMyTrip** (all 6 routes — airport picker works by
  IATA code). Its quotes flow into `raw_fare_quotes` with `"live": true`.
- The rest need, in order of leverage: (1) paid residential proxies
  (free-proxy IPs are pre-burned), (2) per-site form automation as done for
  EMT, (3) official airline NDC / OTA affiliate APIs for production use.

## Reproducing
`./venv/bin/python -m scraper.audit DEL BOM --window 7 [--with-proxies]`
