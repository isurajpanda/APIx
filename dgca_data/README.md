# DGCA benchmark data

This directory holds the **published DGCA monthly average domestic fare** series
used to back-test the APIx index, as required by problem statement 26056:

> "demonstrate at least 30 days of back-tested results against publicly
> available DGCA monthly average-fare data"

## File

`dgca_monthly_avg_fare.csv` — one row per calendar month:

```csv
month,avg_fare_inr
2026-01,5123.45
2026-02,5280.10
```

- `month` — `YYYY-MM` of the DGCA reporting period
- `avg_fare_inr` — published all-route average domestic fare for that month

## Where to download (published sources)

1. **eSankhyiki (MoSPI open-data portal)** — https://esankhyiki.mospi.gov.in
   Search for DGCA / aviation / airfare datasets (the link cited in the problem
   statement).
2. **DGCA — Data & Reports → Aviation Data and Statistics → Air Transport →
   Domestic Air Transport → Monthly/Annual statistics**
   (https://www.dgca.gov.in/digigov-portal) — monthly city-pair passenger
   traffic and airfare-monitoring tables (PDF/Excel). DGCA publishes average
   airfare for 72 domestic routes monthly (see DGCA tariff-monitoring
   releases and MoSPI parliamentary replies citing them).
3. **DGCA Monthly Domestic Air Traffic Reports** — route-level passenger
   traffic for basket weights.

The portal pages are JavaScript-rendered; download the files through a browser
and drop the CSV above. Do NOT fabricate the benchmark — `dgca.backtest`
refuses to quote a correlation when the file is absent.

## Route-level DGCA traffic (for weights)

`dgca_city_pair_traffic.csv` (optional, same folder):

```csv
origin,destination,monthly_passengers
DEL,BOM,123456
```

Used to set `routes.weight` from actual DGCA passenger traffic shares.
