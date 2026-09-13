from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from mcp import Client, StdioServerParameters
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from psycopg.types.json import Jsonb

from . import db

OPA_URL = os.getenv("OPA_URL", "http://opa:8181/v1/data/mcp/authz/decision")
HTTP_MCP_URL = os.getenv("HTTP_MCP_URL", "http://mock-http-mcp:9000/mcp/")
GITHUB_MCP_URL = os.getenv("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/")
GITHUB_TOKEN = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")
EFFECT_LOG = Path(os.getenv("EFFECT_LOG", "/runtime/upstream-effects.jsonl"))
REPORT_DIR = Path(os.getenv("REPORT_DIR", "/reports"))
POLICY_PATH = Path(os.getenv("POLICY_PATH", "/policy/policy.rego"))
TIME_MCP_PYTHON = os.getenv("TIME_MCP_PYTHON", "/opt/time-mcp/bin/python")
APPROVAL_TTL_MINUTES = 10

TOOL_SPECS = {
    "read_document": {"server_id": "mock-http", "registry_name": "read_document", "action": "r"},
    "write_document": {"server_id": "mock-http", "registry_name": "write_document", "action": "w"},
    "send_external": {"server_id": "mock-http", "registry_name": "send_external", "action": "x"},
    "get_current_time": {"server_id": "mock-stdio", "registry_name": "get_current_time", "action": "r"},
    "github_get_file": {"server_id": "github", "registry_name": "get_file_contents", "action": "r"},
}
UNSAFE_METADATA = re.compile(
    r"ignore\s+(all\s+)?previous|system\s+prompt|credential|secret\s+key|bypass\s+policy",
    re.IGNORECASE,
)


def _configure_tracing() -> Any:
    provider = TracerProvider(resource=Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "mcp-security-gateway")}))
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318").rstrip("/") + "/v1/traces"
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    try:
        trace.set_tracer_provider(provider)
    except Exception:
        pass
    return trace.get_tracer("mcp-governance.gateway")


tracer = _configure_tracing()


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def effect_count() -> int:
    if not EFFECT_LOG.exists():
        return 0
    with EFFECT_LOG.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _tool_view(tool: Any) -> dict:
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.input_schema,
    }


async def _discover(server_id: str) -> dict:
    if server_id == "mock-http":
        client_source: Any = HTTP_MCP_URL
    elif server_id == "mock-stdio":
        client_source = StdioServerParameters(
            command=TIME_MCP_PYTHON,
            args=["-m", "mcp_server_time"],
        )
    else:
        raise RuntimeError(f"discovery is disabled for {server_id}")

    async with Client(client_source) as client:
        listed = await client.list_tools()
        info = client.server_info
        return {
            "version": info.version if info else "unknown",
            "protocol_version": str(client.protocol_version),
            "tools": [_tool_view(tool) for tool in listed.tools],
        }


