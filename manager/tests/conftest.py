"""
Fixtures shared between test modules, registered here once.

They used to be imported into each module that needed them, which ruff reads
as an import redefined by every test taking the fixture as an argument (F811,
fourteen times). Here, pytest finds them for every module of the directory.
"""

from tests.test_api_routes import client            # noqa: F401 — pytest fixture
from tests.test_roles import accounts, store        # noqa: F401 — pytest fixtures
from tests.test_users import admin, alice           # noqa: F401 — pytest fixtures
