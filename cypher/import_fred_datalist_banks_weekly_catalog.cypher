CREATE CONSTRAINT provider_id_unique IF NOT EXISTS
FOR (p:Provider)
REQUIRE p.provider_id IS UNIQUE;

CREATE CONSTRAINT dataset_id_unique IF NOT EXISTS
FOR (d:Dataset)
REQUIRE d.dataset_id IS UNIQUE;

CREATE CONSTRAINT raw_artifact_sha256_unique IF NOT EXISTS
FOR (a:RawArtifact)
REQUIRE a.sha256 IS UNIQUE;

CREATE CONSTRAINT source_member_key_unique IF NOT EXISTS
FOR (m:SourceMember)
REQUIRE m.member_key IS UNIQUE;

CREATE CONSTRAINT series_catalog_key_unique IF NOT EXISTS
FOR (s:Series)
REQUIRE s.catalog_key IS UNIQUE;

CREATE CONSTRAINT series_variant_key_unique IF NOT EXISTS
FOR (v:SeriesVariant)
REQUIRE v.variant_key IS UNIQUE;


LOAD CSV WITH HEADERS FROM
'file:///fred_public_datalist_banks_weekly_bfaf15972702/providers.csv'
AS row
FIELDTERMINATOR ','
MERGE (p:Provider {provider_id: row.provider_id})
SET p.display_name = row.display_name,
    p.description = row.description,
    p.homepage_url = row.homepage_url;


LOAD CSV WITH HEADERS FROM
'file:///fred_public_datalist_banks_weekly_bfaf15972702/datasets.csv'
AS row
FIELDTERMINATOR ','
MATCH (p:Provider {provider_id: row.provider_id})
MERGE (d:Dataset {dataset_id: row.dataset_id})
SET d.source_datalist_id = row.source_datalist_id,
    d.title = row.title,
    d.source_url = row.source_url,
    d.ingestion_status = row.ingestion_status,
    d.audit_status = row.audit_status,
    d.audit_at_utc = row.audit_at_utc,
    d.metadata_series_count = toInteger(row.metadata_series_count),
    d.normalized_series_count = toInteger(row.normalized_series_count)
MERGE (p)-[:PUBLISHED]->(d);


LOAD CSV WITH HEADERS FROM
'file:///fred_public_datalist_banks_weekly_bfaf15972702/raw_artifacts.csv'
AS row
FIELDTERMINATOR ','
MATCH (d:Dataset {dataset_id: row.dataset_id})
MERGE (a:RawArtifact {sha256: row.sha256})
SET a.provider_id = "fred",
    a.bytes = toInteger(row.bytes),
    a.original_file_name = row.original_file_name,
    a.raw_file_name = row.raw_file_name,
    a.raw_file_path = row.raw_file_path,
    a.registered_at_utc = row.registered_at_utc,
    a.storage_class = row.storage_class
MERGE (d)-[:HAS_RAW_ARTIFACT]->(a);


LOAD CSV WITH HEADERS FROM
'file:///fred_public_datalist_banks_weekly_bfaf15972702/source_members.csv'
AS row
FIELDTERMINATOR ','
MATCH (d:Dataset {dataset_id: row.dataset_id})
WITH d, row, row.dataset_id + ":" + row.member_path AS memberKey
MERGE (m:SourceMember {member_key: memberKey})
SET m.dataset_id = row.dataset_id,
    m.member_path = row.member_path,
    m.frequency_label = row.frequency_label,
    m.data_column_count = toInteger(row.data_column_count),
    m.base_series_count = toInteger(row.base_series_count),
    m.normalized_row_count = toInteger(row.normalized_row_count),
    m.nonmissing_value_count = toInteger(row.nonmissing_value_count)
MERGE (d)-[:HAS_SOURCE_MEMBER]->(m);


LOAD CSV WITH HEADERS FROM
'file:///fred_public_datalist_banks_weekly_bfaf15972702/series.csv'
AS row
FIELDTERMINATOR ','
MATCH (d:Dataset {dataset_id: row.dataset_id})
MERGE (s:Series {catalog_key: row.catalog_key})
SET s.series_id = row.series_id,
    s.dataset_id = row.dataset_id,
    s.source_datalist_id = row.source_datalist_id,
    s.title = row.title,
    s.source = row.source,
    s.release = row.release,
    s.units_level = row.units_level,
    s.frequency = row.frequency,
    s.seasonal_adjustment = row.seasonal_adjustment,
    s.real_time_start = row.real_time_start,
    s.period_end = row.period_end,
    s.notes = row.notes,
    s.raw_archive_sha256 = row.raw_archive_sha256
MERGE (d)-[:CONTAINS_SERIES]->(s);


LOAD CSV WITH HEADERS FROM
'file:///fred_public_datalist_banks_weekly_bfaf15972702/series_variants.csv'
AS row
FIELDTERMINATOR ','
MATCH (s:Series {catalog_key: row.series_catalog_key})
MATCH (m:SourceMember {
  member_key: row.dataset_id + ":" + row.source_member_path
})
MERGE (v:SeriesVariant {variant_key: row.variant_key})
SET v.series_id = row.series_id,
    v.dataset_id = row.dataset_id,
    v.transformation_code = row.transformation_code,
    v.raw_column_name = row.raw_column_name,
    v.source_member_path = row.source_member_path,
    v.frequency_label = row.frequency_label
MERGE (s)-[:HAS_TRANSFORMATION]->(v)
MERGE (v)-[:AVAILABLE_IN]->(m);
