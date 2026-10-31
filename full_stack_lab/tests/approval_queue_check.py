"""Isolated approval API checks; no running gateway, identity provider, or database."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        super().__init__(detail)


def load(role="admin", rows=None):
    path = Path(__file__).resolve().parents[1] / "gateway/app/agent_service.py"
    node = next(n for n in ast.parse(path.read_text(encoding="utf-8")).body
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "approvals")
    node.decorator_list = []
    node.args.defaults = [ast.Constant(None), ast.Constant(1)]
    db = SimpleNamespace(fetch_all=AsyncMock(side_effect=[rows or [], []]),
                         fetch_one=AsyncMock(return_value={"total": 65, "oldest": "oldest-request"}))
    scope = {"asyncio": asyncio, "db": db, "HTTPException": HTTPError,
             "current_identity": AsyncMock(return_value={"roles": [role], "principal": "reviewer", "user_id": "reviewer-id"})}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(path), "exec"), scope)
    return scope["approvals"], db


class ApprovalQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_employee_cannot_read_queue_or_count(self):
        handler, db = load(role="employee")
        with self.assertRaises(HTTPError) as failure:
            await handler()
        self.assertEqual(failure.exception.status_code, 403)
        db.fetch_all.assert_not_awaited()
        db.fetch_one.assert_not_awaited()

    async def test_later_page_keeps_global_total_and_redacts_high_impact_arguments(self):
        handler, db = load(rows=[{"id": "request", "arguments": {"raw": "sensitive-placeholder"},
                                 "explanation": {"arguments": {"string": 2}, "summary": "Reviewed operation"}}])
        result = await handler(page=3)
        self.assertEqual((result["page"], result["page_size"], result["total"]), (3, 30, 65))
        self.assertEqual(result["oldest"], "oldest-request")
        self.assertEqual(result["approvals"][0]["arguments"], {"string": 2})
        self.assertNotIn("sensitive-placeholder", str(result))
        query, params = db.fetch_all.call_args_list[0].args
        self.assertEqual(params[-1], 60)
        self.assertIn("a.expires_at>now()", query)
        self.assertIn("ORDER BY a.expires_at, a.created_at, a.id", query)

    async def test_count_failure_is_not_reported_as_an_empty_queue(self):
        handler, db = load()
        db.fetch_one.side_effect = RuntimeError("database unavailable")
        with self.assertRaises(RuntimeError):
            await handler()


if __name__ == "__main__":
    unittest.main()
