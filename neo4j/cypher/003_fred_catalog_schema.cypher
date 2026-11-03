// 003_fred_catalog_schema.cypher
//
// Purpose:
//   Constraints and indexes for the full FRED catalog graph used by the
//   ADIT2200 term project. Extends 001 (Provider, Category) and coexists
//   with the datalist model (Dataset, Series, SeriesVariant): the Series
//   key format "fred:<series_id>" is the same, so a series that arrives by
//   either path is one node.
//
// Design rule carried over from the project README:
//   Dense observation values are NOT graph nodes. They live in PostgreSQL
//   (fred_schema.sql). The graph holds the catalog, its provenance, and the
//   unstructured document layer.
//
// Graph entities (key properties):
//   (:Provider {provider_id})                                       from 001
//   (:Category {provider_id, category_id})  key "fred:category:<id>" from 001
//   (:Source   {source_key})                 "fred:source:<id>"
//   (:Release  {release_key})                "fred:release:<id>"
//   (:ReleaseDate {rd_key})                  "<release_key>:<date>"
//   (:Series   {series_catalog_key})         "fred:<series_id>"
//   (:Frequency {code}) (:Units {code}) (:SeasonalAdjustment {code})
//   (:TagGroup {group_id})  (:Tag {tag_name})
//   (:Document {doc_id})    (:Chunk {chunk_key})  "<doc_id>:<seq>"
//   (:CatalogSnapshot {snapshot_id})                                from 002
//
// Relationships:
//   (:Release)-[:PUBLISHED_BY]->(:Source)
//   (:Release)-[:SCHEDULED_ON]->(:ReleaseDate)
//   (:Series)-[:IN_RELEASE]->(:Release)
//   (:Series)-[:HAS_FREQUENCY]->(:Frequency)
//   (:Series)-[:MEASURED_IN]->(:Units)
//   (:Series)-[:ADJUSTED]->(:SeasonalAdjustment)
//   (:Series)-[:IN_CATEGORY]->(:Category)
//   (:Category)-[:CHILD_OF]->(:Category)                            from 001
//   (:Series)-[:TAGGED]->(:Tag)-[:IN_GROUP]->(:TagGroup)
//   (:Document)-[:DESCRIBES]->(:Release)
//   (:Document)-[:HAS_CHUNK]->(:Chunk)
//   (:CatalogSnapshot)-[:CONTAINS_SERIES]->(:Series)

CREATE CONSTRAINT source_key_unique IF NOT EXISTS
FOR (s:Source) REQUIRE s.source_key IS UNIQUE;

CREATE CONSTRAINT release_key_unique IF NOT EXISTS
FOR (r:Release) REQUIRE r.release_key IS UNIQUE;

// Neo4j Community has no NODE KEY or composite uniqueness, so the composite
// natural key (release_key, date) is concatenated into one property.
CREATE CONSTRAINT release_date_key IF NOT EXISTS
FOR (d:ReleaseDate) REQUIRE d.rd_key IS UNIQUE;

CREATE CONSTRAINT series_catalog_key_unique IF NOT EXISTS
FOR (s:Series) REQUIRE s.series_catalog_key IS UNIQUE;

CREATE CONSTRAINT frequency_code_unique IF NOT EXISTS
FOR (f:Frequency) REQUIRE f.code IS UNIQUE;

CREATE CONSTRAINT units_code_unique IF NOT EXISTS
FOR (u:Units) REQUIRE u.code IS UNIQUE;

CREATE CONSTRAINT sa_code_unique IF NOT EXISTS
FOR (a:SeasonalAdjustment) REQUIRE a.code IS UNIQUE;

CREATE CONSTRAINT tag_group_id_unique IF NOT EXISTS
FOR (g:TagGroup) REQUIRE g.group_id IS UNIQUE;

CREATE CONSTRAINT tag_name_unique IF NOT EXISTS
FOR (t:Tag) REQUIRE t.tag_name IS UNIQUE;

CREATE CONSTRAINT document_id_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.doc_id IS UNIQUE;

// Community edition: composite (doc_id, seq) concatenated, as for ReleaseDate.
CREATE CONSTRAINT chunk_key IF NOT EXISTS
FOR (c:Chunk) REQUIRE c.chunk_key IS UNIQUE;

// secondary indexes, mirroring fred_schema.sql
CREATE INDEX series_last_updated IF NOT EXISTS FOR (s:Series)      ON (s.last_updated);
CREATE INDEX series_id_lookup    IF NOT EXISTS FOR (s:Series)      ON (s.series_id);
CREATE INDEX release_date_date   IF NOT EXISTS FOR (d:ReleaseDate) ON (d.date);

// unstructured layer (FULLTEXT and VECTOR index DDL are Neo4j-specific)
CREATE FULLTEXT INDEX chunk_text IF NOT EXISTS
FOR (c:Chunk) ON EACH [c.text];

CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding)
OPTIONS { indexConfig: {
    `vector.dimensions`: 768,
    `vector.similarity_function`: 'cosine' } };