async def refresh_catalog(server_id: str) -> dict:
    server = await db.fetch_one("SELECT * FROM mcp_servers WHERE id=%s", (server_id,))
    if not server:
        raise RuntimeError(f"unregistered server: {server_id}")
    if server["status"] == "DISABLED":
        return {"server_id": server_id, "status": "DISABLED", "reason": server["status_reason"]}

    discovered = await _discover(server_id)
    observed = {tool["name"]: tool for tool in discovered["tools"]}
    registered_rows = await db.fetch_all("SELECT * FROM mcp_tools WHERE server_id=%s ORDER BY name", (server_id,))
    registered = {row["name"]: row for row in registered_rows}

    for name, tool in observed.items():
        if name not in registered:
            continue
        description_hash = canonical_hash(tool["description"])
        schema_hash = canonical_hash(tool["input_schema"])
        await db.execute(
            """UPDATE mcp_tools SET observed_description_hash=%s, observed_schema_hash=%s,
               observed_server_version=%s, observed_at=now() WHERE server_id=%s AND name=%s""",
            (description_hash, schema_hash, discovered["version"], server_id, name),
        )
    registered_rows = await db.fetch_all("SELECT * FROM mcp_tools WHERE server_id=%s ORDER BY name", (server_id,))
    registered = {row["name"]: row for row in registered_rows}
    names_match = set(observed) == set(registered)
    metadata_safe = all(not UNSAFE_METADATA.search(tool["description"]) for tool in observed.values())
    findings: list[dict] = []
    if not names_match:
        findings.append({
            "type": "tool-set-drift",
            "added": sorted(set(observed) - set(registered)),
            "missing": sorted(set(registered) - set(observed)),
        })
    if not metadata_safe:
        findings.append({"type": "unsafe-description", "tools": [name for name, tool in observed.items() if UNSAFE_METADATA.search(tool["description"])]})

    hashes_match = True
    for name in set(observed) & set(registered):
        row = registered[name]
        tool = observed[name]
        mismatches = []
        if row["approved_description_hash"] != canonical_hash(tool["description"]):
            mismatches.append("description")
        if row["approved_schema_hash"] != canonical_hash(tool["input_schema"]):
            mismatches.append("schema")
        if row["approved_server_version"] != discovered["version"]:
            mismatches.append("version")
        if mismatches:
            hashes_match = False
            findings.append({"type": "contract-drift", "tool": name, "fields": mismatches})

    exact_match = names_match and metadata_safe and hashes_match
    await db.fetch_one(
        """INSERT INTO catalog_snapshots(server_id, server_version, catalog_hash, tool_count, exact_match, findings)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (server_id, discovered["version"], canonical_hash(discovered["tools"]), len(observed), exact_match, Jsonb(findings)),
    )
    await db.execute(
        "UPDATE mcp_servers SET status=%s, status_reason=%s, last_seen_at=now() WHERE id=%s",
        (
            "READY" if exact_match else "DRIFT",
            "승인 계약과 일치" if exact_match else "도구 계약 변화가 탐지됨",
            server_id,
        ),
    )
    return {
        "server_id": server_id,
        "status": "READY" if exact_match else "DRIFT",
        "protocol_version": discovered["protocol_version"],
        "version": discovered["version"],
        "tool_count": len(observed),
        "findings": findings,
    }


async def bootstrap() -> None:
    await db.wait_until_ready()
    if POLICY_PATH.exists():
        digest = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
        await db.execute("UPDATE policy_versions SET status='SUPERSEDED' WHERE status='ACTIVE' AND source_sha256<>%s", (digest,))
        await db.execute(
            """INSERT INTO policy_versions(id, source_path, source_sha256, status)
               VALUES (%s,%s,%s,'ACTIVE') ON CONFLICT (id) DO UPDATE SET status='ACTIVE'""",
            (f"rego-{digest[:12]}", str(POLICY_PATH), digest),
        )

    for server_id in ("mock-http", "mock-stdio"):
        for attempt in range(20):
            try:
                await refresh_catalog(server_id)
                break
            except Exception as exc:
                if attempt == 19:
                    await db.execute(
                        "UPDATE mcp_servers SET status='ERROR', status_reason=%s WHERE id=%s",
                        (str(exc)[:240], server_id),
                    )
                await asyncio.sleep(1)


async def _contract(server_id: str, tool_name: str) -> dict:
    server = await db.fetch_one("SELECT * FROM mcp_servers WHERE id=%s", (server_id,))
    tool = await db.fetch_one(
        "SELECT * FROM mcp_tools WHERE server_id=%s AND name=%s", (server_id, tool_name)
    )
    if not server or not tool:
        return {
            "registered": False,
            "enabled": False,
            "schema_hash_match": False,
            "description_hash_match": False,
            "version_match": False,
            "known_tools_only": False,
            "metadata_safe": False,
            "supplier_approved": False,
            "critical_vulnerabilities": 0,
        }

    latest = await db.fetch_one(
        "SELECT * FROM catalog_snapshots WHERE server_id=%s ORDER BY id DESC LIMIT 1", (server_id,)
    )
    critical = await db.fetch_one(
        "SELECT critical_count FROM supply_chain_reports WHERE source_ref=%s ORDER BY id DESC LIMIT 1",
        (server["source_ref"],),
    )
    return {
        "registered": True,
        "enabled": bool(tool["enabled"] and server["status"] != "DISABLED"),
        "schema_hash_match": bool(tool["approved_schema_hash"] and tool["approved_schema_hash"] == tool["observed_schema_hash"]),
        "description_hash_match": bool(tool["approved_description_hash"] and tool["approved_description_hash"] == tool["observed_description_hash"]),
        "version_match": bool(tool["approved_server_version"] and tool["approved_server_version"] == tool["observed_server_version"]),
        "known_tools_only": bool(latest and latest["exact_match"]),
        "metadata_safe": not bool(latest and any(item.get("type") == "unsafe-description" for item in latest["findings"])),
        "supplier_approved": server["status"] != "BLOCKED_SUPPLY_CHAIN",
        "critical_vulnerabilities": int(critical["critical_count"]) if critical else 0,
    }


async def _policy(input_document: dict) -> dict:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(OPA_URL, json={"input": input_document})
        response.raise_for_status()
        result = response.json().get("result")
        if not isinstance(result, dict) or "decision" not in result:
            raise RuntimeError("OPA returned no decision")
        return result


async def _call_upstream(spec: dict, arguments: dict) -> dict:
    if spec["server_id"] == "mock-http":
        source: Any = HTTP_MCP_URL
    elif spec["server_id"] == "mock-stdio":
        source = StdioServerParameters(command=TIME_MCP_PYTHON, args=["-m", "mcp_server_time"])
    elif spec["server_id"] == "github":
        raise RuntimeError("GitHub MCP authentication is not configured")
    else:
        raise RuntimeError("unknown upstream MCP server")

    async with Client(source) as client:
        result = await client.call_tool(spec["registry_name"], arguments)
        if result.is_error:
            messages = [getattr(item, "text", str(item)) for item in result.content]
            raise RuntimeError("; ".join(messages))
        if result.structured_content is not None:
            return result.structured_content
        return {"content": [getattr(item, "text", str(item)) for item in result.content]}


def _upstream_arguments(tool_name: str, payload: dict, restrictions: dict) -> dict:
    if tool_name == "read_document":
        return {"document_id": payload["document_id"]}
    if tool_name == "write_document":
        return {"document_id": payload["document_id"], "content": payload.get("content", "")}
    if tool_name == "send_external":
        content = payload.get("content", "")
        if restrictions.get("max_chars"):
            content = content[: int(restrictions["max_chars"])]
        return {
            "document_id": payload["document_id"],
            "destination": restrictions.get("destination", payload.get("destination", "")),
            "content": content,
        }
    if tool_name == "get_current_time":
        return {"timezone": payload.get("timezone", "Asia/Seoul")}
    if tool_name == "github_get_file":
        return {key: payload[key] for key in ("owner", "repo", "path") if key in payload}
    return {}


async def _record_decision(event: dict) -> int:
    row = await db.fetch_one(
        """INSERT INTO decisions(
             request_id, trace_id, user_token, role, tool_name, data_class, action,
             decision, policy_id, reason, upstream_executed, restrictions,
             approval_id, request_payload, result_preview, error)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (
            event["request_id"], event["trace_id"], event["user_token"], event["role"],
            event["tool_name"], event["data_class"], event["action"], event["decision"],
            event["policy_id"], event["reason"], event["upstream_executed"],
            Jsonb(event.get("restrictions") or {}), event.get("approval_id"),
            Jsonb(event.get("request_payload") or {}), Jsonb(event["result"]) if event.get("result") is not None else None,
            event.get("error"),
        ),
    )
    return int(row["id"])


