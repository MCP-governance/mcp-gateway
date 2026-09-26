"""Exercise the plan 2 boundary against the real pinned task API envelope."""
import json

import httpx
from fastapi import FastAPI, HTTPException
import pytest

from services import scanner

SID = "550e8400-e29b-41d4-a716-446655440000"
ADMIN = {"Authorization": "Bearer admin"}


@pytest.fixture
async def scan_client(monkeypatch):
    for key in ("AIG_SCAN_MODEL", "AIG_SCAN_MODEL_TOKEN", "AIG_SCAN_MODEL_BASE_URL", "AIG_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AIG_BASE_URL", "http://aig-web:8088")
    monkeypatch.setenv("AIG_USERNAME", "public_user")
    monkeypatch.setenv("TEST_TARGETS", '{"demo":"http://test-mcp:8000/mcp"}')
    monkeypatch.setenv("SERVICE_TOKEN", "zone-secret")
    calls, observations = [], []
    responses = []

    async def authenticate(request, admin=False):
        assert admin is True
        token = request.headers.get("authorization", "")
        if token == "Bearer user":
            raise HTTPException(403, "Administrator role required")
        if token != "Bearer admin":
            raise HTTPException(401, "Keycloak login required")
        return {"sub": "operator"}

    def upstream(request):
        calls.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(scanner, "authenticate", authenticate)
    monkeypatch.setattr(scanner, "emit", lambda service, kind, attrs: observations.append((service, kind, attrs)))
    app = FastAPI()
    app.include_router(scanner.router)
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as external:
        app.state.client = external
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
            yield client, calls, responses, observations


def ok(data):
    return httpx.Response(200, json={"status": 0, "data": data})


async def test_submission_uses_only_configured_target_and_metadata(scan_client, monkeypatch):
    client, calls, responses, events = scan_client
    monkeypatch.setenv("AIG_SCAN_MODEL", "test-model")
    monkeypatch.setenv("AIG_SCAN_MODEL_TOKEN", "llm-credential")
    monkeypatch.setenv("AIG_API_KEY", "aig-key")
    responses.append(ok({"session_id": SID}))
    response = await client.post("/scans", json={"target": "demo"}, headers=ADMIN)
    assert response.status_code == 202
    assert response.json() == {"session_id": SID, "status": "submitted", "approval": "unchanged"}
    assert len(calls) == 1
    assert calls[0].url == "http://aig-web:8088/api/v1/app/taskapi/tasks"
    assert json.loads(calls[0].content) == {
        "type": "mcp_scan", "content": {"prompt": "http://test-mcp:8000/mcp", "thread": 1, "language": "en",
        "model": {"model": "test-model", "token": "llm-credential", "base_url": "https://api.openai.com/v1"}}}
    assert calls[0].headers["username"] == "public_user"
    assert calls[0].headers["api-key"] == "aig-key"
    assert "authorization" not in calls[0].headers
    assert "llm-credential" not in json.dumps(events)
    assert events[0][2]["subject"] == "operator"


@pytest.mark.parametrize("headers,status", [({}, 401), ({"Authorization": "Bearer user"}, 403)])
async def test_admin_gate_precedes_scan_work(scan_client, headers, status):
    client, calls, _, _ = scan_client
    assert (await client.post("/scans", json={"target": "demo"}, headers=headers)).status_code == status
    assert (await client.get("/scans/" + SID, headers=headers)).status_code == status
    assert calls == []


@pytest.mark.parametrize("body,status", [
    ({"target": "not-configured"}, 400),
    ({"target": "http://169.254.169.254/latest/meta-data"}, 422),
    ({"target": "demo", "prompt": "http://other-host"}, 422),
    ({"target": "demo", "attachments": "/etc/passwd"}, 422),
])
async def test_target_allowlist_and_schema_reject_arbitrary_submission(scan_client, body, status):
    client, calls, _, _ = scan_client
    assert (await client.post("/scans", json=body, headers=ADMIN)).status_code == status
    assert calls == []


@pytest.mark.parametrize("configuration", ["[]", "{broken", '{"demo":"file:///etc/passwd"}', '{"demo":"http://user:password@test-mcp/mcp"}'])
async def test_bad_deployment_configuration_fails_closed(scan_client, monkeypatch, configuration):
    client, calls, _, _ = scan_client
    monkeypatch.setenv("TEST_TARGETS", configuration)
    assert (await client.post("/scans", json={"target": "demo"}, headers=ADMIN)).status_code == 503
    assert calls == []


