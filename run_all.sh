#!/usr/bin/env bash
# run_all.sh: build the FRED Metadata Catalog end to end (handoff 4.1, 4.2, 4.3, 5.1).
#
#   export FRED_API_KEY=...  NEO4J_PASSWORD=...     # environment only, never read from files
#   ./run_all.sh                    # all steps into a NEW database (default name: fred)
#   ./run_all.sh --fresh            # drop and recreate the database first (destroys its data)
#   ./run_all.sh graph documents    # only some steps, against an already-loaded database
#
# Steps, in order:  sample  load  graph  documents
#   sample     4.1  schema, triggers, sample data, queries, trigger proof, expected values
#   load       4.2  truncate sample rows, live FRED load, every SQL query must return rows
#   graph      4.3  docker cp CSVs into the Neo4j import dir, 003, 004, counts vs SQL
#   documents  5.1  press-release PDFs -> chunks -> embeddings, docker cp, 005
#
# Optional environment:
#   FRED_DB (fred)  MAX_SERIES (100)  RELEASES ("50 10 53 13")  DOC_RELEASES ("50 13")
#   DOC_LAST (6)  VENV (~/.venvs/fred)  NEO4J_CONTAINER (data_retrival_neo4j)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

FRED_DB="${FRED_DB:-fred}"
MAX_SERIES="${MAX_SERIES:-100}"
RELEASES="${RELEASES:-50 10 53 13}"
OBS_SERIES="UNRATE PAYEMS GDPC1 CPIAUCSL INDPRO"
DOC_RELEASES="${DOC_RELEASES:-50 13}"
DOC_LAST="${DOC_LAST:-6}"
VENV="${VENV:-$HOME/.venvs/fred}"
NEO4J_CONTAINER="${NEO4J_CONTAINER:-data_retrival_neo4j}"
LOGDIR="$ROOT/data/staging/run_all/$(date -u +%Y-%m-%dT%H-%M-%SZ)"

export FRED_PG="dbname=$FRED_DB"
export NEO4J_IMPORT="$ROOT/data/staging/neo4j-import"   # host-writable; copied into the container
export FRED_PAYLOADS="$ROOT/payloads"
STAGED="$NEO4J_IMPORT/fred_catalog"

# --- arguments ---------------------------------------------------------------
FRESH=0; STEPS=()
for arg in "$@"; do
    case "$arg" in
        --fresh) FRESH=1 ;;
        sample|load|graph|documents) STEPS+=("$arg") ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "unknown argument: $arg (see --help)" >&2; exit 2 ;;
    esac