async def execute_call(payload: dict, approval_granted: bool = False, approval_id: str | None = None) -> dict:
    request_id = str(uuid.uuid4())
    before = effect_count()
    with tracer.start_as_current_span("mcp.gateway.call") as span:
        trace_id = f"{span.get_span_context().trace_id:032x}"
        tool_name = str(payload.get("tool_name", "unknown"))
        spec = TOOL_SPECS.get(tool_name, {"server_id": "mock-http", "registry_name": tool_name, "action": "x"})
        principal = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (payload.get("user_token", ""),))
        document = None
        if tool_name in {"get_current_time", "github_get_file"}:
            data_class = "public"
        else:
            document = await db.fetch_one("SELECT * FROM documents WHERE id=%s", (payload.get("document_id", ""),))
            data_class = document["data_class"] if document else "important"
        role = principal["role"] if principal else "unknown"
        span.set_attribute("mcp.tool", tool_name)
        span.set_attribute("mcp.role", role)
        span.set_attribute("mcp.data_class", data_class)

        base_event = {
            "request_id": request_id,
            "trace_id": trace_id,
            "user_token": str(payload.get("user_token", "unknown")),
            "role": role,
            "tool_name": tool_name,
            "data_class": data_class,
            "action": spec["action"],
            "upstream_executed": False,
            "approval_id": approval_id,
            "request_payload": payload,
            "result": None,
            "error": None,
        }

        if not principal or (spec["server_id"] == "mock-http" and not document):
            base_event.update({
                "decision": "Block",
                "policy_id": "P-INPUT-001",
                "reason": "합성 사용자 토큰 또는 문서 ID가 유효하지 않습니다.",
                "restrictions": {},
            })
            decision_id = await _record_decision(base_event)
            return {**base_event, "decision_id": decision_id, "effect_before": before, "effect_after": effect_count()}

        if spec["server_id"] != "github":
            try:
                await refresh_catalog(spec["server_id"])
            except Exception as exc:
                span.record_exception(exc)

        contract = await _contract(spec["server_id"], spec["registry_name"])
        policy_input = {
            "principal": {"role": role, "synthetic": bool(principal["synthetic"])},
            "resource": {"id": payload.get("document_id", "time"), "data_class": data_class},
            "tool": {"name": spec["registry_name"], "action": spec["action"]},
            "approval": {"granted": approval_granted, "id": approval_id},
            "contract": contract,
        }
        try:
            result = await _policy(policy_input)
        except Exception as exc:
            result = {
                "decision": "Block",
                "policy_id": "P-CONTROL-FAIL-CLOSED",
                "reason": "OPA 정책 결정에 실패하여 기본 차단했습니다.",
                "restrictions": {},
            }
            base_event["error"] = str(exc)[:500]

        base_event.update(result)
        span.set_attribute("mcp.decision", result["decision"])
        span.set_attribute("mcp.policy_id", result["policy_id"])

        if result["decision"] == "Approval":
            new_approval_id = str(uuid.uuid4())
            fingerprint = canonical_hash(payload)
            await db.execute(
                """INSERT INTO approvals(id, request_fingerprint, request_payload, status, requested_by, expires_at)
                   VALUES (%s,%s,%s,'PENDING',%s,%s)""",
                (
                    new_approval_id, fingerprint, Jsonb(payload), payload["user_token"],
                    datetime.now(UTC) + timedelta(minutes=APPROVAL_TTL_MINUTES),
                ),
            )
            base_event["approval_id"] = new_approval_id
        elif result["decision"] in {"Allow", "Alert", "Restrict"}:
            effective = _upstream_arguments(tool_name, payload, result.get("restrictions") or {})
            try:
                with tracer.start_as_current_span("mcp.upstream.call") as upstream_span:
                    upstream_span.set_attribute("mcp.server", spec["server_id"])
                    upstream_span.set_attribute("mcp.transport", "stdio" if spec["server_id"] == "mock-stdio" else "streamable-http")
                    base_event["result"] = await _call_upstream(spec, effective)
                base_event["upstream_executed"] = True
                base_event["effective_arguments"] = effective
            except Exception as exc:
                base_event.update({
                    "decision": "Block",
                    "policy_id": "MCP-UPSTREAM-001",
                    "reason": "허용 후 upstream MCP 실행이 실패했습니다.",
                    "error": str(exc)[:500],
                })
                span.record_exception(exc)

        decision_id = await _record_decision(base_event)
        after = effect_count()
        return {**base_event, "decision_id": decision_id, "effect_before": before, "effect_after": after}


