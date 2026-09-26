# SCRAPING_ETHICS

- Rate limits: ≥2s delay between requests, 1 concurrent request per domain
  (`scraper/routes.yaml → politeness`; audit uses 2.0s too).
- `robots.txt` checked path-aware before every source run
  (`BaseScraper.check_robots` on the exact search URL, not just the domain
  root); disallowed paths are logged as `robots_disallowed` and skipped.
  Ixigo `/search/result/` is disallowed → parked by the gate (no override flag
  fetches it; `--ignore-robots` only reports the decision).
- Prefer OTA internal JSON/XHR endpoints over full browser rendering to
  minimize server load.
- ToS: airline/OTA ToS typically restrict automated collection; this
  prototype defaults to `APIX_SCRAPER_MOCK=true` (synthetic quotes, no live
  hits). Enable live scraping only with legal clearance, and throttle further.
  Currently live: EaseMyTrip only (form-driven flow, `scraper/emt.py`);
  per-platform audit status in `LIVE_STATUS.md`.
- Stealth: live fetches use stock Chrome UA, webdriver/plugins/languages
  shims, en-IN locale, HTTP/1.1 fallback (`scraper/live.py`). This is
  fingerprint minimization, not circumvention.
- No CAPTCHA solving: sources gating on reCAPTCHA (Ixigo, Air India Express)
  are parked, never bypassed. CAPTCHA → status `captcha_blocked`.
- Ixigo rule (explicit): no scraping of `/search/result/`, no CAPTCHA solving,
  no PerimeterX/bot-mitigation bypass, no proxy trick to evade the gate.
  Compliant path only: official Ixigo affiliate/API via `scraper/ixigo_api.py`
  (`IXIGO_API_KEY`/`IXIGO_API_URL`). Without credentials the Ixigo quote is
  recorded as parked `no_data` — never a fabricated fare.
- Per-provider arrangements: `scraper/form_flows.py` registry (live / scaffold /
  api_only / parked) + notes in `scraper/routes.yaml`.
- Kill-switch: set any source to `false` under `enabled_sources` in
  `scraper/routes.yaml` to disable it instantly.
- CAPTCHA → status `captcha_blocked`, skip without retry-storm; sold-out →
  `sold_out` (kept as availability metric, never priced as zero).

## Proxy pool (40x failover)

- Source: proxifly free-proxy IN list (socks4/socks5/http; `PROXY_LIST_URL`).
- Direct requests always go out on our own IP first. Only when a site returns
  HTTP 40x (403/429 → `BlockedByStatus`) does the scraper fail over **once**
  to the fastest checked proxy — no retry storms through free proxies.
- `scraper/proxies.py` re-fetches the list and re-checks every entry against
  `http://checkip.amazonaws.com/` every `PROXY_REFRESH_HOURS` (default 3h,
  matching upstream refresh cadence); results are upserted into the `proxies`
  table ordered by latency, dead entries marked `working=false` with
  `fail_count+1`. No extra dependencies: SOCKS4/5 handshakes are implemented
  on stdlib sockets.
- Free proxies are untrusted third parties: traffic is limited to public
  fare-search pages (no credentials ever sent through a proxy).
