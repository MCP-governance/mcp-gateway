"""Approved local MCP servers run on the caller's own device (DEV-73, D-175).

The gateway keeps one decision path: execute_call judges the call exactly as for a remote
server, and only the transport differs. Each MCP message becomes a row here that the
device's root runner takes over its own outbound long-poll, so the device opens no port and
the managed account never touches the container engine.
"""
from __future__ import annotations

import asyncio
import base64
import contextvars
import hashlib
import json
import os
import posixpath
import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from mcp import types
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from . import db

PREFIX = "local:"
# ponytail: the gateway polls its own row; LISTEN/NOTIFY when per-call latency matters.
POLL_SECONDS = 0.05
MAX_RESULT_BODY = 1024 * 1024  # the inspected result is capped later (MAX_RESULT_BYTES); this bounds the upload


IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/:-]{0,200}@sha256:[0-9a-f]{64}$")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
# Loader and interpreter hooks would let a manifest run code the image does not contain.
ENV_DENIED = re.compile(r"^(LD_|DYLD_|PYTHON|NODE_OPTIONS$|BASH_ENV$|ENV$|PATH$|HOME$)")
REASONS = {"local_file": "로컬 파일", "local_tool": "로컬 도구", "device": "장치"}
# A manifest under review during registration, before the server exists in the registry.
registering: contextvars.ContextVar[dict | None] = contextvars.ContextVar("registering", default=None)


class NotStarted(ConnectionError):
    """The device never took the message: nothing ran."""


def manifest_errors(manifest: dict, server_id: str) -> list[str]:
    """The same rules the device runner applies again before it starts anything (C10 §8)."""
    errors = []
    if set(manifest) != {"server_id", "image", "command", "mounts", "env", "reason"}:
        return ["매니페스트 항목은 server_id·image·command·mounts·env·reason만 허용합니다."]
    if manifest["server_id"] != server_id:
        errors.append("매니페스트의 서버 id가 등록 id와 다릅니다.")
    if not isinstance(manifest["image"], str) or not IMAGE.fullmatch(manifest["image"]):
        errors.append("이미지는 sha256 digest로 고정해야 합니다.")
    command = manifest["command"]
    if not isinstance(command, list) or len(command) > 32 or not all(
            isinstance(a, str) and 0 < len(a) <= 512 and chr(0) not in a for a in command):
        errors.append("명령은 문자열 목록(32개 이하)이어야 합니다.")
    mounts = manifest["mounts"]
    if not isinstance(mounts, list) or len(mounts) > 8:
        errors.append("마운트는 8개 이하 목록이어야 합니다.")
    else:
        for item in mounts:
            path = item.get("path") if isinstance(item, dict) else None
            parts = path.split("/") if isinstance(path, str) else []
            if (set(item) != {"path", "mode"} or item["mode"] not in {"ro", "rw"} or not path
                    or path.startswith("/") or posixpath.normpath(path) != path
                    or any(p in {"", ".", ".."} or p.startswith(".") for p in parts)):
                errors.append(f"마운트 경로는 홈 아래 점으로 시작하지 않는 상대 경로만 허용합니다: {path!r}")
    env = manifest["env"]
    if not isinstance(env, dict) or len(env) > 32 or not all(
            ENV_NAME.fullmatch(k) and not ENV_DENIED.match(k) and isinstance(v, str) and len(v) <= 256
            for k, v in env.items()):
        errors.append("환경 변수 이름·값이 허용 범위를 벗어났습니다.")
    reason = manifest["reason"]
    if (not isinstance(reason, dict) or reason.get("kind") not in REASONS
            or not isinstance(reason.get("text"), str) or not 10 <= len(reason["text"].strip()) <= 500):
        errors.append("로컬 실행이 필요한 이유(로컬 파일·로컬 도구·장치)와 설명이 필요합니다.")
    return errors


