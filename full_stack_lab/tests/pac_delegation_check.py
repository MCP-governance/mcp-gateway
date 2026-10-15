"""PAC-05: what counts as a delegation claim, and that the agent identity is never trusted (unit level).

The policy decision itself (PAC-05-DELEGATION-UNSUPPORTED from the Rego bundle) is covered by the Rego
tests and by tests/intake_identity_pg_check.py against a real OPA.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import mcp_facade, pac  # noqa: E402


class DelegationTest(unittest.TestCase):
    def test_token_claims_that_say_someone_acts_for_someone_else(self):
        for claim in pac.DELEGATION_CLAIMS:
            state = pac.delegation({"transport_claims": {claim: "x", "sub": "user-1"}})
            self.assertTrue(state["asserted"], claim)
            self.assertEqual(state["sources"], [f"claim:{claim}"])

    def test_headers_are_names_only_and_limited_to_the_known_ones(self):
        state = pac.delegation({"client": {"delegation_headers": ["x-on-behalf-of", "x-something-else"]}})
        self.assertEqual(state["sources"], ["header:x-on-behalf-of"])

    def test_no_marker_is_no_delegation(self):
        state = pac.delegation({"transport_claims": {"sub": "user-1", "scope": "mcp"}, "client": {"harness": {"name": "claude-code"}}})
        self.assertFalse(state["asserted"])
        self.assertEqual(state["sources"], [])

    def test_agent_identity_is_a_reported_source_and_never_verified(self):
        cases = {"client_info": {"harness": {"name": "claude-code", "user_agent": "ua"}},
                 "user_agent": {"harness": {"user_agent": "ua"}}, "none": {}}
        for source, client in cases.items():
            state = pac.delegation({"client": client})
            self.assertEqual(state["agent_identity"], {"source": source, "verified": False})
            self.assertIs(state["actor_verified"], False)
            self.assertIs(state["verified"], False)

    def test_a_forged_verified_flag_in_the_request_is_ignored(self):
        state = pac.delegation({"transport_claims": {"act": {}}, "client": {"actor_verified": True, "delegation": {"verified": True}}})
        self.assertTrue(state["asserted"])
        self.assertIs(state["actor_verified"], False)

    def test_facade_forwards_only_header_names(self):
        headers = {"x-on-behalf-of": "user-9", "x-agent-name": "evil", "user-agent": "ua"}
        context = SimpleNamespace(request=SimpleNamespace(headers=headers, scope={}), session=None)
        client = mcp_facade._client_context(context, {"claims": {}})
        self.assertEqual(client["delegation_headers"], ["x-on-behalf-of"])
        self.assertNotIn("user-9", str(client["delegation_headers"]))

    def test_policy_input_binds_the_claim_into_the_request(self):
        # The same flag feeds both the request and the classification fact, so the two cannot disagree.
        source = (Path(pac.__file__)).read_text(encoding="utf-8")
        self.assertEqual(source.count('"on_behalf_of": delegated["asserted"]'), 2)
        self.assertIn('"delegation": delegated', source)


if __name__ == "__main__":
    unittest.main()
