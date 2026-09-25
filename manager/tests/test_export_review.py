"""
tools/export-for-review.sh, run for real on a small stand-in tree: the
archive holds the code and none of the secrets, and it is not written at all
when a kept file carries a value of .env.
"""

import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "export-for-review.sh"

pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("bash", "find", "tar", "xargs", "grep")),
    reason="needs bash, find, tar, xargs and grep")

SECRET = "fake-value-for-the-test"
# Written in two halves: whole, this line would itself be a private-key block
# for the script, gitleaks and every scanner run on the repository.
KEY_BLOCK = "-----BEGIN RSA " + "PRIVATE KEY-----"


def tree(tmp_path):
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "tools" / SCRIPT.name)
    (repo / "app.py").write_text("print('hello')\n")
    (repo / ".env").write_text(f"PG_PASSWORD={SECRET}\nexport SESSION_SECRET=\"abcdefghijkl\"\nPG_USER=gw_manager\n")
    (repo / ".env.example").write_text("PG_PASSWORD=CHANGE_ME\n")
    (repo / ".env.prod").write_text(f"PG_PASSWORD={SECRET}\n")
    (repo / "server.key").write_text("x\n")
    (repo / "gw.dump").write_text("x\n")
    (repo / "__pycache__").mkdir()
    (repo / "__pycache__" / "app.cpython-312.pyc").write_text("x\n")
    return repo


def run(repo, out):
    return subprocess.run(["bash", str(repo / "tools" / SCRIPT.name), str(out)],
                          capture_output=True, text=True, timeout=60)


def test_the_archive_holds_the_code_and_no_secret(tmp_path):
    repo = tree(tmp_path)
    result = run(repo, tmp_path / "out")
    assert result.returncode == 0, result.stdout + result.stderr
    assert SECRET not in result.stdout + result.stderr
    [archive] = list((tmp_path / "out").glob("manager-review-*.tar.gz"))
    with tarfile.open(archive) as tar:
        names = {n.split("/", 1)[1] for n in tar.getnames() if "/" in n}
        contents = b"".join(tar.extractfile(m).read() for m in tar.getmembers() if m.isfile())
    assert {"app.py", ".env.example", "tools/export-for-review.sh", "REVIEW-EXPORT.txt"} <= names
    assert not names & {".env", ".env.prod", "server.key", "gw.dump", "__pycache__/app.cpython-312.pyc"}
    assert SECRET.encode() not in contents


def test_a_leaked_value_stops_the_export(tmp_path):
    repo = tree(tmp_path)
    (repo / "settings.py").write_text(f"DSN = 'postgresql://u:{SECRET}@db/x'\n")
    (repo / "notes.txt").write_text(KEY_BLOCK + "\n")
    result = run(repo, tmp_path / "out")
    assert result.returncode == 1
    assert "settings.py holds the value of PG_PASSWORD" in result.stdout
    assert "notes.txt:1 (private key)" in result.stdout
    assert SECRET not in result.stdout + result.stderr, "the value itself is never printed"
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").iterdir())


def test_a_default_shipped_in_the_example_is_not_a_secret(tmp_path):
    """
    The repository's .env starts as a copy of .env.example: a value the example
    ships (a default password documented in the README) is public, and stops
    nothing. The same key with another value in .env still does.
    """
    repo = tree(tmp_path)
    (repo / ".env.example").write_text("PG_PASSWORD=CHANGE_ME\nDEFAULT_PASSWORD=shipped-default\n")
    (repo / ".env").write_text("DEFAULT_PASSWORD=shipped-default\n")
    (repo / ".env.prod").unlink()
    (repo / "README.md").write_text("First sign-in: shipped-default.\n")
    result = run(repo, tmp_path / "out")
    assert "SECRET:" not in result.stdout, result.stdout
    assert result.returncode == 0, result.stdout + result.stderr

    (repo / ".env").write_text("DEFAULT_PASSWORD=changed-by-the-deployment\n")
    (repo / "notes.md").write_text("changed-by-the-deployment\n")
    result = run(repo, tmp_path / "out2")
    assert result.returncode == 1
    assert "notes.md holds the value of DEFAULT_PASSWORD" in result.stdout


def test_the_repository_itself_exports_clean(tmp_path):
    """
    The first run on the lab stopped on this very file: a test that writes a
    fake key must not carry one. Run on the real tree, the script must pass.
    """
    result = subprocess.run(["bash", str(SCRIPT), str(tmp_path)], capture_output=True, text=True, timeout=120)
    assert "SECRET:" not in result.stdout, result.stdout
    assert result.returncode == 0, result.stdout + result.stderr


def test_domain_names_outside_tests_are_listed(tmp_path):
    """A lab or customer name in a comment is what the address check misses."""
    repo = tree(tmp_path)
    (repo / "notes.md").write_text("reached on intranet.acme.fr, see https://github.com/x and example.org\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_x.py").write_text("HOST = 'lab.acme.fr'\n")
    result = run(repo, tmp_path / "out")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "notes.md:intranet.acme.fr (1)" in result.stdout
    assert "github.com" not in result.stdout and "notes.md:example.org" not in result.stdout
    assert "lab.acme.fr" not in result.stdout, "tests are left out"
