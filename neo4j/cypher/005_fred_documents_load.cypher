// 005_fred_documents_load.cypher
//
// Purpose:
//   Load the unstructured layer: one Document per agency press release
//   (PDF kept unchanged under data/raw/documents/<release_id>/), split
//   into text chunks with embeddings for full-text and vector search.
//
// Required generated input (data/catalog/neo4j-import/fred_catalog/):
//   documents.csv   doc_id,release_id,release_date,file_type,source_name,path,title,sha256
//   chunks.csv      doc_id,seq,text,embedding      (embedding = JSON array string)
//
// The embedding column is parsed with a plain string split so no APOC is
// needed. Produce it with fred_load.py --documents, which uses a local
// sentence-transformer (768 dims; change 003 if you pick another model).

LOAD CSV WITH HEADERS FROM "file:///fred_catalog/documents.csv" AS row
MATCH (r:Release {release_key: "fred:release:" + row.release_id})
MERGE (d:Document {doc_id: row.doc_id})
  SET d.release_key  = r.release_key,
      d.release_date = date(row.release_date),
      d.file_type    = row.file_type,
      d.source_name  = row.source_name,
      d.path         = row.path,
      d.title        = row.title,
      d.sha256       = row.sha256
MERGE (d)-[:DESCRIBES]->(r);

LOAD CSV WITH HEADERS FROM "file:///fred_catalog/chunks.csv" AS row
MATCH (d:Document {doc_id: row.doc_id})
MERGE (c:Chunk {chunk_key: row.doc_id + ":" + row.seq})
  SET c.doc_id = row.doc_id,
      c.seq    = toInteger(row.seq),
      c.text   = row.text
MERGE (d)-[:HAS_CHUNK]->(c)
WITH c, row
WITH c, [x IN split(replace(replace(row.embedding, "[", ""), "]", ""), ",") | toFloat(trim(x))] AS vec
// Neo4j-specific: db.create.setNodeVectorProperty
CALL db.create.setNodeVectorProperty(c, "embedding", vec)
RETURN count(c) AS chunks_loaded;
