import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { EN } from "../gateway/app/agent_static/i18n-en.mjs";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end));
const ui = runInNewContext(`${section("class Raw {", "function detailText(")}
const chip = (tone, value) => html\`<span class="chip \${tone}">\${value}</span>\`;
const when = (value) => '시각:' + value;
const empty = () => '';
const kv = (rows) => html\`<dl>\${rows.map(([key, value]) => html\`<dt>\${key}</dt><dd>\${value}</dd>\`)}</dl>\`;
const panel = (title, body) => html\`<section>\${title}\${body}</section>\`;
const decisionChip = (value) => chip('block', value);
const harnessName = (value) => value;
const policyLedger = [{policy_id: 'custom', name: '<img src=x>'}];
const policyLabel = (id) => id;
const CHECK_LABEL = {};
const ALERT_KIND = {'unapproved-endpoint-mcp': '미등록 MCP 사용'};
${section("function shadowLink(", "async function refreshBadges(")}
${section("const decisionReason =", "const VALIDITY =")}
${section("function alertGroups(", "const alertsTab =")}
${section("const TOOL_PATH =", "ROUTES.policy =")}
({decisionTable, groupedAlerts, alertGroups, alertTarget, endpointCallsTab});`, {URLSearchParams});

test("blocked rows keep seven columns and distinguish duplicate calls from consent before opening detail", () => {
  const result = String(ui.decisionTable([
    {id: 1, decision: "Block", policy_id: "P-RATE-003", tool: "write", server: "Memory"},
    {id: 2, decision: "Block", policy_id: "P-CONSENT-001", tool: "search", server: "HF"},
    {id: 3, decision: "Block", policy_id: "custom", tool: "<script>"},
    {id: 4, decision: "Block", policy_id: "UNKNOWN-INTERNAL-CODE"},
  ]));
  assert.equal((result.match(/<th>/g) || []).length, 7);
  assert.ok(result.includes('class="sub">중복 호출 차단'));
  assert.ok(result.includes('class="sub">이용 동의 필요'));
  assert.ok(result.includes("&lt;img src=x&gt;"));
  assert.ok(result.includes("&lt;script&gt;"));
  assert.ok(result.includes("사유 미확인"));
  assert.ok(!result.includes("UNKNOWN-INTERNAL-CODE"));
});

test("endpoint route chips use brand, restrict and alert without changing the table", () => {
  const body = String(ui.endpointCallsTab({rows: ["gateway", "connector", "local"].map((path) => ({path})), total: 3}).body);
  for (const [tone, label] of [["brand", "게이트웨이"], ["restrict", "커넥터"], ["alert", "로컬 MCP"]]) {
    assert.ok(body.includes(`class="chip ${tone}">${label}`));
  }
  assert.equal((body.match(/<th(?:\s|>)/g) || []).length, 10);
});

const alert = (overrides = {}) => ({kind: "unapproved-endpoint-mcp", origin: "endpoint-inventory",
  created_at: "2026-11-01T00:20:00Z", hostname: "work-pc", owner_name: "직원 이름",
  evidence: {endpoint_id: "long-device-uuid", policy_id: "MCP-SHADOW-001", label: "Memory", place: "config-a", channel: "stdio"}, ...overrides});

test("collapsed alerts name the host, user, server/tool and latest timestamp; identifiers stay out of the title", () => {
  const first = alert(), latest = alert({created_at: "2026-11-01T00:22:00Z"});
  const result = String(ui.groupedAlerts([first, latest]));
  const title = /<summary>(.*?)<\/summary>/.exec(result)[1];
  for (const text of ["work-pc", "직원 이름", "Memory", "00:22:00Z", "2건"]) assert.ok(title.includes(text));
  assert.ok(!title.includes("long-device-uuid"));
  const tool = String(ui.groupedAlerts([alert({origin: "endpoint-tool", evidence: {...first.evidence, place: "read_graph"}})]));
  assert.ok(/<summary>.*read_graph.*<\/summary>/.test(tool));
  const escaped = String(ui.groupedAlerts([alert({hostname: "<img>", evidence: {...first.evidence, label: "<script>"}})]));
  assert.ok(!escaped.includes("<img>"));
  assert.ok(!escaped.includes("<script>"));
});

test("alerts with different origins, devices, tools, policies or source evidence never collapse together", () => {
  const base = alert();
  for (const changed of [alert({origin: "endpoint-listener"}),
    ...[{endpoint_id: "other"}, {tool: "other"}, {channel: "https"}, {place: "config-b"}, {policy_id: "other"}, {user_token: "other"}, {checks: [{sha256: "other"}]}]
      .map((e) => alert({evidence: {...base.evidence, ...e}}))]) {
    assert.equal(ui.alertGroups([base, changed]).length, 2);
  }
  assert.equal(ui.alertGroups([base, alert({evidence: {...base.evidence, record_id: "new-report"}})]).length, 1);
  assert.equal(ui.alertGroups([base, alert({reason: "다른 판정 근거"})]).length, 2);
});

test("new labels have English translations", () => {
  for (const label of ["중복 호출 차단", "이용 동의 필요", "사유 미확인", "엔드포인트 식별자", "빈 서버 이름 Enter · Ctrl+C 취소"]) {
    assert.ok(EN[label]);
  }
});
