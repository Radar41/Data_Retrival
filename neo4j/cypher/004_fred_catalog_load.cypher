// 004_fred_catalog_load.cypher
//
// Purpose:
//   Load the FRED catalog CSVs written by fred_load.py (or the MATLAB
//   exporters) into the graph. LOAD CSV only; no APOC required.
//
// Required generated input (data/catalog/neo4j-import/fred_catalog/):
//   sources.csv            source_id,source_name,source_link
//   releases.csv           release_id,release_name,press_release,release_link
//   release_sources.csv    release_id,source_id
//   release_dates.csv      release_id,release_date,date_status
//   series.csv             series_id,title,release_id,frequency_code,frequency_name,
//                          units_code,units_name,sa_code,sa_name,observation_start,
//                          observation_end,last_updated,popularity,notes
//   categories.csv         category_id,category_name,parent_id
//   series_categories.csv  series_id,category_id
//   tag_groups.csv         group_id,group_name
//   tags.csv               tag_name,group_id,tag_notes,popularity
//   series_tags.csv        series_id,tag_name
//
// Parameter (set before running):   :param snapshot_id => "2026-11-03T21-00-00Z"
// Every node touched is linked to the CatalogSnapshot so a load is reproducible.

MATCH (provider:Provider {provider_id: "fred"})
MERGE (snapshot:CatalogSnapshot {snapshot_id: $snapshot_id})
  SET snapshot.provider_id = "fred",
      snapshot.endpoint = "releases, release/sources, release/dates, release/series, series/categories, series/tags",
      snapshot.schema_version = "2"
MERGE (provider)-[:EXPOSED_IN]->(snapshot);

// --- sources ---------------------------------------------------------------
LOAD CSV WITH HEADERS FROM "file:///fred_catalog/sources.csv" AS row
MERGE (s:Source {source_key: "fred:source:" + row.source_id})
  SET s.provider_id = "fred",
      s.source_id   = toInteger(row.source_id),
      s.name        = row.source_name,
      s.link        = row.source_link;

// --- releases, M:N to sources, weak-entity dates ----------------------------
LOAD CSV WITH HEADERS FROM "file:///fred_catalog/releases.csv" AS row
MERGE (r:Release {release_key: "fred:release:" + row.release_id})
  SET r.provider_id   = "fred",
      r.release_id    = toInteger(row.release_id),
      r.name          = row.release_name,
      r.press_release = toBoolean(row.press_release),
      r.link          = row.release_link;

LOAD CSV WITH HEADERS FROM "file:///fred_catalog/release_sources.csv" AS row
MATCH (r:Release {release_key: "fred:release:" + row.release_id})
MATCH (s:Source  {source_key:  "fred:source:"  + row.source_id})
MERGE (r)-[:PUBLISHED_BY]->(s);

LOAD CSV WITH HEADERS FROM "file:///fred_catalog/release_dates.csv" AS row
MATCH (r:Release {release_key: "fred:release:" + row.release_id})
MERGE (d:ReleaseDate {release_key: r.release_key, date: date(row.release_date)})
  SET d.status = row.date_status
MERGE (r)-[:SCHEDULED_ON]->(d);

// --- series and its three lookups ------------------------------------------
LOAD CSV WITH HEADERS FROM "file:///fred_catalog/series.csv" AS row
MATCH (snapshot:CatalogSnapshot {snapshot_id: $snapshot_id})
MERGE (se:Series {series_catalog_key: "fred:" + row.series_id})
  SET se.provider_id       = "fred",
      se.series_id         = row.series_id,
      se.title             = row.title,
      se.observation_start = CASE WHEN row.observation_start = "" THEN null ELSE date(row.observation_start) END,
      se.observation_end   = CASE WHEN row.observation_end   = "" THEN null ELSE date(row.observation_end)   END,
      se.last_updated      = CASE WHEN row.last_updated = "" THEN null ELSE datetime(replace(row.last_updated, " ", "T")) END,
      se.popularity        = toInteger(row.popularity),
      se.notes             = row.notes
MERGE (snapshot)-[:CONTAINS_SERIES]->(se)
WITH se, row
MATCH (r:Release {release_key: "fred:release:" + row.release_id})
MERGE (se)-[:IN_RELEASE]->(r)
MERGE (f:Frequency {code: row.frequency_code})          ON CREATE SET f.name = row.frequency_name
MERGE (u:Units {code: row.units_code})                  ON CREATE SET u.name = row.units_name
MERGE (a:SeasonalAdjustment {code: row.sa_code})        ON CREATE SET a.name = row.sa_name
MERGE (se)-[:HAS_FREQUENCY]->(f)
MERGE (se)-[:MEASURED_IN]->(u)
MERGE (se)-[:ADJUSTED]->(a);

// --- categories: same key scheme as 001 so crawl output and this merge -------
LOAD CSV WITH HEADERS FROM "file:///fred_catalog/categories.csv" AS row
MERGE (c:Category {provider_id: "fred", category_id: row.category_id})
  SET c.name         = row.category_name,
      c.parent_id    = coalesce(row.parent_id, ""),
      c.category_key = "fred:category:" + row.category_id,
      c.is_root      = (row.category_id = "0")
WITH c, row
WHERE row.parent_id IS NOT NULL AND row.parent_id <> "" AND row.parent_id <> row.category_id
MERGE (p:Category {provider_id: "fred", category_id: row.parent_id})
MERGE (c)-[:CHILD_OF]->(p);

LOAD CSV WITH HEADERS FROM "file:///fred_catalog/series_categories.csv" AS row
MATCH (se:Series {series_catalog_key: "fred:" + row.series_id})
MATCH (c:Category {provider_id: "fred", category_id: row.category_id})
MERGE (se)-[:IN_CATEGORY]->(c);

// --- tags -------------------------------------------------------------------
LOAD CSV WITH HEADERS FROM "file:///fred_catalog/tag_groups.csv" AS row
MERGE (g:TagGroup {group_id: row.group_id}) SET g.name = row.group_name;

LOAD CSV WITH HEADERS FROM "file:///fred_catalog/tags.csv" AS row
MATCH (g:TagGroup {group_id: row.group_id})
MERGE (t:Tag {tag_name: row.tag_name})
  SET t.notes = row.tag_notes, t.popularity = toInteger(row.popularity)
MERGE (t)-[:IN_GROUP]->(g);

LOAD CSV WITH HEADERS FROM "file:///fred_catalog/series_tags.csv" AS row
MATCH (se:Series {series_catalog_key: "fred:" + row.series_id})
MATCH (t:Tag {tag_name: row.tag_name})
MERGE (se)-[:TAGGED]->(t);

// --- summary ----------------------------------------------------------------
MATCH (snapshot:CatalogSnapshot {snapshot_id: $snapshot_id})-[:CONTAINS_SERIES]->(se:Series)
RETURN snapshot.snapshot_id AS snapshot_id, count(se) AS series_loaded;
