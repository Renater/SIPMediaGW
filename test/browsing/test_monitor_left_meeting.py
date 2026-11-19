"""
Once the gateway has joined, it watches the meeting page and hangs up the call
when the page reports that it has left, or when the page has navigated away and
lost window.meeting (a platform that reloads its page when the meeting ends).
A script error, or a connector without hasLeft(), ends the watch without
hanging up.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

RUNTIME_ONLY = ("selenium", "selenium.webdriver", "selenium.common", "selenium.common.exceptions")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))
with patch.dict(sys.modules, {name: MagicMock() for name in RUNTIME_ONLY if name not in sys.modules}):
    import browsing as browsing_module

HANGUP = ['echo "/hangup" | netcat -q 1 127.0.0.1 5555']


def watched(*answers):
    """A browsing session whose page gives these answers, one per check."""
    session = browsing_module.Browsing.__new__(browsing_module.Browsing)
    session.driver = MagicMock()
    session.driver.execute_script.side_effect = list(answers)
    return session


def watch(session):
    with patch.object(browsing_module.subprocess, "run") as run, \
            patch.object(browsing_module.time, "sleep"):
        session.monitorLeftMeeting(checkInterval=0).join(timeout=5)
    return run


@pytest.mark.parametrize("answer", ["gone", True])
def test_hangs_up_when_the_page_has_gone_or_has_left(answer):
    run = watch(watched(answer))
    run.assert_called_once_with(HANGUP, shell=True)


def test_keeps_watching_while_in_the_meeting():
    session = watched(False, False, True)
    run = watch(session)
    assert session.driver.execute_script.call_count == 3
    run.assert_called_once_with(HANGUP, shell=True)


def test_a_connector_without_has_left_ends_the_watch():
    run = watch(watched(None))
    run.assert_not_called()


def test_a_script_error_does_not_hang_up():
    run = watch(watched(RuntimeError("script timeout")))
    run.assert_not_called()


def test_the_page_is_asked_for_window_meeting_first():
    session = watched(False, True)
    watch(session)
    script = session.driver.execute_script.call_args_list[0].args[0]
    assert script.startswith("if (!window.meeting) return 'gone';")
    assert "window.meeting.hasLeft()" in script
