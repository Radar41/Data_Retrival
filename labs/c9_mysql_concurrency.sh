#!/usr/bin/env bash
# C9 lab (MySQL 8.4 / InnoDB): the same three experiments as c9_pg_concurrency.sh.
# Runs in a scratch database lab_c9 inside the class Shore-to-Shore container
# (course/env/shoretoshore, container shoretoshore-mysql), dropped at the end.
# The class data in database `shoretoshore` is never touched.
#   bash labs/c9_mysql_concurrency.sh
set -u
C=${S2S_CONTAINER:-shoretoshore-mysql}
M() { docker exec -i "$C" sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -s lab_c9 2>&1 | grep -v "Using a password"'; }

docker exec -i "$C" sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" 2>/dev/null' <<'SQL'
DROP DATABASE IF EXISTS lab_c9; CREATE DATABASE lab_c9;
SQL
reset() { echo "DROP TABLE IF EXISTS account; CREATE TABLE account(id INT PRIMARY KEY, balance INT NOT NULL) ENGINE=InnoDB; INSERT INTO account VALUES (1,100),(2,100);" | M; }

# read into a variable, wait 1 s, write variable + amount. $2 = '' or 'FOR UPDATE'
session() { printf "SELECT @@transaction_isolation INTO @iso; START TRANSACTION; SELECT balance INTO @b FROM account WHERE id=1 %s; DO SLEEP(1); UPDATE account SET balance=@b+%s WHERE id=1; COMMIT;\n" "$2" "$1" | M; }

echo "== 1. Lost update (InnoDB default REPEATABLE READ, no lock): +10 and +20 at the same time"
reset
session 10 "" & session 20 "" & wait
echo "isolation: $(echo 'SELECT @@transaction_isolation;' | M)"
echo "final balance (should be 130): $(echo 'SELECT balance FROM account WHERE id=1;' | M)"

echo "== 2. Same work with SELECT ... FOR UPDATE"
reset
session 10 "FOR UPDATE" & session 20 "FOR UPDATE" & wait
echo "final balance: $(echo 'SELECT balance FROM account WHERE id=1;' | M)"

echo "== 3. Deadlock"
reset
echo "START TRANSACTION; UPDATE account SET balance=balance-1 WHERE id=1; DO SLEEP(1); UPDATE account SET balance=balance+1 WHERE id=2; COMMIT;" | M | sed 's/^/  A: /' &
echo "START TRANSACTION; UPDATE account SET balance=balance-1 WHERE id=2; DO SLEEP(1); UPDATE account SET balance=balance+1 WHERE id=1; COMMIT;" | M | sed 's/^/  B: /' &
wait
echo "balances after: $(echo "SELECT GROUP_CONCAT(CONCAT(id,'=',balance) ORDER BY id SEPARATOR ' ') FROM account;" | M)"

docker exec -i "$C" sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" 2>/dev/null' <<'SQL'
DROP DATABASE lab_c9;
SQL
echo "== cleaned up (database lab_c9 dropped)"
