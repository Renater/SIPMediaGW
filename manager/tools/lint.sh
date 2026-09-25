#!/bin/sh
# The three static checks, in the test image (which carries the tools):
#
#   docker run --rm -v "$PWD:/repo:ro" -w /repo --entrypoint sh gw-manager-tests tools/lint.sh
#
# Runs all three even when the first fails, so one run shows everything;
# exits non-zero if any did. Caches go to /tmp: the repository is read-only.
cd "$(dirname "$0")/.." || exit 1
status=0

echo "== ruff"
ruff check --no-cache . || status=1

echo "== mypy"
MYPY_CACHE_DIR=/tmp/mypy-cache mypy || status=1

echo "== pip-audit"
# Runtime dependencies only: an advisory on pytest is not a production risk.
# Needs network for the advisory database; the test image has it.
pip-audit --progress-spinner off -r requirements.txt || status=1

exit $status
