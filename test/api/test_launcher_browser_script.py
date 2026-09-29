"""
executeInExistingChromeSession runs its script in the session the gateway
already has, with one request to chromedriver, and never opens a session of
its own: a new session is a new Chrome in the container, and interact asks
for the connector state every 2 s.
"""
import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from HTTPLauncher import DockerGateway


def answer(value):
    return io.BytesIO(json.dumps({"value": value}).encode())


def run(script, *args, session="abc123", reply=None, error=None):
    sent = []

    def urlopen(request, timeout=None):
        sent.append(request)
        if error is not None:
            raise error
        return reply

    backend = DockerGateway.__new__(DockerGateway)
    with patch.object(DockerGateway, "getSeleniumSessionId", return_value=session), \
         patch("HTTPLauncher.urllib.request.urlopen", side_effect=urlopen):
        result = backend.executeInExistingChromeSession("0", script, *args)
    return result, sent


def test_the_script_runs_in_the_existing_session_only():
    result, sent = run("return window.meeting.uiState();", reply=answer({"mic": "on"}))
    assert result == {"mic": "on"}
    assert len(sent) == 1, "one request, no session opened"
    request = sent[0]
    assert request.get_method() == "POST"
    assert request.full_url == "http://127.0.0.1:9510/session/abc123/execute/sync"
    assert json.loads(request.data) == {"script": "return window.meeting.uiState();", "args": []}


def test_arguments_are_passed_through():
    _, sent = run("return window.meeting.reaction(arguments[0]);", "applause", reply=answer(True))
    assert json.loads(sent[0].data)["args"] == ["applause"]


def test_a_script_error_is_reported_with_the_browser_message():
    body = io.BytesIO(json.dumps({"value": {"error": "javascript error",
                                            "message": "window.meeting is undefined\nstack..."}}).encode())
    error = urllib.error.HTTPError("http://127.0.0.1:9510/", 500, "err", {}, body)
    with pytest.raises(RuntimeError, match="window.meeting is undefined"):
        run("return window.meeting.x();", error=error)


def test_no_session_means_no_request():
    with patch("HTTPLauncher.urllib.request.urlopen") as urlopen:
        backend = DockerGateway.__new__(DockerGateway)
        with patch.object(DockerGateway, "getSeleniumSessionId", return_value=None):
            with pytest.raises(RuntimeError, match="no browser session"):
                backend.executeInExistingChromeSession("0", "return 1;")
    urlopen.assert_not_called()
