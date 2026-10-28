"""Offline production bodies, real temporary files and local IPC; no live MCP evidence."""
import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import types
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from approved_mcp_download_check import DownloadTests, HTTPException, USER, COMMIT, SOURCE

ROOT = SOURCE.parents[3]
KIT = ROOT / "endpoint-agent"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


access = module("kit_access_check", KIT / "kit_access.py")
screen = module("kit_screen_check", KIT / "kit_screen.py")
release = module("product_hygiene_check", ROOT / "deploy/check.py")


def functions(names, scope):
    nodes = [copy.deepcopy(n) for n in ast.parse(SOURCE.read_text(encoding="utf-8")).body if getattr(n, "name", "") in names]
    assert {n.name for n in nodes} == set(names)
    for node in nodes:
        node.decorator_list = []
    tree = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(tree), str(SOURCE), "exec"), scope)
    return types.SimpleNamespace(**scope)


class Login(unittest.TestCase):
    def test_login_changes_address_keeps_secrets_only_in_request_and_does_not_mutate_bundle(self):
        bundle = {"gateway_url": "https://old.example", "ca_sha256": "pin"}
        call = Mock(return_value={"enrollment_token": "one-use", "expires_at": "later"})
        result = access.login(bundle, call, lambda _: ("https://new.example/", "staff", "memory-only"))
        self.assertEqual(bundle, {"gateway_url": "https://old.example", "ca_sha256": "pin"})
        self.assertEqual(result["gateway_url"], "https://new.example")
        self.assertEqual(result["enrollment_token"], "one-use")
        self.assertNotIn("memory-only", json.dumps(result))
        self.assertEqual(call.call_args.args[1:], ("/auth/kit-enrollment", {"email": "staff", "password": "memory-only"}))
        self.assertEqual(call.call_args.kwargs, {"credential": False})

    def test_failure_locked_pending_throttled_and_network_are_fixed_labels_without_secret(self):
        for error, label in [(urllib.error.HTTPError("secret", 401, "secret", {}, io.BytesIO(b'')), "아이디·비밀번호"),
                             (urllib.error.HTTPError("secret", 403, "secret", {}, io.BytesIO(b'{}')), "계정 잠김"),
                             (urllib.error.HTTPError("secret", 403, "secret", {}, io.BytesIO(json.dumps({"detail": "관리자 승인 대기"}).encode())), "관리자 승인 대기"),
                             (urllib.error.HTTPError("secret", 429, "secret", {}, io.BytesIO(b'')), "시도 제한"),
                             (OSError("secret"), "네트워크")]:
            with self.subTest(label=label), self.assertRaises(access.LoginError) as caught:
                access.login({"gateway_url": "https://gateway.example"}, Mock(side_effect=error), lambda *_: ("https://gateway.example", "staff", "secret"))
            self.assertIn(label, str(caught.exception))
            self.assertNotIn("secret", str(caught.exception))

    def test_wrong_password_asks_again_with_reason_then_succeeds(self):
        wrong = urllib.error.HTTPError("u", 401, "u", {}, io.BytesIO(b""))
        call = Mock(side_effect=[wrong, {"enrollment_token": "t"}])
        asked = []
        def inputs(address, notice=""):
            asked.append((address, notice))
            return ("gateway.example:8000/", "staff", "pw")
        result = access.login({"gateway_url": "https://gateway.example"}, call, inputs)
        self.assertEqual(result["gateway_url"], "https://gateway.example:8000")
        self.assertEqual(asked[0][1], "")
        self.assertIn("아이디·비밀번호", asked[1][1])

    def test_refused_account_stops_at_once_and_shows_gateway_sentence(self):
        for code, text in [(403, "사용 중지된 계정입니다."), (429, "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.")]:
            error = urllib.error.HTTPError("u", code, "u", {}, io.BytesIO(json.dumps({"detail": text}).encode()))
            call, inputs = Mock(side_effect=error), Mock(return_value=("https://gateway.example", "staff", "pw"))
            with self.assertRaises(access.LoginError) as caught:
                access.login({"gateway_url": "https://gateway.example"}, call, inputs)
            self.assertEqual(caught.exception.kit_reason, text)
            self.assertEqual(call.call_count, 1)

    def test_three_mistakes_end_and_closed_input_is_a_label_not_a_traceback(self):
        wrong = urllib.error.HTTPError("u", 401, "u", {}, io.BytesIO(b""))
        call = Mock(side_effect=wrong)
        with self.assertRaises(access.LoginError):
            access.login({"gateway_url": "https://g.example"}, call, lambda *_: ("https://g.example", "staff", "pw"))
        self.assertEqual(call.call_count, 3)
        # Ctrl-D at a terminal prompt is a cancel (the installer prints the cancel line), not a terminal error.
        with self.assertRaises(KeyboardInterrupt):
            access.login({"gateway_url": "https://g.example"}, call, Mock(side_effect=EOFError))

    def test_login_prompt_without_terminal_stops_before_any_screen(self):
        with patch("sys.stdin", io.StringIO("")), contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(ValueError):
            screen.login_inputs("https://gateway.example")
        self.assertEqual(out.getvalue(), "")

    def test_expired_model_login_reads_as_login_needed(self):
        self.assertEqual(screen.legacy_cell("claude 실패 · 로그인 필요 · Failed to authenticate"), "로그인 필요")
        self.assertNotIn("1 로그인", screen.frame({}, lines=40))

    def test_noninteractive_password_never_falls_back_to_echo(self):
        import getpass
        with patch("builtins.input", side_effect=["", "staff"]), patch.object(getpass, "getpass", side_effect=getpass.GetPassWarning), \
             contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            screen.login_inputs("https://gateway.example")


