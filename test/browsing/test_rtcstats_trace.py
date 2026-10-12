"""
rtcstatsTrace makes the call's Chrome load the rtcstats library, as an
extension content script, in every tab and frame before any meeting script
runs, and only when RTCSTATS_ENABLED=true with a ws(s):// server URL. A
failure here must never stop the call, and the server token must never reach
the logs.
"""
import json
import os
import sys
import urllib.parse
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))
import rtcstatsTrace  # noqa: E402

ON = {"RTCSTATS_ENABLED": "true", "RTCSTATS_SERVER_URL": "wss://stats.example.org/sipmediagw"}


class Options:
    """The part of selenium's ChromeOptions the module uses."""
    def __init__(self, *arguments):
        self.arguments = list(arguments)

    def add_argument(self, argument):
        self.arguments.append(argument)


def assets(tmp_path, monkeypatch):
    bundle = tmp_path / "rtcstats.bundle.js"
    bundle.write_text("window.__sipmediagwRtcstatsLib = {};")
    boot = tmp_path / "bootstrap.js"
    boot.write_text("/* bootstrap */")
    monkeypatch.setattr(rtcstatsTrace, "BUNDLE", str(bundle))
    monkeypatch.setattr(rtcstatsTrace, "BOOTSTRAP", str(boot))
    return tmp_path / "extension"


def test_disabled_by_default():
    assert rtcstatsTrace.serverUrl({}) is None
    assert rtcstatsTrace.serverUrl({"RTCSTATS_ENABLED": "false",
                                    "RTCSTATS_SERVER_URL": "ws://x"}) is None


def test_enabled_without_server_warns_and_stays_off(capsys):
    assert rtcstatsTrace.serverUrl({"RTCSTATS_ENABLED": "true"}) is None
    assert "rtcstats:" in capsys.readouterr().out


def test_enabled_with_server():
    assert rtcstatsTrace.serverUrl(ON) == ON["RTCSTATS_SERVER_URL"]


def test_server_without_websocket_scheme_is_refused(capsys):
    for url in ("stats.example.org/x", "https://stats.example.org/x"):
        env = {"RTCSTATS_ENABLED": "true", "RTCSTATS_SERVER_URL": url}
        assert rtcstatsTrace.serverUrl(env) is None
    assert "rtcstats:" in capsys.readouterr().out


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


def test_prepare_does_nothing_when_disabled(tmp_path):
    options = Options("--no-sandbox")
    assert rtcstatsTrace.prepare(options, "gw0", "r", "jitsi", env={},
                                 extensionDir=str(tmp_path / "extension")) is False
    assert options.arguments == ["--no-sandbox"]
    assert not (tmp_path / "extension").exists()


def test_prepare_loads_the_trace_in_every_tab_and_frame_before_the_page(tmp_path, monkeypatch):
    extension = assets(tmp_path, monkeypatch)
    options = Options("--no-sandbox")
    assert rtcstatsTrace.prepare(options, "gw0", "room1", "jitsi", env=ON,
                                 extensionDir=str(extension)) is True
    assert options.arguments == ["--no-sandbox", "--load-extension=" + str(extension)]
    manifest = json.loads((extension / "manifest.json").read_text())
    assert manifest["manifest_version"] == 3
    script, = manifest["content_scripts"]
    assert script["matches"] == ["<all_urls>"]
    assert script["run_at"] == "document_start"
    assert script["world"] == "MAIN"
    assert script["all_frames"] is True and script["match_about_blank"] is True
    source = (extension / script["js"][0]).read_text()
    assert "window.__sipmediagwRtcstatsLib = {};" in source and "/* bootstrap */" in source
    assert "room=room1" in source and "gw=gw0" in source


def test_prepare_twice_loads_the_extension_once(tmp_path, monkeypatch):
    extension = assets(tmp_path, monkeypatch)
    options = Options()
    rtcstatsTrace.prepare(options, "gw0", "r", "jitsi", env=ON, extensionDir=str(extension))
    rtcstatsTrace.prepare(options, "gw0", "r", "jitsi", env=ON, extensionDir=str(extension))
    assert options.arguments == ["--load-extension=" + str(extension)]


def test_missing_bundle_disables_tracing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rtcstatsTrace, "BUNDLE", str(tmp_path / "absent.js"))
    options = Options()
    assert rtcstatsTrace.prepare(options, "gw0", "r", "jitsi", env=ON,
                                 extensionDir=str(tmp_path / "extension")) is False
    assert options.arguments == []
    assert "rtcstats:" in capsys.readouterr().out


def test_unwritable_extension_dir_disables_tracing(tmp_path, monkeypatch):
    assets(tmp_path, monkeypatch)
    blocker = tmp_path / "file"
    blocker.write_text("")
    options = Options()
    assert rtcstatsTrace.prepare(options, "gw0", "r", "jitsi", env=ON,
                                 extensionDir=str(blocker / "extension")) is False
    assert options.arguments == []


def test_logs_never_show_the_token(tmp_path, monkeypatch, capsys):
    extension = assets(tmp_path, monkeypatch)
    env = {"RTCSTATS_ENABLED": "true",
           "RTCSTATS_SERVER_URL": "wss://stats.example.org/x?rtcstats-token=SECRET"}
    rtcstatsTrace.prepare(Options(), "gw0", "r", "jitsi", env=env, extensionDir=str(extension))
    out = capsys.readouterr().out
    assert "SECRET" not in out and "stats.example.org" in out


def driver(handles=("main",), closedIn=("main",)):
    d = Mock()
    d.window_handles = list(handles)
    d.current_window_handle = handles[0]
    visited = []

    def switch(handle):
        d.current_window_handle = handle
        visited.append(handle)
    d.switch_to.window.side_effect = switch
    d.execute_script.side_effect = lambda script: d.current_window_handle in closedIn
    d.visited = visited
    return d


def test_close_closes_every_tab_and_comes_back():
    d = driver(handles=("lobby", "meeting"), closedIn=("lobby", "meeting"))
    with patch("rtcstatsTrace.time.sleep") as sleep:
        rtcstatsTrace.close(d, flushSeconds=0.5)
    assert "__sipmediagwRtcstatsCloseAll" in d.execute_script.call_args.args[0]
    assert d.execute_script.call_count == 2
    assert d.visited[-1] == "lobby"
    sleep.assert_called_once_with(0.5)


def test_close_without_trace_does_not_wait():
    d = driver(closedIn=())
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
