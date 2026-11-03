// fred_queries.cypher
//
// Same numbering as fred_queries.sql so the two can be read side by side.
// Q07, Q08 and Q10 are about observation vintages; those rows live only in
// PostgreSQL by design (README: dense observations stay out of Neo4j), so
// they have no graph version. Q13 shows how the two stores combine.
//
// Reading guide:  SQL JOIN  ->  pattern  (a)-[:REL]->(b)
//                 GROUP BY  ->  implicit grouping on non-aggregated columns
//                 LEFT JOIN ->  OPTIONAL MATCH
//                 IN subq   ->  EXISTS { ... }
//                 recursive ->  variable-length path [:CHILD_OF*0..]
//                 EXCEPT    ->  collect() a list, then NOT ... IN list

// Q01  Monthly, seasonally adjusted series updated since 2026-10-01
MATCH (se:Series)-[:HAS_FREQUENCY]->(:Frequency {code:'M'}),
      (se)-[:ADJUSTED]->(:SeasonalAdjustment {code:'SA'})
WHERE se.last_updated >= datetime('2026-10-01T00:00:00')
RETURN se.series_id, se.title, se.last_updated
ORDER BY se.last_updated DESC;


// Q02  Series per agency, by frequency   (GROUP BY is implicit, WHERE after WITH is HAVING)
MATCH (src:Source)<-[:PUBLISHED_BY]-(:Release)<-[:IN_RELEASE]-(se:Series)-[:HAS_FREQUENCY]->(f:Frequency)
WITH src.name AS source_name, f.name AS frequency_name, count(se) AS n_series
WHERE n_series >= 1
RETURN source_name, frequency_name, n_series
ORDER BY source_name, n_series DESC;


// Q03  Which source publishes GDPC1, and through which release?
MATCH (se:Series {series_id:'GDPC1'})-[:IN_RELEASE]->(r:Release)-[:PUBLISHED_BY]->(src:Source)
RETURN se.series_id, r.name AS release_name, src.name AS source_name;


// Q04  Every release with its series count, including releases with none   (OPTIONAL MATCH = LEFT JOIN)
MATCH (r:Release)
OPTIONAL MATCH (r)<-[:IN_RELEASE]-(se:Series)
RETURN r.release_id, r.name, count(se) AS n_series
ORDER BY n_series, r.name;


// Q05  Releases scheduled in the week of 2026-11-02 and the series they update
MATCH (r:Release)-[:SCHEDULED_ON]->(rd:ReleaseDate)
WHERE rd.date >= date('2026-11-02') AND rd.date <= date('2026-11-08')
  AND EXISTS { (r)-[:SCHEDULED_ON]->(:ReleaseDate {status:'scheduled'}) }
MATCH (r)<-[:IN_RELEASE]-(se:Series)
RETURN r.name AS release_name, rd.date AS release_date, se.series_id
ORDER BY release_date, release_name, se.series_id;


// Q06  Every series under category 10 including all subcategories
//      One variable-length pattern replaces the recursive CTE.
//      *0.. includes the category itself; the path length is the depth.
MATCH p = (root:Category {provider_id:'fred', category_id:'10'})<-[:CHILD_OF*0..]-(c:Category)<-[:IN_CATEGORY]-(se:Series)
RETURN length(p) - 1 AS depth, c.name AS category_name, se.series_id, se.title
ORDER BY depth, category_name, se.series_id;


// Q06b The same walk upward: the full breadcrumb of a series
MATCH (se:Series {series_id:'UNRATE'})-[:IN_CATEGORY]->(leaf:Category)-[:CHILD_OF*0..]->(anc:Category)
WITH se, leaf, collect(anc.name) AS crumbs
RETURN se.series_id, leaf.name AS leaf_category, reverse(crumbs) AS path_from_root;


