// Runs in every frame before the page's own scripts (CDP
// Page.addScriptToEvaluateOnNewDocument, see src/rtcstatsTrace.py).
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
            if (!connected) {
                connected = true;
                trace.connect(config.url);
            }
            trace(...args);
        };
        const options = {getStatsInterval: config.getStatsInterval};
        lib.wrapRTCPeerConnection(lazyTrace, window, options);
        lib.wrapGetUserMedia(lazyTrace, window);
        lib.wrapEnumerateDevices(lazyTrace, window);
        lib.wrapSetSinkId(lazyTrace, window);

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
    } catch (e) {
        console.warn('[rtcstats] setup failed, tracing off in this frame:', e);
    }
})();
