# LIVE SCRAPING STATUS (audited 2026-09-26, `python -m scraper.audit`)

All 6 basket routes (DEL-BOM, DEL-BLR, BOM-BLR, DEL-CCU, BLR-HYD, MAA-DEL) and
all 11 sources are wired into the scheduler. Live reachability from this
datacenter IP, one quote per source (DEL-BOM T+7):

| Source | Status | Detail |
|---|---|---|
| EaseMyTrip | ✅ SUCCESS | Form-driven flow (`scraper/emt.py`); genuine fares in DB (BLR-HYD T+7 ₹3,759; DEL-BOM T+15 ₹6,090) |
| IndiGo | ⚠️ empty app shell | 200, no captcha, but Angular renders zero inputs (content APIs stall for automated clients) |
| Air India Express | ❌ reCAPTCHA Enterprise | Hard gate on homepage; solving captchas out of scope |
| SpiceJet | ⚠️ autocomplete dead | Homepage loads; suggestion endpoint serves nothing to automation (tried fill + keystroke typing) |
| MakeMyTrip / Yatra / Goibibo | ❌ blocked | HTTP/2 resets, timeouts, PerimeterX challenge |
| Ixigo | ❌ reCAPTCHA on homepage | Hard gate |
| Akasa Air / Cleartrip | ❌ 403 | Direct + free-proxy failover both refused |

## What this means
- Framework (spiders, scheduling, proxy failover, audit) covers all 11.
- Genuinely live today: **EaseMyTrip** (all 6 routes — airport picker works by
  IATA code). Its quotes flow into `raw_fare_quotes` with `"live": true`.
- Ixigo is **parked by policy** (robots `/search/result/` disallowed +
  reCAPTCHA): no scraping hole, no CAPTCHA solving, no mitigation bypass.
  Compliant path: `scraper/ixigo_api.py` with `IXIGO_API_KEY` partnership.
- Full live audit 2026-10-04, DEL-BOM T+7, residential IP (score: 4 SUCCESS, 2 content-blocked, 5 parked, 0 crashes):
  - **Akasa Air: LIVE** — homepage form (`forms/akasa.py`) returned Rs 3,500 (confirmed twice).
  - **SpiceJet: LIVE** — homepage form (`forms/spicejet.py`) returned Rs 3,000 (15 fares).
  - **Cleartrip: PROVISIONAL** — Rs 3,500 (n=3, scoped fare elements; needs one confirmation run).
  - **EaseMyTrip: LIVE (guarded)** — this run returned suspect Rs 1,662 fee soup (zero fare-element matches); `resolve_emt_fares()` now reports SoldOut instead of fake SUCCESS. Genuine fares in DB from earlier runs.
  - **Air India: BLOCKED** — form SUBMITS after OneTrust/combobox fixes, but results carry no priced fares → official API needed. Self-selects real Chrome (bundled build gets TLS-hung); deep link 404s so form-only.
  - **IndiGo: BLOCKED (flaky gating)** — submits on stock Chromium with no priced fares; widget doesn't render under real Chrome. NDC/API recommended. (Do NOT set `APIX_PLAYWRIGHT_CHANNEL=chrome` globally — it breaks IndiGo.)
  - **Parked (affiliate/NDC keys required): MMT / Goibibo / AIX / Yatra** (`provider_apis.py` → `no_data`; opt-in `APIX_SCRAPE_PARKED=true` form attempts exist for these four ONLY, Yatra form-only with no XHR fallback). **Ixigo has no opt-in** — official API only, robots + reCAPTCHA.
  - Shared helper `forms/_common.py` (valid-CSS popup dismissal, bare-code suggestion fallback, real-Chrome retry on TLS-fingerprint resets, scroll + second-chance settle);
    `scraper/live.py` (`launch_browser`, `goto_with_retry`, scoped-first `resolve_fares` killing fee-text false positives).
  - Registry: `scraper/form_flows.py` (`live` / `form_scaffold` / `api_only`).
- The rest need, in order of leverage: (1) residential proxies for high-volume failover,
  (2) official airline NDC / OTA affiliate APIs for production deployment without anti-bot constraints.

## Reproducing
`./venv/bin/python -m scraper.audit DEL BOM --window 7 [--with-proxies]`

All live fetches run Playwright headless Chromium with stealth patches
(`scraper/live.py`: webdriver/plugins/languages/chrome-runtime shims,
en-IN locale, `--disable-http2`) — this lifted EMT/SpiceJet page loads but
does not defeat Akamai/PerimeterX/reCAPTCHA.