// Q09  Tags on BLS series never used on BEA series   (EXCEPT)
MATCH (:Source {source_id:18})<-[:PUBLISHED_BY]-(:Release)<-[:IN_RELEASE]-(:Series)-[:TAGGED]->(t:Tag)
WITH collect(DISTINCT t.tag_name) AS bea_tags
MATCH (:Source {source_id:22})<-[:PUBLISHED_BY]-(:Release)<-[:IN_RELEASE]-(:Series)-[:TAGGED]->(t:Tag)
WHERE NOT t.tag_name IN bea_tags
RETURN DISTINCT t.tag_name
ORDER BY t.tag_name;


// Q11  Series that look overdue relative to their frequency
MATCH (se:Series)-[:HAS_FREQUENCY]->(f:Frequency)
WITH se, f,
     CASE f.code WHEN 'D' THEN duration({days:14})
                 WHEN 'W' THEN duration({months:1})
                 WHEN 'M' THEN duration({months:3})
                 WHEN 'Q' THEN duration({months:6})
                 ELSE          duration({months:18}) END AS grace
WHERE se.observation_end < date() - grace
RETURN se.series_id, f.name AS frequency_name, se.observation_end,
       duration.inDays(se.observation_end, date()).days AS days_since_last_obs
ORDER BY days_since_last_obs DESC;


// Q12  Most common tags across BLS series, with their group
MATCH (:Source {source_id:22})<-[:PUBLISHED_BY]-(:Release)<-[:IN_RELEASE]-(se:Series)-[:TAGGED]->(t:Tag)-[:IN_GROUP]->(g:TagGroup)
RETURN t.tag_name, g.name AS group_name, count(DISTINCT se) AS n_series
ORDER BY n_series DESC, t.tag_name;


// Q12b A graph-only question: tag disagreement audit
//      Series whose frequency lookup says one thing and whose frequency-group tag says another.
MATCH (se:Series)-[:HAS_FREQUENCY]->(f:Frequency),
      (se)-[:TAGGED]->(t:Tag)-[:IN_GROUP]->(:TagGroup {group_id:'freq'})
WHERE toLower(f.name) <> toLower(t.tag_name)
RETURN se.series_id, f.name AS lookup_frequency, t.tag_name AS tag_frequency
ORDER BY se.series_id;


// Q13  The integrated question
//      Step 1 (PostgreSQL, fred_queries.sql Q13): which series were revised most in 2026.
//      Step 2 (here): for those series, find passages in their release documents
//      that talk about revisions. Python passes the SQL result as $revised,
//      a list of {series_id, release_id, n_revisions}.
//      :param revised => [{series_id:'PAYEMS', release_id:50, n_revisions:3}, {series_id:'GDPC1', release_id:53, n_revisions:2}]
UNWIND $revised AS rv
MATCH (se:Series {series_id: rv.series_id})-[:IN_RELEASE]->(r:Release {release_id: rv.release_id})
CALL db.index.fulltext.queryNodes('chunk_text', 'revised OR revision OR revisions') YIELD node AS chunk, score
MATCH (doc:Document)-[:HAS_CHUNK]->(chunk), (doc)-[:DESCRIBES]->(r)
RETURN se.series_id, r.name AS release_name, rv.n_revisions,
       doc.title AS document, doc.release_date, chunk.seq,
       round(score, 2) AS relevance, left(chunk.text, 240) AS passage
ORDER BY rv.n_revisions DESC, relevance DESC
LIMIT 20;


// Q13c Semantic variant: embed the question in Python, pass as $qvec
//      "why were payroll figures revised down"
MATCH (se:Series {series_id:'PAYEMS'})-[:IN_RELEASE]->(r:Release)<-[:DESCRIBES]-(doc:Document)-[:HAS_CHUNK]->(c:Chunk)
WITH collect(c) AS candidates
CALL db.index.vector.queryNodes('chunk_embedding', 10, $qvec) YIELD node, score
WHERE node IN candidates
RETURN node.doc_id, node.seq, round(score, 3) AS similarity, left(node.text, 240) AS passage
ORDER BY similarity DESC
LIMIT 5;
