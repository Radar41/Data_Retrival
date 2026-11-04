# FRED Graph Explorer

An interactive view of the Neo4j catalog, rendered with [neo4jd3](https://eisman.github.io/neo4jd3/) (D3 v4 force layout, Neo4j HTTP-API data format).

| File | What it is |
|---|---|
| `index.html` | The page: view picker, force graph, legend, node/relationship inspector, and a Live Cypher panel |
| `fred_graph_data.js` | Generated snapshot of the graph (`window.FRED_GRAPH`). Do not edit; rerun the exporter |

## Views

- **Schema**: `CALL db.schema.visualization()`: one node per label, one edge per relationship pattern. The `(:Category)-[:CHILD_OF]->(:Category)` self-relationship is listed in the description because neo4jd3 cannot draw a loop.
- **UNRATE, PAYEMS, GDPC1, CPIAUCSL, INDPRO**: each series with its release and source, frequency, units, seasonal adjustment, category path to the root, tags and tag groups, the catalog snapshots that list it, the latest press release describing its release (two text chunks), and the two latest release dates. GDPC1 and CPIAUCSL have no document because their releases have no PDF in the registry.
- **Lineage**: the data-list side (Provider, Dataset, StagingRun, RawArtifact, SourceMember, three series with their SeriesVariants) and the API provenance (CatalogSnapshot, ApiResponseArtifact).

Chunk embeddings (768 floats) are replaced by `embedding_dims` in the snapshot.

## Rebuild the snapshot

From `src/` in MATLAB, with the Neo4j container running and the password in `NEO4J_PASSWORD` (or the vault secret `neo4j_pw`):

```matlab
export_fred_graph_explorer_data()                                   % the five default series
export_fred_graph_explorer_data(SeriesIds=["UNRATE" "M2SL"])      % any series ids
```

## Open it

Any of these work:

- Open `index.html` directly in a browser.
- Serve the folder: `python3 -m http.server 8765 --directory docs/graph_explorer` and open http://localhost:8765 (this is the `graph-explorer` entry in `.claude/launch.json`).
- The published artifact (private link) shows the same snapshot. Its Live Cypher panel cannot reach `localhost`, so use a local copy for live queries.

## Live Cypher

The panel posts to `http://localhost:7474/db/neo4j/tx/commit` with Basic auth and `resultDataContents: ["graph", "row"]`. Graph results replace the drawing; tabular results appear under the inspector. The presets cover tag lookups, the `chunk_text` full-text index, the `chunk_embedding` vector index, a category path, upcoming release dates and label counts. The password is kept only in the page's memory.
