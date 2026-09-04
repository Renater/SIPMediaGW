"""Bearer header is sent when LOG_PUSH_TOKEN is set, absent otherwise."""
import importlib, os, sys
from unittest.mock import patch, MagicMock


def runPush(token):
    os.environ["LOG_PUSH_URL"] = "http://collector.example/call-history"
    os.environ["LOG_PUSH_TOKEN"] = token
    sys.path.insert(0, "src")
    sys.modules.pop("logParse", None)
    mod = importlib.import_module("logParse")
    response = MagicMock(status_code=200, text="ok")
    with patch.object(mod, "readHistoryStable", return_value=["line"]), \
         patch.object(mod, "buildPayloadFromLines", return_value={"call": {}}), \
         patch.object(mod, "truncateHistory"), \
         patch.object(mod.requests, "post", return_value=response) as post:
        mod.pushHistory("/tmp/history.log")
    return post.call_args.kwargs["headers"]


def test_header_present_with_token():
    assert runPush("s3cret")["Authorization"] == "Bearer s3cret"


def test_no_header_without_token():
    assert "Authorization" not in runPush("")
