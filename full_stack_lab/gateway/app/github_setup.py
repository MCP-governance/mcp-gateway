"""Observe a remote catalog, then explicitly activate an operator-reviewed snapshot."""
import asyncio
import json
from pathlib import Path
import sys

import psycopg

from . import db
from .core import GITHUB_MCP_URL, UNSAFE_METADATA, _discover, canonical_hash


async def observe():
    catalog = await _discover("github")
    return {"endpoint": GITHUB_MCP_URL, **catalog}


def commit_review(review):
    with psycopg.connect(db.DATABASE_URL) as connection:
        connection.execute("DELETE FROM mcp_tools WHERE server_id='github'")
        tool = review["tools"][0]
        connection.execute("""INSERT INTO mcp_tools(server_id,name,action,enabled,approved_description_hash,approved_schema_hash,approved_server_version)
                              VALUES ('github','get_file_contents','r',true,%s,%s,%s)""", (canonical_hash(tool["description"]), canonical_hash(tool["input_schema"]), review["version"]))
        connection.execute("UPDATE mcp_servers SET status='READY',status_reason='검토된 remote catalog를 명시 승인',source_ref=%s WHERE id='github'", ("remote-catalog-" + canonical_hash(review)[:16],))


async def main():
    if len(sys.argv) == 2 and sys.argv[1] == "observe":
        print(json.dumps(await observe(), ensure_ascii=False, indent=2))
    elif len(sys.argv) == 3 and sys.argv[1] == "activate-reviewed":
        review = json.loads(Path(sys.argv[2]).read_text())
        current = await observe()
        if current != review or {t["name"] for t in review["tools"]} != {"get_file_contents"} or len(review["tools"]) != 1:
            raise SystemExit("검토 파일과 현재 catalog가 다르거나 읽기 도구 외의 도구가 있습니다.")
        if UNSAFE_METADATA.search(review["tools"][0]["description"]):
            raise SystemExit("위험 메타데이터가 있어 승인을 중단했습니다.")
        await asyncio.to_thread(commit_review, review)
        print("GitHub 읽기 도구 catalog 승인 완료. github_get_file 호출로 검증하세요.")
    else:
        raise SystemExit("usage: python -m app.github_setup observe | activate-reviewed /reports/github-reviewed.json")


if __name__ == "__main__":
    asyncio.run(main())
