"""10-23 기능의 수용 시험 항목(acceptance.py)을 HTTP·DB 대역 위에서 돌려 항목 코드가 기대한 요청·응답 모양을 따르는지 본다.

대역은 서비스가 하는 판정(거부 규칙·상태 전이)을 흉내 낼 뿐이므로 이 시험은 항목이 실제 서비스를 통과했다는 증거가 아니다.
실제 실행은 GitHub CI의 일회용 스택에서 `./console.sh test`가 한다. 새 MCP를 만들거나 외부에 접속하지 않는다.
"""
import json
import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from app import acceptance as a  # noqa: E402

OFFICIAL = "https://github.com/modelcontextprotocol/servers"
TOKENS = {"employee": "t-emp", "admin": "t-adm"}
DIGEST = "a" * 64


class World:
    """수용 스택 서비스의 규칙 중 이 항목들이 기대는 것만 가진 대역."""

    def __init__(self, suggested="w", cosign=False, preset_ok=True):
        self.suggested, self.cosign, self.preset_ok = suggested, cosign, preset_ok
        self.intakes, self.servers, self.consents, self.events, self.sql = {}, {}, [], {}, []
        self.last_decision = None
        self.contract: dict[str, dict] = {}
        self.rejected: list[str] = []
        self.deregistered: list[str] = []

    # ── 서비스 HTTP ──────────────────────────────────────────────────────────
    def handle(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        who = request.headers.get("authorization", "").removeprefix("Bearer ")
        body = json.loads(request.content) if request.content else {}

        def reply(code, **data):
            return httpx.Response(code, json=data)

        if path == "/api/session":
            return reply(200, access_token="t-adm2")
        if (method, path) == ("POST", "/api/mcp-requests"):
            intake = f"00000000-0000-0000-0000-{len(self.intakes):012d}"
            self.intakes[intake] = {"kind": "remote", "status": "HOLD", "path": "", "repo": "", "first": False}
            return reply(200, request={"id": intake})
        if (method, path) == ("POST", "/api/registry/discover"):
            return reply(200, catalog_hash="c" * 64, tools=[{"name": "fetch"}])
        if (method, path) == ("POST", "/api/registry/servers"):
            return reply(409, detail="화면에서 승인한 범위와 다릅니다.")
        if method == "DELETE" and path.startswith("/api/registry/servers/"):
            self.deregistered.append(path.rsplit("/", 1)[1])
            return reply(200)
        step = re.fullmatch(r"/api/mcp-requests/([^/]+)/(approval-preview|approve-and-register|reject|review-contract|approve|register)", path)
        if step:
            return self.intake_step(step[1], step[2], who, body, reply)
        if method == "GET" and path == "/api/consents":
            return reply(200, consents=[dict(c) for c in self.consents])
        decide = re.fullmatch(r"/api/consents/(server/)?([^/]+)", path)
        if decide:
            return self.consent_step(decide[1], decide[2], who, body, reply)
        return reply(404, detail=f"대역에 없는 경로 {method} {path}")

    def proposal(self, intake):
        row = self.intakes[intake]
        if row["kind"] == "remote":
            return {"server_id": "fetch-" + intake[-6:], "endpoint": "https://mcp-fetch-tls:8443/mcp", "data_class": "public",
                    "catalog": {"catalog_hash": "c" * 64}, "tools": {"fetch": self.suggested}, "blockers": [],
                    "tool_reviews": {"fetch": {"purpose": "p" * 8, "asset": "fetch", "consent": True}}}
        return {"server_id": "repo-x", "endpoint": "", "data_class": "public", "catalog": None, "tools": {},
                "blockers": [{"code": "execution-missing", "message": "실행 계약이 없습니다."}], "tool_reviews": {}}

    def preset(self, row):
        official = row["repo"] == OFFICIAL
        table = {"src/filesystem": {"image": "mcp/filesystem", "command": ["/workspace/mcp-docs"],
                                    "mounts": [{"path": "mcp-docs", "mode": "ro"}], "env": {}, "reason_kind": "local_file"},
                 "src/memory": {"image": "mcp/memory", "command": [], "mounts": [{"path": "mcp-memory", "mode": "rw"}],
                                "env": {"MEMORY_FILE_PATH": "/workspace/mcp-memory/memory.json"}, "reason_kind": "local_file"}}
        preset = table.get(row["path"], {}) if official and self.preset_ok else {}
        status = a.ROOT_ONLY_STATUS if official and row["path"] in {"src/git", "src/time"} else ""
        return preset, status

    def intake_step(self, intake, step, who, body, reply):
        row = self.intakes.get(intake)
        if not row:
            return reply(404, detail="없는 신청")
        if step == "reject":
            self.rejected.append(intake)
            return reply(200)
        if who not in {"t-adm", "t-adm2"}:
            return reply(403, detail="관리자만 승인할 수 있습니다.")
        if step in {"review-contract", "approve"}:
            self.contract[step] = body
            return reply(200)
        if step == "register":
            self.servers[body["server_id"]] = {"fetch": body["tools"]["fetch"]}
            return reply(200, status="READY")
        proposal = self.proposal(intake)
        if step == "approval-preview":
            preset, status = self.preset(row)
            return reply(200, proposal=proposal, proposal_sha256=DIGEST, local_run_preset=preset, local_run_status=status)
        if body.get("proposal_sha256") != DIGEST:
            return reply(409, detail="검토 화면이 바뀌었습니다.")
        if proposal["blockers"]:
            return reply(409, detail="검증을 통과하지 못했습니다.")
        actions = {n: v for n, v in body.get("actions", {}).items() if v != proposal["tools"].get(n)}
        if not set(actions) <= set(body["tools"]) or any("rwx".index(v) > "rwx".index(proposal["tools"][n]) for n, v in actions.items()):
            return reply(422, detail="도구 분류는 선택한 도구에서 제안값 이하로만 바꿀 수 있습니다.")
        if self.cosign and who == "t-adm":
            row["first"] = True
            return reply(200, pending=True)
        row["status"], row["actions"] = "APPROVED", actions
        self.servers[proposal["server_id"]] = {"fetch": actions.get("fetch", proposal["tools"]["fetch"])}
        return reply(200, status="READY")

    def consent_step(self, by_server, ident, who, body, reply):
        if who != "t-emp":
            return reply(409, detail="이미 처리됐거나 본인의 동의 요청이 아닙니다.")
        ids = body["consent_ids"] if by_server else [int(ident)]
        if not ids:
            return reply(422, detail="비어 있는 목록")
        by_id = {c["id"]: c for c in self.consents}
        wanted = {"grant": ("GRANTED", {"PENDING", "DENIED", "REVOKED"}, "approved"),
                  "deny": ("DENIED", {"PENDING"}, "rejected"), "revoke": ("REVOKED", {"GRANTED"}, "rejected")}[body["decision"]]
        if (by_server and ident != "acceptance-consent") or any(i not in by_id or by_id[i]["status"] not in wanted[1] for i in ids):
            return reply(409, detail="이미 처리됐거나 본인의 동의 요청이 아닙니다.")
        for i in ids:
            by_id[i].update(status=wanted[0], expires_at="2027-01-01" if wanted[0] == "GRANTED" else None)
            self.events.setdefault(i, []).append({"kind": "user-consent", "outcome": wanted[2], "actor": "emp-principal"})
        return reply(200, consents=[dict(by_id[i]) for i in ids])

    # ── 게이트웨이 호출·DB ──────────────────────────────────────────────────
    async def call(self, who, name, arguments, url):
        sid = url.rstrip("/").rsplit("/", 1)[1]
        mine = next((c for c in self.consents if c["server_id"] == sid), None)
        if mine is None or mine["status"] == "REVOKED":
            if mine is None:
                self.consents.append({"id": 41, "server_id": sid, "tool_name": name, "status": "PENDING", "grade": "public",
                                      "expires_at": None})
            else:
                mine["status"] = "PENDING"
        mine = next(c for c in self.consents if c["server_id"] == sid)
        if mine["status"] == "GRANTED":
            return {"decision": "Allow", "policy_id": "P-AUTHZ-ALLOW-001", "decision_id": "d", "is_error": False, "text": "ok",
                    "upstream_attempted": True}
        self.last_decision = "동의하지 않았습니다" if mine["status"] == "DENIED" else "동의가 필요합니다"
        return {"decision": "Block", "policy_id": "P-CONSENT-001", "decision_id": "d", "is_error": True, "text": "",
                "upstream_attempted": False}

    async def list_tools(self, who, url):
        return [type("Tool", (), {"name": "fetch"})()]

    async def execute(self, sql, params=()):
        self.sql.append((sql, params))
        if "INSERT INTO mcp_intake_requests" in sql:
            ident, _, _, repo, _, path = params
            self.intakes[str(ident)] = {"kind": "repository", "status": "HOLD", "path": path, "repo": repo, "first": False}

    async def fetch_one(self, sql, params=()):
        if "AS intake" in sql:
            return {"intake": self.intakes[params[0]]["status"], "servers": int(params[1] in self.servers)}
        if sql.startswith("SELECT status FROM mcp_intake_requests"):
            return {"status": self.intakes[params[0]]["status"]}
        if sql.startswith("SELECT action FROM mcp_tools"):
            return {"action": self.servers[params[0]]["fetch"]}
        if sql.startswith("SELECT reason FROM decisions"):
            return {"reason": self.last_decision}
        raise AssertionError("대역에 없는 질의: " + sql[:80])

    async def fetch_all(self, sql, params=()):
        if sql.startswith("SELECT name, action, enabled FROM mcp_tools"):
            return [{"name": "fetch", "action": self.servers[params[0]]["fetch"], "enabled": True}] if params[0] in self.servers else []
        if sql.startswith("SELECT name FROM mcp_tools"):
            return [{"name": "fetch"}]
        raise AssertionError("대역에 없는 질의: " + sql[:80])

    async def events_for(self, kind, ident):
        if kind == "consent":
            return self.events.get(ident, [])
        row = self.intakes[ident]
        return [{"kind": "intake-one-click", "outcome": "approved",
                 "scope": {"tools": ["fetch"], **({"actions": row["actions"]} if row.get("actions") else {})}}]


class W7Checks(unittest.IsolatedAsyncioTestCase):
    def set_world(self, **options):
        world = World(**options)
        real = httpx.AsyncClient

        def client(**kwargs):
            return real(transport=httpx.MockTransport(world.handle), **kwargs)

        for target in (patch.object(a.httpx, "AsyncClient", side_effect=client),
                       patch.object(a.db, "execute", new=world.execute), patch.object(a.db, "fetch_one", new=world.fetch_one),
                       patch.object(a.db, "fetch_all", new=world.fetch_all), patch.object(a.review, "events_for", new=world.events_for),
                       patch.object(a, "call", new=world.call), patch.object(a, "operating", new=AsyncMock()),
                       patch.object(a, "list_tools", new=world.list_tools),
                       patch.object(a, "TOKENS", dict(TOKENS)), patch.object(a, "PRINCIPAL", {"employee": "emp-principal", "admin": "adm-principal"}),
                       patch.object(a, "USERS", {"employee": "e@x", "admin": "a@x"}),
                       patch.dict(os.environ, ACCEPTANCE_FETCH_ENDPOINT="https://mcp-fetch-tls:8443/mcp")):
            target.start()
            self.addCleanup(target.stop)
        return world

    async def check_lowered(self, suggested):
        world = self.set_world(suggested=suggested)
        detail = await a.one_click_lowers_tool_class()
        self.assertIn("등록 r", detail)
        self.assertIn("게이트웨이 직접 등록 409", detail)
        self.assertEqual(list(world.servers.values()), [{"fetch": "r"}])
        self.assertEqual(world.deregistered, list(world.servers))

    async def test_write_suggestion_is_lowered_to_read(self):
        await self.check_lowered("w")

    async def test_execute_suggestion_is_lowered_to_read(self):
        await self.check_lowered("x")

    async def test_read_suggestion_registers_without_actions_and_skips_raise_for_top_class(self):
        world = self.set_world(suggested="r")
        self.assertIn("올리기 422", await a.one_click_lowers_tool_class())
        self.assertEqual(list(world.servers.values()), [{"fetch": "r"}])

    async def test_lowering_that_service_accepted_above_suggestion_fails_the_item(self):
        world = self.set_world(suggested="w")
        original = world.intake_step

        def lenient(intake, step, who, body, reply):
            if step == "approve-and-register" and body.get("actions", {}).get("fetch") == "x":
                return reply(200, status="READY")  # 올리기를 받아 주는 잘못된 서비스
            return original(intake, step, who, body, reply)

        world.intake_step = lenient
        with self.assertRaises(AssertionError) as raised:
            await a.one_click_lowers_tool_class()
        self.assertIn("분류 올리기", str(raised.exception))
        self.assertEqual(world.servers, {})  # 항목이 실패했어도 정리 경로(등록 해제·거부)는 돈다
        self.assertEqual(len(world.rejected), 1)

    async def test_second_admin_completes_two_person_tier(self):
        world = self.set_world(suggested="w", cosign=True)
        with patch.dict(os.environ, MOCK_SSO_PASSWORD="x"):
            await a.one_click_lowers_tool_class()
        self.assertEqual(list(world.servers.values()), [{"fetch": "r"}])
        self.assertIn("admin2", a.TOKENS)
        self.assertTrue(any("INSERT INTO principals" in sql for sql, _ in world.sql))

    async def test_server_consent_flow_follows_the_decisions(self):
        world = self.set_world(suggested="w")
        detail = await a.server_consent_flow()
        self.assertIn("도구별 감사 사건", detail)
        self.assertEqual(world.contract["review-contract"]["tool_reviews"]["fetch"]["consent"], True)
        self.assertEqual(world.contract["review-contract"]["allowed_principals"], ["emp-principal"])
        self.assertEqual(world.deregistered, ["acceptance-consent"])
        self.assertEqual([c["status"] for c in world.consents], ["PENDING"])
        self.assertEqual([e["outcome"] for e in world.events[41]], ["rejected", "approved", "rejected"])

    async def test_consent_flow_fails_when_a_stranger_may_decide(self):
        world = self.set_world(suggested="w")
        original = world.consent_step

        def open_door(by_server, ident, who, body, reply):
            return original(by_server, ident, "t-emp", body, reply)  # 관리자의 결정도 본인으로 받는 잘못된 서비스

        world.consent_step = open_door
        with self.assertRaises(AssertionError) as raised:
            await a.server_consent_flow()
        self.assertIn("거부 응답", str(raised.exception))

    async def test_preview_local_run_values_and_cleanup(self):
        world = self.set_world()
        detail = await a.approval_preview_local_run_values()
        self.assertIn("git·time 상태 문구", detail)
        inserted = [p for sql, p in world.sql if "INSERT INTO mcp_intake_requests" in sql]
        self.assertEqual([p[5] for p in inserted], ["src/filesystem", "src/memory", "src/git", "src/time", "src/filesystem"])
        self.assertTrue(all(p[1] == "emp-principal" for p in inserted))
        self.assertEqual(sorted(world.rejected), sorted(world.intakes))  # 합성 신청은 모두 거부로 정리
        self.assertTrue(all(row["status"] == "HOLD" for row in world.intakes.values()))

    async def test_preview_item_fails_when_the_preset_is_missing(self):
        world = self.set_world(preset_ok=False)
        with self.assertRaises(AssertionError):
            await a.approval_preview_local_run_values()
        self.assertEqual(sorted(world.rejected), sorted(world.intakes))  # 실패해도 정리한다

    def test_items_are_registered_after_the_registration_check(self):
        source = Path(a.__file__).read_text(encoding="utf-8")
        order = [source.index(f'("{name}"') for name in (
            "console-registration-pins-and-expires", "one-click-approval-lowers-tool-class",
            "server-level-consent-decisions", "approval-preview-local-run-values", "invited-employee-enrollment")]
        self.assertEqual(order, sorted(order))


if __name__ == "__main__":
    unittest.main()
