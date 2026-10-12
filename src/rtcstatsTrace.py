#!/usr/bin/env python

import os
import json
import time
import urllib.error
import urllib.parse
import urllib.request

ASSETS = os.path.join(os.path.dirname(os.path.normpath(__file__)), '../browsing/assets/rtcstats')
BUNDLE = os.path.join(ASSETS, 'rtcstats.bundle.js')
BOOTSTRAP = os.path.join(ASSETS, 'bootstrap.js')
CHROMEDRIVER = "http://127.0.0.1:9515"
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


def inject(driver, gwName, roomName, browsing, env=os.environ, chromedriver=CHROMEDRIVER):
    url = serverUrl(env)
    if not url:
        return False
    try:
        with open(BUNDLE, "r", encoding="utf-8") as f:
            bundle = f.read()
        with open(BOOTSTRAP, "r", encoding="utf-8") as f:
            bootstrap = f.read()
    except OSError as e:
        print("rtcstats: library not found, tracing off: {}".format(e), flush=True)
        return False
    script = buildScript(traceUrl(url, gwName, roomName, browsing), bundle, bootstrap)
    body = json.dumps({"cmd": "Page.addScriptToEvaluateOnNewDocument",
                       "params": {"source": script}}).encode()
    request = urllib.request.Request(
        "{}/session/{}/goog/cdp/execute".format(chromedriver, driver.session_id),
        data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as reply:
            reply.read()
    except (urllib.error.URLError, OSError) as e:
        print("rtcstats: injection failed, tracing off: {}".format(e), flush=True)
        return False
    print("rtcstats: tracing to {}".format(_withoutQuery(url)), flush=True)
    return True


def close(driver, flushSeconds=1.0):
    try:
        closed = driver.execute_script(
            "if ({0}) {{ {0}(); return true; }} return false;".format(CLOSE_FUNCTION))
    except Exception as e:
        print("rtcstats: could not close the trace: {}".format(e), flush=True)
        return
    if closed:
        # Let the WebSocket close frames leave before Chrome quits.
        time.sleep(flushSeconds)
        print("rtcstats: trace closed", flush=True)
