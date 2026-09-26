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
Daily (native), weekly = 7-day rolling mean, monthly = 30-day rolling mean.

## Relation to theory
Pure Laspeyres with fixed base-period weights (CPI-consistent). A Fisher
variant (geometric mean of Laspeyres/Paasche) is possible once quantity data
per route-day is available; Laspeyres chosen for interpretability and for
compatibility with CPI compilation practice.

## Elasticity
Per-route mean fare by advance-purchase window (T+1..T+45); descriptive curve
only, not a causal estimate.
