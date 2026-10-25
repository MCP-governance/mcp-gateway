"""Run production download bodies with isolated DB/HTTP doubles and no running services.

These unit checks do not prove FastAPI wiring, PostgreSQL races or real Gitea behavior.
Run the same file with the gateway dependencies installed for the optional ASGI auth check.
"""
from __future__ import annotations

import ast
import asyncio
import copy
import hashlib
import os
import re
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

SOURCE = Path(__file__).resolve().parent.parent / "gateway/app/agent_service.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
COMMIT = "a" * 40
USER = {"roles": ["employee"], "principal": "employee-identity"}


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code


class StreamingResponse:
    def __init__(self, content, **kwargs):
        self.body_iterator = content
        self.__dict__.update(kwargs)


class BackgroundTask:
    def __init__(self, function):
        self.function = function

    async def __call__(self):
        self.function()


class TransportError(Exception):
    pass


def load():
    names = {"caller", "current_identity", "gitea_admin_client", "approved_mcp_rows", "approved_mcp_repo_path",
             "list_approved_mcp", "receive_mcp_source", "download_approved_mcp_source"}
    nodes = [copy.deepcopy(n) for n in TREE.body if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes} == names
    for node in nodes:
        node.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    scope = dict(asyncio=asyncio, hashlib=hashlib, os=os, re=re, tempfile=tempfile, datetime=datetime,
                 UTC=timezone.utc, quote=quote, HTTPException=HTTPException, StreamingResponse=StreamingResponse,
                 BackgroundTask=BackgroundTask, Depends=lambda fn: fn, Header=lambda **kw: None,
                 CONSOLE_SCOPE="console", GITEA_ORG="mcp", MCP_SOURCE_MAX_BYTES=8,
                 MCP_SOURCE_DOWNLOAD_SLOTS=asyncio.Semaphore(2))
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), scope)
    return scope


class DownloadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.scope = load()
        self.env = patch.dict(os.environ, {"GITEA_PUBLIC_URL": "http://console/git"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.row = dict(intake_id="intake-1", intake_status="APPROVED", display_name="Notes",
                        repository_url="https://github.com/example/notes", endpoint_url="", intake_kind="repository",
                        commit_sha=COMMIT, internal_repo_url="http://console/git/mcp/example-notes-intake1",
                        server_id="notes", server_status="READY", lifecycle="OPERATING", source_ref=f"notes@{COMMIT}")
        self.spec = dict(intake_id="intake-1", version=COMMIT, valid_until=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                         local={"image": "pinned"})
        self.allowed = [USER["principal"]]
        self.scope["registry"] = types.SimpleNamespace(server=lambda _: self.spec,
            source_ref=lambda _: f"notes@{COMMIT}", allowed_principals=lambda _: self.allowed,
            permits=lambda allowed, token: allowed is None or "*" in allowed or token in allowed)
        self.queries = []

        async def fetch_all(query, params):
            self.queries.append((query, params))
            return [copy.deepcopy(self.row)]

        self.scope["db"] = types.SimpleNamespace(fetch_all=fetch_all)
        self.events = []

        async def record_event(*args, **kwargs):
            self.events.append((args, kwargs))

        self.scope["review"] = types.SimpleNamespace(record_event=record_event, SERVER=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"))
        self.blocks, self.headers, self.status = [b"zip", b"data"], {}, 200
        self.http_error, self.after_block, self.wait_block = None, None, False
        self.client_args, self.stream_args, self.files = [], [], []
        self.closed = False
        test = self

        class Upstream:
            @property
            def status_code(self):
                return test.status

            @property
            def headers(self):
                return test.headers

            async def __aenter__(self):
                if test.http_error:
                    raise test.http_error
                return self

            async def __aexit__(self, *args):
                test.closed = True

            async def aiter_raw(self, chunk_size):
                assert chunk_size == 64 << 10
                for block in test.blocks:
                    if test.wait_block:
                        await asyncio.Event().wait()
                    if test.after_block:
                        test.after_block()
                    yield block

        class Client:
            def __init__(self, **kwargs):
                test.client_args.append(kwargs)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                test.closed = True

            def stream(self, *args, **kwargs):
                test.stream_args.append((args, kwargs))
                return Upstream()

        self.scope["httpx"] = types.SimpleNamespace(AsyncClient=Client, HTTPError=TransportError)
        original = tempfile.SpooledTemporaryFile

        def spool(**kwargs):
            handle = original(**kwargs)
            self.files.append(handle)
            return handle

        self.scope["tempfile"] = types.SimpleNamespace(SpooledTemporaryFile=spool)

    async def denied(self, status, *, commit=COMMIT, user=USER):
        with self.assertRaises(HTTPException) as caught:
            await self.scope["download_approved_mcp_source"]("notes", commit, user)
        self.assertEqual(caught.exception.status_code, status)
        self.assertEqual(self.events, [])
        self.assertTrue(all(f.closed for f in self.files))

    async def test_routes_require_caller_and_console_auth(self):
        routes = [n for n in TREE.body if isinstance(n, ast.AsyncFunctionDef) and n.name in
                  {"list_approved_mcp", "download_approved_mcp_source"}]
        for node in routes:
            self.assertTrue(any(ast.unparse(d) == "Depends(caller)" for d in node.args.defaults))
        seen = []

        async def authenticated_user(header, *, require_scope):
            seen.append((header, require_scope))
            if header is None:
                raise HTTPException(401, "login")
            return USER

        self.scope["authenticated_user"] = authenticated_user
        with self.assertRaises(HTTPException) as caught:
            await self.scope["caller"](None)
        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(await self.scope["caller"]("Bearer console"), USER)
        self.assertEqual(seen, [(None, "console"), ("Bearer console", "console")])

    async def test_success_preserves_bytes_digest_headers_and_append_event(self):
        self.headers = {"content-length": "7"}
        response = await self.scope["download_approved_mcp_source"]("notes", COMMIT, USER)
        digest = hashlib.sha256(b"zipdata").hexdigest()
        self.assertEqual(b"".join([part async for part in response.body_iterator]), b"zipdata")
        await response.background()
        self.assertTrue(self.files[0].closed)
        self.assertEqual(response.headers["X-Content-SHA256"], digest)
        self.assertEqual(response.headers["Content-Length"], "7")
        self.assertEqual(response.headers["Content-Disposition"], 'attachment; filename="notes-aaaaaaaaaaaa.zip"')
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(self.events, [(("mcp-source-download", "recorded", "server", "notes", USER["principal"]),
            {"scope": {"intake_id": "intake-1", "commit": COMMIT, "sha256": digest, "bytes": 7}})])
        args, kwargs = self.stream_args[0]
        self.assertEqual(args, ("GET", f"/api/v1/repos/mcp/example-notes-intake1/archive/{COMMIT}.zip"))
        self.assertFalse(kwargs["follow_redirects"])
        self.assertEqual(kwargs["headers"], {"Accept-Encoding": "identity"})
        self.assertNotIn(USER["principal"], repr(self.client_args))
        self.assertEqual(len(self.queries), 2)
        self.assertEqual(self.queries[0][1], ("notes", "notes"))

    async def test_unapproved_and_withdrawn_intakes_never_contact_gitea(self):
        for status in ["HOLD", "VALIDATED", "REJECTED"]:
            self.row["intake_status"] = status
            await self.denied(403)
        self.assertEqual(self.client_args, [])

    async def test_disabled_deregistered_and_terminating_servers_are_refused(self):
        for status in ["DISABLED", "BLOCKED_SUPPLY_CHAIN", "DRIFT", "ERROR", "PENDING"]:
            self.row["server_status"] = status
            await self.denied(403)
        self.row["server_status"] = "READY"
        self.row["lifecycle"] = "TERMINATING"
        await self.denied(403)
        self.row["lifecycle"] = "OPERATING"
        self.spec = None
        await self.denied(403)

    async def test_wrong_commit_or_ref_is_refused_before_io(self):
        for commit in ["b" * 40, COMMIT[:12], "main", "../main"]:
            await self.denied(409, commit=commit)
        self.spec["version"] = "b" * 40
        await self.denied(403)
        self.assertEqual(self.client_args, [])

    async def test_unscoped_employee_is_refused_and_admin_can_review(self):
        self.allowed = []
        await self.denied(403)
        admin = {"roles": ["admin"], "principal": "operator"}
        self.assertEqual(len(await self.scope["approved_mcp_rows"](admin)), 1)

    async def test_everyone_audience_lets_any_employee_download(self):
        # D-234: allowed_principals ["*"] means every active employee; others in the list are not required.
        self.allowed = ["*"]
        rows = await self.scope["approved_mcp_rows"]({"roles": ["employee"], "principal": "another-employee"})
        self.assertEqual([r["server_id"] for r in rows], ["notes"])
        self.allowed = ["someone-else"]
        self.assertEqual(await self.scope["approved_mcp_rows"](USER), [])

    async def test_expired_missing_naive_or_invalid_expiry_is_refused(self):
        for expiry in ["2000-01-01T00:00:00+00:00", None, "bad", "2099-01-01T00:00:00"]:
            self.spec["valid_until"] = expiry
            await self.denied(403)

    async def test_registration_must_name_same_intake_and_source(self):
        self.spec["intake_id"] = "other"
        await self.denied(403)
        self.spec["intake_id"] = self.row["intake_id"]
        self.row["source_ref"] = "other"
        await self.denied(403)

    async def test_remote_has_connection_only_and_no_archive(self):
        self.row.update(intake_kind="remote-endpoint", endpoint_url="https://service/mcp", commit_sha=None)
        result = await self.scope["list_approved_mcp"](USER)
        self.assertFalse(result["servers"][0]["source_available"])
        self.assertEqual(result["servers"][0]["execution"], "remote")
        self.assertEqual(result["servers"][0]["source_url"], "https://service/mcp")
        self.assertEqual(result["servers"][0]["connection_url"], "/mcp/notes/")
        self.assertNotIn("internal_repo_url", result["servers"][0])
        await self.denied(409)
        self.assertEqual(self.client_args, [])

    async def test_list_classifies_pc_runtime_and_hosted_source(self):
        for local, runtime, expected in [({"image": "pin"}, None, "pc"), (None, {"id": "1"}, "runtime"), (None, None, "remote")]:
            self.spec.update(local=local, runtime=runtime)
            result = await self.scope["list_approved_mcp"](USER)
            self.assertEqual(result["servers"][0]["execution"], expected)
            self.assertTrue(result["servers"][0]["source_available"])

    async def test_untrusted_or_missing_internal_repository_is_refused(self):
        for url in [None, "http://other/git/mcp/repo", "http://console/git/other/repo",
                    "http://console/git/mcp/../repo", "http://console/git/mcp/repo?ref=main",
                    "http://console/git/mcp/repo%2Fother", "http://console/git/mcp/repo/extra"]:
            self.row["internal_repo_url"] = url
            await self.denied(409)
        self.assertEqual(self.client_args, [])

    async def test_header_and_stream_caps_abort_and_close(self):
        self.headers = {"content-length": "9"}
        await self.denied(413)
        self.headers = {}
        self.blocks = [b"12345678", b"9"]
        await self.denied(413)
        self.assertTrue(self.closed)

    async def test_exact_cap_is_allowed_without_content_length(self):
        self.blocks = [b"1234", b"5678"]
        response = await self.scope["download_approved_mcp_source"]("notes", COMMIT, USER)
        self.assertEqual(b"".join([part async for part in response.body_iterator]), b"12345678")

    async def test_bad_headers_empty_truncated_encoded_and_redirected_responses_fail(self):
        for headers in [{"content-length": "bad"}, {"content-length": "8"}, {"content-encoding": "gzip"}]:
            self.headers = headers
            await self.denied(502)
        self.headers, self.blocks = {}, []
        await self.denied(502)
        self.blocks = [b"zipdata"]
        for status in [302, 401, 404, 500]:
            self.status = status
            await self.denied(502)

    async def test_transport_failure_and_timeout_close_without_success_event(self):
        for error in [TransportError(), asyncio.TimeoutError()]:
            self.http_error = error
            await self.denied(502)

    async def test_revocation_or_replacement_during_fetch_prevents_delivery(self):
        self.after_block = lambda: self.row.update(intake_status="REJECTED")
        await self.denied(409)
        self.row["intake_status"] = "APPROVED"
        self.after_block = lambda: self.row.update(internal_repo_url="http://console/git/mcp/replaced")
        await self.denied(409)

    async def test_audit_failure_fails_closed(self):
        async def unavailable(*args, **kwargs):
            raise RuntimeError("ledger unavailable")
        self.scope["review"].record_event = unavailable
        with self.assertRaisesRegex(RuntimeError, "ledger unavailable"):
            await self.scope["download_approved_mcp_source"]("notes", COMMIT, USER)
        self.assertTrue(self.files[0].closed)

    async def test_cancellation_and_early_consumer_close_release_spool(self):
        self.wait_block = True
        task = asyncio.create_task(self.scope["download_approved_mcp_source"]("notes", COMMIT, USER))
        while not self.stream_args:
            await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.files[0].closed)
        self.assertEqual(self.events, [])
        self.wait_block = False
        response = await self.scope["download_approved_mcp_source"]("notes", COMMIT, USER)
        await anext(response.body_iterator)
        await response.body_iterator.aclose()
        self.assertTrue(self.files[-1].closed)


if __name__ == "__main__":
    unittest.main()