done
[ ${#STEPS[@]} -eq 0 ] && STEPS=(sample load graph documents)
want() { [[ " ${STEPS[*]} " == *" $1 "* ]]; }

say()  { printf '\n==> %s\n' "$*"; }
die()  { printf '\nFAIL: %s\n' "$*" >&2; exit 1; }
check() { # check <label> <actual> <expected>
    [ "$2" = "$3" ] || die "$1: expected '$3', got '$2'"
    echo "    ok  $1 = $2"
}
q() { psql -d "$FRED_DB" -X -v ON_ERROR_STOP=1 -Atc "$1"; }
cypher() { docker exec -i -e NEO4J_USERNAME=neo4j -e NEO4J_PASSWORD "$NEO4J_CONTAINER" \
               cypher-shell --format plain "$@"; }

# --- preconditions: secrets from the environment only ------------------------
if want load && [ -z "${FRED_API_KEY:-}" ]; then
    die "FRED_API_KEY is not set. Export it in this shell and rerun."
fi
if { want graph || want documents; } && [ -z "${NEO4J_PASSWORD:-}" ]; then
    die "NEO4J_PASSWORD is not set. Export it in this shell and rerun."
fi
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-}"
for tool in psql createdb docker python3; do
    command -v "$tool" >/dev/null || die "$tool not found on PATH"
done
mkdir -p "$LOGDIR"
echo "steps: ${STEPS[*]}   database: $FRED_DB   logs: $LOGDIR"

# --- Python environment ------------------------------------------------------
if [ ! -x "$VENV/bin/python" ]; then
    say "creating venv $VENV"
    python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q -r src/python/requirements.txt
PY="$VENV/bin/python"

# --- Neo4j container ---------------------------------------------------------
if want graph || want documents; then
    if ! docker ps --format '{{.Names}}' | grep -qx "$NEO4J_CONTAINER"; then
        say "starting Neo4j ($NEO4J_CONTAINER)"
        (cd neo4j && docker compose up -d)
    fi
    for _ in $(seq 60); do
        echo 'RETURN 1;' | cypher >/dev/null 2>&1 && break
        sleep 2
    done
    echo 'RETURN 1;' | cypher >/dev/null || die "Neo4j did not accept connections"
fi

copy_csvs() {  # the import dir belongs to the container user (uid 7474, mode 2700)
    docker exec -u 0 "$NEO4J_CONTAINER" mkdir -p /var/lib/neo4j/import/fred_catalog
    docker cp "$STAGED/." "$NEO4J_CONTAINER:/var/lib/neo4j/import/fred_catalog/"
    docker exec -u 0 "$NEO4J_CONTAINER" chown -R 7474:7474 /var/lib/neo4j/import/fred_catalog
}

# --- 4.1 sample data ---------------------------------------------------------
if want sample; then
    say "4.1 PostgreSQL schema + sample data into database '$FRED_DB'"
    if psql -d postgres -X -Atc "SELECT 1 FROM pg_database WHERE datname='$FRED_DB'" | grep -q 1; then
        if [ "$FRESH" = 1 ]; then
            echo "    --fresh: dropping database $FRED_DB"
            dropdb "$FRED_DB"
        else
            die "database '$FRED_DB' already exists. Use --fresh to drop it, FRED_DB=<name> for another, or skip 'sample'."
        fi
    fi
    createdb "$FRED_DB"
    for f in fred_schema fred_triggers fred_sample_data; do
        psql -d "$FRED_DB" -X -q -v ON_ERROR_STOP=1 -f "sql/$f.sql" > "$LOGDIR/$f.log"
    done
    psql -d "$FRED_DB" -X -v ON_ERROR_STOP=1 -f sql/fred_queries.sql > "$LOGDIR/queries_sample.txt"
    check "sample observation rows" "$(q 'SELECT count(*) FROM observation')" 21
    check "Q07 revisions GDPC1,INDPRO,PAYEMS,UNRATE" \
        "$(q "SELECT string_agg(n::text, ',' ORDER BY s) FROM (SELECT series_id s, count(*)-count(DISTINCT observation_date) n FROM observation WHERE series_id IN ('PAYEMS','GDPC1','INDPRO','UNRATE') GROUP BY 1) t")" \
        "2,1,3,1"
    check "Q10 PAYEMS 2026-07 as of 2026-09-15" "$(q "SELECT value_as_of('PAYEMS', DATE '2026-07-01', DATE '2026-09-15')::numeric(12,0)")" 159150
    check "Q10 PAYEMS 2026-07 current" "$(q "SELECT value_as_of('PAYEMS', DATE '2026-07-01', DATE '9999-12-31')::numeric(12,0)")" 159090
    check "Q11 overdue series" "$(awk '/days_since_last_obs/{f=1;next} f&&/rows?\)/{exit} f&&NR>0&&!/^-/' "$LOGDIR/queries_sample.txt" | awk -F'|' '{gsub(/ /,"",$1); print $1}' | paste -sd,)" STALE1
    # trigger proof (business rule 11), inside a transaction that is rolled back
    proof="$(psql -d "$FRED_DB" -X -v ON_ERROR_STOP=1 -At <<'SQL'
BEGIN;
INSERT INTO observation VALUES ('UNRATE', DATE '2026-09-01', DATE '2026-11-06', DEFAULT, 4.5);
SELECT realtime_end FROM observation WHERE series_id='UNRATE' AND observation_date=DATE '2026-09-01' AND realtime_start=DATE '2026-10-02';
SELECT value_as_of('UNRATE', DATE '2026-09-01', DATE '2026-10-15')::numeric(3,1);
ROLLBACK;
SQL
)"
    proof="$(echo "$proof" | grep -v -e '^BEGIN' -e '^INSERT' -e '^ROLLBACK' | paste -sd,)"
    check "trigger closes prior vintage, value_as_of" "$proof" "2026-11-05,4.4"
fi

