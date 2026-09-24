import test from "node:test";
import assert from "node:assert/strict";
import {
  DECISION_LIMIT,
  mergeDecisions,
  reconcileSnapshot,
  streamPayload,
  filterDecisions,
  executionLabel,
  healthLabel,
} from "../gateway/app/agent_static/console-state.mjs";

const decision = (id, fields = {}) => ({
  id,
  decision: "Allow",
  tool_name: "document.read",
  policy_id: "POL-READ",
  user_token: "viewer-test",
  role: "employee",
  trace_id: `trace-${id}`,
  upstream_attempted: true,
  upstream_executed: true,
  ...fields,
});

test("a reconnect merges numeric IDs once and keeps the newest forty rows", () => {
  const current = Array.from({ length: 40 }, (_, index) => decision(index + 1));
  const updated = decision("40", { decision: "Block", upstream_executed: false });
  const incoming = [decision(41), updated, decision(42), decision(42)];
  const original = structuredClone({ current, incoming });

  const merged = mergeDecisions(current, incoming);

  assert.equal(DECISION_LIMIT, 40);
  assert.deepEqual(merged.map((row) => Number(row.id)),
    Array.from({ length: 40 }, (_, index) => 42 - index));
  assert.equal(merged.find((row) => Number(row.id) === 40).decision, "Block");
  assert.deepEqual({ current, incoming }, original, "merging must not mutate source rows");
});

test("decision IDs sort numerically and invalid IDs cannot displace real decisions", () => {
  const rows = ["10", "2", "9", 0, -1, 1.5, "invalid", Number.MAX_SAFE_INTEGER + 1]
    .map((id) => decision(id));
  assert.deepEqual(mergeDecisions([], rows).map((row) => row.id), ["10", "9", "2"]);
  assert.deepEqual(mergeDecisions([], rows, 2).map((row) => row.id), ["10", "9"]);
});

test("the actual server SSE rows/cursor envelope produces a resumable cursor", () => {
  // agent_service.py emits ascending rows with cursor equal to their largest ID.
  const payload = { rows: [decision(101), decision(102), decision(103)], cursor: 103 };
  const parsed = streamPayload(payload);
  assert.deepEqual(parsed.rows.map((row) => row.id), [103, 102, 101]);
  assert.equal(parsed.cursor, 103);
});

test("supported legacy SSE envelopes do not lose decisions", () => {
  assert.deepEqual(streamPayload([decision(2), decision(3)]).rows.map((row) => row.id), [3, 2]);
  assert.deepEqual(streamPayload({ decisions: [decision(4)] }).rows.map((row) => row.id), [4]);
});

test("empty and malformed SSE containers cannot manufacture a decision or cursor", () => {
  for (const payload of [undefined, null, {}, [], "unexpected", { rows: null }, { rows: {} },
    { rows: "unexpected", cursor: 999 }, { rows: [decision("bad-id")] }]) {
    assert.deepEqual(streamPayload(payload), { rows: [], cursor: 0 });
  }
});

test("a malformed row does not prevent the next valid decision from rendering", () => {
  const parsed = streamPayload({ rows: [null, undefined, "unexpected", 5, {}, decision(7)] });
  assert.deepEqual(parsed.rows.map((row) => row.id), [7]);
  assert.equal(parsed.cursor, 7);
});

test("request search supports trace IDs and combines with verdict and execution filters", () => {
  const rows = [
    decision(1, { decision: "Block", trace_id: "TRACE-SPECIAL", upstream_executed: false }),
    decision(2, { decision: "Allow", trace_id: "trace-special", upstream_executed: false }),
    decision(3, { decision: "Block", trace_id: "trace-special" }),
    decision(4, { decision: "Block", trace_id: "trace-other", upstream_executed: false }),
  ];
  assert.deepEqual(filterDecisions(rows, "  trace-SPECIAL  ", "Block", "unconfirmed")
    .map((row) => row.id), [1]);
  assert.deepEqual(filterDecisions(rows, "", "all", "unconfirmed")
    .map((row) => row.id), [1, 2, 4]);
  assert.deepEqual(filterDecisions(rows), rows);
  assert.deepEqual(filterDecisions(rows, "absent-trace"), []);
});

test("request search tolerates absent text fields and matches the documented fields", () => {
  for (const field of ["tool_name", "policy_id", "user_token", "role", "trace_id"]) {
    const rows = [{ id: 1, decision: "Allow", [field]: "Unique-Match" }, { id: 2 }];
    assert.deepEqual(filterDecisions(rows, "unique-match").map((row) => row.id), [1]);
  }
});

test("execution labels distinguish output blocking, no execution, and uncertain effects", () => {
  assert.equal(executionLabel(decision(1, { decision: "Block" })), "실행 후 출력 차단");
  assert.equal(executionLabel(decision(2)), "실행 확인");
  assert.equal(executionLabel(decision(3, { upstream_executed: false })), "실행 여부 미확인");
  assert.equal(executionLabel(decision(4, { decision: "Approval", upstream_attempted: false,
    upstream_executed: false })), "승인 대기 / 미실행");
  assert.equal(executionLabel(decision(5, { decision: "Block", upstream_attempted: false,
    upstream_executed: false })), "미실행");
});

test("health labels never report unknown status as normal", () => {
  assert.equal(healthLabel({ status: "ok" }), "정상");
  assert.equal(healthLabel({ status: "degraded" }), "일부 서비스 저하");
  assert.equal(healthLabel({ status: "down" }), "연결 장애");
  for (const health of [undefined, null, {}, { status: null }, { status: "connecting" },
    { status: "constructor" }, { status: "toString" }]) {
    assert.equal(healthLabel(health), "상태 미확인");
  }
});


test("a snapshot cannot erase a newer SSE row, even when its result is empty", () => {
  assert.deepEqual(reconcileSnapshot([{ id: 1 }], [], 0).map((r) => r.id), [1]);
  assert.deepEqual(reconcileSnapshot([{ id: 43 }, { id: 42 }], [{ id: 42 }, { id: 41 }], 42).map((r) => r.id), [43, 42, 41]);
  assert.deepEqual(reconcileSnapshot([{ id: 1 }], [], 1), []);
});
