#!/bin/sh
# Build the gateway image as a release: versioned, and refusing to be `dev`.
#
#   ./tools/build-release.sh
#
# git describe gives the last tag, how far past it this is, and the commit —
# "v1.9.0-3-g471eab4" reads as three commits after v1.9.0. The --dirty suffix
# appears when the tree has uncommitted changes, which on a release build is
# itself the most interesting thing the field could say.
set -eu
cd "$(dirname "$0")/.."

version=$(git describe --tags --always --dirty 2>/dev/null || echo "")
if [ -z "$version" ]; then
    echo "no version from git describe; not a repository?" >&2
    exit 1
fi
case "$version" in
    *-dirty) echo "warning: building from a modified tree ($version)" >&2 ;;
esac

echo "building $version"
ALLOW_DEV_BUILD=0 GW_VERSION="$version" docker compose build "$@"