async def approve_request(approval_id: str, reviewer_token: str) -> dict:
    reviewer = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (reviewer_token,))
    if not reviewer or reviewer["role"] != "admin":
        raise ValueError("합성 관리자만 승인할 수 있습니다.")
    row = await db.fetch_one("SELECT * FROM approvals WHERE id=%s", (approval_id,))
    if not row or row["status"] != "PENDING":
        raise ValueError("대기 중인 승인 요청이 아닙니다.")
    if row["expires_at"] <= datetime.now(UTC):
        await db.execute("UPDATE approvals SET status='EXPIRED' WHERE id=%s", (approval_id,))
        raise ValueError("승인 요청의 10분 유효시간이 지났습니다.")

    claimed = await db.fetch_one(
        """UPDATE approvals SET status='APPROVED', reviewed_by=%s, reviewed_at=now()
           WHERE id=%s AND status='PENDING' AND expires_at>now() RETURNING *""",
        (reviewer_token, approval_id),
    )
    if not claimed:
        raise ValueError("다른 승인자가 먼저 처리했습니다.")
    payload = claimed["request_payload"]
    if canonical_hash(payload) != claimed["request_fingerprint"]:
        await db.execute("UPDATE approvals SET status='REJECTED' WHERE id=%s", (approval_id,))
        raise ValueError("승인 요청 내용의 무결성 검증에 실패했습니다.")

    result = await execute_call(payload, approval_granted=True, approval_id=approval_id)
    final_status = "EXECUTED" if result["upstream_executed"] else "REJECTED"
    await db.execute(
        "UPDATE approvals SET status=%s, executed_decision_id=%s WHERE id=%s",
        (final_status, result["decision_id"], approval_id),
    )
    return result


