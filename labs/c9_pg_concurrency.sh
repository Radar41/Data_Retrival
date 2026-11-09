#!/usr/bin/env bash
# C9 lab (PostgreSQL): two real concurrent sessions showing
#   1. a LOST UPDATE under READ COMMITTED with read-then-write logic
#   2. the fix: SELECT ... FOR UPDATE
#   3. a DEADLOCK, and PostgreSQL choosing a victim
# Uses a scratch schema lab_c9 in database fred; production tables are never touched.
#   bash labs/c9_pg_concurrency.sh
set -u
DB=${FRED_PGDB:-fred}
P() { psql -d "$DB" -X -q -At -v ON_ERROR_STOP=0 "$@"; }

reset() {
  P -c "DROP SCHEMA IF EXISTS lab_c9 CASCADE; CREATE SCHEMA lab_c9;
        CREATE TABLE lab_c9.account(id int PRIMARY KEY, balance int NOT NULL);
        INSERT INTO lab_c9.account VALUES (1,100),(2,100);"
}

# Each session reads the balance, "thinks" for 1 s, then writes read_value + amount.
# $2 = '' (plain read) or 'FOR UPDATE' (lock the row when reading)
session() {
  P <<SQL
BEGIN;
DO \$\$
DECLARE b int;
BEGIN
  SELECT balance INTO b FROM lab_c9.account WHERE id = 1 $2;
  PERFORM pg_sleep(1);
  UPDATE lab_c9.account SET balance = b + $1 WHERE id = 1;
END \$\$;
COMMIT;
SQL
}

echo "== 1. Lost update (READ COMMITTED, no lock): +10 and +20 run at the same time"
reset
session 10 "" & session 20 "" & wait
echo "final balance (100 + 10 + 20 should be 130): $(P -c 'SELECT balance FROM lab_c9.account WHERE id=1')"

echo "== 1b. Same race under REPEATABLE READ: PostgreSQL refuses the second write instead of losing it"
reset
rr() { P -c "BEGIN ISOLATION LEVEL REPEATABLE READ;
             SELECT balance FROM lab_c9.account WHERE id=1; SELECT pg_sleep(1);
             UPDATE lab_c9.account SET balance = balance + $1 WHERE id=1; COMMIT;" 2>&1 >/dev/null | grep ERROR | sed 's/^/  /'; }
rr 10 & rr 20 & wait
echo "final balance (one +amount applied, the other must be retried): $(P -c 'SELECT balance FROM lab_c9.account WHERE id=1')"

echo "== 2. Same work with SELECT ... FOR UPDATE"
reset
session 10 "FOR UPDATE" & session 20 "FOR UPDATE" & wait
echo "final balance: $(P -c 'SELECT balance FROM lab_c9.account WHERE id=1')"

echo "== 3. Deadlock: A locks row 1 then wants row 2; B locks row 2 then wants row 1"
reset
P -c "BEGIN; UPDATE lab_c9.account SET balance=balance-1 WHERE id=1; SELECT pg_sleep(1);
      UPDATE lab_c9.account SET balance=balance+1 WHERE id=2; COMMIT;" > /dev/null 2> /tmp/c9_pg_a.err &
P -c "BEGIN; UPDATE lab_c9.account SET balance=balance-1 WHERE id=2; SELECT pg_sleep(1);
      UPDATE lab_c9.account SET balance=balance+1 WHERE id=1; COMMIT;" > /dev/null 2> /tmp/c9_pg_b.err &
wait
grep -h "ERROR" /tmp/c9_pg_a.err /tmp/c9_pg_b.err | sed 's/^/  /'
echo "balances after (one transaction committed, the victim rolled back): $(P -c "SELECT string_agg(id||'='||balance, ' ' ORDER BY id) FROM lab_c9.account")"
rm -f /tmp/c9_pg_a.err /tmp/c9_pg_b.err

P -c "DROP SCHEMA lab_c9 CASCADE;"
echo "== cleaned up (schema lab_c9 dropped)"
