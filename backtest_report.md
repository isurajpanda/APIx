# Back-test report — 30-day validation vs DGCA

## Setup
- APIx pipeline (generate → clean → Laspeyres index) backfilled for 45 days
  via `db/backfill.py --days 45`: **14,850 raw quotes → 14,549 fares →
  44 daily index rows (2026-08-13 … 2026-09-26)**, base period = first 7 days
  (=100). First value 97.12, last 107.16 (~+10% over the window with weekly
  cyclicality). Plus 3 genuine live EaseMyTrip quotes in `raw_fare_quotes`.
- DGCA benchmark: monthly average domestic fare series for overlapping
  routes (DGCA tariff-monitoring reports / data.gov.in / eSankhyiki), rebased
  to the same base for comparability. Prototype comparison uses a synthetic
  DGCA proxy with the same seasonal shape plus reporting noise; replace with
  the published figures before official adoption.

## Results (prototype)
- Dashboard → Back-test view overlays the DB-backed daily index vs its
  7-day rolling trend over the full 44-day window.
- DGCA monthly proxy series tracks the same direction; Pearson **r ≈ 0.93**
  on normalized levels (synthetic benchmark — recompute on published DGCA
  figures before official use).

## Divergence discussion (honest limitations)
1. DGCA publishes **monthly averages**; APIx is **daily** — intra-month
   volatility is invisible to DGCA by construction.
2. Weighting differs: DGCA route mix vs APIx 6-route DGCA-traffic basket.
3. Lead-time mix: APIx averages T+1..T+45 windows; DGCA reflects realized
   transaction mix (skewed to late bookings).
4. Mock-data caveat: this prototype report uses synthetic fares; correlation
   must be recomputed on live-scraped data.

## Verdict
Directionally consistent; methodology transparent. Proceed to live-data
validation with the exact DGCA dataset cited in METHODOLOGY.md.
