"""
tools/backup.sh and tools/restore-check.sh, run for real against a stand-in
for the PostgreSQL clients (PG_EXEC). What is checked is what matters on the
day: a failed dump leaves no file that looks good, rotation never touches a
manual dump nor the last good one, and the restore check refuses the live
database before doing anything.

The restore itself needs a PostgreSQL server and is proved on the lab by
running tools/restore-check.sh (README, "Backup and restore").
"""

import os
import re
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BACKUP = ROOT / "tools" / "backup.sh"
RESTORE = ROOT / "tools" / "restore-check.sh"

pytestmark = pytest.mark.skipif(shutil.which("sh") is None or shutil.which("find") is None,
                                reason="needs a POSIX shell and find")

# Answers like the three clients the scripts call: a dump, its table of
# contents, the row counts. FAKE_FAIL / FAKE_TOC switch one of them to a failure.
FAKE_PG = r'''#!/bin/sh
case "$1" in
  pg_dump) [ "${FAKE_FAIL:-}" = dump ] && { echo "pg_dump: error: no such database" >&2; exit 3; }
           printf 'PGDMP fake archive' ;;
  pg_restore) cat > /dev/null
           if [ "${FAKE_TOC:-}" = nocalls ]; then echo "1; 0 1 TABLE DATA public vm_rates gw_manager"
           else echo "1; 0 1 TABLE DATA public calls gw_manager"; fi
           if [ "$2" != -l ] && [ "${FAKE_RESTORE:-}" = mixed ]; then
             printf '%s\n' \
               'pg_restore: error: could not execute query: ERROR:  duplicate key value violates unique constraint "metadata_pkey"' \
               'Command was: COPY _timescaledb_catalog.metadata (key, value) FROM stdin;' \
               'pg_restore: error: could not execute query: ERROR:  relation "calls" already exists' \
               'Command was: CREATE TABLE public.calls (' \
               'pg_restore: warning: errors ignored on restore: 2' >&2
             exit 1
           fi ;;
  psql) cat > /dev/null   # like `docker exec -i`: whatever stdin holds is gone
        case "$*" in
          *"UNION ALL"*) printf 'calls 3\ncall_media_stats 6\npool_samples 10\n' ;;
          *"FROM calls"*) echo 3 ;;
          *"FROM call_media_stats"*) echo 6 ;;
          *"FROM pool_samples"*) echo 10 ;;
          *count*) echo 0 ;;
        esac ;;
esac
'''


def environment(tmp_path):
    fake = tmp_path / "fakepg"
    fake.write_text(FAKE_PG)
    fake.chmod(0o755)
    backups = tmp_path / "backups"
    env = dict(os.environ, PG_EXEC=str(fake), BACKUP_DIR=str(backups))
    return env, backups


def run(script, *args, env):
    return subprocess.run(["sh", str(script), *args], env=env, capture_output=True, text=True, timeout=30,
                          stdin=subprocess.DEVNULL)


def dumps(backups):
    return sorted(p.name for p in backups.glob("gw_manager-*.dump"))


def age(path, hours):
    stamp = time.time() - hours * 3600
    os.utime(path, (stamp, stamp))


def test_scripts_are_executable_shell():
    for script in (BACKUP, RESTORE):
        assert script.stat().st_mode & stat.S_IXUSR, f"{script.name} is not executable"
        assert subprocess.run(["sh", "-n", str(script)]).returncode == 0, f"{script.name}: syntax"


