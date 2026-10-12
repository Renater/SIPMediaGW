// Runs in every tab and frame before the page's own scripts (extension
// content script, MAIN world, document_start: see src/rtcstatsTrace.py).
(function () {
    const CLOSE_MESSAGE = 'sipmediagw:rtcstats:close';
    const config = window.__sipmediagwRtcstats;
    const lib = window.__sipmediagwRtcstatsLib;
    if (!config || !lib || window.__sipmediagwRtcstatsCloseAll) {
        return;
    }
    try {
        const trace = lib.WebSocketTrace({log: console.warn.bind(console)});
        let connected = false;
        let closed = false;
        // Connect on the first WebRTC/media call only: frames without
        // WebRTC (ads, widgets...) must not create empty dumps.
        const lazyTrace = function (...args) {
            if (closed) {
                return;
            }
            // Never let a tracing error reach the meeting's own WebRTC calls.
            try {
                if (!connected) {
                    connected = true;
                    trace.connect(config.url);
                }
                trace(...args);
            } catch (e) {
                closed = true;
                console.warn('[rtcstats] tracing off in this frame:', e);
            }
        };
        // Defined before wrapping anything: a frame whose setup fails
        // halfway must still be able to close what it opened.
        window.__sipmediagwRtcstatsCloseAll = function () {
            if (!closed) {
                closed = true;
                trace.close();
            }
            for (let i = 0; i < window.frames.length; i++) {
                try {
                    window.frames[i].postMessage(CLOSE_MESSAGE, '*');
                } catch (e) { /* frame gone */ }
            }
        };
        window.addEventListener('message', function (event) {
            if (event.data === CLOSE_MESSAGE) {
                window.__sipmediagwRtcstatsCloseAll();
            }
        });

        const options = {getStatsInterval: config.getStatsInterval};
        lib.wrapRTCPeerConnection(lazyTrace, window, options);
        lib.wrapGetUserMedia(lazyTrace, window);
        lib.wrapEnumerateDevices(lazyTrace, window);
        // Not in any rtcstats release yet (v2.4.0); used once it is.
        if (typeof lib.wrapSetSinkId === 'function') {
            lib.wrapSetSinkId(lazyTrace, window);
        }
    } catch (e) {
        console.warn('[rtcstats] setup failed, tracing off in this frame:', e);
    }
})();
