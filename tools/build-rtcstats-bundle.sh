#!/bin/sh
# Rebuild the rtcstats-js browser bundle (https://github.com/rtcstats/rtcstats, MIT)
# committed in browsing/assets/rtcstats/rtcstats.bundle.js.
#
#   ./tools/build-rtcstats-bundle.sh            # rtcstats v2.4.0
#   RTCSTATS_VERSION=v2.5.0 ./tools/build-rtcstats-bundle.sh
#
# The gateway image only copies the committed file; run this when bumping the
# rtcstats version, then commit the result. Node runs in a throwaway container.
set -eu
cd "$(dirname "$0")/.."

RTCSTATS_VERSION=${RTCSTATS_VERSION:-v2.4.0}
out=browsing/assets/rtcstats

docker run --rm \
    -e RTCSTATS_VERSION="$RTCSTATS_VERSION" \
    -e OWNER="$(id -u):$(id -g)" \
    -v "$PWD/$out:/out" \
    node:22-bookworm sh -euc '
        git clone --depth 1 --branch "$RTCSTATS_VERSION" https://github.com/rtcstats/rtcstats.git /rtcstats
        cd /rtcstats
        npm install --omit=dev --ignore-scripts
        npx --yes -p webpack@5.99.9 -p webpack-cli@6.0.1 webpack \
            --entry ./packages/rtcstats-js/rtcstats.js \
            --output-path /build --output-filename rtcstats.bundle.js \
            --mode production \
            --output-library-name __sipmediagwRtcstatsLib --output-library-type window
        grep -q __sipmediagwRtcstatsLib /build/rtcstats.bundle.js
        cp /build/rtcstats.bundle.js /out/rtcstats.bundle.js
        chown "$OWNER" /out/rtcstats.bundle.js
    '

echo "$out/rtcstats.bundle.js built from rtcstats $RTCSTATS_VERSION"
