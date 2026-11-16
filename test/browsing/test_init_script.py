"""
The connector gets the meeting values as JavaScript strings. The display name
is the SIP display name of the room system, and it can contain quotes, for
example "Salle d'honneur". Each value is written as a JSON string, which is
also a JavaScript string with the same value, so these tests read the values
back with the JSON parser.
"""
import copy
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

RUNTIME_ONLY = ("selenium", "selenium.webdriver", "selenium.common", "selenium.common.exceptions")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))
with patch.dict(sys.modules, {name: MagicMock() for name in RUNTIME_ONLY if name not in sys.modules}):
    import browsing as browsing_module

PREFIX = "window.meeting = new window.Browsing("
PROMPTS = {"fr": {"room": "Veuillez entrer le numéro de votre conférence suivi de #<br>(utilisez * pour corriger)"}}
ROOM = {
    "config": {"webrtc_domain": "meet.example.org", "lang": "fr", "ivr_prompts": PROMPTS},
    "roomName": "room1",
    "displayName": "Salle A",
    "roomToken": "token1",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("AUDIO_ONLY", "DUAL_SCREEN_LAYOUT", "DUAL_SCREEN_BY_DEFAULT"):
        monkeypatch.delenv(name, raising=False)


def connector_values(**room):
    meeting = copy.deepcopy(ROOM)
    meeting.update(room)
    script = browsing_module.Browsing(1280, 720, {}, room=meeting, chromeOptions=MagicMock()).initScript
    assert script.startswith(PREFIX) and script.endswith(")")
    return json.loads("[" + script[len(PREFIX):-1] + "]")


@pytest.mark.parametrize("name", [
    "Salle d'honneur", 'Room "A"', "C:\\Rooms\\A", "Line\nbreak", "Sala Müller", "会议室",
    "Room\u2028A", "');window.close();('",
])
def test_the_display_name_reaches_the_connector_as_it_is(name):
    assert connector_values(displayName=name)[2] == name


def test_the_room_name_reaches_the_connector_as_it_is():
    assert connector_values(roomName="l'amphi")[1] == "l'amphi"


def test_the_connector_gets_the_strings_it_expects():
    assert connector_values() == [
        "meet.example.org", "room1", "Salle A", "fr", json.dumps(PROMPTS, ensure_ascii=False),
        "token1", "None", "False"]


def test_the_prompts_keep_their_characters():
    prompts = connector_values()[4]
    assert "numéro" in prompts
    assert json.loads(prompts) == PROMPTS


def test_no_token_is_the_string_none():
    assert connector_values(roomToken=None)[5] == "None"


def test_audio_only_and_the_dual_screen_are_strings(monkeypatch):
    monkeypatch.setenv("AUDIO_ONLY", "true")
    monkeypatch.setenv("DUAL_SCREEN_LAYOUT", "true")
    monkeypatch.setenv("DUAL_SCREEN_BY_DEFAULT", "true")
    assert connector_values()[6:] == ["true", "True"]
