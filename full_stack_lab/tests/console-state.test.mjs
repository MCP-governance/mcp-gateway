// node --test full_stack_lab/tests/console-state.test.mjs   (CI: verify.yml static job)
import test from "node:test";
import assert from "node:assert/strict";
import { FEED_LIMIT, mergeRows, searchRows, liveLabel } from "../gateway/app/agent_static/console-state.mjs";

const row = (id, fields = {}) => ({
  id, decision: "Allow", who: "양승권", department: "플랫폼개발팀", workstation: "ws-ysg",
  server: "git", tool: "git_log", target: "/repos/handbook", policy_id: "P-AUTHZ-ALLOW-001",
  trace_id: `trace-${id}`, reason: "배포된 권한 번들과 등록 계약을 모두 충족했습니다.", ...fields,
});

test("a poll overlapping a page load shows each call once, newest first, within the limit", () => {
  const current = Array.from({ length: 5 }, (_, i) => row(i + 1));
  const updated = row("5", { decision: "Block" });
  const incoming = [row(6), updated, row(7), row(7)];
  const before = structuredClone({ current, incoming });
  const merged = mergeRows(current, incoming, 6);
  assert.deepEqual(merged.map((r) => Number(r.id)), [7, 6, 5, 4, 3, 2]);
  assert.equal(merged.find((r) => Number(r.id) === 5).decision, "Block");
  assert.deepEqual({ current, incoming }, before, "merging must not mutate its inputs");
  assert.equal(FEED_LIMIT, 500);
});

test("ids sort numerically and malformed rows cannot displace real decisions", () => {
  const rows = ["10", "2", "9", 0, -1, 1.5, "bad", Number.MAX_SAFE_INTEGER + 1].map((id) => row(id));
  assert.deepEqual(mergeRows([], rows).map((r) => r.id), ["10", "9", "2"]);
  assert.deepEqual(mergeRows([], [null, undefined, "x", 5, {}, row(7)]).map((r) => r.id), [7]);
  assert.deepEqual(mergeRows(null, undefined), []);
});

test("search matches person, PC, server.tool, target, policy and trace, ignoring case and spaces", () => {
  const rows = [row(1), row(2, { who: "권노경", workstation: "ws-nkk", server: "filesystem", tool: "read_text_file",
    target: "/shared/confidential/pay.csv", policy_id: "P-AUTHZ-DENY-001", trace_id: "ABC123" })];
  for (const q of ["권노경", "WS-NKK", "filesystem.read_text_file", "confidential", "p-authz-deny", "  abc123 "]) {
    assert.deepEqual(searchRows(rows, q).map((r) => r.id), [2], q);
  }
  assert.deepEqual(searchRows(rows, ""), rows);
  assert.deepEqual(searchRows(rows, "absent"), []);
  assert.deepEqual(searchRows([{ id: 3 }, row(4)], "git_log").map((r) => r.id), [4], "absent fields are tolerated");
});

test("the status line never presents a failed poll as fresh", () => {
  const at = new Date(2026, 8, 25, 9, 30, 5).getTime();
  assert.match(liveLabel({ live: true, lastOk: at, failing: true }), /^갱신 실패 — 마지막 성공 09:30:05/);
  assert.match(liveLabel({ live: true, failing: true }), /^갱신 실패 — 화면이 최신이 아닐 수/);
  assert.equal(liveLabel({ live: true, lastOk: at }), "실시간 · 09:30:05 확인");
  assert.equal(liveLabel({ live: true }), "실시간 · 연결 중");
  assert.equal(liveLabel({ live: false, pending: 3 }), "일시정지 · 새 판정 3건 대기");
  assert.equal(liveLabel({ live: false }), "일시정지");
});
