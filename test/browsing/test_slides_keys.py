"""
A room system shares its content as a second video stream (slides). baresip
reports when the slides start and stop, and the IVR turns that into s and q for
the meeting page. Before the meeting is joined these keys would reach the keypad
of the room screen, so they are kept back: slides that are still shown when the
meeting is joined are shared at that moment. Chrome is replaced here.
"""
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

RUNTIME_ONLY = ("qrcode", "requests", "selenium", "selenium.webdriver",
                "selenium.webdriver.chrome", "selenium.webdriver.chrome.service",
                "selenium.webdriver.support", "selenium.webdriver.support.ui",
                "selenium.common", "selenium.common.exceptions")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))
with patch.dict(sys.modules, {name: MagicMock() for name in RUNTIME_ONLY if name not in sys.modules}):
    import browsing as browsing_module
    import ivr as ivr_module


def drain(q):
    keys = []
    while not q.empty():
        keys.append(q.get_nowait())
    return keys


@pytest.fixture
def ivr(monkeypatch):
    monkeypatch.delenv("AUDIO_ONLY", raising=False)
    monkeypatch.delenv("IVR_TIMEOUT", raising=False)
    with patch.object(ivr_module.os, "makedirs", side_effect=OSError("read-only")):
        return ivr_module.IVR(width=1280, height=720, name="Room 2.14")


def test_slides_before_the_meeting_do_not_reach_the_keypad(ivr):
    ivr.showSlides(True)
    assert drain(ivr.userInputs) == []
    assert ivr.screenShared is True
    ivr.showSlides(False)
    assert drain(ivr.userInputs) == []
    assert ivr.screenShared is False


def test_slides_while_the_meeting_is_joining_wait_too(ivr):
    ivr.browsingObj = MagicMock(joined=False)
    ivr.showSlides(True)
    assert drain(ivr.userInputs) == []


def test_in_the_meeting_the_slides_give_s_then_q(ivr):
    ivr.browsingObj = MagicMock(joined=True)
    ivr.showSlides(True)
    ivr.showSlides(True)
    assert drain(ivr.userInputs) == ["s"]
    ivr.showSlides(False)
    ivr.showSlides(False)
    assert drain(ivr.userInputs) == ["q"]


def test_the_meeting_reads_the_slides_state_of_the_ivr(ivr):
    module = types.ModuleType("fakeconnector")

    class FakeConnector:
        def __init__(self, *args):
            self.joined = False

        def run(self):
            pass
    FakeConnector.__module__ = "fakeconnector"
    module.FakeConnector = FakeConnector
    ivr.browsingName = ivr.browsingKey = "fakeconnector"
    ivr.config = {}
    with patch.object(ivr_module.importlib, "import_module", return_value=module):
        ivr.attend({"roomName": "room1"})
    assert ivr.browsingObj.slidesShown() is False
    ivr.showSlides(True)
    assert ivr.browsingObj.slidesShown() is True


ROOM = {
    "config": {"webrtc_domain": "meet.example.org", "lang": "en", "ivr_prompts": {}, "menus": {"fakeconnector": []}},
    "roomName": "room1",
    "displayName": "Room A",
    "roomToken": "",
}


def joined_session(slides_shown):
    session = browsing_module.Browsing(1280, 720, ROOM["config"], "fakeconnector", dict(ROOM), "Room A",
                                       None, MagicMock(), ivr_module.queue.Queue(), MagicMock())
    session.slidesShown = lambda: slides_shown
    session.iconB64 = session.dtmfB64 = ""
    session.menuIcons = {}
    driver = MagicMock()
    driver.execute_script.side_effect = lambda script, *args: script == "return window.meeting.joined"

    def leave():
        session.room = {}
    with patch.object(browsing_module.webdriver, "Remote", return_value=driver), \
            patch.object(browsing_module.rtcstatsTrace, "prepare", return_value=False), \
            patch.multiple(session, loadPage=MagicMock(), join=MagicMock(), monitorLeftMeeting=MagicMock(),
                           loadImages=MagicMock(), loadJS=MagicMock(), checkStreamedSlide=MagicMock(),
                           manageLayout=MagicMock(), interact=MagicMock(side_effect=leave)):
        session.run()
    return session


def test_slides_shown_at_the_join_are_shared_then():
    session = joined_session(True)
    assert session.joined is True
    assert drain(session.userInputs) == ["s"]


def test_no_slides_at_the_join_no_key():
    session = joined_session(False)
    assert session.joined is True
    assert drain(session.userInputs) == []
