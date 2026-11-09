-- C3 lab: what FRED would look like WITH a supertype/subtype (EERD) design.
-- Runs in a scratch schema and cleans up after itself; production tables are only read.
--   psql -d fred -f labs/c3_subtype_sketch.sql
--
-- Design being sketched (deliberately NOT the production model):
--   supertype SERIES_SUP  (series_id, title, freq_type)   freq_type = discriminator
--   subtype   SERIES_MONTHLY   (series_id PK/FK, month_lag)       -- attributes only monthly series have
--   subtype   SERIES_QUARTERLY (series_id PK/FK, fiscal_q_start)  -- attributes only quarterly series have
--   Disjoint (a series is one frequency), partial completeness (A and SA series have no subtype).

DROP SCHEMA IF EXISTS lab_c3 CASCADE;
CREATE SCHEMA lab_c3;
SET search_path = lab_c3, public;

CREATE TABLE series_sup (
    series_id  VARCHAR(40) PRIMARY KEY,
    title      VARCHAR(300) NOT NULL,
    freq_type  VARCHAR(4)   NOT NULL,                        -- discriminator
    CONSTRAINT uq_series_sup_type UNIQUE (series_id, freq_type)  -- lets subtypes pin the type
);

-- Each subtype carries the discriminator value it is allowed to have: this is what
-- makes the specialization DISJOINT in SQL (a row can't be in both subtypes).
CREATE TABLE series_monthly (
    series_id  VARCHAR(40) PRIMARY KEY,
    freq_type  VARCHAR(4) NOT NULL DEFAULT 'M' CHECK (freq_type = 'M'),
    month_lag  SMALLINT,                                     -- invented subtype attribute
    FOREIGN KEY (series_id, freq_type) REFERENCES series_sup (series_id, freq_type) ON DELETE CASCADE
);
CREATE TABLE series_quarterly (
    series_id      VARCHAR(40) PRIMARY KEY,
    freq_type      VARCHAR(4) NOT NULL DEFAULT 'Q' CHECK (freq_type = 'Q'),
    fiscal_q_start SMALLINT,                                 -- invented subtype attribute
    FOREIGN KEY (series_id, freq_type) REFERENCES series_sup (series_id, freq_type) ON DELETE CASCADE
);

INSERT INTO series_sup SELECT series_id, title, frequency_code FROM public.series;
INSERT INTO series_monthly (series_id)   SELECT series_id FROM series_sup WHERE freq_type = 'M';
INSERT INTO series_quarterly (series_id) SELECT series_id FROM series_sup WHERE freq_type = 'Q';

-- 1. How many rows landed where (partial completeness: A and SA have no subtype)
SELECT 'supertype' AS t, count(*) FROM series_sup
UNION ALL SELECT 'monthly',   count(*) FROM series_monthly
UNION ALL SELECT 'quarterly', count(*) FROM series_quarterly
UNION ALL SELECT 'no subtype', count(*) FROM series_sup s
          WHERE NOT EXISTS (SELECT 1 FROM series_monthly m WHERE m.series_id = s.series_id)
            AND NOT EXISTS (SELECT 1 FROM series_quarterly q WHERE q.series_id = s.series_id);

-- 2. Disjointness is enforced: putting a monthly series into the quarterly subtype fails
DO $$
BEGIN
  INSERT INTO series_quarterly (series_id) VALUES ('UNRATE');
  RAISE NOTICE 'UNEXPECTED: insert succeeded';
EXCEPTION WHEN foreign_key_violation THEN
  RAISE NOTICE 'disjoint rule held: UNRATE (M) cannot be a quarterly subtype row';
END $$;

-- 3. Reading a subtype means a join back to the supertype
SELECT s.series_id, s.title, m.month_lag
FROM series_sup s JOIN series_monthly m USING (series_id)
WHERE s.series_id = 'UNRATE';

RESET search_path;
DROP SCHEMA lab_c3 CASCADE;
