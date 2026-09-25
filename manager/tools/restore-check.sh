#!/bin/sh
# Prove that a dump restores: into a scratch database, never into the live one.
#
#   ./tools/restore-check.sh                  the newest dump in BACKUP_DIR
#   ./tools/restore-check.sh <file.dump>      that one
#   ./tools/restore-check.sh <file> --keep    leave gw_manager_restore behind
#
# Creates RESTORE_DB (gw_manager_restore) as the instance's superuser,
# restores into it — wrapped in timescaledb_pre/post_restore() when the dump
# carries the extension —, compares the row counts with those recorded next
# to the dump, reads every reporting view, then drops the scratch database.
# The live database is only ever read, and a target that is not named
# *_restore is refused before anything runs.
set -eu
cd "$(dirname "$0")/.."

PG_CONTAINER="${PG_CONTAINER:-postgres}"
PG_USER="${PG_USER:-gw_manager}"
PG_DB="${PG_DB:-gw_manager}"
PG_SUPERUSER="${PG_SUPERUSER:-root}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/gw_manager}"
TARGET="${RESTORE_DB:-gw_manager_restore}"
# The reporting views: a restore that brings the tables back but not what the
# console reads is not a restore.
VIEWS="monthly_service pool_profile monthly_pool_hours pool_pressure hourly_concurrency close_reasons suspect_sources"

case "$TARGET" in
    "$PG_DB") echo "refusing: $TARGET is the live database" >&2; exit 2 ;;
    *_restore) ;;
    *) echo "refusing: the scratch database must be named *_restore, not $TARGET" >&2; exit 2 ;;
esac

dump="${1:-}"
if [ -z "$dump" ]; then
    dump=$(ls -1t "$BACKUP_DIR"/gw_manager-*.dump 2>/dev/null | head -n 1 || true)
fi
[ -n "$dump" ] && [ -f "$dump" ] || { echo "no dump to check (BACKUP_DIR=$BACKUP_DIR)" >&2; exit 2; }
keep=0
[ "${2:-}" = "--keep" ] && keep=1

pg() { ${PG_EXEC:-docker exec -i $PG_CONTAINER} "$@"; }
su() { pg psql -q -X -v ON_ERROR_STOP=1 -U "$PG_SUPERUSER" "$@"; }
# </dev/null: `docker exec -i` forwards stdin, and value() runs inside a loop
# that reads the .counts file on stdin — the first query would swallow it.
value() { pg psql -X -U "$PG_SUPERUSER" -d "$1" -tAc "$2" < /dev/null; }

echo "dump:   $dump"
echo "target: $TARGET (scratch)"

timescale=0
pg pg_restore -l < "$dump" | grep -q " EXTENSION - timescaledb" && timescale=1

su -d postgres -c "SET client_min_messages = warning" -c "DROP DATABASE IF EXISTS $TARGET" \
   -c "CREATE DATABASE $TARGET OWNER $PG_USER"
if [ "$timescale" = 1 ]; then
    su -d "$TARGET" -c "CREATE EXTENSION IF NOT EXISTS timescaledb" -c "SELECT timescaledb_pre_restore()" > /dev/null
fi