async def test_missing_aig_default_model_is_failure_not_completed(scan_client):
    client, calls, responses, events = scan_client
    responses.append(httpx.Response(200, json={"status": 1, "message": "invalid parameters: model.token is required when no default model is configured", "data": None}))
    response = await client.post("/scans", json={"target": "demo"}, headers=ADMIN)
    assert response.status_code == 503
    assert "LLM credentials" in response.json()["detail"]
    assert "model" not in json.loads(calls[0].content)["content"]
    assert events == []


async def test_partial_model_configuration_fails_before_submission(scan_client, monkeypatch):
    client, calls, _, _ = scan_client
    monkeypatch.setenv("AIG_SCAN_MODEL", "test-model")
    assert (await client.post("/scans", json={"target": "demo"}, headers=ADMIN)).status_code == 503
    assert calls == []


@pytest.mark.parametrize("reply", [httpx.Response(500, text="token=secret"), httpx.Response(302, headers={"Location": "http://other-host"}), httpx.Response(200, text="broken"), httpx.Response(200, json={"status": 1, "message": "secret server detail"}), httpx.ConnectError("connection failed")])
async def test_aig_errors_are_bounded_and_do_not_leak(scan_client, reply):
    client, calls, responses, events = scan_client
    responses.append(reply)
    response = await client.post("/scans", json={"target": "demo"}, headers=ADMIN)
    assert response.status_code == 502
    assert "secret" not in response.text
    assert len(calls) == 1 and events == []


async def test_completed_task_fetches_report_without_changing_approval(scan_client):
    client, calls, responses, events = scan_client
    report = {"results": [{"severity": "high", "title": "Tool injection"}]}
    responses.extend([ok({"status": "done", "log": "model-secret"}), ok(report)])
    response = await client.get("/scans/" + SID, headers=ADMIN)
    assert response.status_code == 200
    assert response.json() == {"session_id": SID, "status": "done", "result": report, "approval": "unchanged"}
    assert [request.url.path for request in calls] == [scanner.AIG_TASK_PATH + "/status/" + SID, scanner.AIG_TASK_PATH + "/result/" + SID]
    assert all(request.method == "GET" for request in calls)
    assert "model-secret" not in response.text and "Tool injection" not in json.dumps(events)


@pytest.mark.parametrize("status", ["doing", "todo", "failed", "error", "terminated"])
async def test_noncompleted_tasks_do_not_fabricate_a_report(scan_client, status):
    client, calls, responses, _ = scan_client
    responses.append(ok({"status": status}))
    response = await client.get("/scans/" + SID, headers=ADMIN)
    assert response.json()["result"] is None
    assert response.json()["status"] == status
    assert response.json()["approval"] == "unchanged"
    assert len(calls) == 1


async def test_malformed_session_never_hits_upstream(scan_client):
    client, calls, _, _ = scan_client
    assert (await client.get("/scans/not-a-session", headers=ADMIN)).status_code == 400
    assert calls == []


async def test_invalid_submission_session_is_not_accepted(scan_client):
    client, _, responses, events = scan_client
    responses.append(ok({"session_id": "../elsewhere"}))
    assert (await client.post("/scans", json={"target": "demo"}, headers=ADMIN)).status_code == 502
    assert events == []


async def test_trivy_ingestion_requires_service_identity_and_real_file(scan_client, monkeypatch, tmp_path):
    client, calls, _, events = scan_client
    report = tmp_path / "trivy.json"
    monkeypatch.setenv("TRIVY_REPORT_PATH", str(report))
    assert (await client.post("/scans/trivy-result", headers=ADMIN)).status_code == 401
    assert (await client.post("/scans/trivy-result", headers={"X-Service-Token": "zone-secret"})).status_code == 503
    report.write_text(json.dumps({"SchemaVersion": 2, "Results": [{"Secrets": [{"Severity": "HIGH", "Match": "secret-value"}], "Vulnerabilities": [{"Severity": "CRITICAL"}]}]}))
    response = await client.post("/scans/trivy-result", headers={"X-Service-Token": "zone-secret"}, json={"path": "/etc/passwd"})
    assert response.json() == {"scanner": "Trivy", "finding_count": 2, "severities": {"CRITICAL": 1, "HIGH": 1}, "types": {"Vulnerabilities": 1, "Secrets": 1}, "approval": "unchanged"}
    assert "secret-value" not in response.text and "secret-value" not in json.dumps(events)
    assert events[0][2]["finding_count"] == 2
    assert calls == []
