"""
HTTPLauncher listens on every address by default. --host restricts it, for
example to 127.0.0.1 when a reverse proxy on the same host is the only way in.
"""
import os
import runpy
import sys
from unittest.mock import patch

import pytest

LAUNCHER = os.path.normpath(os.path.join(os.path.dirname(__file__), "../../HTTPLauncher.py"))


def started_with(*args):
    with patch.object(sys, "argv", ["HTTPLauncher.py", *args]), patch("uvicorn.run") as run:
        runpy.run_path(LAUNCHER, run_name="__main__")
    return run.call_args.kwargs


def test_the_launcher_listens_on_every_address_by_default():
    assert started_with() == {"host": "0.0.0.0", "port": 8100}


@pytest.mark.parametrize("args, expected", [
    (("--host", "127.0.0.1"), {"host": "127.0.0.1", "port": 8100}),
    (("--host", "127.0.0.1", "--port", "8200"), {"host": "127.0.0.1", "port": 8200}),
])
def test_host_sets_the_listening_address(args, expected):
    assert started_with(*args) == expected
