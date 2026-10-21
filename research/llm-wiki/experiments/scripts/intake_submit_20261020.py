"""Submit the 2026-10-20 test-campaign intake requests as the employee test account `user`.

Runs inside the agent-service container (`docker exec ... python`), calling the product handler
`create_mcp_request` itself so the same validation, duplicate check, insert and consent record run.
The only substitution is the caller identity (the employee test principal `user`, read from the
principals table) instead of a password login, because the operator does not type passwords.
It submits only: no exit-terms, contract review, scope, approval or registration call is made here.
usage: python intake_submit_20261020.py submit | status
"""
import asyncio, json, sys
from app import agent_service as svc
from app import db

PURPOSE = ("2026-10-20 PJ1 실환경 시험: 직원 PC에서 쓰려는 공개 {what}. 시험 계정 user 명의, "
           "운영자 지시로 Claude가 대행 제출. 승인·범위는 콘솔에서 사람이 결정.")
LOCAL = [  # (display, repository, risk_input)
    ("GhidraMCP (Ghidra 12.1.4)", "https://github.com/LaurieWired/GhidraMCP",
     dict(data_class="nonimportant", personal_data="none", external_transfer=False, permission="w", users=1, autonomy="supervised")),
    ("Filesystem MCP", "https://github.com/modelcontextprotocol/servers",
     dict(data_class="nonimportant", personal_data="none", external_transfer=False, permission="w", users=1, autonomy="supervised")),
    ("Git MCP (cyanheads)", "https://github.com/cyanheads/git-mcp-server",
     dict(data_class="nonimportant", personal_data="none", external_transfer=True, permission="w", users=1, autonomy="supervised")),
    ("DBHub SQLite MCP", "https://github.com/bytebase/dbhub",
     dict(data_class="nonimportant", personal_data="none", external_transfer=False, permission="w", users=1, autonomy="supervised")),
    ("Playwright MCP", "https://github.com/microsoft/playwright-mcp",
     dict(data_class="nonimportant", personal_data="none", external_transfer=True, permission="x", users=1, autonomy="supervised")),
]
REMOTE = [
    ("Microsoft Learn MCP", "https://learn.microsoft.com/api/mcp"),
    ("DeepWiki MCP", "https://mcp.deepwiki.com/mcp"),
    ("Hugging Face MCP", "https://huggingface.co/mcp"),
    ("Cloudflare Docs MCP", "https://docs.mcp.cloudflare.com/mcp"),
    ("AWS Knowledge MCP", "https://knowledge-mcp.global.api.aws"),
]
PUBLIC_READ = dict(data_class="public", personal_data="none", external_transfer=True, permission="r", users=1,
                   autonomy="supervised")


async def submit():
    row = await db.fetch_one("SELECT token, user_id, role, status FROM principals WHERE token='user'")
    assert row and row["role"] == "employee" and row["status"] == "active", row
    identity = {"principal": row["token"], "user_id": row["user_id"], "roles": [row["role"]]}

    async def as_employee(_authorization):
        return identity
    svc.current_identity = as_employee
    items = [svc.McpIntake(display_name=n, repository_url=u, intake_kind="repository", requested_transport="stdio",
                           purpose=PURPOSE.format(what="로컬 stdio MCP 서버"), risk_input=r) for n, u, r in LOCAL]
    items += [svc.McpIntake(display_name=n, endpoint_url=u, intake_kind="remote-endpoint",
                            requested_transport="streamable-http", purpose=PURPOSE.format(what="원격 MCP 서비스(무료·무계정)"),
                            risk_input=PUBLIC_READ) for n, u in REMOTE]
    for item in items:
        try:
            out = await svc.create_mcp_request(item, authorization=None)
            r = out["request"]
            print(json.dumps({"ok": True, "id": str(r["id"]), "name": r["display_name"], "status": r["status"]}, ensure_ascii=False))
        except Exception as exc:  # record refusals as produced
            print(json.dumps({"ok": False, "name": item.display_name, "error": f"{type(exc).__name__}: "
                              f"{getattr(exc, 'status_code', '')} {getattr(exc, 'detail', exc)}"}, ensure_ascii=False))


async def status():
    rows = await db.fetch_all(
        """SELECT id, display_name, intake_kind, COALESCE(endpoint_url, repository_url) target, requested_transport, status,
                  risk_level, commit_sha, validation_attempts, review_note, evidence, provenance, risk_input, created_at, validated_at
           FROM mcp_intake_requests WHERE created_at > '2026-10-20 05:00+00' ORDER BY created_at""")
    for r in rows:
        print(json.dumps(r, default=str, ensure_ascii=False))

asyncio.run({"submit": submit, "status": status}[sys.argv[1]]())
