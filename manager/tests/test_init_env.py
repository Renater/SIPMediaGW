"""
tools/init-env.sh: the shipped .env starts without a secret, the script fills
the empty ones once and never touches a value that is already there.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "init-env.sh"

pytestmark = pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX shell")


def _copy(tmp_path):
    """A checkout of the Manager reduced to the script and the example file."""
    (tmp_path / "tools").mkdir()
    shutil.copy(SCRIPT, tmp_path / "tools" / "init-env.sh")
    shutil.copy(ROOT / ".env.example", tmp_path / ".env")
    return tmp_path


def _run(repo):
    return subprocess.run(["sh", str(repo / "tools" / "init-env.sh")], cwd=repo,
                          capture_output=True, text=True, check=True)


def _values(path):
    return dict(line.split("=", 1) for line in path.read_text().splitlines()
                if re.match(r"^[A-Z_]+=", line))


def test_the_shipped_env_holds_no_secret():
    """What goes to the repository: the defaults, every secret empty."""
    env = _values(ROOT / ".env.example")
    assert env["MANAGER_SESSION_SECRET"] == ""
    assert env["INGEST_TOKEN"] == ""
    assert env["PROXYAPI_ADMIN_TOKEN"] == ""
    assert ":CHANGE_ME@" in env["DATABASE_URL"]


def test_fills_the_empty_secrets_and_prints_none(tmp_path):
    repo = _copy(tmp_path)
    result = _run(repo)
    env = _values(repo / ".env")
    assert re.fullmatch(r"[0-9a-f]{64}", env["MANAGER_SESSION_SECRET"])
    assert re.fullmatch(r"[0-9a-f]{48}", env["INGEST_TOKEN"])
    password = re.search(r"://gw_manager:([^@]*)@", env["DATABASE_URL"]).group(1)
    assert re.fullmatch(r"[0-9a-f]{32}", password)
    for secret in (env["MANAGER_SESSION_SECRET"], env["INGEST_TOKEN"], password):
        assert secret not in result.stdout + result.stderr
    assert "PROXYAPI_ADMIN_TOKEN is empty" in result.stdout
    assert (repo / ".env").stat().st_mode & 0o077 == 0


def test_a_second_run_changes_nothing(tmp_path):
    repo = _copy(tmp_path)
    _run(repo)
    first = (repo / ".env").read_text()
    result = _run(repo)
    assert (repo / ".env").read_text() == first
    assert "Nothing to generate" in result.stdout


def test_never_overwrites_a_value(tmp_path):
    repo = _copy(tmp_path)
    env_file = repo / ".env"
    text = env_file.read_text().replace("MANAGER_SESSION_SECRET=\n", "MANAGER_SESSION_SECRET=kept\n")
    env_file.write_text(text)
    _run(repo)
    env = _values(env_file)
    assert env["MANAGER_SESSION_SECRET"] == "kept"
    assert env["INGEST_TOKEN"] != ""
    # Everything else is the file as it was, line for line.
    before = [line for line in text.splitlines() if not line.startswith(("INGEST_TOKEN=", "DATABASE_URL="))]
    after = [line for line in env_file.read_text().splitlines() if not line.startswith(("INGEST_TOKEN=", "DATABASE_URL="))]
    assert before == after
