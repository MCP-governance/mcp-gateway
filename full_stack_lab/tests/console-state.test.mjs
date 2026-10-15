// node --test full_stack_lab/tests/console-state.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import {
  FEED_LIMIT, mergeRows, searchRows, liveLabel, hourBuckets, splitBy, sankeyData, harnessLabel,
  observationRows, listenerCoverage,
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
    tool: "read_text_file", target: "/shared/confidential/pay.csv", policy_id: "PAC-11", trace_id: "ABC123" })];
  for (const q of ["권노경", "WS-NKK", "OpenCode", "filesystem.read_text_file", "confidential", "pac-11", "  abc123 "]) {
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

test("endpoint observation shows disabled, stale and failed sources separately from zero accepted rows", () => {
  const now = Date.parse("2026-10-14T04:00:00Z");
  const at = (seconds) => new Date(now - seconds * 1000).toISOString();
  const rows = observationRows([{ endpoint_id: "ep-1", detail: { observation: {
    inventory: { state: "disabled", reported_at: at(2), accepted_count: 0 },
    process: { state: "success", reported_at: at(181), last_success_at: at(181), accepted_count: 3 },
    network: { state: "failed", reported_at: at(4), accepted_count: 0, error_code: "timeout" },
    os: { state: "unsupported", accepted_count: 0 },
  } } }], now);
  assert.deepEqual(rows.map((r) => [r.channel, r.stateLabel, r.freshnessLabel, r.acceptedCount]), [
    ["inventory", "중지", "최근 보고", 0],
    ["process", "보고됨", "오래됨", 3],
    ["network", "실패", "최근 보고", 0],
    ["os", "지원 안 함", "확인 불가", 0],
  ]);
  assert.equal(rows[2].hasError, true);
  assert.equal("error_code" in rows[2], false, "raw error enums are not exposed to the view");
  assert.equal(observationRows([{ endpoint_id: "ep-2", detail: { observation: {
    os: { state: "success", reported_at: new Date(now + 6000).toISOString(), accepted_count: 1 },
  } } }], now)[3].freshnessLabel, "확인 불가", "a future server timestamp is not called fresh");
});

test("listener-only endpoints remain in coverage counts and expose no raw command line or owner token", () => {
  const now = Date.parse("2026-10-14T04:00:00Z");
  const view = listenerCoverage([
    { endpoint_id: "listener-only", hostname: "ws-1", source: "stdio-process", address: "127.0.0.1", port: 7777,
      process_name: "blender", server_name: "MCP server", mcp_evidence: "suspected", classification: "shadow",
      observed_at: new Date(now - 30_000).toISOString(), command_line: "secret --token abc", owner_token: "bearer-secret" },
    { endpoint_id: "residue-only", source: "local-socket", address: "/run/mcp.sock", classification: "retired-residue",
      mcp_evidence: "unknown", observed_at: new Date(now - 181_000).toISOString(), scan_source_status: { state: "disabled" } },
    { endpoint_id: "registered", source: "network", classification: "registered", observed_at: new Date(now).toISOString() },
  ], now);
  assert.equal(view.total, 2);
  assert.deepEqual(view.byEndpoint, [{ endpointId: "listener-only", count: 1 }, { endpointId: "residue-only", count: 1 }]);
  assert.equal(view.rows[0].source, "표준입출력 프로세스");
  assert.equal(view.rows[0].evidence, "MCP로 추정");
  assert.equal(view.rows[0].classification, "미등록");
  assert.equal(view.rows[0].freshnessLabel, "최근 보고");
  assert.equal(view.rows[1].freshnessLabel, "오래됨");
  assert.equal(view.rows[1].scanStatusLabel, "중지");
  assert.equal("command_line" in view.rows[0], false);
  assert.equal("owner_token" in view.rows[0], false);
});

test("enforced is green only with fresh evidence of a ledger row or a kernel heartbeat", async () => {
  const { statusView, dedupeItems, pipelineOf, ageSeconds } = await import("../gateway/app/agent_static/console-state.mjs");
  const now = Date.parse("2026-10-01T10:00:00Z");
  const at = (s) => new Date(now - s * 1000).toISOString();
  assert.equal(statusView({ state: "gateway_enforced", evidence_kind: "ledger", evidence_at: at(60), evidence_ref: 4812 }, now).tone, "allow");
  assert.match(statusView({ state: "gateway_enforced", evidence_kind: "ledger", evidence_at: at(60), evidence_ref: 4812 }, now).evLabel, /감사 기록 #4812/);
  const noRecord = statusView({ state: "gateway_enforced", evidence_kind: "none" }, now);
  assert.equal(noRecord.tone, "outline");
  assert.equal(noRecord.evLabel, "경유 기록 없음");
  assert.equal(statusView({ state: "endpoint_enforced", evidence_kind: "kernel", evidence_at: at(42) }, now).tone, "allow");
  const stale = statusView({ state: "endpoint_enforced", evidence_kind: "kernel", evidence_at: at(181) }, now);
  assert.equal(stale.tone, "outline");
  assert.ok(stale.stale && stale.level <= 1 && stale.evLabel.endsWith("만료"));
  assert.equal(statusView({ state: "vendor_enforced", evidence_kind: "manual", evidence_at: at(3600) }, now).tone, "restrict");
  assert.equal(statusView({ state: "bypass_possible", evidence_kind: "report", evidence_at: at(60) }, now).tone, "block");
  assert.equal(statusView({}, now).state, "unknown_not_enrolled");
  assert.equal(ageSeconds("not a date", now), null);

  const items = dedupeItems([
    { key: "k|a|pc1", item_key: "k", owner: "a", device: "pc1", state: "observed_only", bypass: ["x"] },
    { key: "k|b|pc2", item_key: "k", owner: "b", device: "pc2", state: "bypass_possible", bypass: ["y"] },
    { key: "gateway:github", state: "gateway_enforced" },
  ]);
  assert.equal(items.length, 2);
  const merged = items.find((i) => i.key === "k");
  assert.equal(merged.pcs, 2);
  assert.equal(merged.state, "bypass_possible", "one open PC makes the item bypassable");
  assert.deepEqual(merged.owners, ["a", "b"]);
  assert.deepEqual(merged.bypass, ["x", "y"]);

  const refused = pipelineOf({ event_kind: "mcp-connection", decision: "Block", policy_id: "MCP-REGISTRY-001", planes: ["gateway"] });
  assert.deepEqual(refused.map((n) => n.state), ["reported", "refused-connection", "none", "not_sent", "not_executed"]);
  const withheld = pipelineOf({ device_id: "d", planes: ["gateway", "endpoint"], attempted: true, executed: true, response: "withheld" });
  assert.deepEqual(withheld.map((n) => n.state), ["signed", "decided", "bound", "executed", "withheld"]);
});
