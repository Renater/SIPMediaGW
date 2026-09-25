#!/bin/sh
# Run the suite in a container carrying both Python and Node.
#
# Builds the image on first use and reuses it afterwards, so the common case is
# as fast as running pytest directly. Arguments are passed through to pytest.
set -e
cd "$(dirname "$0")/.."
docker build -q -t gw-manager-tests -f tools/Dockerfile.test . > /dev/null
# With a test database, forward its DSN and share the host network so that
# 127.0.0.1 in the DSN is the host (where postgres publishes 5432), not the
# container. Without it the database tests skip, as they always did.
#
#   DATABASE_URL_TEST=postgresql://gw_manager:PASS@127.0.0.1:5432/gw_manager ./tools/test.sh
if [ -n "${DATABASE_URL_TEST:-}" ]; then
    set -- -e DATABASE_URL_TEST --network host gw-manager-tests "$@"
else
    set -- gw-manager-tests "$@"
fi
exec docker run --rm -v "$PWD:/repo:ro" -w /repo "$@"
