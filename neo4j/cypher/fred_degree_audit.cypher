// FRED catalog: cardinality (degree) audit for Neo4j.
//
// The ERD and the logical design carry cardinality as crow's feet, NOT NULL
// and foreign keys. Neo4j Community has no way to declare any of that: a
// relationship type can connect any number of nodes in either direction.
// So every crow's-foot constraint becomes a query whose expected answer is
// zero rows. Run the file after each load; a non-empty result is either a
// data problem or a documented exception (listed with the query).
//
// One statement per constraint, separated by a line holding only ";".
// Source of each rule: the fk / join-table row in
// src/+dbdesign/fred_relational_model.m and the relationship row in
// src/+dbdesign/fred_graph_model.m.

// A01  fk_series_release: every Series is in exactly one Release.
//      Known exception: the 41 data-list series (dataset_id set) came from
//      the FRED data-list archive, not the series API, and carry release
//      as text only. They should be 0 here once the catalog crawl reaches them.
MATCH (s:Series)
WITH s, count { (s)-[:IN_RELEASE]->(:Release) } AS d
WHERE d <> 1
RETURN 'A01 Series-IN_RELEASE' AS rule, s.series_id AS node, d AS degree,
       s.dataset_id IS NOT NULL AS datalist_series
;

// A02  fk_series_frequency: exactly one Frequency.
MATCH (s:Series)
WITH s, count { (s)-[:HAS_FREQUENCY]->(:Frequency) } AS d
WHERE d <> 1
RETURN 'A02 Series-HAS_FREQUENCY' AS rule, s.series_id AS node, d AS degree,
       s.dataset_id IS NOT NULL AS datalist_series
;

// A03  fk_series_units: exactly one Units.
MATCH (s:Series)
WITH s, count { (s)-[:MEASURED_IN]->(:Units) } AS d
WHERE d <> 1
RETURN 'A03 Series-MEASURED_IN' AS rule, s.series_id AS node, d AS degree,
       s.dataset_id IS NOT NULL AS datalist_series
;

// A04  fk_series_sa: exactly one SeasonalAdjustment.
MATCH (s:Series)
WITH s, count { (s)-[:ADJUSTED]->(:SeasonalAdjustment) } AS d
WHERE d <> 1
RETURN 'A04 Series-ADJUSTED' AS rule, s.series_id AS node, d AS degree,
       s.dataset_id IS NOT NULL AS datalist_series
;

// A05  series_category (rule 5): a series is classified in at least one
//      category. Zero is the data-list exception again.
MATCH (s:Series)
WITH s, count { (s)-[:IN_CATEGORY]->(:Category) } AS d
WHERE d < 1
RETURN 'A05 Series-IN_CATEGORY' AS rule, s.series_id AS node, d AS degree,
       s.dataset_id IS NOT NULL AS datalist_series
;

// A06  release_source (rule 1): every release is published by at least one
//      source. Mandatory on the release side in the ERD.
MATCH (r:Release)
WITH r, count { (r)-[:PUBLISHED_BY]->(:Source) } AS d
WHERE d < 1
RETURN 'A06 Release-PUBLISHED_BY' AS rule, r.release_key AS node, d AS degree, false AS datalist_series
;

// A07  fk_release_date_release (weak entity, rule 2): a ReleaseDate belongs
//      to exactly one Release. The FK direction is reversed in the graph
//      (Release-[:SCHEDULED_ON]->ReleaseDate), so count incoming edges.
MATCH (rd:ReleaseDate)
WITH rd, count { (:Release)-[:SCHEDULED_ON]->(rd) } AS d
WHERE d <> 1
RETURN 'A07 ReleaseDate<-SCHEDULED_ON' AS rule, rd.rd_key AS node, d AS degree, false AS datalist_series
;

// A08  fk_category_parent (unary 1:M): at most one parent, and zero only
//      for the root (is_root = true).
MATCH (c:Category)
WITH c, count { (c)-[:CHILD_OF]->(:Category) } AS d
WHERE d > 1 OR (d = 0 AND NOT coalesce(c.is_root, false))
RETURN 'A08 Category-CHILD_OF' AS rule, c.category_key AS node, d AS degree, false AS datalist_series
;

// A09  fk_tag_tag_group (rule 8): exactly one TagGroup.
MATCH (t:Tag)
WITH t, count { (t)-[:IN_GROUP]->(:TagGroup) } AS d
WHERE d <> 1
RETURN 'A09 Tag-IN_GROUP' AS rule, t.tag_name AS node, d AS degree, false AS datalist_series
;

// A10  Document layer (graph only): a Document describes exactly one
//      Release, and a Chunk belongs to exactly one Document.
MATCH (d:Document)
WITH d, count { (d)-[:DESCRIBES]->(:Release) } AS n
WHERE n <> 1
RETURN 'A10 Document-DESCRIBES' AS rule, d.doc_id AS node, n AS degree, false AS datalist_series
;

MATCH (c:Chunk)
WITH c, count { (:Document)-[:HAS_CHUNK]->(c) } AS n
WHERE n <> 1
RETURN 'A11 Chunk<-HAS_CHUNK' AS rule, c.chunk_key AS node, n AS degree, false AS datalist_series
;

// A12  Lineage (graph only): a SeriesVariant belongs to exactly one Series
//      and is available in exactly one SourceMember.
MATCH (v:SeriesVariant)
WITH v, count { (:Series)-[:HAS_TRANSFORMATION]->(v) } AS a,
        count { (v)-[:AVAILABLE_IN]->(:SourceMember) } AS b
WHERE a <> 1 OR b <> 1
RETURN 'A12 SeriesVariant' AS rule, v.variant_key AS node, a + b AS degree, true AS datalist_series
;

// A13  Dangling business keys: the FK value kept as a property must agree
//      with the edge (the graph stores both; they can drift).
MATCH (rd:ReleaseDate)<-[:SCHEDULED_ON]-(r:Release)
WHERE rd.release_key <> r.release_key
RETURN 'A13 ReleaseDate.release_key drift' AS rule, rd.rd_key AS node, 1 AS degree, false AS datalist_series
;

MATCH (c:Chunk)<-[:HAS_CHUNK]-(d:Document)
WHERE c.doc_id <> d.doc_id
RETURN 'A14 Chunk.doc_id drift' AS rule, c.chunk_key AS node, 1 AS degree, false AS datalist_series
;
