#!/bin/sh
# Apply the schema files, in the order db/apply_order.txt gives.
#
#   ./tools/migrate.sh              apply
#   ./tools/migrate.sh --dry-run    list what would be applied, touch nothing
#
# The whole run is ONE transaction: an error anywhere leaves the database as
# it was before the first file. No schema file may open its own transaction.
#
# The files are written to be replayed (IF NOT EXISTS, OR REPLACE), which is
# what lets one script serve a fresh database and a deployed one alike.
#
# Where to run it: the postgres container, user and database come from the
# environment, with the lab's values as defaults.
set -eu
cd "$(dirname "$0")/.."

PG_CONTAINER="${PG_CONTAINER:-postgres}"
PG_USER="${PG_USER:-gw_manager}"
PG_DB="${PG_DB:-gw_manager}"
ORDER="db/apply_order.txt"

dry=0
[ "${1:-}" = "--dry-run" ] && dry=1

# Comments and blank lines out; what remains is one file name per line.
files=$(grep -v '^[[:space:]]*#' "$ORDER" | grep -v '^[[:space:]]*$')
[ -n "$files" ] || { echo "nothing to apply: $ORDER is empty" >&2; exit 1; }

for f in $files; do
    [ -f "db/$f" ] || { echo "listed but missing: db/$f" >&2; exit 1; }
done

if [ "$dry" = 1 ]; then
    for f in $files; do echo "would apply db/$f"; done
    exit 0
fi

# One transaction for the whole run: a failure in the fifth file leaves the
# database exactly as it was before the first. Applied file by file, lot1's
# DROP VIEW monthly_pool_cost stayed dropped until schema_rates.sql — and an
# error in between left /reporting/pool-cost answering 503.
for f in $files; do echo "applying db/$f"; done
for f in $files; do cat "db/$f"; echo; done \
    | docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 --single-transaction \
        -U "$PG_USER" -d "$PG_DB"
echo "schema applied ($(echo "$files" | wc -l | tr -d ' ') files, one transaction)"
