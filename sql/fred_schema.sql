-- ============================================================================
--  FRED Metadata Catalog : Physical Design (DDL)
--  Adrian Aziza  |  azizaa@bc.edu  |  ADIT2200-01 Database Management, Fall 2026
--
--  Source model  : approved ERD (16 entities: 3 associative, 3 weak, 2 unary)
--  Target DBMS   : PostgreSQL 16+ (tested clean on 16.15). MySQL 8 / MariaDB version: sql/mysql/fred_schema.sql
--  Normal form   : all relations in 3NF/BCNF (see fred_logical_design.md)
--
--  Conventions
--    * Natural keys from the FRED API are kept as primary keys (series_id such
--      as 'UNRATE' is stable and public), so no surrogate/auto-increment keys.
--    * Every constraint is named: pk_<table>, fk_<table>_<ref>, ck_<table>_<rule>
--    * Tables are created parent-first so every FOREIGN KEY can be declared
--      inline; DROP order at the end is the reverse.
--    * Lookup tables (FREQUENCY, UNITS, SEASONAL_ADJUSTMENT) hold the short
--      codes FRED returns (frequency_short, units_short, seasonal_adjustment_short).
-- ============================================================================


-- ---------------------------------------------------------------------------
--  1. LOOKUP (reference) TABLES
--     Small, stable code lists. Each code describes many series (1:M).
-- ---------------------------------------------------------------------------

-- FREQUENCY : how often a series is observed (FRED frequency_short values)
CREATE TABLE frequency (
    frequency_code   VARCHAR(4)    NOT NULL,            -- 'M', 'Q', 'A', 'W', 'D', 'BW', 'SA'
    frequency_name   VARCHAR(40)   NOT NULL,            -- 'Monthly', 'Quarterly', ...
    CONSTRAINT pk_frequency PRIMARY KEY (frequency_code)
);

-- UNITS : unit of measure (FRED units_short values)
CREATE TABLE units (
    units_code       VARCHAR(80)   NOT NULL,            -- '%', 'Bil. of $', 'Index 1982-84=100'
    units_name       VARCHAR(120)  NOT NULL,            -- 'Percent', 'Billions of Dollars', ...
    CONSTRAINT pk_units PRIMARY KEY (units_code)
);

-- SEASONAL_ADJUSTMENT : SA / NSA / SAAR (FRED seasonal_adjustment_short values)
CREATE TABLE seasonal_adjustment (
    sa_code          VARCHAR(8)    NOT NULL,            -- 'SA', 'NSA', 'SAAR'
    sa_name          VARCHAR(80)   NOT NULL,            -- 'Seasonally Adjusted', ...
    CONSTRAINT pk_seasonal_adjustment PRIMARY KEY (sa_code)
);


-- ---------------------------------------------------------------------------
--  2. PROVENANCE : who publishes what
-- ---------------------------------------------------------------------------

-- SOURCE : publishing agency (BLS, BEA, Census, Federal Reserve Board)
CREATE TABLE source (
    source_id        INTEGER       NOT NULL,            -- FRED source id (BLS = 22, BEA = 18)
    source_name      VARCHAR(200)  NOT NULL,
    source_link      VARCHAR(400),                      -- agency home page, may be absent
    CONSTRAINT pk_source PRIMARY KEY (source_id)
);

-- RELEASE : named publication (Employment Situation, Gross Domestic Product)
CREATE TABLE release (
    release_id       INTEGER       NOT NULL,            -- FRED release id (Employment Situation = 50)
    release_name     VARCHAR(200)  NOT NULL,
    press_release    BOOLEAN       NOT NULL DEFAULT TRUE,  -- FRED press_release flag
    release_link     VARCHAR(400),
    CONSTRAINT pk_release PRIMARY KEY (release_id)
);