async def import_supply_chain_reports() -> list[dict]:
    imported: list[dict] = []
    sbom = REPORT_DIR / "sbom.cdx.json"
    if sbom.exists():
        data = json.loads(sbom.read_text(encoding="utf-8"))
        summary = {"components": len(data.get("components", [])), "format": data.get("bomFormat")}
        await db.execute("DELETE FROM supply_chain_reports WHERE scanner='Syft' AND report_path=%s", (str(sbom),))
        await db.execute(
            """INSERT INTO supply_chain_reports(scanner, scanner_version, source_ref, report_path, status, summary)
               VALUES ('Syft','1.51.1','workspace',%s,'IMPORTED',%s)""",
            (str(sbom), Jsonb(summary)),
        )
        imported.append({"scanner": "Syft", **summary})

    trivy = REPORT_DIR / "trivy.json"
    if trivy.exists():
        data = json.loads(trivy.read_text(encoding="utf-8"))
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0}
        for result in data.get("Results") or []:
            for vulnerability in result.get("Vulnerabilities") or []:
                severity = vulnerability.get("Severity", "")
                if severity in counts:
                    counts[severity] += 1
        summary = {"targets": len(data.get("Results") or []), "counts": counts}
        await db.execute("DELETE FROM supply_chain_reports WHERE scanner='Trivy' AND report_path=%s", (str(trivy),))
        await db.execute(
            """INSERT INTO supply_chain_reports(scanner, scanner_version, source_ref, report_path, status,
               critical_count, high_count, medium_count, summary)
               VALUES ('Trivy','0.74.0','workspace',%s,'IMPORTED',%s,%s,%s,%s)""",
            (str(trivy), counts["CRITICAL"], counts["HIGH"], counts["MEDIUM"], Jsonb(summary)),
        )
        imported.append({"scanner": "Trivy", **summary})

    sarif = REPORT_DIR / "mcp-scan.sarif.json"
    if sarif.exists():
        data = json.loads(sarif.read_text(encoding="utf-8"))
        results = [item for run in data.get("runs", []) for item in run.get("results", [])]
        levels = {"error": 0, "warning": 0, "note": 0}
        for item in results:
            level = item.get("level", "warning")
            levels[level] = levels.get(level, 0) + 1
        summary = {"findings": len(results), "levels": levels}
        await db.execute("DELETE FROM supply_chain_reports WHERE scanner='AI-Infra-Guard mcp-scan' AND report_path=%s", (str(sarif),))
        await db.execute(
            """INSERT INTO supply_chain_reports(scanner, scanner_version, source_ref, report_path, status,
               critical_count, high_count, medium_count, summary)
               VALUES ('AI-Infra-Guard mcp-scan','036c39bd03b3','workspace',%s,'IMPORTED',%s,%s,%s,%s)""",
            (str(sarif), levels["error"], levels["warning"], levels["note"], Jsonb(summary)),
        )
        imported.append({"scanner": "AI-Infra-Guard mcp-scan", **summary})
    return imported
