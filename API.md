# API reference (summary; full schema at `/docs` Swagger UI)

Auth: header `X-API-Key: <APIX_API_KEY>` on all endpoints except `/api/v1/health`.
Caching: Memcached (fallback: in-process), TTL 300s.

| Endpoint | Params | Returns |
|---|---|---|
| `GET /api/v1/index/daily` | `start,end` (YYYY-MM-DD) | `{granularity, series:[{index_date,index_value,methodology_version,base_period}]}` |
| `GET /api/v1/index/weekly` | same | 7-day sampled series |
| `GET /api/v1/index/monthly` | same | 30-day sampled series |
| `GET /api/v1/routes` | — | basket + weights |
| `GET /api/v1/fares/heatmap` | — | latest avg fare per route |
| `GET /api/v1/fares/elasticity/{route_id}` | route 1–6 | price vs window T+1..T+45 |
| `GET /api/v1/health` | — | DB status + last scrape |
