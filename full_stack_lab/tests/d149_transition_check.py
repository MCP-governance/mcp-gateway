"""Adversarial checks for D-149's unpinned-output transition and audit record."""
from __future__ import annotations

import ast
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock

APP = Path(__file__).resolve().parents[1] / "gateway" / "app"


def production_approve_contract(namespace):
    tree = ast.parse((APP / "core.py").read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "approve_contract")
    module = ModuleType("d149_transition_unit")
    module.__dict__.update(namespace)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(APP / "core.py"), "exec"), module.__dict__)
    return module.approve_contract


class D149Transition(unittest.IsolatedAsyncioTestCase):
    async def test_reapproval_audit_keeps_legacy_null_distinct_from_pinned_none(self):
        observed_hash = "observed-output-hash"
        row = {
            "name": "read", "approved_description_hash": "description", "observed_description_hash": "description",
            "approved_schema_hash": "input", "observed_schema_hash": "input",
            "approved_server_version": "1", "observed_server_version": "1",
            "approved_output_schema_hash": None, "observed_output_schema_hash": observed_hash,
        }
        inserted = []

        async def execute(query, params):
            if query.lstrip().startswith("INSERT INTO catalog_snapshots"):
                inserted.append(params[4].obj)

        connection = SimpleNamespace(execute=AsyncMock(side_effect=execute))

        @asynccontextmanager
        async def transaction():
            yield connection

        db = SimpleNamespace(
            fetch_one=AsyncMock(return_value={"status": "READY", "lifecycle": "OPERATING", "endpoint": "https://unit.invalid"}),
            fetch_all=AsyncMock(return_value=[row]), transaction=transaction,
        )
        function = production_approve_contract({
            "db": db,
            "registry": SimpleNamespace(is_console_registration=lambda _: False),
            "output_contract": SimpleNamespace(
                observed_matches=lambda current: True,
                approved_hash=lambda _: "canonical-null-hash",
            ),
            "canonical_hash": lambda _: "change-hash",
            "Jsonb": lambda value: SimpleNamespace(obj=value),
            "review": SimpleNamespace(record_event=AsyncMock()),
            "refresh_catalog": AsyncMock(return_value={"status": "READY"}),
            "upstream": SimpleNamespace(release_pool=AsyncMock()),
        })

        await function("server", "reviewer", "reviewed output schema")

        change = inserted[0][0]["changes"][0]
        self.assertIsNone(change["from"]["output_schema"])
        self.assertEqual(change["to"]["output_schema"], observed_hash)


if __name__ == "__main__":
    unittest.main(verbosity=2)
