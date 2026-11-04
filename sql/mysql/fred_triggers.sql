-- ============================================================================
--  FRED Metadata Catalog : triggers, function and procedures (MySQL 8 / MariaDB)
--  PostgreSQL original: ../fred_triggers.sql
--
--  Run with the mysql client (it understands DELIMITER):
--      mysql fred_mysql < sql/mysql/fred_triggers.sql
--
--  The one real difference from PostgreSQL is the vintage rule. In PostgreSQL
--  a BEFORE INSERT trigger on OBSERVATION updates OBSERVATION to close the
--  prior vintage. MySQL forbids a trigger from modifying the table it is
--  defined on (error 1442, "Can't update table 'observation' in stored
--  function/trigger because it is already used by statement which invoked
--  this stored function/trigger"). So in MySQL the rule is enforced by a
--  stored procedure, add_vintage(), which closes the open vintage and inserts
--  the new one inside one transaction. New vintages go through add_vintage();
--  the bulk copy from PostgreSQL (load_from_postgres.sh) inserts rows whose
--  realtime_end is already correct, so it does not need it.
-- ============================================================================

DROP PROCEDURE IF EXISTS add_vintage;
DROP TRIGGER   IF EXISTS refresh_series_range;
DROP FUNCTION  IF EXISTS value_as_of;
DROP PROCEDURE IF EXISTS post_release;

DELIMITER //

-- ---------------------------------------------------------------------------
--  PROCEDURE : enforce the vintage rule (business rule 11)
--  "A revision never overwrites a value: it closes the prior vintage by
--   setting its realtime end date and adds a new vintage."
-- ---------------------------------------------------------------------------
CREATE PROCEDURE add_vintage(IN p_series   VARCHAR(40),
                             IN p_obs_date DATE,
                             IN p_start    DATE,
                             IN p_value    DECIMAL(24,8))
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;
    START TRANSACTION;
    -- close the vintage that is still current for this period
    UPDATE observation
       SET realtime_end = DATE_SUB(p_start, INTERVAL 1 DAY)
     WHERE series_id        = p_series
       AND observation_date = p_obs_date
       AND realtime_end     = '9999-12-31'
       AND realtime_start   < p_start;
    -- add the new vintage as the current one
    INSERT INTO observation (series_id, observation_date, realtime_start, realtime_end, value)
    VALUES (p_series, p_obs_date, p_start, '9999-12-31', p_value);
    COMMIT;
END //


-- ---------------------------------------------------------------------------
--  TRIGGER : keep the derived SERIES attributes consistent
--  observation_start / observation_end are controlled denormalization.
--  AFTER INSERT on OBSERVATION updates SERIES (a different table, so this
--  one is allowed as a trigger in MySQL).
-- ---------------------------------------------------------------------------
CREATE TRIGGER refresh_series_range
AFTER INSERT ON observation
FOR EACH ROW
BEGIN
    UPDATE series
       SET observation_start = LEAST(COALESCE(observation_start, NEW.observation_date), NEW.observation_date),
           observation_end   = GREATEST(COALESCE(observation_end, NEW.observation_date), NEW.observation_date)
     WHERE series_id = NEW.series_id;
END //


-- ---------------------------------------------------------------------------
--  FUNCTION : value of a series as of a given date (vintage lookup)
-- ---------------------------------------------------------------------------
CREATE FUNCTION value_as_of(p_series VARCHAR(40), p_obs_date DATE, p_as_of DATE)
RETURNS DECIMAL(24,8)
READS SQL DATA
BEGIN
    RETURN (SELECT value
              FROM observation
             WHERE series_id = p_series
               AND observation_date = p_obs_date
               AND p_as_of BETWEEN realtime_start AND realtime_end
             LIMIT 1);
END //


-- ---------------------------------------------------------------------------
--  PROCEDURE : mark a release date as actual once the release posts
--  (and stamp last_updated on every series in that release)
-- ---------------------------------------------------------------------------
CREATE PROCEDURE post_release(IN p_release_id INTEGER, IN p_date DATE)
BEGIN
    UPDATE release_date SET date_status = 'actual'
     WHERE release_id = p_release_id AND release_date = p_date;
    UPDATE series SET last_updated = CURRENT_TIMESTAMP
     WHERE release_id = p_release_id;
END //

DELIMITER ;