class LoginAPI(unittest.IsolatedAsyncioTestCase):
    async def test_api_uses_same_password_verifier_rate_limit_and_enrollment_issuer(self):
        endpoint = types.ModuleType("kit_test.endpoint_plane")
        endpoint.enrollment_token = AsyncMock(return_value={"enrollment_token": "grant"})
        verify = AsyncMock(return_value={"token": "authenticated-owner"})
        scope = {"__package__": "kit_test", "password_principal": verify,
                 "JSONResponse": lambda value, **kw: (value, kw)}
        api = functions(["kit_enrollment"], scope)
        request = types.SimpleNamespace(email="staff", password="secret")
        peer = types.SimpleNamespace(client=types.SimpleNamespace(host="192.0.2.20"))
        with patch.dict("sys.modules", {"kit_test.endpoint_plane": endpoint}):
            result = await api.kit_enrollment(request, peer)
            verify.assert_awaited_once_with("staff", "secret", "192.0.2.20")
            endpoint.enrollment_token.assert_awaited_once_with("authenticated-owner")
            self.assertEqual(result[1]["headers"], {"Cache-Control": "no-store"})
            for status in (401, 403, 429):
                verify.side_effect = HTTPException(status, "refused")
                endpoint.enrollment_token.reset_mock()
                with self.assertRaises(HTTPException):
                    await api.kit_enrollment(request, peer)
                endpoint.enrollment_token.assert_not_awaited()

    async def test_device_identity_comes_from_key_not_body_and_admin_devices_have_no_audience_bypass(self):
        device = {"owner_token": "owner", "endpoint_id": "device", "managed_state": "active"}
        endpoint = types.ModuleType("kit_test.endpoint_plane")
        endpoint.authenticate_device = AsyncMock(return_value=device)
        scope = {"__package__": "kit_test", "HTTPException": HTTPException, "Header": lambda **kw: None,
                 "db": types.SimpleNamespace(fetch_one=AsyncMock(return_value={"token": "owner"}))}
        api = functions(["endpoint_source_caller"], scope)
        with patch.dict("sys.modules", {"kit_test.endpoint_plane": endpoint}):
            user = await api.endpoint_source_caller("device-key")
            endpoint.authenticate_device.assert_awaited_once_with("device-key", "enforcement")
            self.assertEqual(user, {"principal": "owner", "endpoint_id": "device", "roles": ["employee"]})
            for state in ("pending", "quarantined", "revoked"):
                endpoint.authenticate_device.return_value = {**device, "managed_state": state}
                with self.assertRaises(HTTPException):
                    await api.endpoint_source_caller("device-key")
            endpoint.authenticate_device.return_value = device
            scope["db"].fetch_one.return_value = None
            with self.assertRaises(HTTPException):
                await api.endpoint_source_caller("device-key")


