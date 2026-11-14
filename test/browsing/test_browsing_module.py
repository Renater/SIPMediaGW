"""
A webrtc_domains entry may name its connector in "browsing", so that several
instances of one platform (one entry per instance) share a single connector.
Without "browsing", the key is the connector, as before.
"""
import os
import sys
import types
from unittest.mock import MagicMock, patch

# ivr.py needs the gateway's runtime packages only at import time; the stand-ins
# are removed again so that they never reach other test modules.
RUNTIME_ONLY = ("qrcode", "requests", "selenium", "selenium.webdriver",
                "selenium.webdriver.chrome", "selenium.webdriver.chrome.service",
                "selenium.webdriver.support", "selenium.webdriver.support.ui")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))
with patch.dict(sys.modules, {name: MagicMock() for name in RUNTIME_ONLY if name not in sys.modules}):
    import ivr as ivr_module

DOMAINS = {
    "jitsi": {"name": "Jitsi Meet", "domain": "meet.example.org"},
    "edumeet-a": {"name": "eduMEET A", "domain": "a.example.org", "browsing": "edumeet"},
    "edumeet-b": {"name": "eduMEET B", "domain": "b.example.org", "browsing": "edumeet"},
}


def new_ivr():
    # The IVR writes a Chrome policy file under /etc when it can: not from a test.
    with patch.object(ivr_module.os, "makedirs", side_effect=OSError("read-only")):
        return ivr_module.IVR(width=1280, height=720)


def ivr_with_domains():
    ivr = new_ivr()
    ivr.config = {"webrtc_domains": DOMAINS}
    return ivr


def test_key_is_the_connector_without_browsing():
    assert ivr_with_domains().browsingModule("jitsi") == "jitsi"


def test_browsing_names_the_connector():
    ivr = ivr_with_domains()
    assert ivr.browsingModule("edumeet-a") == "edumeet"
    assert ivr.browsingModule("edumeet-b") == "edumeet"


def test_unknown_key_and_missing_config_fall_back_to_the_key():
    assert ivr_with_domains().browsingModule("Some Platform") == "someplatform"
    assert new_ivr().browsingModule("jitsi") == "jitsi"


def test_attend_loads_the_connector_of_the_entry():
    created = {}

    class Connector:
        def __init__(self, width, height, config, modName, room, *rest):
            created["modName"] = modName
            created["room"] = room

        def run(self):
            created["ran"] = True

    module = types.ModuleType("fakeconnector")
    Connector.__module__ = "fakeconnector"
    module.Connector = Connector

    ivr = new_ivr()
    ivr.config = {"webrtc_domains": {"x.example.org": {"domain": "x.example.org", "browsing": "fakeconnector"}}}
    ivr.browsingKey = "x.example.org"
    room = {"roomName": "lecture1", "config": {"webrtc_domain": "x.example.org"}}
    with patch.dict(sys.modules, {"fakeconnector": module}):
        ivr.attend(room)

    assert created == {"modName": "fakeconnector", "room": room, "ran": True}
