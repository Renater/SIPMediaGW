#!/usr/bin/env python

import os
import json
import time
import urllib.parse

ASSETS = os.path.join(os.path.dirname(os.path.normpath(__file__)), '../browsing/assets/rtcstats')
BUNDLE = os.path.join(ASSETS, 'rtcstats.bundle.js')
BOOTSTRAP = os.path.join(ASSETS, 'bootstrap.js')
EXTENSION_DIR = "/tmp/sipmediagw-rtcstats"
CONFIG_GLOBAL = "window.__sipmediagwRtcstats"
CLOSE_FUNCTION = "window.__sipmediagwRtcstatsCloseAll"
GET_STATS_INTERVAL_MS = 1000


def serverUrl(env=os.environ):
    if env.get('RTCSTATS_ENABLED') != 'true':
        return None
    url = env.get('RTCSTATS_SERVER_URL', '').strip()
    if not url:
        print("rtcstats: RTCSTATS_ENABLED is true but RTCSTATS_SERVER_URL is empty, tracing off", flush=True)
        return None
    if urllib.parse.urlsplit(url).scheme not in ('ws', 'wss'):
        print("rtcstats: RTCSTATS_SERVER_URL must start with ws:// or wss://, tracing off", flush=True)
        return None
    return url


def traceUrl(serverUrl, gwName, roomName, browsing):
    parts = urllib.parse.urlsplit(serverUrl)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query += [(k, v) for k, v in (('gw', gwName), ('room', roomName), ('browsing', browsing)) if v]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def buildScript(url, bundle, bootstrap):
    config = {"url": url, "getStatsInterval": GET_STATS_INTERVAL_MS}
    return "{} = {};\n{}\n{}".format(CONFIG_GLOBAL, json.dumps(config), bundle, bootstrap)


def _withoutQuery(url):
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parts._replace(query='', fragment=''))


def prepare(chromeOptions, gwName, roomName, browsing, env=os.environ, extensionDir=EXTENSION_DIR):
    """Make the Chrome about to start run the trace in every tab and frame,
    before the page's own scripts: an unpacked extension whose content
    script runs in the page's world at document_start. Call it before the
    driver is created."""
    loadArg = '--load-extension=' + extensionDir
    if loadArg in chromeOptions.arguments:
        chromeOptions.arguments.remove(loadArg)
    url = serverUrl(env)
    if not url:
        return False
    try:
        with open(BUNDLE, "r", encoding="utf-8") as f:
            bundle = f.read()
        with open(BOOTSTRAP, "r", encoding="utf-8") as f:
            bootstrap = f.read()
        manifest = {
            "manifest_version": 3,
            "name": "SIPMediaGW rtcstats",
            "version": "1.0",
            "content_scripts": [{
                "matches": ["<all_urls>"],
                "js": ["rtcstats.js"],
                "run_at": "document_start",
                "all_frames": True,
                "match_about_blank": True,
                "world": "MAIN"
            }]
        }
        os.makedirs(extensionDir, exist_ok=True)
        with open(os.path.join(extensionDir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        with open(os.path.join(extensionDir, "rtcstats.js"), "w", encoding="utf-8") as f:
            f.write(buildScript(traceUrl(url, gwName, roomName, browsing), bundle, bootstrap))
    except OSError as e:
        print("rtcstats: cannot set up the trace, tracing off: {}".format(e), flush=True)
        return False
    chromeOptions.add_argument(loadArg)
    print("rtcstats: tracing to {}".format(_withoutQuery(url)), flush=True)
    return True


def close(driver, flushSeconds=1.0):
    # Some platforms (BBB ESR, Webinaire) run the meeting in a tab they
    # open themselves: close the trace in every tab, then come back.
    closed = False
    try:
        current = driver.current_window_handle
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            closed = driver.execute_script(
                "if ({0}) {{ {0}(); return true; }} return false;".format(CLOSE_FUNCTION)) or closed
        driver.switch_to.window(current)
    except Exception as e:
        print("rtcstats: could not close the trace: {}".format(e), flush=True)
    if closed:
        # Let the WebSocket close frames leave before Chrome quits.
        time.sleep(flushSeconds)
        print("rtcstats: trace closed", flush=True)
