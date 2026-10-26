import asyncio, unittest
from unittest.mock import AsyncMock, patch
import psycopg
from app import core

class RefreshRetry(unittest.TestCase):
    def test_deadlock_is_retried_not_marked_error(self):
        refresh = AsyncMock(side_effect=[psycopg.errors.DeadlockDetected(), {"status": "READY"}])
        with patch.object(core.registry, "servers", return_value=["gitea"]), \
             patch.object(core.registry, "server", return_value={}), \
             patch.object(core, "refresh_catalog", refresh), \
             patch.object(core.db, "execute", AsyncMock()) as execute:
            self.assertEqual(asyncio.run(core.refresh_all_catalogs()), {"gitea": "READY"})
        self.assertEqual(refresh.await_count, 2)
        execute.assert_not_awaited()          # ERROR로 내리지 않음

    def test_persistent_failure_still_errors(self):  # fail-closed 유지
        refresh = AsyncMock(side_effect=psycopg.errors.DeadlockDetected())
        with patch.object(core.registry, "servers", return_value=["gitea"]), \
             patch.object(core.registry, "server", return_value={}), \
             patch.object(core, "refresh_catalog", refresh), \
             patch.object(core.db, "execute", AsyncMock()) as execute:
            self.assertEqual(asyncio.run(core.refresh_all_catalogs()), {"gitea": "ERROR"})
        execute.assert_awaited_once()

if __name__ == "__main__":
    unittest.main()
