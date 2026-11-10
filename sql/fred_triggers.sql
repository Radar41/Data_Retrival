-- ============================================================================
--  FRED Metadata Catalog : triggers and procedures (Week 10 material)
--  PostgreSQL syntax. MySQL equivalents follow each object in comments.
-- ============================================================================

-- ---------------------------------------------------------------------------
--  TRIGGER 1 : enforce the vintage rule (business rule 11)
--  "A revision never overwrites a value: it closes the prior vintage by
--   setting its realtime end date and adds a new vintage."
--  BEFORE INSERT on OBSERVATION: close any open vintage for the same
--  (series, observation_date) by setting realtime_end to the day before the
--  new vintage starts. The application never has to remember to do this.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_close_prior_vintage() RETURNS trigger AS $$
BEGIN
    UPDATE observation
       SET realtime_end = NEW.realtime_start - INTERVAL '1 day'
     WHERE series_id        = NEW.series_id
       AND observation_date = NEW.observation_date
       AND realtime_end     = DATE '9999-12-31'
       AND realtime_start   < NEW.realtime_start;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER close_prior_vintage
BEFORE INSERT ON observation
FOR EACH ROW EXECUTE FUNCTION trg_close_prior_vintage();

-- MySQL 8 version:
-- DELIMITER //
-- CREATE TRIGGER close_prior_vintage BEFORE INSERT ON observation
-- FOR EACH ROW
-- BEGIN
--   UPDATE observation
--      SET realtime_end = DATE_SUB(NEW.realtime_start, INTERVAL 1 DAY)
--    WHERE series_id = NEW.series_id AND observation_date = NEW.observation_date
--      AND realtime_end = '9999-12-31' AND realtime_start < NEW.realtime_start;
-- END //
-- DELIMITER ;


-- ---------------------------------------------------------------------------
--  TRIGGER 2 : keep the derived SERIES attributes consistent
--  observation_start / observation_end are controlled denormalization.
--  AFTER INSERT on OBSERVATION: widen the series range if needed.
--  Statement-level with a transition table: one UPDATE per series per INSERT
--  statement, not one per row. A per-row version updates the same series row
--  once per vintage; inside one transaction every update leaves a new row
--  version the next one must step over, so a 1,051,467-row series (ANFCI)
--  ran for hours. The loader inserts a whole series in one statement.
--  MySQL has no statement-level triggers; sql/mysql keeps the per-row form.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_refresh_series_range() RETURNS trigger AS $$
BEGIN
    UPDATE series s
       SET observation_start = LEAST(COALESCE(s.observation_start, n.lo), n.lo),
           observation_end   = GREATEST(COALESCE(s.observation_end, n.hi), n.hi)
      FROM (SELECT series_id, MIN(observation_date) AS lo, MAX(observation_date) AS hi
              FROM new_rows GROUP BY series_id) n
     WHERE s.series_id = n.series_id;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS refresh_series_range ON observation;
CREATE TRIGGER refresh_series_range
AFTER INSERT ON observation
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT EXECUTE FUNCTION trg_refresh_series_range();


-- ---------------------------------------------------------------------------
--  FUNCTION : value of a series as of a given date (vintage lookup)
--  Returns the value that was current on 'as_of' for 'obs_date'.
--  Demonstrates a function (returns a value) vs. a procedure (performs work).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION value_as_of(p_series VARCHAR, p_obs_date DATE, p_as_of DATE)
RETURNS DECIMAL AS $$
    SELECT value
      FROM observation
     WHERE series_id = p_series
       AND observation_date = p_obs_date
       AND p_as_of BETWEEN realtime_start AND realtime_end
     LIMIT 1;
$$ LANGUAGE sql STABLE;


-- ---------------------------------------------------------------------------
--  PROCEDURE : mark a release date as actual once the release posts
--  (and stamp last_updated on every series in that release)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE post_release(p_release_id INTEGER, p_date DATE)
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE release_date SET date_status = 'actual'
     WHERE release_id = p_release_id AND release_date = p_date;
    UPDATE series SET last_updated = CURRENT_TIMESTAMP
     WHERE release_id = p_release_id;
END;
$$;
