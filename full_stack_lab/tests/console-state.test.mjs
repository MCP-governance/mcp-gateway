// node --test full_stack_lab/tests/console-state.test.mjs   (CI: verify.yml static job)
import test from "node:test";
import assert from "node:assert/strict";
import {
  FEED_LIMIT, mergeRows, searchRows, liveLabel, hourBuckets, splitBy, sankeyData, harnessLabel,
} from "../gateway/app/agent_static/console-state.mjs";

const row = (id, fields = {}) => ({
  id, decision: "Allow", who: "양승권", department: "플랫폼개발팀", workstation: "ws-ysg", harness: "claude-code",
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

test("search matches person, PC, harness, server.tool, target, policy and trace, ignoring case and spaces", () => {
  const rows = [row(1), row(2, { who: "권노경", workstation: "ws-nkk", harness: "opencode", server: "filesystem",
    tool: "read_text_file", target: "/shared/confidential/pay.csv", policy_id: "P-AUTHZ-DENY-001", trace_id: "ABC123" })];
  for (const q of ["권노경", "WS-NKK", "OpenCode", "filesystem.read_text_file", "confidential", "p-authz-deny", "  abc123 "]) {
    assert.deepEqual(searchRows(rows, q).map((r) => r.id), [2], q);
  }
  assert.deepEqual(searchRows(rows, ""), rows);
  assert.deepEqual(searchRows(rows, "absent"), []);
  assert.deepEqual(searchRows([{ id: 3 }, row(4)], "git_log").map((r) => r.id), [4], "absent fields are tolerated");
});

test("the status phrase never presents a failed poll as fresh", () => {
  const at = new Date(2026, 8, 25, 9, 30, 5).getTime();
  assert.equal(liveLabel({ live: true, lastOk: at, failing: true }), "갱신 실패 · 마지막 09:30:05");
  assert.equal(liveLabel({ live: true, failing: true }), "갱신 실패");
  assert.equal(liveLabel({ live: true, lastOk: at }), "실시간 · 09:30:05");
  assert.equal(liveLabel({ live: true }), "실시간 · 연결 중");
  assert.equal(liveLabel({ live: false, pending: 3 }), "일시정지 · 대기 3건");
  assert.equal(liveLabel({ live: false }), "일시정지");
});

test("24 hourly buckets end at the current hour and keep empty hours at zero", () => {
  const now = new Date(2026, 8, 25, 14, 42).getTime();
  const hour = (h) => new Date(2026, 8, 25, h).toISOString();
  const buckets = hourBuckets([
    { hour: hour(14), decision: "Allow", n: 3 }, { hour: hour(14), decision: "Block", n: "2" },
    { hour: hour(9), decision: "Alert", n: 1 },
    { hour: new Date(2026, 8, 24, 10).toISOString(), decision: "Allow", n: 9 },  // older than 24 h: dropped
    { hour: hour(13), decision: "Unknown", n: 5 },                             // not a decision: dropped
  ], now);
  assert.equal(buckets.length, 24);
  assert.equal(buckets.at(-1).label, "14시");
  assert.deepEqual([buckets.at(-1).Allow, buckets.at(-1).Block, buckets.at(-1).total], [3, 2, 5]);
  assert.equal(buckets.at(-6).Alert, 1);
  assert.equal(buckets.reduce((s, b) => s + b.total, 0), 6);
  assert.equal(buckets[0].label, "15시");
});

test("splitBy counts per key with a decision split, largest first", () => {
  const rows = [row(1), row(2, { server: "email", decision: "Block" }), row(3, { server: "email" }), row(4, { server: "" })];
  assert.deepEqual(splitBy(rows, "server").map((g) => [g.key, g.total, g.Allow, g.Block]), [["email", 2, 1, 1], ["git", 1, 1, 0]]);
  assert.deepEqual(splitBy(rows, (r) => harnessLabel(r.harness)).map((g) => g.key), ["Claude Code"]);
  assert.deepEqual(splitBy([{ server: "a", decision: "Allow", n: 4 }], "server", (r) => r.n)[0].total, 4);
});

test("sankey layers never merge a server with a harness of the same name", () => {
  const { nodes, links } = sankeyData([
    { harness: "claude-code", server: "git", decision: "Allow", n: 2 },
    { harness: "opencode", server: "git", decision: "Block", n: 1 },
    { harness: "fetch", server: "fetch", decision: "Allow", n: 1 },
    { harness: "x", server: "y", decision: "Allow", n: 0 },
  ]);
  assert.deepEqual(nodes.map((n) => [n.name, n.layer]), [
    ["Claude Code", 0], ["git ·", 1], ["Allow", 2], ["OpenCode", 0], ["Block", 2], ["fetch", 0], ["fetch ·", 1]]);
  assert.equal(links.find((l) => l.source === "git ·" && l.target === "Allow").value, 2);
  assert.equal(links.length, 6);
});
