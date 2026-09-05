"""Conftest-equivalent for unittest: run the suite offline regardless of ``.env``.

``main.py`` calls ``load_dotenv()`` on import and the repo root carries a
git-ignored ``.env`` with hosted Supabase credentials, which would flip every
test into hosted mode (503s, rejected offline tokens). unittest discovery
imports test modules in sorted order and never imports the start directory's
``__init__.py`` (``discover -s tests`` makes ``tests`` the top level), so this
module -- ``test__`` sorts before ``test_a`` -- blanks the durable-backend
variables before any test module imports ``main``. ``load_dotenv`` never
overrides a variable that is already present, even when it is "".

Set ``COVENANT_TEST_KEEP_ENV=1`` to keep the real environment (hosted runs,
``TEST_DATABASE_URL`` integration tests).
"""

from __future__ import annotations

import os
import unittest

BLANKED = (
    "DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_DB_URL",
    "TEST_DATABASE_URL",
    # An LLM key switches the AG-UI agent to a live model; tests use the
    # deterministic offline graph.
    "LITELLM_API_KEY",
    "OPENAI_API_KEY",
)

KEEP_ENV = os.getenv("COVENANT_TEST_KEEP_ENV") == "1"

if not KEEP_ENV:
    for _name in BLANKED:
        os.environ[_name] = ""


class OfflineTestEnvironment(unittest.TestCase):
    @unittest.skipIf(KEEP_ENV, "COVENANT_TEST_KEEP_ENV=1 keeps the real environment")
    def test_suite_runs_offline(self) -> None:
        import main

        self.assertFalse(main.platform.enabled)
        self.assertEqual(main.combined_durability_status.queue.mode, "offline-memory")
        self.assertEqual(main.combined_durability_status.checkpoint.mode, "offline-memory")


if __name__ == "__main__":
    unittest.main()
