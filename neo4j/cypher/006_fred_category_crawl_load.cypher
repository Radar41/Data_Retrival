// 006_fred_category_crawl_load.cypher
//
// Purpose:
//   Load the full FRED category tree from the MATLAB breadth-first crawl
//   (src/fred_category_tree_crawl.m, Path A) so the graph holds every
//   category, not only the ancestors of loaded series (004).
//
// Input (data/catalog/neo4j-import/, container path /var/lib/neo4j/import/):
//   fred_all_categories.csv   CategoryID,Name,ParentID
//   = data/catalog/fred/crawls/active/all_categories.csv (5,199 rows; the
//     root 0 is not a row: 001 creates it)
//
// Keys are the same as 001 and 004 (Category {provider_id, category_id},
// category_id as a string), so this merges into the nodes they created.
// LOAD CSV only, no APOC; no Neo4j-specific procedures.
//
// Parameters (the crawl's own start time, from crawl_manifest.json):
//   :param snapshot_id => "2026-09-02T16-48-53Z"
//   :param retrieved_at_utc => "2026-09-02T16:48:53Z"

MATCH (provider:Provider {provider_id: "fred"})
MERGE (snapshot:CatalogSnapshot {snapshot_id: $snapshot_id})
  SET snapshot.provider_id      = "fred",
      snapshot.retrieved_at_utc = $retrieved_at_utc,
      snapshot.endpoint         = "category/children (full breadth-first crawl)",
      snapshot.schema_version   = "2"
MERGE (provider)-[:EXPOSED_IN]->(snapshot)
MERGE (root:Category {provider_id: "fred", category_id: "0"})
  ON CREATE SET root.name = "FRED Root", root.parent_id = "", root.is_root = true,
                root.category_key = "fred:category:0";

// nodes first, so every CHILD_OF target exists regardless of row order
LOAD CSV WITH HEADERS FROM "file:///fred_all_categories.csv" AS row
MATCH (snapshot:CatalogSnapshot {snapshot_id: $snapshot_id})
MERGE (c:Category {provider_id: "fred", category_id: row.CategoryID})
  SET c.name         = row.Name,
      c.parent_id    = row.ParentID,
      c.category_key = "fred:category:" + row.CategoryID,
      c.is_root      = false
MERGE (snapshot)-[:CONTAINS_CATEGORY]->(c);

LOAD CSV WITH HEADERS FROM "file:///fred_all_categories.csv" AS row
MATCH (c:Category {provider_id: "fred", category_id: row.CategoryID})
MATCH (p:Category {provider_id: "fred", category_id: row.ParentID})
MERGE (c)-[:CHILD_OF]->(p);

// summary
MATCH (snapshot:CatalogSnapshot {snapshot_id: $snapshot_id})-[:CONTAINS_CATEGORY]->(c:Category)
WITH snapshot, count(c) AS categories_loaded
MATCH (:Category {provider_id: "fred", category_id: "0"})<-[:CHILD_OF*0..]-(r:Category)
RETURN snapshot.snapshot_id AS snapshot_id, categories_loaded, count(r) AS reachable_from_root;