-- RELEASE_SOURCE : associative entity resolving the M:N between RELEASE and
-- SOURCE (business rule 1: a release can be published jointly by several
-- agencies, and an agency publishes many releases). No identifier assigned,
-- so the two foreign keys form the composite primary key (MAPER step 4).
CREATE TABLE release_source (
    release_id       INTEGER       NOT NULL,
    source_id        INTEGER       NOT NULL,
    CONSTRAINT pk_release_source PRIMARY KEY (release_id, source_id),
    CONSTRAINT fk_release_source_release FOREIGN KEY (release_id)
        REFERENCES release (release_id) ON DELETE CASCADE,
    CONSTRAINT fk_release_source_source  FOREIGN KEY (source_id)
        REFERENCES source (source_id)  ON DELETE RESTRICT
);

-- RELEASE_DATE : WEAK entity. A date has no meaning apart from its release,
-- so the owner key migrates in and the primary key is (owner key + partial
-- identifier) per MAPER step 2. Business rule 2.
CREATE TABLE release_date (
    release_id       INTEGER       NOT NULL,
    release_date     DATE          NOT NULL,
    date_status      VARCHAR(10)   NOT NULL DEFAULT 'scheduled',  -- 'scheduled' | 'actual'
    CONSTRAINT pk_release_date PRIMARY KEY (release_id, release_date),
    CONSTRAINT fk_release_date_release FOREIGN KEY (release_id)
        REFERENCES release (release_id) ON DELETE CASCADE,
    CONSTRAINT ck_release_date_status CHECK (date_status IN ('scheduled', 'actual'))
);

