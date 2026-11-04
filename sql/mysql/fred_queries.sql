-- ============================================================================
--  FRED Metadata Catalog : SQL query set
--  Each query answers one information need from the proposal and demonstrates
--  one technique from the course. The same questions are written in Cypher in
--  fred_queries.cypher, in the same order, so the two can be compared.
--  MySQL 8 / MariaDB version of ../fred_queries.sql, same numbering.
--  Changes: `release` is quoted (reserved word) and Q11 uses DATEDIFF /
--  DATE_SUB instead of PostgreSQL interval arithmetic.
-- ============================================================================

-- Q01  Single table, WHERE, ORDER BY                              [Week 7]
--      Which monthly, seasonally adjusted series were updated in October 2026?
SELECT series_id, title, last_updated
  FROM series
 WHERE frequency_code = 'M'
   AND sa_code = 'SA'
   AND last_updated >= TIMESTAMP '2026-10-01'
 ORDER BY last_updated DESC;


-- Q02  Aggregate, GROUP BY, HAVING                                [Week 7]
--      How many series does each agency publish, by frequency?
--      (source -> release_source -> release -> series)
SELECT s.source_name, f.frequency_name, COUNT(se.series_id) AS n_series
  FROM source s
  JOIN release_source rs ON rs.source_id = s.source_id
  JOIN `release` r         ON r.release_id = rs.release_id
  JOIN series se         ON se.release_id = r.release_id
  JOIN frequency f       ON f.frequency_code = se.frequency_code
 GROUP BY s.source_name, f.frequency_name
HAVING COUNT(se.series_id) >= 1
 ORDER BY s.source_name, n_series DESC;


-- Q03  Multi-table inner join                                     [Week 8, HW 5 pattern]
--      Which source publishes series X, and through which release?
SELECT se.series_id, r.release_name, s.source_name
  FROM series se
  JOIN `release` r         ON r.release_id = se.release_id
  JOIN release_source rs ON rs.release_id = r.release_id
  JOIN source s          ON s.source_id = rs.source_id
 WHERE se.series_id = 'GDPC1';


-- Q04  LEFT OUTER JOIN                                            [Week 8, HW 6 pattern]
--      Every release and its series count, including releases with none.
SELECT r.release_id, r.release_name, COUNT(se.series_id) AS n_series
  FROM `release` r
  LEFT JOIN series se ON se.release_id = r.release_id
 GROUP BY r.release_id, r.release_name
 ORDER BY n_series, r.release_name;


-- Q05  Subquery with IN                                            [Week 8, PHW 7 pattern]
--      Which releases are scheduled in the week of 2026-11-02, and which
--      series will they update?
SELECT r.release_name, rd.release_date, se.series_id
  FROM `release` r
  JOIN release_date rd ON rd.release_id = r.release_id
  JOIN series se       ON se.release_id = r.release_id
 WHERE rd.release_date BETWEEN DATE '2026-11-02' AND DATE '2026-11-08'
   AND r.release_id IN (SELECT release_id FROM release_date WHERE date_status = 'scheduled')
 ORDER BY rd.release_date, r.release_name, se.series_id;


-- Q06  Recursive CTE on the unary relationship                     [beyond course; the graph comparison]
--      Which series fall under category X, including all its subcategories?
--      MySQL 8 supports WITH RECURSIVE with identical syntax.
WITH RECURSIVE subtree AS (
    SELECT category_id, category_name, 0 AS depth
      FROM category
     WHERE category_id = 10                              -- Population, Employment, & Labor Markets
    UNION ALL
    SELECT c.category_id, c.category_name, st.depth + 1
      FROM category c
      JOIN subtree st ON c.parent_id = st.category_id
)
SELECT st.depth, st.category_name, se.series_id, se.title
  FROM subtree st
  JOIN series_category sc ON sc.category_id = st.category_id
  JOIN series se          ON se.series_id = sc.series_id
 ORDER BY st.depth, st.category_name, se.series_id;


-- Q07  CASE expression                                             [Week 9, PHW 9 pattern]
--      Classify each series by how often its values get revised
--      (revisions = vintages stored minus distinct periods covered).
SELECT se.series_id,
       COUNT(o.realtime_start) - COUNT(DISTINCT o.observation_date) AS n_revisions,
       CASE WHEN COUNT(o.realtime_start) - COUNT(DISTINCT o.observation_date) = 0 THEN 'never revised'
            WHEN COUNT(o.realtime_start) - COUNT(DISTINCT o.observation_date) = 1 THEN 'revised once'
            ELSE 'revised repeatedly' END AS revision_band
  FROM series se
  JOIN observation o ON o.series_id = se.series_id
 GROUP BY se.series_id
 ORDER BY n_revisions DESC, se.series_id;


