#!/bin/sh
# Logical backup of the Manager database, and its rotation.
#
#   ./tools/backup.sh intraday      a dump kept KEEP_INTRADAY_HOURS (48)
#   ./tools/backup.sh nightly       a dump kept KEEP_NIGHTLY_DAYS (30)
#   ./tools/backup.sh manual        a dump never rotated: before a migration
#   ./tools/backup.sh --print-cron  the two crontab lines, for review
#   ./tools/backup.sh --install-cron  put them in this user's crontab (idempotent)
#
# Every dump is checked before it counts: it must list the data of `calls`.
# It is written under a temporary name and renamed only once checked, so a
# file named *.dump is always a complete, readable dump. Rotation runs only
# after a successful dump: a failing backup never deletes the last good one.
#
# Next to each dump, <dump>.counts holds the row counts of the main tables,
# read right after the dump; tools/restore-check.sh compares a restore
# against them. `last-success` is touched on success: its age is what a
# monitor should watch (find "$BACKUP_DIR/last-success" -mmin -1500).
#
# The database carries the TimescaleDB extension (the instance is shared with
# Homer; no hypertable here). pg_dump handles it; restoring needs the
# same extension version and timescaledb_pre/post_restore(), which
# tools/restore-check.sh does and the README spells out.
set -eu
cd "$(dirname "$0")/.."
here=$(pwd)

PG_CONTAINER="${PG_CONTAINER:-postgres}"
PG_USER="${PG_USER:-gw_manager}"
PG_DB="${PG_DB:-gw_manager}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/gw_manager}"
KEEP_INTRADAY_HOURS="${KEEP_INTRADAY_HOURS:-48}"
KEEP_NIGHTLY_DAYS="${KEEP_NIGHTLY_DAYS:-30}"
MARK="# gw_manager-backup"
# Tables counted next to each dump. Their data must come back on restore.
TABLES="calls call_media_stats pool_samples manager_users user_audit org_units org_unit_rules org_unit_audit recompute_log"

# Every PostgreSQL client runs inside the database container. PG_EXEC
# replaces that prefix: the tests point it at a stand-in.
pg() { ${PG_EXEC:-docker exec -i $PG_CONTAINER} "$@"; }

printCron() {
    log="$BACKUP_DIR/backup.log"
    echo "0 8-20/2 * * 1-5 BACKUP_DIR=$BACKUP_DIR $here/tools/backup.sh intraday >> $log 2>&1 $MARK"
    echo "0 2 * * * BACKUP_DIR=$BACKUP_DIR $here/tools/backup.sh nightly >> $log 2>&1 $MARK"
}

kind="${1:-}"
case "$kind" in
    intraday|nightly|manual) ;;
    --print-cron) printCron; exit 0 ;;
    --install-cron)
        { crontab -l 2>/dev/null | grep -vF "$MARK" || true; printCron; } | crontab -
        echo "crontab: $(crontab -l | grep -cF "$MARK") gw_manager-backup lines"
        exit 0 ;;
    *) echo "usage: $0 intraday|nightly|manual|--print-cron|--install-cron" >&2; exit 2 ;;
esac

umask 077
mkdir -p "$BACKUP_DIR"
file="$BACKUP_DIR/gw_manager-$(date +%Y%m%d-%H%M)-$kind.dump"
part="$file.part"
trap 'rm -f "$part" "$part.err" "$part.counts"' EXIT

fail() {
    echo "$(date -Iseconds) FAILED $kind: $1"
    exit 1
}

pg pg_dump -U "$PG_USER" -Fc "$PG_DB" > "$part" 2> "$part.err" \
    || fail "pg_dump: $(tail -n 3 "$part.err" | tr '\n' ' ')"
[ -s "$part" ] || fail "empty dump"
# The check reads the archive's table of contents, not the database: what is
# checked is the file that will be restored.
pg pg_restore -l < "$part" 2>/dev/null | grep -q "TABLE DATA public calls " \
    || fail "the dump does not list the data of calls"

query=""
for table in $TABLES; do
    query="$query${query:+ UNION ALL }SELECT '$table', count(*) FROM $table"
done
pg psql -U "$PG_USER" -d "$PG_DB" -tA -F ' ' -c "$query" > "$part.counts" \
    || fail "row counts"

mv "$part.counts" "$file.counts"
mv "$part" "$file"

removed=$( {
    find "$BACKUP_DIR" -maxdepth 1 -name 'gw_manager-*-intraday.dump' -mmin +$((KEEP_INTRADAY_HOURS * 60)) -print
    find "$BACKUP_DIR" -maxdepth 1 -name 'gw_manager-*-nightly.dump' -mmin +$((KEEP_NIGHTLY_DAYS * 1440)) -print
} | while read -r old; do rm -f "$old" "$old.counts"; echo "$old"; done | wc -l)

touch "$BACKUP_DIR/last-success"
echo "$(date -Iseconds) ok $kind $(basename "$file") $(du -k "$file" | cut -f1) KiB, $removed rotated out"