-- RELEASE_TABLE_ELEMENT : the table tree FRED publishes for a release
-- (release/tables): section > table > header > series row. Business rule 12.
-- A regular entity (FRED's element_id is global) with a UNARY 1:M "contains"
-- mapped by a self-referencing foreign key (MAPER step 5A), as CATEGORY.
-- series_id is kept as text, not a foreign key: the catalog loads a subset
-- of each release's series, and the tree names all of them.
CREATE TABLE release_table_element (
    element_id       INTEGER       NOT NULL,            -- FRED element id
    release_id       INTEGER       NOT NULL,
    parent_id        INTEGER,                           -- NULL for a top-level section
    element_type     VARCHAR(8)    NOT NULL,            -- 'section' | 'table' | 'header' | 'series'
    element_name     VARCHAR(300)  NOT NULL,            -- section title, table title, row label
    element_level    SMALLINT      NOT NULL,            -- indentation level within its table
    line_no          INTEGER,                           -- line number in the published table
    series_id        VARCHAR(40),                       -- FRED series id on 'series' rows (no FK, see above)
    CONSTRAINT pk_release_table_element PRIMARY KEY (element_id),
    CONSTRAINT fk_rte_release FOREIGN KEY (release_id)
        REFERENCES release (release_id) ON DELETE RESTRICT,
    CONSTRAINT fk_rte_parent FOREIGN KEY (parent_id)
        REFERENCES release_table_element (element_id) ON DELETE RESTRICT,
    CONSTRAINT ck_rte_type CHECK (element_type IN ('section', 'table', 'header', 'series'))
);


-- ---------------------------------------------------------------------------
--  3. CLASSIFICATION : categories (hierarchy) and tags (grouped keywords)
-- ---------------------------------------------------------------------------

-- CATEGORY : topic hierarchy. UNARY 1:M relationship "Parent Of" is mapped by
-- a self-referencing foreign key (MAPER step 5A). Root category has NULL parent.
CREATE TABLE category (
    category_id      INTEGER       NOT NULL,            -- FRED category id (root = 0)
    category_name    VARCHAR(200)  NOT NULL,
    parent_id        INTEGER,                           -- NULL only for the root
    CONSTRAINT pk_category PRIMARY KEY (category_id),
    CONSTRAINT fk_category_parent FOREIGN KEY (parent_id)
        REFERENCES category (category_id) ON DELETE RESTRICT
);

-- TAG_GROUP : the kind of tag (FRED group_id: 'freq', 'gen', 'geo', 'geot',
-- 'rls', 'seas', 'src', 'cc'). Business rule 8.
CREATE TABLE tag_group (
    group_id         VARCHAR(8)    NOT NULL,
    group_name       VARCHAR(80)   NOT NULL,            -- 'Frequency', 'General', 'Geography', ...
    CONSTRAINT pk_tag_group PRIMARY KEY (group_id)
);

-- TAG : keyword label. tag_name is unique in FRED and is the natural key.
CREATE TABLE tag (
    tag_name         VARCHAR(120)  NOT NULL,
    group_id         VARCHAR(8)    NOT NULL,
    tag_notes        VARCHAR(400),
    popularity       SMALLINT,                          -- FRED 0-100 popularity score
    CONSTRAINT pk_tag PRIMARY KEY (tag_name),
    CONSTRAINT fk_tag_tag_group FOREIGN KEY (group_id)
        REFERENCES tag_group (group_id) ON DELETE RESTRICT
);


-- ---------------------------------------------------------------------------
--  4. SERIES : the central entity (one FRED time series)
-- ---------------------------------------------------------------------------

-- Business rules 3 and 4: each series belongs to exactly one release and has
-- exactly one frequency, one unit and one seasonal adjustment, so the four
-- "one side" keys migrate here as foreign keys (MAPER step 3A).
-- observation_start / observation_end are DERIVED from OBSERVATION (min/max
-- observation_date) and are kept as controlled denormalization: FRED serves
-- them directly, they are read in every catalog query, and they change only
-- when a release posts. A trigger (fred_triggers.sql) keeps them consistent.
CREATE TABLE series (
    series_id         VARCHAR(40)   NOT NULL,           -- 'UNRATE', 'GDPC1', 'CPIAUCSL'
    title             VARCHAR(300)  NOT NULL,
    release_id        INTEGER       NOT NULL,
    frequency_code    VARCHAR(4)    NOT NULL,
    units_code        VARCHAR(80)   NOT NULL,
    sa_code           VARCHAR(8)    NOT NULL,
    observation_start DATE,                             -- derived: MIN(observation_date)
    observation_end   DATE,                             -- derived: MAX(observation_date)
    last_updated      TIMESTAMP,                        -- FRED last_updated
    popularity        SMALLINT,
    notes             TEXT,                             -- free text from the agency
    CONSTRAINT pk_series PRIMARY KEY (series_id),
    CONSTRAINT fk_series_release   FOREIGN KEY (release_id)
        REFERENCES release (release_id)            ON DELETE RESTRICT,
    CONSTRAINT fk_series_frequency FOREIGN KEY (frequency_code)
        REFERENCES frequency (frequency_code)      ON DELETE RESTRICT,
    CONSTRAINT fk_series_units     FOREIGN KEY (units_code)
        REFERENCES units (units_code)              ON DELETE RESTRICT,
    CONSTRAINT fk_series_sa        FOREIGN KEY (sa_code)
        REFERENCES seasonal_adjustment (sa_code)   ON DELETE RESTRICT,
    CONSTRAINT ck_series_obs_range CHECK (observation_end IS NULL
                                          OR observation_start IS NULL
                                          OR observation_end >= observation_start)
);

-- SERIES_CATEGORY : associative entity for the M:N SERIES-CATEGORY
-- (business rule 5). Composite primary key of the two foreign keys.
CREATE TABLE series_category (
    series_id        VARCHAR(40)   NOT NULL,
    category_id      INTEGER       NOT NULL,
    CONSTRAINT pk_series_category PRIMARY KEY (series_id, category_id),
    CONSTRAINT fk_series_category_series   FOREIGN KEY (series_id)
        REFERENCES series (series_id)     ON DELETE CASCADE,
    CONSTRAINT fk_series_category_category FOREIGN KEY (category_id)
        REFERENCES category (category_id) ON DELETE RESTRICT
);

-- SERIES_TAG : associative entity for the M:N SERIES-TAG (business rule 7).
CREATE TABLE series_tag (
    series_id        VARCHAR(40)   NOT NULL,
    tag_name         VARCHAR(120)  NOT NULL,
    CONSTRAINT pk_series_tag PRIMARY KEY (series_id, tag_name),
    CONSTRAINT fk_series_tag_series FOREIGN KEY (series_id)
        REFERENCES series (series_id) ON DELETE CASCADE,
    CONSTRAINT fk_series_tag_tag    FOREIGN KEY (tag_name)
        REFERENCES tag (tag_name)     ON DELETE RESTRICT
);


-- ---------------------------------------------------------------------------
--  5. OBSERVATION : WEAK entity holding every vintage of every value
-- ---------------------------------------------------------------------------

-- Business rules 9, 10, 11. Identified by (series_id, observation_date,
-- realtime_start). A revision never overwrites: the prior row's realtime_end
-- is closed and a new row with a later realtime_start is inserted. The
-- current value of a series on a date is the row where realtime_end =
-- '9999-12-31' (FRED's own sentinel for "still current").
CREATE TABLE observation (
    series_id        VARCHAR(40)   NOT NULL,
    observation_date DATE          NOT NULL,            -- the period the value describes
    realtime_start   DATE          NOT NULL,            -- first day this value was published
    realtime_end     DATE          NOT NULL DEFAULT DATE '9999-12-31',  -- last day it was current
    value            DECIMAL(24,8),                     -- NULL where FRED reports '.'
    CONSTRAINT pk_observation PRIMARY KEY (series_id, observation_date, realtime_start),
    CONSTRAINT fk_observation_series FOREIGN KEY (series_id)
        REFERENCES series (series_id) ON DELETE CASCADE,
    CONSTRAINT ck_observation_realtime CHECK (realtime_end >= realtime_start)
);

-- VINTAGE_DATE : WEAK entity, every date on which FRED published a new or
-- revised value for the series (series/vintagedates). Business rule 13.
-- For a series whose vintages are loaded it equals DISTINCT realtime_start
-- in OBSERVATION; for the rest it is the revision timeline on its own.
CREATE TABLE vintage_date (
    series_id        VARCHAR(40)   NOT NULL,
    vintage_date     DATE          NOT NULL,
    CONSTRAINT pk_vintage_date PRIMARY KEY (series_id, vintage_date),
    CONSTRAINT fk_vintage_date_series FOREIGN KEY (series_id)
        REFERENCES series (series_id) ON DELETE CASCADE
);


-- ---------------------------------------------------------------------------
--  6. INDEXES (secondary access paths; primary keys are already indexed)
--     Chosen from the information-needs list in the proposal.
-- ---------------------------------------------------------------------------
CREATE INDEX ix_series_release        ON series (release_id);           -- "which series does release X update"
CREATE INDEX ix_series_frequency_sa   ON series (frequency_code, sa_code); -- "monthly SA series"
CREATE INDEX ix_series_last_updated   ON series (last_updated);         -- "what changed this week"
CREATE INDEX ix_release_date_date     ON release_date (release_date);   -- "releases scheduled in week W"
CREATE INDEX ix_rte_release           ON release_table_element (release_id); -- table tree of release X
CREATE INDEX ix_rte_parent            ON release_table_element (parent_id);  -- children of an element
CREATE INDEX ix_rte_series            ON release_table_element (series_id);  -- "where does series X appear in the tables"
CREATE INDEX ix_category_parent       ON category (parent_id);          -- hierarchy walk
CREATE INDEX ix_series_category_cat   ON series_category (category_id); -- reverse lookup of the M:N
CREATE INDEX ix_series_tag_tag        ON series_tag (tag_name);         -- reverse lookup of the M:N
CREATE INDEX ix_tag_group             ON tag (group_id);
CREATE INDEX ix_observation_current   ON observation (series_id, realtime_end, observation_date); -- "current value as of"
CREATE INDEX ix_observation_vintage   ON observation (series_id, observation_date, realtime_end); -- "how many revisions"
CREATE INDEX ix_vintage_date_date     ON vintage_date (vintage_date);   -- "what was revised on day D"


-- ---------------------------------------------------------------------------
--  7. DROP SCRIPT (reverse creation order; run to reset)
-- ---------------------------------------------------------------------------
-- DROP TABLE vintage_date;
-- DROP TABLE observation;
-- DROP TABLE series_tag;
-- DROP TABLE series_category;
-- DROP TABLE series;
-- DROP TABLE tag;
-- DROP TABLE tag_group;
-- DROP TABLE category;
-- DROP TABLE release_table_element;
-- DROP TABLE release_date;
-- DROP TABLE release_source;
-- DROP TABLE release;
-- DROP TABLE source;
-- DROP TABLE seasonal_adjustment;
-- DROP TABLE units;
-- DROP TABLE frequency;