# Not --exit-on-error: TimescaleDB's own catalog can raise harmless errors on
# restore (a row CREATE EXTENSION already wrote). Those are shown and let
# through; an error on any other object fails the check.
errors=$(mktemp)
trap 'rm -f "$errors"' EXIT
pg pg_restore -U "$PG_SUPERUSER" -d "$TARGET" < "$dump" 2> "$errors" || true
# pg_restore writes one block per error: "pg_restore: error: ..." and, for a
# failed statement, the "Command was: ..." lines under it. A block is
# tolerated only when it names TimescaleDB (its catalog, its extension);
# anything else — another object, an unreadable archive, a lost connection —
# is blocking. Each block is shown with its verdict.
verdicts=$(awk '
    function close_block() {
        if (block == "") return
        split(block, first, "\n")
        printf "  [%s] %s\n", (block ~ /timescaledb/) ? "tolerated" : "BLOCKING", substr(first[1], 1, 160)
        block = ""
    }
    /^pg_restore: error:/ { close_block(); block = $0; next }
    /^pg_restore: /       { close_block(); next }
    { if (block != "") block = block "\n" $0 }
    END { close_block() }' "$errors")
if [ -n "$verdicts" ]; then
    echo "pg_restore errors:"
    printf '%s\n' "$verdicts"
fi
blocking=$(printf '%s\n' "$verdicts" | grep -c "\[BLOCKING\]" || true)
if [ "$blocking" != 0 ]; then
    echo "RESTORE FAILED ($blocking blocking error(s)) — $TARGET left in place for inspection"
    exit 1
fi
if [ "$timescale" = 1 ]; then
    su -d "$TARGET" -c "SELECT timescaledb_post_restore()" > /dev/null
fi
su -d "$TARGET" -c "ANALYZE"

status=0
counts="$dump.counts"
printf '%-20s %10s %10s  %s\n' table recorded restored verdict
if [ -f "$counts" ]; then
    while read -r table recorded; do
        # A table the dump did not bring back is a mismatch to report, not a
        # reason for `set -e` to stop the check without a word.
        if ! restored=$(value "$TARGET" "SELECT count(*) FROM $table" 2>/dev/null); then
            printf '%-20s %10s %10s  %s\n' "$table" "$recorded" "-" "MISSING"
            status=1
            continue
        fi
        # Counts are read just after the dump: a row written in between (a
        # pool sample, a call) is in the count and not in the dump. Never the
        # other way round, and never more than a handful.
        slack=0
        case "$table" in pool_samples|calls) slack=5 ;; call_media_stats) slack=50 ;; esac
        if [ "$restored" -le "$recorded" ] && [ $((recorded - restored)) -le "$slack" ]; then
            verdict=ok
        else
            verdict=MISMATCH; status=1
        fi
        printf '%-20s %10s %10s  %s\n' "$table" "$recorded" "$restored" "$verdict"
    done < "$counts"
else
    echo "(no $counts: compared with the live database, restored must not exceed it)"
    for table in calls call_media_stats pool_samples manager_users org_units; do
        live=$(value "$PG_DB" "SELECT count(*) FROM $table")
        # A table the dump did not bring back is a mismatch to report, not a
        # reason for `set -e` to stop the check without a word.
        if ! restored=$(value "$TARGET" "SELECT count(*) FROM $table" 2>/dev/null); then
            printf '%-20s %10s %10s  %s\n' "$table" "$live" "-" "MISSING"
            status=1
            continue
        fi
        verdict=ok
        if [ "$restored" -gt "$live" ] || { [ "$restored" = 0 ] && [ "$live" != 0 ]; }; then verdict=MISMATCH; status=1; fi
        printf '%-20s %10s %10s  %s\n' "$table" "$live" "$restored" "$verdict"
    done
fi

for view in $VIEWS; do
    if rows=$(value "$TARGET" "SELECT count(*) FROM $view" 2>&1); then
        printf '%-24s %8s rows  ok\n' "$view" "$rows"
    else
        printf '%-24s FAILED: %s\n' "$view" "$rows"; status=1
    fi
done

if [ "$timescale" = 1 ]; then
    echo "timescaledb $(value "$TARGET" "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")," \
         "restoring=$(value "$TARGET" "SHOW timescaledb.restoring")"
fi

if [ "$status" = 0 ] && [ "$keep" = 0 ]; then
    su -d postgres -c "DROP DATABASE $TARGET"
    echo "restore check passed; $TARGET dropped"
elif [ "$status" = 0 ]; then
    echo "restore check passed; $TARGET kept (--keep)"
else
    echo "RESTORE CHECK FAILED — $TARGET left in place for inspection"
fi
exit "$status"
