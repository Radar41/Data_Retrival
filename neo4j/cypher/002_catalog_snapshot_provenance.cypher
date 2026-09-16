// 002_catalog_snapshot_provenance.cypher
//
// Purpose:
//   Add reproducibility/provenance nodes for a FRED catalog snapshot.
//
// This script is parameterized. Replace the parameter values before
// running in Neo4j Browser, or later provide them through cypher-shell.
//
// Required prior graph:
//   (:Provider {provider_id: "fred"})
//   (:Category {provider_id, category_id})
//
// Relationships created:
//   (:Provider)-[:EXPOSED_IN]->(:CatalogSnapshot)
//   (:CatalogSnapshot)-[:RAW_RESPONSE]->(:ApiResponseArtifact)
//   (:CatalogSnapshot)-[:CONTAINS_CATEGORY]->(:Category)

CREATE CONSTRAINT catalog_snapshot_id_unique IF NOT EXISTS
FOR (snapshot:CatalogSnapshot)
REQUIRE snapshot.snapshot_id IS UNIQUE;

CREATE CONSTRAINT api_response_artifact_path_unique IF NOT EXISTS
FOR (artifact:ApiResponseArtifact)
REQUIRE artifact.path IS UNIQUE;

// Replace these values with those printed by:
// catalog = fred_catalog_build();
// catalog.SnapshotID
// catalog.SnapshotDirectory
//
// Do not put API keys in this script or in graph properties.

WITH {
    provider_id: "fred",
    snapshot_id: "2026-09-02T04-42-54Z",
    retrieved_at_utc: "2026-09-02T04:42:54Z",
    endpoint: "category/children",
    request_parameters: "{\"category_id\":0}",
    snapshot_directory: "/home/radar-41-0/Documents/Data_Retrival/data/catalog/fred/snapshots/2026-09-02T04-42-54Z",
    raw_response_file: "/home/radar-41-0/Documents/Data_Retrival/data/catalog/fred/snapshots/2026-09-02T04-42-54Z/response.json",
    manifest_file: "/home/radar-41-0/Documents/Data_Retrival/data/catalog/fred/snapshots/2026-09-02T04-42-54Z/catalog_manifest.json",
    normalized_categories_file: "/home/radar-41-0/Documents/Data_Retrival/data/catalog/fred/snapshots/2026-09-02T04-42-54Z/fred_root_categories.csv",
    neo4j_import_file: "fred_root_categories.csv",
    category_count: 8
} AS input

MATCH (provider:Provider {
    provider_id: input.provider_id
})

MERGE (snapshot:CatalogSnapshot {
    snapshot_id: input.snapshot_id
})

SET snapshot.provider_id = input.provider_id,
    snapshot.retrieved_at_utc = input.retrieved_at_utc,
    snapshot.endpoint = input.endpoint,
    snapshot.request_parameters = input.request_parameters,
    snapshot.snapshot_directory = input.snapshot_directory,
    snapshot.manifest_file = input.manifest_file,
    snapshot.normalized_categories_file = input.normalized_categories_file,
    snapshot.neo4j_import_file = input.neo4j_import_file,
    snapshot.category_count = input.category_count,
    snapshot.schema_version = "1"

MERGE (provider)-[:EXPOSED_IN]->(snapshot)

MERGE (artifact:ApiResponseArtifact {
    path: input.raw_response_file
})

SET artifact.provider_id = input.provider_id,
    artifact.snapshot_id = input.snapshot_id,
    artifact.kind = "raw_api_response",
    artifact.format = "json",
    artifact.endpoint = input.endpoint

MERGE (snapshot)-[:RAW_RESPONSE]->(artifact)

WITH snapshot, input
MATCH (category:Category {
    provider_id: input.provider_id
})
WHERE category.category_id <> "0"

MERGE (snapshot)-[:CONTAINS_CATEGORY]->(category)

RETURN snapshot.snapshot_id AS snapshot_id,
       snapshot.retrieved_at_utc AS retrieved_at_utc,
       count(category) AS linked_categories;
