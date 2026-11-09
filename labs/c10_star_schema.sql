-- labs/c10_star_schema.sql
-- C10 lab: a star schema over the FRED vintage store, built in its own schema
-- (lab_c10) so the production model in public (sql/fred_schema.sql) is never
-- touched. Safe to rerun: it drops and rebuilds lab_c10.
--
--   psql -d fred -f labs/c10_star_schema.sql
--   psql -d fred -c 'DROP SCHEMA lab_c10 CASCADE'      -- remove it
--
-- Grain of the fact table: ONE ROW PER SERIES PER OBSERVATION PERIOD.
-- The OLTP table public.observation stores one row per *vintage*
-- (series, period, realtime_start); the warehouse rolls the vintages up so
-- analysts can ask "what is the value now, what was first printed, and how
-- often was it revised" without touching the realtime columns.

BEGIN;

DROP SCHEMA IF EXISTS lab_c10 CASCADE;
CREATE SCHEMA lab_c10;
SET search_path = lab_c10, public;

-- Dimension: date (one row per calendar period that has data)
CREATE TABLE dim_date (
    date_key      DATE        PRIMARY KEY,
    year          SMALLINT    NOT NULL,
    quarter       SMALLINT    NOT NULL,
    month         SMALLINT    NOT NULL,
    month_name    VARCHAR(9)  NOT NULL,
    decade        SMALLINT    NOT NULL
);
INSERT INTO dim_date
SELECT d, EXTRACT(YEAR FROM d), EXTRACT(QUARTER FROM d), EXTRACT(MONTH FROM d),
       TRIM(TO_CHAR(d, 'Month')), (EXTRACT(YEAR FROM d)::int / 10) * 10
FROM (SELECT DISTINCT observation_date AS d FROM public.observation) x;

-- Dimension: release, denormalized with its sources (a star, not a snowflake:
-- the M:N release_source is flattened into one text attribute)
CREATE TABLE dim_release (
    release_id    INTEGER      PRIMARY KEY,
    release_name  VARCHAR(200) NOT NULL,
    source_names  TEXT
);
INSERT INTO dim_release
SELECT r.release_id, r.release_name,
       string_agg(s.source_name, '; ' ORDER BY s.source_name)
FROM public.release r
LEFT JOIN public.release_source rs ON rs.release_id = r.release_id
LEFT JOIN public.source s          ON s.source_id   = rs.source_id
GROUP BY r.release_id, r.release_name;

-- Dimension: series, with the three lookups folded in (denormalized on purpose)
CREATE TABLE dim_series (
    series_id      VARCHAR(40)  PRIMARY KEY,
    title          VARCHAR(300) NOT NULL,
    frequency_name VARCHAR(40)  NOT NULL,
    units_name     VARCHAR(120) NOT NULL,
    sa_name        VARCHAR(80)  NOT NULL
);
INSERT INTO dim_series
SELECT se.series_id, se.title, f.frequency_name, u.units_name, sa.sa_name
FROM public.series se
JOIN public.frequency f            ON f.frequency_code = se.frequency_code
JOIN public.units u                ON u.units_code     = se.units_code
JOIN public.seasonal_adjustment sa ON sa.sa_code       = se.sa_code;

-- Fact: one row per series per observation period
CREATE TABLE fact_observation (
    series_id         VARCHAR(40) NOT NULL REFERENCES dim_series (series_id),
    date_key          DATE        NOT NULL REFERENCES dim_date (date_key),
    release_id        INTEGER     NOT NULL REFERENCES dim_release (release_id),
    value_current     NUMERIC,              -- open vintage (realtime_end = 9999-12-31); NULL if none open
    value_first_print NUMERIC,              -- earliest vintage
    n_vintages        INTEGER     NOT NULL, -- additive measure: revisions = n_vintages - 1
    PRIMARY KEY (series_id, date_key)
);
INSERT INTO fact_observation
SELECT o.series_id, o.observation_date, se.release_id,
       MAX(o.value) FILTER (WHERE o.realtime_end = DATE '9999-12-31'),
       (ARRAY_AGG(o.value ORDER BY o.realtime_start))[1],
       COUNT(*)
FROM public.observation o
JOIN public.series se ON se.series_id = o.series_id
GROUP BY o.series_id, o.observation_date, se.release_id;

CREATE INDEX ix_fact_date    ON fact_observation (date_key);
CREATE INDEX ix_fact_release ON fact_observation (release_id);

-- Materialized view: revisions per release per year (a pre-computed cube slice)
CREATE MATERIALIZED VIEW mv_revisions_by_release_year AS
SELECT r.release_name, d.year,
       COUNT(*)                   AS periods,
       SUM(f.n_vintages - 1)      AS revisions,
       ROUND(AVG(f.n_vintages - 1), 2) AS avg_revisions_per_period
FROM fact_observation f
JOIN dim_release r ON r.release_id = f.release_id
JOIN dim_date d    ON d.date_key   = f.date_key
GROUP BY r.release_name, d.year;

COMMIT;

ANALYZE lab_c10.fact_observation;

-- ---------------------------------------------------------------- queries
-- A1  Row counts: OLTP vintages vs warehouse facts
SELECT 'public.observation' AS tbl, COUNT(*) FROM public.observation
UNION ALL SELECT 'lab_c10.fact_observation', COUNT(*) FROM lab_c10.fact_observation;

-- A2  ROLLUP: revisions by frequency and decade, with subtotals and a grand total
SELECT s.frequency_name, d.decade, SUM(f.n_vintages - 1) AS revisions
FROM lab_c10.fact_observation f
JOIN lab_c10.dim_series s ON s.series_id = f.series_id
JOIN lab_c10.dim_date d   ON d.date_key  = f.date_key
WHERE d.decade >= 2000
GROUP BY ROLLUP (s.frequency_name, d.decade)
ORDER BY s.frequency_name NULLS LAST, d.decade NULLS LAST;

-- A3  How much does the first print miss? UNRATE, current vs first print
SELECT COUNT(*) AS periods,
       ROUND(AVG(ABS(value_current - value_first_print)), 4) AS mean_abs_revision,
       MAX(ABS(value_current - value_first_print))           AS max_abs_revision
FROM lab_c10.fact_observation
WHERE series_id = 'UNRATE' AND value_current IS NOT NULL;

-- A4  regr_slope / corr: linear trend in monthly UNRATE since 2010 (per year)
SELECT ROUND(regr_slope(value_current, EXTRACT(EPOCH FROM date_key) / 31557600)::numeric, 4) AS slope_per_year,
       ROUND(corr(value_current, EXTRACT(EPOCH FROM date_key))::numeric, 4)                  AS corr_with_time,
       regr_count(value_current, EXTRACT(EPOCH FROM date_key))                                AS n
FROM lab_c10.fact_observation
WHERE series_id = 'UNRATE' AND date_key >= DATE '2010-01-01';

-- A5  Window aggregate: 12-month moving average of UNRATE, last 6 months
SELECT date_key, value_current,
       ROUND(AVG(value_current) OVER (ORDER BY date_key ROWS BETWEEN 11 PRECEDING AND CURRENT ROW), 3) AS ma12
FROM lab_c10.fact_observation
WHERE series_id = 'UNRATE'
ORDER BY date_key DESC
LIMIT 6;

-- A6  The materialized view: most-revised release-years
SELECT * FROM lab_c10.mv_revisions_by_release_year
ORDER BY revisions DESC LIMIT 5;
