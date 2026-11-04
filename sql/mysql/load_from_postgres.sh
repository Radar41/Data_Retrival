#!/usr/bin/env bash
# Build the MySQL / MariaDB copy of the FRED catalog from the PostgreSQL one.
#
#   sql/mysql/load_from_postgres.sh            # create MYSQL_DB, copy every table
#   sql/mysql/load_from_postgres.sh --fresh    # drop MYSQL_DB first
#
# PostgreSQL is the system of record (fred_load.py writes there). This script
# creates the MySQL schema, copies all 14 tables parent-first, then installs
# the triggers and routines, and finally checks that every table's row count
# matches PostgreSQL and that Q06 (recursive CTE) returns the same rows.
#
# Environment:
#   PG_DB      PostgreSQL database           (default fred)
#   MYSQL_DB   MySQL / MariaDB database      (default fred_mysql)
#   MYSQL      mysql client command          (default "mysql"; add -u/-p/-h here,
#              or put credentials in ~/.my.cnf; never on the command line)
set -euo pipefail
cd "$(dirname "$0")/../.."

PG_DB="${PG_DB:-fred}"
MYSQL_DB="${MYSQL_DB:-fred_mysql}"
read -r -a MYSQL_CMD <<< "${MYSQL:-mysql}"
FRESH=0; [[ "${1:-}" == "--fresh" ]] && FRESH=1

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
my()   { "${MYSQL_CMD[@]}" --local-infile=1 "$@"; }
mydb() { my "$MYSQL_DB" "$@"; }

if my -N -e "SHOW DATABASES LIKE '$MYSQL_DB'" | grep -qx "$MYSQL_DB"; then
    if [[ $FRESH -eq 1 ]]; then
        my -e "DROP DATABASE \`$MYSQL_DB\`"
    else
        echo "database $MYSQL_DB exists; rerun with --fresh to rebuild it" >&2; exit 1
    fi
fi
my -e "CREATE DATABASE \`$MYSQL_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin"
mydb < sql/mysql/fred_schema.sql
echo "schema created in $MYSQL_DB"

# table : SELECT list in PostgreSQL (column order = the MySQL table's)
# parents first so every FOREIGN KEY target exists when its children load
declare -a ORDER=(frequency units seasonal_adjustment source release release_source
                  release_date category tag_group tag series series_category series_tag observation)
declare -A SELECT=(
  [release]="release_id, release_name, press_release::int, release_link"
  # category is self-referencing: load it level by level from the root down
  [category]="c.category_id, c.category_name, c.parent_id FROM category c JOIN (
              WITH RECURSIVE t AS (SELECT category_id, 0 AS depth FROM category WHERE parent_id IS NULL
                                   UNION ALL
                                   SELECT c2.category_id, t.depth + 1 FROM category c2 JOIN t ON c2.parent_id = t.category_id)
              SELECT * FROM t) d USING (category_id) ORDER BY d.depth, c.category_id"
)

for t in "${ORDER[@]}"; do
    cols="${SELECT[$t]:-*}"
    if [[ "$cols" == *"FROM category c"* ]]; then q="SELECT $cols"; else q="SELECT $cols FROM $t"; fi
    q="$(tr '\n' ' ' <<< "$q")"          # \copy must be a single line
    psql -d "$PG_DB" -q -c "\\copy ($q) TO '$TMP/$t.csv' WITH (FORMAT csv, NULL 'NULL')"
    # NULL unquoted = SQL NULL; "NULL" quoted = the string. No backslash escapes in PostgreSQL CSV.
    mydb -e "LOAD DATA LOCAL INFILE '$TMP/$t.csv' INTO TABLE \`$t\`
             CHARACTER SET utf8mb4
             FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"' ESCAPED BY ''
             LINES TERMINATED BY '\n';
             SHOW WARNINGS LIMIT 5;"
    printf '  %-20s %s rows\n' "$t" "$(mydb -N -e "SELECT COUNT(*) FROM \`$t\`")"
done

mydb < sql/mysql/fred_triggers.sql
echo "triggers and routines installed"

# --- checks: every table matches PostgreSQL ----------------------------------
fail=0
for t in "${ORDER[@]}"; do
    a="$(psql -d "$PG_DB" -Atc "SELECT COUNT(*) FROM $t")"
    b="$(mydb -N -e "SELECT COUNT(*) FROM \`$t\`")"
    if [[ "$a" != "$b" ]]; then echo "MISMATCH $t: postgres $a, mysql $b"; fail=1; fi
done
# observation values survive the copy exactly (sum over every vintage)
a="$(psql -d "$PG_DB" -Atc "SELECT COALESCE(SUM(value),0)::numeric(38,8) FROM observation")"
b="$(mydb -N -e "SELECT CAST(COALESCE(SUM(value),0) AS DECIMAL(38,8)) FROM observation")"
[[ "$a" == "$b" ]] || { echo "MISMATCH observation value sum: $a vs $b"; fail=1; }
# Q06 on category 10: same rows in both
q06='WITH RECURSIVE subtree AS (SELECT category_id FROM category WHERE category_id = 10
       UNION ALL SELECT c.category_id FROM category c JOIN subtree st ON c.parent_id = st.category_id)
     SELECT sc.series_id, sc.category_id FROM subtree st JOIN series_category sc ON sc.category_id = st.category_id
     ORDER BY 1, 2'
diff <(psql -d "$PG_DB" -At -F $'\t' -c "$q06") <(mydb -N -e "$q06") > /dev/null \
    || { echo "MISMATCH Q06"; fail=1; }
# value_as_of agrees with the PostgreSQL function
a="$(psql -d "$PG_DB" -Atc "SELECT value_as_of('PAYEMS', DATE '2020-04-01', DATE '2020-06-01')")"
b="$(mydb -N -e "SELECT value_as_of('PAYEMS', '2020-04-01', '2020-06-01')")"
[[ "${a%%.*}" == "${b%%.*}" ]] || { echo "MISMATCH value_as_of: $a vs $b"; fail=1; }

if [[ $fail -eq 0 ]]; then
    echo "OK: all 14 tables, observation values, Q06 and value_as_of match PostgreSQL"
else
    exit 1
fi
