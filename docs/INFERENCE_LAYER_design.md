# Inference and governance layer: Memgraph, Cognee, Mem0 on the FRED catalog

Status: design, 2026-11-04. Nothing in this document is built. It sits on top of the catalog that is built (PostgreSQL = the former, Neo4j = the latter, see `FRED_Catalog_ADIT2200_Handoff.md`) and is outside the ADIT2200 scope except where noted in section 8.

## 1. The idea in one paragraph

Every FRED release is an event. When the Employment Situation posts on a Friday, three hundred series get new vintages at once. Today the catalog records that as rows. The inference layer treats each posting as a point arriving in a conversation that has been going on for decades between series: copper moved, and some months later electrical-equipment producer prices moved. The job of the layer is to hold those lead-lag relations as first-class, evidenced, revisable objects, to attach the qualitative record (what the agency said in the press release, what the analyst noted) to them, and to react when a new event arrives. The three new packages each do one part of that, and the rule that keeps it honest is the same one the catalog already lives by: nothing is overwritten, everything carries provenance.

## 2. Vocabulary (what means what)

| Term | Definition | Where it lives |
|---|---|---|
| **Vintage** | one published value of one series for one period (`observation` row) | PostgreSQL only, as now |
| **Event** | one series receiving a new vintage on one release date: `(series_id, release_date)` with the new value, change from prior period, and revision to prior periods | PostgreSQL `event` table, mirrored as `(:Event)` in Memgraph |
| **Entity** | a thing the qualitative record talks about: a commodity, an industry, a policy, an agency, a series | Memgraph `(:Entity)`, created by Cognee or by hand |
| **Statement** | a sentence-level claim extracted from a document, with its chunk id | Memgraph `(:Statement)-[:FROM]->(chunk ref)` |
| **Hypothesis** | a proposed lead-lag relation between two series or entities: `(a)-[:LEADS {lag, strength, method}]->(b)` | Memgraph relationship, versioned |
| **Evidence** | a link from a Hypothesis to the Statements and Events that support or contradict it | Memgraph `[:SUPPORTED_BY]`, `[:CONTRADICTED_BY]` |
| **Memory** | a distilled, deduplicated fact about an Entity with a validity window, the unit Mem0 manages ("copper rose 3% m/m in Oct 2026; lead relation to PPI electrical equipment at 4 to 6 months") | Mem0 store (vector + graph, graph backend = Memgraph) |
| **Governance record** | for every Hypothesis and Memory: who or what created it, from which snapshot, which documents, when, and what superseded it | properties on the node or edge; never deleted |

The Königsberg point from the class carries straight over: a Hypothesis is a bridge, and the bridge is the object of study. In the former it would be a junction table with a lag column; in the latter it is an edge that can itself be evidenced, versioned and traversed.

## 3. Stores and their roles

| Store | Role | Why this one |
|---|---|---|
| **PostgreSQL** (former) | system of record: catalog tables, every vintage, the `event` table | already built, constraints enforced, vintage trigger already exists |
| **Neo4j** (latter) | the class deliverable: catalog graph, provenance, press-release documents with full-text and vector indexes | already built; stays frozen for grading |
| **Memgraph** | the live inference graph: Events, Entities, Statements, Hypotheses, Evidence; native triggers fire on insert; streams consume events | in-memory, native `CREATE TRIGGER`, Kafka/Pulsar streams, MAGE algorithms, same Cypher as the latter, open-source graph features Mem0 moved to paid |
| **Cognee** | turns documents into graph: chunks the press releases and notes, extracts Entities and Statements with an LLM, writes them to Memgraph via its community adapter | does the qualitative-to-structured step so you do not hand-write entity extraction |
| **Mem0** | the memory layer: add / update / supersede facts per Entity, retrieval by similarity plus graph neighborhood; its graph store points at Memgraph so memories and hypotheses share nodes | gives Memories their own lifecycle (dedup, conflict, decay) instead of reinventing it |

Neo4j and Memgraph run side by side. The class never sees Memgraph; the inference layer never writes to Neo4j. The port of the latter's Cypher into Memgraph is the exercise you already planned, and the `Neo4j-specific` comments in `neo4j/cypher/*` mark the lines that change.

## 4. What reads what (the data flow)

```
FRED API ──fred_load.py──▶ PostgreSQL (vintages, catalog)
                              │
                              │ AFTER INSERT ON observation (per release batch)
                              ▼
                        event table  ──pg NOTIFY 'fred_event'──▶  event_worker.py
                                                                      │
                   ┌──────────────────────────────────────────────────┼──────────────┐
                   ▼                                                  ▼              ▼
           Memgraph (:Event)                                  Neo4j (unchanged)   Mem0.add(...)
                   │ CREATE TRIGGER ON CREATE :Event                                 │
                   ▼                                                                 │
     evaluate open Hypotheses touching this series                                   │
     attach [:SUPPORTED_BY] / [:CONTRADICTED_BY] to the new Event                    │
     update strength, write a new Hypothesis version if it crossed a threshold        │
                   │                                                                 │
                   └────────────── Memory written for the Entity ◀───────────────────┘

press-release PDFs (data/raw/documents) ──Cognee──▶ Memgraph (:Entity), (:Statement)
                                                          │
                                                          └── link Statement → Series by name/tag match
                                                              link Statement → Event by release_date
```

Reads, by consumer:

