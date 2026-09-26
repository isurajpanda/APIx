# Scrape checklist — which sites are working right now

Full live audit 2026-10-04, DEL-BOM T+7, residential IP (11/11 sources,
`APIX_SCRAPER_MOCK=false`; real-Chrome channel forced fleet-wide for that run —
note the per-spider channel lesson below). Prior datacenter audit in
`LIVE_STATUS.md` was harsher. The robots gate (`scraper/base.py`, path-aware)
enforces the PARKED rows — do not override it.

| # | Site (source) | Live path in code | Robots on target | Audit result 2026-10-04 | Verdict |
|---|---|---|---|---|---|
| 1 | EaseMyTrip (`easemytrip`) | homepage form `scraper/emt.py` | ✅ allowed | ✅ SUCCESS 1,662 (920 seen) — **suspect**: zero fare-element matches, fee/coupon soup. Now guarded: `resolve_emt_fares()` reports SoldOut instead of fake SUCCESS | **WORKING (guarded)** — genuine fares in DB from earlier runs |
| 2 | Akasa Air (`akasa_direct`) | homepage form `scraper/forms/akasa.py` | ✅ allowed | ✅ **SUCCESS 3,500 (25 seen, round 3) / 3,500 (2 seen, audit)** | **WORKING** |
| 3 | SpiceJet (`spicejet_direct`) | homepage form `scraper/forms/spicejet.py` | ✅ allowed (never `/api/v1`) | ✅ **SUCCESS 3,000 (15 seen)** | **WORKING** |
| 4 | Cleartrip (`cleartrip`) | homepage form + `/flights/results` fallback, scoped-first rule | ✅ (never `/flights/search*`) | ✅ **SUCCESS 3,500 (3 seen)** — thin, needs confirmation | **PROVISIONAL** |
| 5 | Air India (`airindia_direct`) | homepage form `scraper/forms/airindia.py`, form-only, self-selects real Chrome | ⚠️ CLI fetch times out → fail-open | ⚠️ SOLD_OUT — form SUBMITS (OneTrust/combobox fixes), results carry no priced fares | **BLOCKED — needs official API** |
| 6 | IndiGo (`indigo_direct`) | homepage form `scraper/forms/indigo.py` + dead deep-link fallback (404s) | ⚠️ fail-open | ⚠️ stock Chromium: submits, no fares; real Chrome: widget doesn't render (1 hidden input) | **BLOCKED (flaky gating) — NDC/API recommended** |
| 7 | Yatra (`yatra`) | affiliate API only (`YATRA_*`) | homepage reachable, no mappable form | PARKED (Diya-AI redesign; XHR challenged, never fetched) | **PARKED — needs `YATRA_API_KEY`** |
| 8 | Ixigo (`ixigo`) | official API only `scraper/ixigo_api.py` — no backdoor | ❌ `/search/result/` DISALLOWED → gate parks it | `robots_disallowed` | **PARKED — needs `IXIGO_API_KEY`** |
| 9 | Goibibo (`goibibo`) | affiliate API only | ❌ search path DISALLOWED → gate parks it | `robots_disallowed` | **PARKED — needs `GOIBIBO_API_KEY`** |
| 10 | MakeMyTrip (`makemytrip`) | affiliate API only | ⚠️ fail-open, TLS-resets automation | PARKED (no keys) | **PARKED — needs `MMT_API_KEY`** |
| 11 | Air India Express (`airindia_express`) | official API only | n/a — reCAPTCHA Enterprise | PARKED (no keys) | **PARKED — needs `AIX_API_KEY`; never solve CAPTCHA** |

**Audit score: 4 SUCCESS (2 solid + 1 provisional + 1 suspect-now-guarded), 2 content-blocked, 5 parked. 0 crashes.**

## Channel lesson (important for the next run)

Forcing `APIX_PLAYWRIGHT_CHANNEL=chrome` fleet-wide HURT IndiGo (widget renders
on stock Chromium, not on real Chrome) while Air India NEEDS real Chrome
(bundled build gets TLS-hung). So: **do not set the env globally** — Air India
self-selects it via `preferred_channel="chrome"` in `forms/airindia.py`.
Next audit command is the plain one below.

## Operator checklist

### Working today (no action)
- [x] EaseMyTrip end-to-end (guarded against fee-text; genuine fares in DB)
- [x] Akasa Air end-to-end (Rs 3,500 DEL-BOM T+7, confirmed twice)
- [x] SpiceJet end-to-end (Rs 3,000 DEL-BOM T+7, 15 fares)
- [x] `APIX_SCRAPER_MOCK=true` demo path intact (11/11 mock quotes ok)
- [x] Robots gate parks Ixigo/Goibibo; no backdoor exists for Ixigo

### To confirm / activate
- [ ] Cleartrip: re-run audit once more (n=3 is thin) → confirm fares persist
- [ ] Air India / IndiGo / SpiceJet-content: pursue NDC/direct API partnerships
- [ ] Yatra / Ixigo / Goibibo / MMT / AIX: obtain affiliate/NDC keys → fill `*_API_URL` in `.env` → re-run audit

### Never do (policy guardrails)
- [ ] Never scrape Ixigo `/search/result/` or solve its reCAPTCHA (no backdoor; gate enforces `robots_disallowed`)
- [ ] Never scrape Cleartrip `/flights/search*` (only homepage form + `/flights/results`)
- [ ] Never hit Yatra's challenged XHR trigger directly (Yatra backdoor is form-only by construction)
- [ ] Never set `APIX_PLAYWRIGHT_CHANNEL=chrome` globally (breaks IndiGo); per-spider preference only
- [ ] Never add CAPTCHA-solving, PerimeterX/Akamai bypass, or proxy-rotation-to-evade logic

## Commands

```bash
# Full wiring check (no network scraping, mock-safe)
python -m pytest -q
# Live audit, one route x 11 sources (respects robots by default; Air India
# self-selects real Chrome — no global channel env needed)
APIX_SCRAPER_MOCK=false python -m scraper.audit DEL BOM --window 7
# Scheduler stays mock-safe by default; live only with legal clearance
python -m scraper.scheduler --once
```
