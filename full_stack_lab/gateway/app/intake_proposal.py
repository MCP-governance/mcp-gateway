"""Deterministic suggestions; only the recorded human approval enables them."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from urllib.parse import urlsplit


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def server_id(row: dict) -> str:
    address = urlsplit(row.get("endpoint_url") or row.get("repository_url") or "")
    source = address.hostname if row.get("intake_kind") == "remote-endpoint" else address.path.strip("/")
    # A monorepo holds many servers: name each by its folder, not by the owner every one of them shares
    # (10-23: filesystem, memory and sequentialthinking all became "modelcontextprotocol-…" to the harness).
    if row.get("intake_kind") != "remote-endpoint" and (row.get("repository_path") or "").strip("/"):
        source = row["repository_path"].strip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"[^a-z0-9]+", "-", (source or "mcp").lower()).strip("-")
    slug = re.sub(r"^[^a-z]+", "", slug)[:21].rstrip("-") or "mcp"
    return f"{slug}-{str(row['id']).replace('-', '')[:8]}"


def action(tool: dict) -> str:
    hints = {k.replace("_", "").lower(): v for k, v in (tool.get("annotations") or {}).items()}
    arguments = " ".join((tool.get("input_schema") or {}).get("properties") or {})
    if hints.get("destructivehint") is True or re.search(r"command|script|shell|exec", arguments, re.I):
        return "x"
    return tool.get("suggested") if tool.get("suggested") in {"r", "w", "x"} else (
        "r" if hints.get("readonlyhint") is True else "x" if hints.get("openworldhint") is True else "w")


def risk_input(row: dict, tools: list[dict]) -> dict:
    stated = row.get("risk_input") or {}
    text = json.dumps(tools, ensure_ascii=False).lower()
    personal = "sensitive" if re.search(r"health|medical|biometric|건강|의료|민감", text) else (
        "unique_id" if re.search(r"passport|ssn|주민등록|여권", text) else (
            "general" if re.search(r"email|phone|customer|person|이메일|고객|개인", text) else "none"))
    return {"data_class": stated.get("data_class", "important"), "personal_data": personal,
            "external_transfer": row.get("intake_kind") == "remote-endpoint" or any(
                (t.get("annotations") or {}).get("openWorldHint", (t.get("annotations") or {}).get("open_world_hint", True))
                is not False for t in tools),
            "permission": max((action(t) for t in tools), key=lambda a: "rwx".index(a), default="x"),
            "users": 1, "autonomy": "autonomous"}


def tool_reviews(row: dict, tools: list[dict]) -> dict:
    # Inferring a URL destination from an argument name would grant arbitrary egress. Keep it empty.
    return {t["name"]: {"purpose": row["purpose"][:200], "asset": row["display_name"][:200],
                        "destinations": [], "inputs": list((t.get("input_schema") or {}).get("properties") or {}),
                        "mask": True, "grade": "public", "accepts_from": [], "consent": True}
            for t in tools}


def supplier(row: dict) -> dict:
    record = row.get("provenance") or {}
    return {**(record.get("supplier_metadata") or {}), **((row.get("evidence") or {}).get("supplier_assurance") or {})}


def source_record(row: dict, found: dict) -> dict:
    if row.get("intake_kind") != "remote-endpoint":
        return row.get("provenance") or {}
    return {"kind": "provider-hosted", "source_url": row["endpoint_url"], "version": found["version"],
            "version_immutable": False, "license": {"spdx": None, "applicable": False},
            "artifact": {"applicable": False, "reason": "해당 없음", "endpoint": row["endpoint_url"]},
            "contract_sha256": found["catalog_hash"]}


def basis(row: dict) -> str:
    return digest({**{key: row.get(key) for key in ("submitted_by", "repository_url", "endpoint_url", "commit_sha",
                   "source_ref", "purpose", "requested_tools")},
                   "data_class": (row.get("risk_input") or {}).get("data_class", "important"),
                   "artifact": (row.get("provenance") or {}).get("artifact") if row.get("intake_kind") == "repository" else None})


def scan_basis(gate: dict) -> str:
    critical = gate.get("critical") or {}
    return digest({"scanners": gate.get("scanners"), "vuln_db": (gate.get("vuln_db") or {}).get("updated_at"),
                   "critical": {"count": critical.get("count"), "ids": critical.get("ids")}})


# 공식 modelcontextprotocol/servers 이미지의 PC 격리 실행 기본값. 승인 화면이 미리 채울 뿐이며 관리자가 바꾼다.
# 서명 전 검사(local_jobs.manifest_errors)·이미지 저장소 허용은 그대로 적용돼 승인 범위는 넓어지지 않는다.
OFFICIAL_SERVERS = "https://github.com/modelcontextprotocol/servers"
_LOCAL = {"image": "", "command": [], "mounts": [], "env": {}, "reason_kind": "local_tool", "reason_text": ""}
LOCAL_RUN_PRESETS = {
    "src/filesystem": {**_LOCAL, "image": "mcp/filesystem", "command": ["/workspace/mcp-docs"],
                       "mounts": [{"path": "mcp-docs", "mode": "ro"}], "reason_kind": "local_file",
                       "reason_text": "PC 문서 폴더 읽기 전용 접근"},
    "src/memory": {**_LOCAL, "image": "mcp/memory", "mounts": [{"path": "mcp-memory", "mode": "rw"}],
                   "env": {"MEMORY_FILE_PATH": "/workspace/mcp-memory/memory.json"}, "reason_kind": "local_file",
                   "reason_text": "PC 폴더에 지식 그래프 영구 저장"},
    "src/sequentialthinking": {**_LOCAL, "image": "mcp/sequentialthinking", "reason_text": "PC 안에서 도는 단계별 사고 도구"},
}
# git·time 이미지는 인터프리터가 /root(0700) 아래 uv 설치에 있어 관리 계정(UID)으로 exec가 거부된다(10-23 PJ1 docker 29.8.1 실측).
# 환경 변수·tmpfs로 풀 수 없고 루트 실행은 허용하지 않으므로 제안하지 않고 상태만 보인다.
ROOT_ONLY_IMAGES = {"src/git", "src/time"}
ROOT_ONLY_STATUS = "관리 계정으로 실행할 수 없는 이미지"


def local_run_preset(row: dict) -> dict:
    """공식 저장소의 알려진 경로만 제안한다. 같은 경로라도 다른 저장소의 서버에는 공식 이미지를 제안하지 않는다."""
    if not _official(row):
        return {}
    return copy.deepcopy(LOCAL_RUN_PRESETS.get((row.get("repository_path") or "").strip("/"), {}))


def _official(row: dict) -> bool:
    return (row.get("repository_url") or "").rstrip("/").removesuffix(".git").lower() == OFFICIAL_SERVERS


def local_run_status(row: dict) -> str:
    """제안을 못 하는 공식 이미지의 이유를 짧은 상태 문구로. 제안이 있거나 모르는 경로면 빈 문자열."""
    return ROOT_ONLY_STATUS if _official(row) and (row.get("repository_path") or "").strip("/") in ROOT_ONLY_IMAGES else ""
