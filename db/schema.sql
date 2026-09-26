-- APIx schema (PostgreSQL 15+; TimescaleDB optional but recommended).
-- On hosts without TimescaleDB (e.g. native Windows, where no official build
-- ships), everything below still applies cleanly on plain PostgreSQL: the app
-- only queries plain tables, hypertables/continuous aggregates are a speedup.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
        CREATE EXTENSION IF NOT EXISTS timescaledb;
    ELSE
        RAISE NOTICE 'timescaledb not available - continuing on plain PostgreSQL';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS fares (
    id                          BIGSERIAL,
    scrape_timestamp            TIMESTAMPTZ NOT NULL,
    flight_date                 DATE NOT NULL,
    origin                      TEXT NOT NULL,
    destination                 TEXT NOT NULL,
    carrier                     TEXT NOT NULL,
    fare_class                  TEXT,
    advance_purchase_window     INTEGER NOT NULL,
    base_fare                   NUMERIC(10,2),
    taxes                       NUMERIC(10,2),
    udf                         NUMERIC(10,2),
    convenience_fee             NUMERIC(10,2),
    total_fare                  NUMERIC(10,2) NOT NULL,
    source                      TEXT NOT NULL,
    decomposition_available     BOOLEAN DEFAULT FALSE,
    is_outlier                  BOOLEAN DEFAULT FALSE,
    availability_status         TEXT DEFAULT 'available',
    created_at                  TIMESTAMPTZ DEFAULT now()
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable('fares', 'scrape_timestamp');
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uniq_fare_key ON fares
    (origin, destination, carrier, flight_date, advance_purchase_window, source, scrape_timestamp);

CREATE TABLE IF NOT EXISTS routes (
    route_id     SERIAL PRIMARY KEY,
    origin       TEXT NOT NULL,
    destination  TEXT NOT NULL,
    weight       NUMERIC(6,4) NOT NULL,
    active       BOOLEAN DEFAULT TRUE,
    UNIQUE (origin, destination)
);

CREATE TABLE IF NOT EXISTS daily_index (
    index_date          DATE PRIMARY KEY,
    index_value         NUMERIC(10,4) NOT NULL,
    methodology_version TEXT NOT NULL,
    base_period          DATE NOT NULL,
    computed_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_fare_quotes (
    id                       BIGSERIAL PRIMARY KEY,
    source                   TEXT NOT NULL,
    origin                   TEXT NOT NULL,
    destination              TEXT NOT NULL,
    carrier                  TEXT,
    advance_purchase_window  INTEGER,
    scrape_timestamp         TIMESTAMPTZ NOT NULL,
    raw_payload              JSONB NOT NULL,
    status                   TEXT NOT NULL
);

-- Free-proxy pool (checked against checkip.amazonaws.com, fastest first)
CREATE TABLE IF NOT EXISTS proxies (
    endpoint     TEXT PRIMARY KEY, -- e.g. 'socks5://1.2.3.4:1080'
    scheme       TEXT NOT NULL,    -- socks4 / socks5 / http
    latency_ms   INTEGER,          -- last successful check latency (NULL = dead)
    working      BOOLEAN DEFAULT FALSE,
    last_checked TIMESTAMPTZ,
    fail_count   INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_proxies_working_latency ON proxies (working, latency_ms);

-- Continuous aggregates (TimescaleDB only; skipped on plain PostgreSQL)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        CREATE MATERIALIZED VIEW IF NOT EXISTS avg_fare_daily
        WITH (timescaledb.continuous) AS
        SELECT time_bucket('1 day', scrape_timestamp) AS bucket, origin, destination,
               AVG(total_fare) AS avg_fare, COUNT(*) AS n
        FROM fares WHERE availability_status = 'available' AND is_outlier = FALSE
        GROUP BY bucket, origin, destination
        WITH NO DATA;

        CREATE MATERIALIZED VIEW IF NOT EXISTS avg_fare_weekly
        WITH (timescaledb.continuous) AS
        SELECT time_bucket('7 days', scrape_timestamp) AS bucket, origin, destination,
               AVG(total_fare) AS avg_fare, COUNT(*) AS n
        FROM fares WHERE availability_status = 'available' AND is_outlier = FALSE
        GROUP BY bucket, origin, destination
        WITH NO DATA;

        CREATE MATERIALIZED VIEW IF NOT EXISTS avg_fare_monthly
        WITH (timescaledb.continuous) AS
        SELECT time_bucket('30 days', scrape_timestamp) AS bucket, origin, destination,
               AVG(total_fare) AS avg_fare, COUNT(*) AS n
        FROM fares WHERE availability_status = 'available' AND is_outlier = FALSE
        GROUP BY bucket, origin, destination
        WITH NO DATA;
    END IF;
END $$;