- `event_worker.py` reads PostgreSQL (the new events, the series' lookups), writes Memgraph and Mem0.
- Memgraph triggers read only Memgraph.
- Cognee reads `data/raw/documents/` and the catalog's series titles (to resolve names), writes Memgraph.
- Mem0 reads and writes its own collection plus Memgraph nodes.
- Nothing reads the latter except the class queries and `fred_integrated.py`.
- The e3nn / residual work reads PostgreSQL vintages and Memgraph hypotheses. It is the consumer of this layer, not part of it.

## 5. The copper example, concretely

Series: `PCOPPUSDM` (copper price, IMF via FRED), `WPU1017` or `PCU3353...` (PPI electrical equipment and wiring), `IPG3353S` (industrial production, electrical equipment).

1. `PCOPPUSDM` is in the loaded releases, so each monthly posting creates an Event with `change_pct = +3.1`.
2. A seed Hypothesis exists: `(:Series {id:'PCOPPUSDM'})-[:LEADS {lag_months: 4, strength: null, method: 'seed', version: 1, created_by: 'adrian', snapshot_id: ...}]->(:Series {id:'WPU1017'})`.
3. The Memgraph trigger on the copper Event finds that Hypothesis, schedules a check for the WPU1017 Event four months out, and records nothing else yet.
4. Four months later the WPU1017 Event arrives. The trigger compares direction and magnitude against the copper Event, attaches `[:SUPPORTED_BY]` or `[:CONTRADICTED_BY]`, recomputes `strength` over all evidence pairs, and if the value changed writes version 2 of the edge with `supersedes: 1`. Version 1 stays.
5. Cognee has extracted from a G.17 press release the Statement "output of electrical equipment declined as input costs rose", linked to Entity `electrical equipment` and to the G.17 Event of that date. The trigger adds it as evidence too; a Statement is qualitative evidence, an Event is quantitative.
6. Mem0 receives a Memory for Entity `copper`: "Oct 2026: +3.1% m/m; lead relation to PPI electrical equipment at 4 months, strength 0.62 over 31 pairs, last confirmed 2027-02." When the next copper Event arrives, Mem0 updates rather than appends.

The strength computation itself is deliberately dumb at first (sign agreement rate over aligned pairs). The residual-fingerprint and e3nn work replaces it later; the layer's job is to hold the structure and the evidence, not to be the model.

## 6. Governance rules (the part that makes it a database and not a notebook)

1. **No overwrite.** Hypotheses and Memories are versioned with `supersedes`; Events and Statements are immutable. Same rule as `observation.realtime_end`.
2. **Every inferred object names its inputs.** `method`, `snapshot_id`, document chunk ids, and the Events it used. A Hypothesis with no evidence edges is `status: 'seed'` and is excluded from downstream reads.
3. **Humans and models are both authors.** `created_by` is `adrian`, `cognee:<model>`, `trigger:<name>`, or `mem0`. Queries can filter by author class.
4. **Thresholds are data.** The strength cutoffs that promote a Hypothesis from `seed` to `candidate` to `accepted` live in a `(:Policy)` node, not in code, so changing them is itself a versioned event.
5. **Nothing dense in the graphs.** Events are one row per (series, release_date); vintages stay in PostgreSQL. If an analysis needs the full series it reads PostgreSQL.

## 7. Build order (minimum that demonstrates the loop)

1. PostgreSQL: `event` table + an AFTER INSERT trigger on `observation` that upserts one event per (series, release batch) and `NOTIFY fred_event`. This is Week 10 homework material applied to your own schema.
2. Memgraph container next to the Neo4j one (different ports). Port `003` to Memgraph; add `Event`, `Entity`, `Statement`, `Policy` labels and the `LEADS`, `SUPPORTED_BY`, `CONTRADICTED_BY` types. One `CREATE TRIGGER ... ON CREATE AFTER COMMIT` for `:Event`.
3. `src/python/event_worker.py`: `LISTEN fred_event`, write `(:Event)`, call Mem0.
4. Cognee with the Memgraph community adapter over the 12 press releases already registered; inspect what it extracts before trusting it. LLM: start local (Ollama on the RTX 4000 Ada) so no document text leaves the machine; switch to an API only if quality forces it.
5. Mem0 configured with Memgraph as graph store and a local embedder (the same `all-mpnet-base-v2` already in use, so vectors are comparable across layers).
6. The copper seed Hypothesis and a replay: run the worker over the 63k vintages already loaded so the trigger fires historically and the strength has evidence on day one.

Each step is a commit with a status entry, same relay as before. Step 1 is independent of the new packages and is worth doing this week.

## 8. Boundary with ADIT2200

Inside the class: PostgreSQL and Neo4j, the catalog, the integrated question, triggers (Week 10 homework), and the SQL-versus-Cypher comparison. Step 1 above and the degree audits are legitimate class material.

Outside the class: Memgraph, Cognee, Mem0, hypotheses, memories. These are the K-Space data infrastructure and the substrate for the vector-graph and e3nn work. They can appear in the final presentation as "where this goes next", one slide, not as deliverables.

## 9. Open decisions

- Memgraph as the only Cypher store after the term ends, or keep Neo4j for its vector index. Decide after the Cypher port shows what breaks.
- Local LLM for Cognee and Mem0 versus API. Local first.
- Whether Events are emitted per series or per release batch. Per series (one node each) keeps the trigger logic simple; per batch is fewer nodes. Start per series.
- Which PPI series is the right "electrical equipment" target for the copper demo. Check the FRED catalog for the current WPU/PCU code before seeding.
