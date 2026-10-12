"""
rtcstatsTrace registers the rtcstats library in the call's Chrome before any
meeting page loads, and only when RTCSTATS_ENABLED=true with a server URL. A
failure here must never stop the call, and the server token must never reach
the logs.
"""
import io
import json
import os
import sys
import urllib.error
import urllib.parse
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))
import rtcstatsTrace  # noqa: E402

ON = {"RTCSTATS_ENABLED": "true", "RTCSTATS_SERVER_URL": "wss://stats.example.org/sipmediagw"}


def driver():
    d = Mock()
    d.session_id = "abc123"
    return d


def assets(tmp_path, monkeypatch):
    bundle = tmp_path / "rtcstats.bundle.js"
    bundle.write_text("window.__sipmediagwRtcstatsLib = {};")
    boot = tmp_path / "bootstrap.js"
    boot.write_text("/* bootstrap */")
    monkeypatch.setattr(rtcstatsTrace, "BUNDLE", str(bundle))
    monkeypatch.setattr(rtcstatsTrace, "BOOTSTRAP", str(boot))


def test_disabled_by_default():
    assert rtcstatsTrace.serverUrl({}) is None
    assert rtcstatsTrace.serverUrl({"RTCSTATS_ENABLED": "false",
                                    "RTCSTATS_SERVER_URL": "ws://x"}) is None


def test_enabled_without_server_warns_and_stays_off(capsys):
    assert rtcstatsTrace.serverUrl({"RTCSTATS_ENABLED": "true"}) is None
    assert "rtcstats:" in capsys.readouterr().out


def test_enabled_with_server():
    assert rtcstatsTrace.serverUrl(ON) == ON["RTCSTATS_SERVER_URL"]


def test_trace_url_keeps_token_and_adds_call_metadata():
    url = rtcstatsTrace.traceUrl("wss://s.example/p?rtcstats-token=JWT", "gw0", "room1", "jitsi")
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert query == {"rtcstats-token": ["JWT"], "gw": ["gw0"], "room": ["room1"], "browsing": ["jitsi"]}
    assert url.startswith("wss://s.example/p?")


def test_trace_url_encodes_room_names():
    url = rtcstatsTrace.traceUrl("ws://s", "gw0", "Réunion a/b & c", "bigbluebutton")
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert query["room"] == ["Réunion a/b & c"]
    assert " " not in url


def test_trace_url_leaves_out_empty_values():
    url = rtcstatsTrace.traceUrl("ws://s", "", "", "teams")
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(url).query) == {"browsing": ["teams"]}


def test_build_script_sets_config_before_bundle_and_bootstrap():
    script = rtcstatsTrace.buildScript("ws://s?gw=1", "BUNDLE();", "BOOT();")
    assert script.index("window.__sipmediagwRtcstats =") < script.index("BUNDLE();") < script.index("BOOT();")
    config = json.loads(script.split("=", 1)[1].split(";\n", 1)[0])
    assert config == {"url": "ws://s?gw=1", "getStatsInterval": 1000}


def test_inject_does_nothing_when_disabled():
    with patch("rtcstatsTrace.urllib.request.urlopen") as urlopen:
        assert rtcstatsTrace.inject(driver(), "gw0", "r", "jitsi", env={}) is False
    urlopen.assert_not_called()


def test_inject_registers_script_on_new_document(tmp_path, monkeypatch):
    assets(tmp_path, monkeypatch)
    with patch("rtcstatsTrace.urllib.request.urlopen",
               return_value=io.BytesIO(b'{"value": {}}')) as urlopen:
        assert rtcstatsTrace.inject(driver(), "gw0", "room1", "jitsi", env=ON) is True
    request = urlopen.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:9515/session/abc123/goog/cdp/execute"
    assert request.get_method() == "POST"
    body = json.loads(request.data)
    assert body["cmd"] == "Page.addScriptToEvaluateOnNewDocument"
    source = body["params"]["source"]
    assert "window.__sipmediagwRtcstatsLib = {};" in source and "/* bootstrap */" in source
    assert "room=room1" in source and "gw=gw0" in source


def test_missing_bundle_disables_tracing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rtcstatsTrace, "BUNDLE", str(tmp_path / "absent.js"))
    with patch("rtcstatsTrace.urllib.request.urlopen") as urlopen:
        assert rtcstatsTrace.inject(driver(), "gw0", "r", "jitsi", env=ON) is False
    urlopen.assert_not_called()
    assert "rtcstats:" in capsys.readouterr().out


def test_chromedriver_error_disables_tracing(tmp_path, monkeypatch):
    assets(tmp_path, monkeypatch)
    with patch("rtcstatsTrace.urllib.request.urlopen",
               side_effect=urllib.error.URLError("refused")):
        assert rtcstatsTrace.inject(driver(), "gw0", "r", "jitsi", env=ON) is False


def test_logs_never_show_the_token(tmp_path, monkeypatch, capsys):
    assets(tmp_path, monkeypatch)
    env = {"RTCSTATS_ENABLED": "true",
           "RTCSTATS_SERVER_URL": "wss://stats.example.org/x?rtcstats-token=SECRET"}
    with patch("rtcstatsTrace.urllib.request.urlopen", return_value=io.BytesIO(b"{}")):
        rtcstatsTrace.inject(driver(), "gw0", "r", "jitsi", env=env)
    out = capsys.readouterr().out
    assert "SECRET" not in out and "stats.example.org" in out


def test_close_waits_for_the_websockets_to_close():
    d = driver()
    d.execute_script.return_value = True
    with patch("rtcstatsTrace.time.sleep") as sleep:
        rtcstatsTrace.close(d, flushSeconds=0.5)
    assert "__sipmediagwRtcstatsCloseAll" in d.execute_script.call_args.args[0]
    sleep.assert_called_once_with(0.5)


def test_close_without_trace_does_not_wait():
    d = driver()
    d.execute_script.return_value = False
    with patch("rtcstatsTrace.time.sleep") as sleep:
        rtcstatsTrace.close(d)
    sleep.assert_not_called()


def test_close_never_raises():
    d = driver()
    d.execute_script.side_effect = Exception("window closed")
    rtcstatsTrace.close(d)


def test_bootstrap_uses_the_names_python_relies_on():
    with open(rtcstatsTrace.BOOTSTRAP, encoding="utf-8") as f:
        source = f.read()
    assert rtcstatsTrace.CONFIG_GLOBAL in source
    assert rtcstatsTrace.CLOSE_FUNCTION in source
    assert "window.__sipmediagwRtcstatsLib" in source
    assert "'sipmediagw:rtcstats:close'" in source
