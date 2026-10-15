"""The artifact check against a real Gitea: agent_service.internal_archive_digest on the archive Gitea itself
serves, compared with a digest built only from the Git objects Gitea reports (tree + blobs).

Run ONLY in a disposable lab with a throwaway Gitea container (docs/ai/TESTING.md). Environment:
GITEA_URL, GITEA_USER, GITEA_PASSWORD. Nothing here touches the appliance's own Gitea.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import sys
from pathlib import Path

import httpx

for candidate in (Path(__file__).resolve().parent.parent / "gateway", Path("/app")):
    if (candidate / "app").is_dir():
        sys.path.insert(0, str(candidate))
        break
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
from app import agent_service, provenance

REPO = "notes"
FILES = {
    "src/server.py": b"print('serve')\n",
    "src/nested/deep/util.py": b"VALUE = 1\n",
    "docs/한글 문서.md": "내용\n".encode(),
    "empty.txt": b"",
    "bin/blob.bin": bytes(range(256)),
}


async def put(client: httpx.AsyncClient, path: str, data: bytes) -> None:
    api = f"/api/v1/repos/{os.environ['GITEA_USER']}/{REPO}/contents/{path}"
    existing = await client.get(api, params={"ref": "main"})
    body = {"content": base64.b64encode(data).decode(), "message": f"write {path}", "branch": "main"}
    response = await (client.put(api, json={**body, "sha": existing.json()["sha"]}) if existing.status_code == 200 else client.post(api, json=body))
    assert response.status_code in (200, 201), f"{path}: {response.status_code} {response.text}"


async def head(client: httpx.AsyncClient) -> str:
    response = await client.get(f"/api/v1/repos/{os.environ['GITEA_USER']}/{REPO}/branches/main")
    response.raise_for_status()
    return response.json()["commit"]["id"]


async def digest_from_objects(client: httpx.AsyncClient, commit: str) -> dict:
    """Built from Git objects, not from an archive: the tree listing, then every blob."""
    base = f"/api/v1/repos/{os.environ['GITEA_USER']}/{REPO}/git"
    tree = (await client.get(f"{base}/trees/{commit}", params={"recursive": "true", "per_page": 1000})).json()
    assert not tree.get("truncated"), "tree listing truncated"
    entries, total = [], 0
    for item in tree["tree"]:
        if item["type"] == "blob":
            data = base64.b64decode((await client.get(f"{base}/blobs/{item['sha']}")).json()["content"])
            entries.append((item["path"], hashlib.sha256(data).hexdigest()))
            total += len(data)
    return {"sha256": provenance.manifest_digest(entries), "files": len(entries), "bytes": total}


async def main() -> None:
    auth = (os.environ["GITEA_USER"], os.environ["GITEA_PASSWORD"])
    async with httpx.AsyncClient(base_url=os.environ["GITEA_URL"].rstrip("/"), auth=auth, timeout=60, trust_env=False) as client:
        created = await client.post("/api/v1/user/repos", json={"name": REPO, "private": True, "auto_init": True, "default_branch": "main",
                                                                "license": "MIT", "readme": "Default"})
        assert created.status_code == 201, created.text
        for path, data in FILES.items():
            await put(client, path, data)
        path = f"/api/v1/repos/{os.environ['GITEA_USER']}/{REPO}"
        first = await head(client)
        archived = await agent_service.internal_archive_digest(client, path, first)
        from_objects = await digest_from_objects(client, first)
        assert archived == from_objects, (archived, from_objects)
        assert archived["files"] >= len(FILES) + 1, archived  # auto_init adds a README and a licence
        print("PASS the archive Gitea serves hashes to the digest built from its Git objects:",
              archived["sha256"][:16], archived["files"], "files", archived["bytes"], "bytes")

        await put(client, "src/server.py", b"print('tampered')\n")
        second = await head(client)
        assert second != first
        changed = await agent_service.internal_archive_digest(client, path, second)
        assert changed == await digest_from_objects(client, second) and changed["sha256"] != archived["sha256"], "a changed file must change the digest"
        assert await agent_service.internal_archive_digest(client, path, first) == archived, "a pinned commit keeps its own digest"
        print("PASS a changed file moves the digest and a pinned commit keeps its own")

        try:
            await agent_service.internal_archive_digest(client, path, "0" * 40)
        except agent_service.HTTPException as exc:
            assert exc.status_code == 502, exc.status_code
            print("PASS an archive Gitea cannot produce is an error, never a match")
        else:
            raise AssertionError("a missing archive was treated as a match")


if __name__ == "__main__":
    asyncio.run(main())