-- Q08  Window function with LAG and PARTITION BY                   [Week 9, PHW 9 #7 pattern]
--      For each series and observation period, how much did each successive
--      vintage move the value?
SELECT series_id, observation_date, realtime_start, value,
       value - LAG(value) OVER (PARTITION BY series_id, observation_date
                                ORDER BY realtime_start) AS change_from_prior_vintage,
       ROW_NUMBER() OVER (PARTITION BY series_id, observation_date
                          ORDER BY realtime_start) AS vintage_no
  FROM observation
 WHERE series_id IN ('PAYEMS', 'GDPC1')
 ORDER BY series_id, observation_date, realtime_start;


-- Q09  Set operation (EXCEPT)                                      [Week 9, PHW 9 #3 pattern]
--      Tags used on BLS series that are never used on BEA series.
--      MySQL 8.0.31+ supports EXCEPT; older MySQL needs NOT IN / NOT EXISTS.
SELECT st.tag_name
  FROM series_tag st
  JOIN series se         ON se.series_id = st.series_id
  JOIN release_source rs ON rs.release_id = se.release_id
 WHERE rs.source_id = 22                                   -- BLS
EXCEPT
SELECT st.tag_name
  FROM series_tag st
  JOIN series se         ON se.series_id = st.series_id
  JOIN release_source rs ON rs.release_id = se.release_id
 WHERE rs.source_id = 18                                   -- BEA
 ORDER BY tag_name;


-- Q10  Vintage lookup (the point of the realtime columns)
--      What was PAYEMS for July 2026 as of 2026-09-15, and what is it now?
SELECT 'as of 2026-09-15' AS vantage, value
  FROM observation
 WHERE series_id = 'PAYEMS' AND observation_date = DATE '2026-07-01'
   AND DATE '2026-09-15' BETWEEN realtime_start AND realtime_end
UNION ALL
SELECT 'current', value
  FROM observation
 WHERE series_id = 'PAYEMS' AND observation_date = DATE '2026-07-01'
   AND realtime_end = DATE '9999-12-31';


-- Q11  Date arithmetic against a lookup                            [Week 7 dates]
--      Which series look overdue relative to their frequency?
--      A monthly series whose last observation is more than ~2 months old, etc.
SELECT se.series_id, f.frequency_name, se.observation_end,
       DATEDIFF(CURRENT_DATE, se.observation_end) AS days_since_last_obs
  FROM series se
  JOIN frequency f ON f.frequency_code = se.frequency_code
 WHERE se.observation_end <
       CASE se.frequency_code
            WHEN 'D' THEN DATE_SUB(CURRENT_DATE, INTERVAL 14 DAY)
            WHEN 'W' THEN DATE_SUB(CURRENT_DATE, INTERVAL 1 MONTH)
            WHEN 'M' THEN DATE_SUB(CURRENT_DATE, INTERVAL 3 MONTH)
            WHEN 'Q' THEN DATE_SUB(CURRENT_DATE, INTERVAL 6 MONTH)
            ELSE          DATE_SUB(CURRENT_DATE, INTERVAL 18 MONTH)
       END
 ORDER BY days_since_last_obs DESC;


-- Q12  Most common tags across one source                          [aggregate + join]
SELECT t.tag_name, tg.group_name, COUNT(*) AS n_series
  FROM tag t
  JOIN tag_group tg      ON tg.group_id = t.group_id
  JOIN series_tag st     ON st.tag_name = t.tag_name
  JOIN series se         ON se.series_id = st.series_id
  JOIN release_source rs ON rs.release_id = se.release_id
 WHERE rs.source_id = 22
 GROUP BY t.tag_name, tg.group_name
 ORDER BY n_series DESC, t.tag_name;


-- Q13  The relational half of the integrated question
--      Which series were revised most in 2026? (The document half lives in Neo4j;
--      the Python layer joins the two result sets on series_id / release_id.)
SELECT se.series_id, se.release_id, COUNT(*) AS n_vintages_2026,
       COUNT(*) - COUNT(DISTINCT o.observation_date) AS n_revisions_2026
  FROM observation o
  JOIN series se ON se.series_id = o.series_id
 WHERE o.realtime_start >= DATE '2026-01-01'
 GROUP BY se.series_id, se.release_id
HAVING COUNT(*) - COUNT(DISTINCT o.observation_date) > 0
 ORDER BY n_revisions_2026 DESC, se.series_id;