def canonical(manifest: dict) -> bytes:
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def verify(manifest: dict, signature: str) -> bool:
    """The gateway checks the approver's signature too, but the device trusts only its pinned key."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    # A PEM in an env file arrives on one line with literal \n separators.
    pem = os.getenv("LOCAL_MANIFEST_PUBKEY", "").replace("\\n", "\n").strip()
    if not pem:
        raise ValueError("로컬 실행 매니페스트 서명 검증 키가 구성되지 않았습니다.")
    try:
        load_pem_public_key(pem.encode()).verify(base64.b64decode(signature, validate=True), canonical(manifest))
    except (InvalidSignature, ValueError):
        return False
    return True


async def applicant_device(token: str) -> str:
    """The contract is observed where the applicant will run it: their active managed PC."""
    row = await db.fetch_one(
        """SELECT endpoint_id FROM endpoint_agents WHERE owner_token=%s AND status='active' AND managed_state='active'
           AND local_uid IS NOT NULL ORDER BY heartbeat_at DESC NULLS LAST LIMIT 1""", (token,))
    if not row:
        raise ValueError("신청자의 활성 관리형 PC가 없어 로컬 실행 계약을 확인할 수 없습니다.")
    return row["endpoint_id"]


def local_block(manifest: dict, signature: str, observer_device: str, server_id: str) -> dict:
    errors = manifest_errors(manifest, server_id)
    if errors:
        raise ValueError(" / ".join(errors))
    if not verify(manifest, signature):
        raise ValueError("매니페스트 서명이 승인 키와 맞지 않습니다.")
    return {"manifest": manifest, "signature": signature, "observer_device": observer_device,
            "manifest_sha256": hashlib.sha256(canonical(manifest)).hexdigest()}


def server_of(endpoint: str | None) -> str | None:
    value = (endpoint or "").strip()
    return value[len(PREFIX):] if value.startswith(PREFIX) and value[len(PREFIX):] else None


async def _device(device_id: str | None) -> dict:
    device = await db.fetch_one("SELECT * FROM endpoint_agents WHERE endpoint_id=%s", (device_id,)) if device_id else None
    if not device or device["status"] != "active" or device["managed_state"] != "active" or not device.get("local_uid"):
        raise NotStarted("로컬 실행을 맡을 활성 관리형 엔드포인트가 없습니다.")
    return device


async def exchange(device_id: str, local: dict, method: str, params: dict, timeout: float) -> dict:
    await _device(device_id)
    job = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO local_jobs(id, device_id, server_id, manifest_sha256, manifest, signature, method, params, deadline)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (job, device_id, local["manifest"]["server_id"], local["manifest_sha256"], Jsonb(local["manifest"]),
         local["signature"], method, Jsonb(params), datetime.now(UTC) + timedelta(seconds=timeout)))
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        row = await db.fetch_one("SELECT state, result, error FROM local_jobs WHERE id=%s", (job,))
        if row["state"] == "done":
            if row["error"]:
                raise RuntimeError(row["error"])
            return row["result"]
        await asyncio.sleep(POLL_SECONDS)
    expired = await db.fetch_one(
        "UPDATE local_jobs SET state='expired', finished_at=now() WHERE id=%s AND state='queued' RETURNING id", (job,))
    if expired:
        raise NotStarted("엔드포인트가 로컬 실행 요청을 받지 않았습니다.")
    # Taken but unanswered: it may have run. The caller records the outcome as unknown.
    raise TimeoutError("로컬 실행 결과가 기한 안에 오지 않았습니다.")


class LocalClient:
    """The subset of the SDK client _call_upstream and discovery use."""

    def __init__(self, device_id: str, local: dict, timeout: float):
        self.device_id, self.local, self.timeout = device_id, local, timeout
        self.protocol_version = None
        self.server_info = None
        self.reused = False

    async def _send(self, method: str, params: dict) -> dict:
        return await exchange(self.device_id, self.local, method, params, self.timeout)

    async def start(self) -> None:
        hello = await self._send("initialize", {})
        self.protocol_version = hello.get("protocolVersion")
        self.server_info = types.Implementation.model_validate(hello.get("serverInfo") or {"name": "", "version": ""})

    async def list_tools(self, cursor=None, **_):
        return types.ListToolsResult.model_validate(await self._send("tools/list", {"cursor": cursor} if cursor else {}))

    async def call_tool(self, name: str, arguments: dict):
        from .output_contract import WireRejected
        result = await self._send("tools/call", {"name": name, "arguments": arguments})
        try:
            return types.CallToolResult.model_validate(result)
        except ValidationError as exc:
            raise WireRejected("도구 응답이 협상된 출력 형식과 일치하지 않습니다.") from exc


@asynccontextmanager
async def session(endpoint: str, timeout: float, device_id: str | None, *, discovery: bool):
    from . import registry
    server_id = server_of(endpoint)
    pending = registering.get()
    local = (pending if discovery and pending and pending["manifest"]["server_id"] == server_id
             else (registry.server(server_id) or {}).get("local") or {})
    if not local.get("manifest_sha256"):
        raise NotStarted("승인된 로컬 실행 매니페스트가 없습니다.")
    # Discovery has no caller; the contract is observed on the device the applicant named. A call
    # runs only on the caller's own device and never falls back to another one.
    target = local.get("observer_device") if discovery else device_id
    if not target:
        raise NotStarted("로컬 실행은 관리형 엔드포인트에서 호출해야 합니다.")
    # The first observation may include pulling the image on the device.
    client = LocalClient(target, local, max(timeout, 100) if discovery else timeout)
    await client.start()
    yield client


# ── device side ──────────────────────────────────────────────────────────────

async def claim(device: dict, wait: float) -> dict | None:
    loop = asyncio.get_running_loop()
    end = loop.time() + wait
    while True:
        row = await db.fetch_one(
            """UPDATE local_jobs SET state='claimed', claimed_at=now()
               WHERE id = (SELECT id FROM local_jobs WHERE device_id=%s AND state='queued' AND deadline > now()
                           ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
               RETURNING id, server_id, manifest_sha256, manifest, signature, method, params, deadline""",
            (device["endpoint_id"],))
        if row or loop.time() >= end:
            return row and {**row, "id": str(row["id"]), "deadline": row["deadline"].isoformat()}
        await asyncio.sleep(0.1)


async def complete(device: dict, job_id: str, result: dict | None, error: str | None) -> bool:
    if (result is None) == (error is None):
        raise ValueError("결과와 오류 중 하나만 보냅니다.")
    if result is not None and len(json.dumps(result)) > MAX_RESULT_BODY:
        result, error = None, "로컬 실행 결과가 상한을 넘었습니다."
    changed = await db.execute(
        """UPDATE local_jobs SET state='done', result=%s, error=%s, finished_at=now()
           WHERE id=%s AND device_id=%s AND state='claimed'""",
        (Jsonb(result) if result is not None else None, error and error[:500], job_id, device["endpoint_id"]))
    return changed == 1
