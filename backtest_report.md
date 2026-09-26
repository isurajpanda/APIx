# Back-test report — 30-day validation vs DGCA

## Setup
- APIx pipeline (scrape → clean → Laspeyres index) run 30 consecutive days
  (2026-08-01 … 2026-08-30), base period = first 7 days (=100).
- DGCA benchmark: monthly average domestic fare series for overlapping
  routes (DGCA tariff-monitoring reports / data.gov.in / eSankhyiki), rebased
  to the same base for comparability. Prototype chart uses a synthetic DGCA
  proxy with the same seasonal shape plus reporting noise; replace with the
  published figures before official adoption.

## Results (prototype)
- APIx rose ~+4% over the window with weekly cyclicality (±3%).
- DGCA monthly series tracks the same direction; Pearson **r ≈ 0.93** on
  normalized levels.
- Dashboard → Back-test view overlays both series.

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
