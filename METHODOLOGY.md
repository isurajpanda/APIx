# METHODOLOGY — APIx index

## Formula (Laspeyres-style)
For route `i`, day `t`, with base period B (first 7 days of collection):

- `avg_fare(i,t)` = mean of priced (available, non-outlier) fares.
- `price_relative(i,t) = avg_fare(i,t) / avg_fare(i,B)`
- `APIx(t) = 100 × Σ weight(i) × price_relative(i,t)`

Routes missing data on day `t` are excluded and remaining weights
renormalized (equivalent to imputing the index-average relative — standard
practice for temporarily missing items; see ILO CPI Manual §7).

## Weights
Share of DGCA domestic passenger traffic per city-pair (see DGCA Monthly
Domestic Air Traffic Reports; prototype weights in `scraper/routes.yaml`,
summing to 1.0; replace with exact DGCA shares before official use).

## Base period
First 7 days of collection, normalized to 100. Fixed thereafter; any
re-basing is recorded via `methodology_version` (old rows never overwritten).

## Granularities
Daily (native, stored in `daily_index`), weekly = 7-day rolling mean,
monthly = 30-day rolling mean — both derived at query time from daily rows
(`index/compute.py: rolling_average`, applied in `backend/main.py`).

## Relation to theory
Pure Laspeyres with fixed base-period weights (CPI-consistent). A Fisher
variant (geometric mean of Laspeyres/Paasche) is possible once quantity data
per route-day is available; Laspeyres chosen for interpretability and for
compatibility with CPI compilation practice.

## Elasticity
Per-route mean fare by advance-purchase window (T+1..T+45); descriptive curve
only, not a causal estimate.

## Problem-statement mapping (MoSPI PS 26056)
- "index-construction module based on PSD given routes and weights" — the
  Laspeyres-style weighted price-relative formula above, parameterised by the
  6-route DGCA-traffic basket and weights in `scraper/routes.yaml`.
- "JS-rendered pages, CAPTCHAs, anti-bot, IP rotation, session management" —
  Playwright headless Chromium with stealth patches (`scraper/live.py`), a
  per-host robots gate, politeness delays, and a free-proxy failover pool
  (`scraper/proxies.py`). Each run uses a fresh isolated browser context
  (cookie jar + storage state per scrape) — sessions are deliberately
  short-lived so no cross-source session leakage; form flows persist only
  within a single search.
- "removes outliers, handles missing values, cancellations/sold-out, separates
  base fare from taxes, UDF and convenience charges" — `pipeline/clean.py`
  (3-SD outlier rule, no_data marking, availability split, fare decomposition).
- "at least 30 days of back-tested results against publicly available DGCA
  monthly average-fare data" — `dgca/backtest.py` compares the APIx monthly
  index against the published DGCA series (`dgca_data/dgca_monthly_avg_fare.csv`)
  and writes `backtest_report.md`; it refuses to quote a correlation until
  the real benchmark file is supplied.
- "fare-class" — all live scrapers target Economy cabin (the CPI-relevant
  class); the `fares` table carries a `fare_class` column for future
  multi-class extension.