# --- 4.2 real load -----------------------------------------------------------
if want load; then
    say "4.2 live FRED load: releases $RELEASES, --max-series $MAX_SERIES (about 25 min)"
    q 'TRUNCATE source, release, category, tag_group, tag CASCADE' >/dev/null
    # shellcheck disable=SC2086
    "$PY" src/python/fred_load.py --releases $RELEASES --observations $OBS_SERIES \
        --max-series "$MAX_SERIES" | tee "$LOGDIR/load.log"
    [ "$(ls "$STAGED"/*.csv | wc -l)" -ge 10 ] || die "expected 10 catalog CSVs in $STAGED"
    [ -f "$FRED_PAYLOADS/manifest.json" ] || die "payloads/manifest.json missing"
    psql -d "$FRED_DB" -X -v ON_ERROR_STOP=1 -f sql/fred_queries.sql > "$LOGDIR/queries_real.txt"
    empty="$(grep -c '^(0 rows)' "$LOGDIR/queries_real.txt" || true)"
    check "SQL queries returning 0 rows" "$empty" 0
    echo "    series $(q 'SELECT count(*) FROM series'), observation vintages $(q 'SELECT count(*) FROM observation')"
fi

# --- 4.3 Neo4j catalog -------------------------------------------------------
if want graph; then
    say "4.3 Neo4j catalog graph"
    [ -f "$STAGED/series.csv" ] || die "no staged CSVs in $STAGED: run the 'load' step first"
    copy_csvs
    # 004 needs Provider {provider_id:"fred"}; 001 creates it but also needs the
    # MATLAB crawl CSV, so create just the provider and 001's constraints here.
    cypher > /dev/null <<'CYPHER'
CREATE CONSTRAINT provider_id_unique IF NOT EXISTS FOR (p:Provider) REQUIRE p.provider_id IS UNIQUE;
CREATE CONSTRAINT category_key_unique IF NOT EXISTS FOR (c:Category) REQUIRE (c.provider_id, c.category_id) IS UNIQUE;
MERGE (p:Provider {provider_id: "fred"})
  ON CREATE SET p.name = "Federal Reserve Economic Data", p.short_name = "FRED",
                p.api_base_url = "https://api.stlouisfed.org/fred/", p.project = "Data_Retrival";
CYPHER
    cypher < neo4j/cypher/003_fred_catalog_schema.cypher > "$LOGDIR/003.log"
    snapshot="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
    cypher --param "snapshot_id => '$snapshot'" < neo4j/cypher/004_fred_catalog_load.cypher > "$LOGDIR/004.log"
    loaded="$(tail -1 "$LOGDIR/004.log" | awk -F', ' '{print $2}')"
    check "004 series_loaded = SQL count(series)" "$loaded" "$(q 'SELECT count(*) FROM series')"
    sql_q06="$(q "WITH RECURSIVE st AS (SELECT category_id FROM category WHERE category_id=10 UNION ALL SELECT c.category_id FROM category c JOIN st ON c.parent_id=st.category_id) SELECT count(*) FROM st JOIN series_category sc USING (category_id)")"
    cy_q06="$(echo "MATCH (:Category {provider_id:'fred', category_id:'10'})<-[:CHILD_OF*0..]-(:Category)<-[:IN_CATEGORY]-(se:Series) RETURN count(*);" | cypher | tail -1)"
    check "Q06 rows, Cypher = SQL" "$cy_q06" "$sql_q06"
    echo "    snapshot_id $snapshot"
fi

# --- 5.1 documents -----------------------------------------------------------
if want documents; then
    say "5.1 press releases for releases $DOC_RELEASES (last $DOC_LAST each)"
    # shellcheck disable=SC2086
    "$PY" src/python/fred_load.py --documents --releases $DOC_RELEASES --doc-last "$DOC_LAST" \
        2> "$LOGDIR/documents.stderr" | tee "$LOGDIR/documents.log"
    copy_csvs
    cypher < neo4j/cypher/005_fred_documents_load.cypher > "$LOGDIR/005.log"
    chunks="$(tail -1 "$LOGDIR/005.log")"
    check "005 chunks_loaded = chunks.csv rows" "$chunks" \
        "$("$PY" -c "import csv,sys; csv.field_size_limit(sys.maxsize); print(sum(1 for _ in csv.DictReader(open('$STAGED/chunks.csv'))))")"
fi

say "done. Integrated question:  $PY src/python/fred_integrated.py"
