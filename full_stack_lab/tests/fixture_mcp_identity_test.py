"""Offline checks for the token boundary in the two lab ingress fixtures.

These exercise the requests and embedded gateway code, without a server double or
any claim about a running IdP, database, or MCP server.
"""
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from types import ModuleType
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
import urllib.request
import urllib.error


def load(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reservation = load("reservation_effect_check")
adversarial = load("adversarial_check")


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class FixtureMcpIdentityTests(unittest.TestCase):
    def test_adversarial_uses_actor_password_grant(self):
        seen = []

        def urlopen(request, timeout):
            seen.append((request, timeout))
            return Response(b'{"access_token":"mcp-worker"}')

        with patch.dict("os.environ", {"IDP_INTERNAL_URL": "http://idp.internal/"}), \
                patch.object(urllib.request, "urlopen", side_effect=urlopen):
            self.assertEqual(adversarial.mcp_token("worker@bob.local", "secret"), "mcp-worker")
        request, timeout = seen[0]
        self.assertEqual(request.full_url, "http://idp.internal/oauth/token")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Content-type"), "application/x-www-form-urlencoded")
        self.assertEqual(parse_qs(request.data.decode()), {
            "grant_type": ["password"], "client_id": ["adversarial-ws"],
            "username": ["worker@bob.local"], "password": ["secret"]})
        self.assertEqual(timeout, 15)

    def test_reservation_grant_and_call_use_mcp_token_only(self):
        issued = []
        console = {"race": "console-session"}
        mcp = {}
        app = ModuleType("app")
        acceptance = ModuleType("app.acceptance")
        acceptance.TOKENS = console
        acceptance.MCP_TOKENS = mcp

        async def call(who, tool, args, url):
            self.assertEqual((who, tool, url),
                             ("race", "execute_sql", "http://127.0.0.1:8080/mcp/postgres/"))
            self.assertEqual(args, {"sql": "SELECT 1"})
            self.assertEqual(mcp["race"], "mcp-reservation")
            self.assertEqual(console["race"], "console-session")
            return {"decision": "Allow", "policy_id": "P-AUTHZ-ALLOW-001", "decision_id": 7}

        acceptance.call = call
        app.acceptance = acceptance

        def urlopen(request, timeout):
            issued.append((request, timeout))
            return Response(b'{"access_token":"mcp-reservation"}')

        def check_output(command, *, input=None, text=None, timeout=None):
            if command[4] == "gateway" and command[6] == "-c":
                self.assertTrue(text)
                self.assertLessEqual(timeout, 45)
                stream = io.StringIO()
                with patch.object(sys, "stdin", io.StringIO(input)), patch.object(sys, "stdout", stream), \
                        patch.object(urllib.request, "urlopen", side_effect=urlopen), \
                        patch.dict("os.environ", {"IDP_INTERNAL_URL": "http://idp.internal/"}), \
                        patch.dict(sys.modules, {"app": app, "app.acceptance": acceptance}):
                    exec(command[7], {"__name__": "__main__"})
                return stream.getvalue()
            self.assertEqual(command[0:4], ["docker", "compose", "exec", "-T"])
            return '{"upstream_attempted":true,"upstream_executed":true}'

        with patch.object(reservation.subprocess, "check_output", side_effect=check_output):
            bearer = reservation.mcp_token("reservation@bob.local", "secret")
            self.assertEqual(bearer, "mcp-reservation")
            result = reservation.mcp_write(bearer, "SELECT 1")
        request, timeout = issued[0]
        self.assertEqual(request.full_url, "http://idp.internal/oauth/token")
        self.assertEqual(parse_qs(request.data.decode()), {
            "grant_type": ["password"], "client_id": ["reservation-check-ws"],
            "username": ["reservation@bob.local"], "password": ["secret"]})
        self.assertEqual(timeout, 15)
        self.assertEqual(result["decision"], "Allow")
        self.assertTrue(result["upstream_executed"])

    def test_oauth_failures_abort_instead_of_using_console_credential(self):
        with patch.object(urllib.request, "urlopen", side_effect=urllib.error.HTTPError(
                "http://idp.internal/oauth/token", 403, "forbidden", None, None)):
            with self.assertRaises(urllib.error.HTTPError):
                adversarial.mcp_token("worker@bob.local", "secret")
        with patch.object(reservation.subprocess, "check_output", side_effect=subprocess.CalledProcessError(
                1, ["docker", "compose", "exec", "gateway"])):
            with self.assertRaises(subprocess.CalledProcessError):
                reservation.mcp_token("reservation@bob.local", "secret")


if __name__ == "__main__":
    unittest.main()
