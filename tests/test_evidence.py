import hashlib
import json

import httpx
import pytest

from services import evidence


def otlp(data=None, status=0):
    return {"resourceSpans": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "gateway"}}]},
                              "scopeSpans": [{"spans": [{"traceId": "abc", "spanId": "def", "name": "mcp.call",
                                  "status": {"code": status}, "attributes": [
                                      {"key": "evidence.kind", "value": {"stringValue": "presidio.inspect"}},
                                      {"key": "evidence.data", "value": {"stringValue": json.dumps(data or {})}},
                                      {"key": "authorization", "value": {"stringValue": "Bearer secret"}}]}]}]}]}


async def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def test_normalization_drops_raw_arguments_and_tokens():
    normalized = evidence.normalize(otlp({"tool": "search", "server": "demo", "arguments": {"password": "secret"},
                                          "token": "Bearer secret", "findings": [{"entity_type": "CREDENTIAL", "text": "secret"}]}))
    event = normalized[0]
    assert event["service"] == "gateway"
    assert event["data"] == {"tool": "search", "server": "demo", "finding_count": 1,
                              "presidio.entity_types": ["CREDENTIAL"]}
    assert "secret" not in json.dumps(normalized)
    assert evidence.evaluate(event) == ("high", ["presidio-findings"])


@pytest.mark.parametrize("event,risk", [
    ({"kind": "mcp.call", "data": {}}, "low"),
    ({"kind": "mcp.call", "data": {"status": "blocked"}}, "medium"),
    ({"kind": "tool.drift", "data": {}}, "high"),
    ({"kind": "presidio", "data": {"finding_count": 2}}, "high"),
])
def test_evidence_risk(event, risk):
    assert evidence.evaluate(event)[0] == risk


@pytest.mark.asyncio
async def test_internal_services_refuse_missing_tokens(monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", "trusted")
    async with await client(evidence.decision) as session:
        assert (await session.get("/tools")).status_code == 401
        assert (await session.post("/tools/register", json={"server": "s", "tool": "t", "definition": {}})).status_code == 401
    async with await client(evidence.processor) as session:
        assert (await session.post("/v1/traces", json=otlp())).status_code == 401


@pytest.mark.asyncio
async def test_register_canonical_hash_and_unknown_defaults(monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", "trusted")
    captured = []

    async def register(server, tool, digest, definition):
        captured.append(digest)
        return {"server": server, "tool": tool, "hash": digest, "approved": False}

    async def unknown(server, tool):
        return None

    monkeypatch.setattr(evidence.db, "register", register)
    monkeypatch.setattr(evidence.db, "tool", unknown)
    async with await client(evidence.decision) as session:
        headers = {"X-Service-Token": "trusted"}
        body = {"server": "s", "tool": "t", "definition": {"b": 1, "a": 2}}
        response = await session.post("/tools/register", json=body, headers=headers)
        assert response.status_code == 200
        assert response.json()["approved"] is False
        assert captured == [hashlib.sha256(b'{"a":2,"b":1}').hexdigest()]
        response = await session.get("/tools/s/missing", headers=headers)
        assert response.json()["approved"] is False


@pytest.mark.asyncio
async def test_analyzer_reads_stored_normalized_evidence(monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", "trusted")

    async def fetch(event_id):
        return {"payload": {"kind": "presidio", "data": {"finding_count": 1}}}

    async def store(event_id, risk, flags):
        return {"id": event_id, "risk": risk, "flags": flags}

    monkeypatch.setattr(evidence.db, "event", fetch)
    monkeypatch.setattr(evidence.db, "analyze", store)
    async with await client(evidence.analyzer) as session:
        response = await session.post("/analyze", json={"event_id": 7}, headers={"X-Service-Token": "trusted"})
        assert response.json() == {"id": 7, "risk": "high", "flags": ["presidio-findings"]}


@pytest.mark.asyncio
async def test_processor_propagates_analysis_failure_and_retries_existing_event(monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", "trusted")
    monkeypatch.setenv("ANALYZER_URL", "http://analyzer")
    attempts = []

    async def ingest(event):
        return {"id": 9, "analyzed_at": None}

    monkeypatch.setattr(evidence.db, "ingest", ingest)
    real_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        if kwargs.get("trust_env") is False:
            async def handler(request):
                attempts.append(json.loads(request.content))
                return httpx.Response(503 if len(attempts) == 1 else 200, json={})
            return real_client(transport=httpx.MockTransport(handler), timeout=15)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(evidence.httpx, "AsyncClient", make_client)
    async with await client(evidence.processor) as session:
        first = await session.post("/v1/traces", json=otlp(), headers={"X-Service-Token": "trusted"})
        second = await session.post("/v1/traces", json=otlp(), headers={"X-Service-Token": "trusted"})
    assert first.status_code == 503
    assert second.status_code == 200
    assert attempts == [{"event_id": 9}, {"event_id": 9}]


@pytest.mark.asyncio
async def test_audit_approval_requires_admin(monkeypatch):
    calls = []

    async def auth(request, admin=False):
        calls.append(admin)
        if admin:
            from fastapi import HTTPException
            raise HTTPException(403, "Administrator role required")
        return {"sub": "employee"}

    monkeypatch.setattr(evidence, "authenticate", auth)
    async with await client(evidence.audit) as session:
        response = await session.put("/tools/s/t", json={"approved": True})
        assert response.status_code == 403
    assert calls == [True]