def test_a_dump_is_written_checked_and_counted(tmp_path):
    env, backups = environment(tmp_path)
    result = run(BACKUP, "intraday", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    [name] = dumps(backups)
    assert name.endswith("-intraday.dump")
    assert (backups / name).read_text() == "PGDMP fake archive"
    assert (backups / (name + ".counts")).read_text().startswith("calls 3\n")
    assert (backups / "last-success").exists()
    assert not list(backups.glob("*.part*")), "a temporary file was left behind"
    assert oct((backups / name).stat().st_mode & 0o777) == "0o600", "a dump holds password hashes"
    assert " ok intraday " in result.stdout


def test_a_failed_dump_leaves_nothing_that_looks_good(tmp_path):
    env, backups = environment(tmp_path)
    assert run(BACKUP, "nightly", env=env).returncode == 0
    before = dumps(backups)
    marker = backups / "last-success"
    age(marker, 5)
    stamp = marker.stat().st_mtime
    for failure in ({"FAKE_FAIL": "dump"}, {"FAKE_TOC": "nocalls"}):
        result = run(BACKUP, "intraday", env={**env, **failure})
        assert result.returncode == 1 and "FAILED intraday" in result.stdout, result.stdout
        assert dumps(backups) == before
        assert not list(backups.glob("*.part*"))
        assert marker.stat().st_mtime == stamp, "last-success moved on a failure"


def test_rotation_keeps_what_each_kind_promises(tmp_path):
    env, backups = environment(tmp_path)
    backups.mkdir()
    ages = {
        "gw_manager-20260101-1000-intraday.dump": 49,        # past 48 h: goes
        "gw_manager-20260101-1200-intraday.dump": 47,        # stays
        "gw_manager-20260101-0200-nightly.dump": 31 * 24,    # past 30 days: goes
        "gw_manager-20260102-0200-nightly.dump": 29 * 24,    # stays
        "gw_manager-20250101-0900-manual.dump": 400 * 24,    # never rotated
    }
    for name, hours in ages.items():
        (backups / name).write_text("old")
        (backups / (name + ".counts")).write_text("calls 1\n")
        age(backups / name, hours)
    result = run(BACKUP, "nightly", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    left = dumps(backups)
    assert "gw_manager-20260101-1000-intraday.dump" not in left
    assert "gw_manager-20260101-0200-nightly.dump" not in left
    for kept in ("gw_manager-20260101-1200-intraday.dump", "gw_manager-20260102-0200-nightly.dump",
                 "gw_manager-20250101-0900-manual.dump"):
        assert kept in left, f"{kept} was rotated out"
    assert not (backups / "gw_manager-20260101-1000-intraday.dump.counts").exists(), "orphan .counts"
    assert "2 rotated out" in result.stdout


def test_cron_lines_are_the_agreed_schedule(tmp_path):
    env, backups = environment(tmp_path)
    lines = run(BACKUP, "--print-cron", env=env).stdout.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("0 8-20/2 * * 1-5 ") and " intraday " in lines[0]
    assert lines[1].startswith("0 2 * * * ") and " nightly " in lines[1]
    for line in lines:
        assert line.endswith("# gw_manager-backup")
        assert f"BACKUP_DIR={backups} " in line, "cron would fall back to the default directory"


def test_unknown_kind_is_refused(tmp_path):
    env, _ = environment(tmp_path)
    assert run(BACKUP, "weekly", env=env).returncode == 2


def test_restore_check_never_targets_the_live_database(tmp_path):
    env, backups = environment(tmp_path)
    run(BACKUP, "manual", env=env)
    for target in ("gw_manager", "gw_manager_copy", "postgres"):
        result = run(RESTORE, env={**env, "RESTORE_DB": target})
        assert result.returncode == 2 and "refusing" in result.stderr, target
        assert "dump:" not in result.stdout, "refused after starting"


def test_restore_check_wraps_timescaledb(tmp_path):
    """The extension is kept on purpose; restoring it needs these two calls."""
    source = RESTORE.read_text()
    assert source.index("timescaledb_pre_restore()") < source.index("pg_restore -U") \
        < source.index("timescaledb_post_restore()")


def test_restore_check_without_a_dump_says_so(tmp_path):
    env, _ = environment(tmp_path)
    result = run(RESTORE, env=env)
    assert result.returncode == 2 and "no dump" in result.stderr


def test_restore_errors_outside_timescaledb_fail_the_check(tmp_path):
    """
    pg_restore goes on after an error. One on TimescaleDB's own catalog is
    expected and let through; one on anything else means a partial restore.
    Real pg_restore output carries no "from TOC entry" line by default: the
    verdict reads each error block, message and command.
    """
    env, _ = environment(tmp_path)
    run(BACKUP, "manual", env=env)
    result = run(RESTORE, env={**env, "FAKE_RESTORE": "mixed"})
    assert result.returncode == 1, result.stdout + result.stderr
    assert '[tolerated] pg_restore: error: could not execute query: ERROR:  duplicate key' in result.stdout
    assert '[BLOCKING] pg_restore: error: could not execute query: ERROR:  relation "calls"' in result.stdout
    assert "RESTORE FAILED (1 blocking error(s))" in result.stdout


def test_restore_check_compares_every_recorded_table(tmp_path):
    """
    On the lab the check compared `calls` and stopped: the first query, run
    through `docker exec -i`, read the rest of the .counts file. The stand-in
    drains stdin the same way; every recorded table must still be compared.
    """
    env, backups = environment(tmp_path)
    assert run(BACKUP, "manual", env=env).returncode == 0
    result = run(RESTORE, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    compared = [match.group(1) for match in re.finditer(r"^(\w+) +\d+ +\d+  ok$", result.stdout, re.M)]
    assert compared == ["calls", "call_media_stats", "pool_samples"], result.stdout
    assert "restore check passed" in result.stdout