class DeviceDownload(DownloadTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.scope["db"].fetch_one = AsyncMock(return_value={"active": True})

    async def test_device_download_owner_audit_audience_expiry_and_withdrawal(self):
        user = {**USER, "endpoint_id": "device"}
        response = await self.scope["download_approved_mcp_source"]("notes", COMMIT, user)
        self.assertEqual(b"".join([x async for x in response.body_iterator]), b"zipdata")
        self.assertEqual(self.events[0][0][4], USER["principal"])
        self.assertEqual(self.events[0][1]["scope"]["endpoint_id"], "device")
        for change in ("audience", "withdrawn", "expired", "device"):
            self.events.clear()
            self.allowed = [] if change == "audience" else [USER["principal"]]
            self.row["server_status"] = "REVOKED" if change == "withdrawn" else "READY"
            self.spec["valid_until"] = "2000-01-01T00:00:00+00:00" if change == "expired" else "2999-01-01T00:00:00+00:00"
            self.scope["db"].fetch_one.return_value = None if change == "device" else {"active": True}
            self.assertEqual(await self.scope["approved_mcp_rows"](user), []) if change != "device" else None
            with self.assertRaises(HTTPException):
                await self.scope["download_approved_mcp_source"]("notes", COMMIT, user)
            self.assertEqual(self.events, [])


class Transfer(unittest.TestCase):
    def exchange(self, data=b"zipdata", *, digest=None, size=None):
        header = {"size": len(data) if size is None else size, "sha256": digest or hashlib.sha256(data).hexdigest()}
        stream = io.BytesIO(json.dumps(header).encode() + b"\n" + data)
        class Duplex:
            def write(self, payload):
                return len(payload)
            read = stream.read
            readline = stream.readline
        return contextlib.nullcontext(Duplex())

    def test_download_verifies_size_hash_deletes_partial_and_never_saves_key(self):
        with tempfile.TemporaryDirectory() as directory:
            for kwargs in ({}, {"digest": "0" * 64}, {"size": 9}):
                with self.subTest(kwargs=kwargs), patch.object(access, "broker", return_value=self.exchange(**kwargs)):
                    command = {"action": "download", "server": "notes", "commit": COMMIT}
                    if kwargs:
                        with self.assertRaises(ValueError):
                            access.receive("local-only", command, directory)
                    else:
                        target = Path(access.receive("local-only", command, directory))
                        self.assertEqual(target.name, "notes-aaaaaaaaaaaa.zip")
                        self.assertEqual(target.read_bytes(), b"zipdata")
                        target.unlink()
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_broker_only_accepts_approved_paths_and_bounded_headers(self):
        for command in (None, [], {"action": "download", "server": "../admin", "commit": COMMIT},
                        {"action": "download", "server": "notes", "commit": "HEAD"}, {"action": "delete"}):
            with self.subTest(command=command), self.assertRaises(ValueError):
                access.source_path(command)
        with patch.object(access, "broker", return_value=self.exchange(size=access.MAX_BYTES + 1)), self.assertRaises(ValueError):
            access.receive("local", {"action": "list"})


class Product(unittest.TestCase):
    def test_private_address_rule_all_ranges_boundaries_and_documentation_networks(self):
        for value in ("10.1.2.3", "172.16.0.1", "172.31.255.255", "192.168.9.1", "100.64.0.1", "100.127.255.255", "10.1.2.3/24"):
            self.assertTrue(release.private_addresses(value), value)
        for value in ("192.0.2.10", "198.51.100.20", "203.0.113.30", "127.0.0.1", "100.63.255.255", "100.128.0.1", "10.0.0.0/8", "172.16.0.0/12", "999.2.3.4"):
            self.assertFalse(release.private_addresses(value), value)

    def test_banner_plain_no_color_and_eighty_columns(self):
        with patch.dict(os.environ, {"NO_COLOR": "1", "TERM": "xterm-256color"}), \
             contextlib.redirect_stdout(io.StringIO()):
            output = io.StringIO()
            view = screen.Screen(output=output, input=io.StringIO())
            text = view.text()
            self.assertNotIn("\x1b", text)
            self.assertNotIn("###", text)  # ASCII output keeps the title, not a smeared block logo
            self.assertIn("MINT", text)
            self.assertTrue(all(screen.width(row) < 80 for row in text.splitlines()))
            view.stop()
        self.assertTrue(all(screen.width(row) < 80 for row in screen.banner()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
