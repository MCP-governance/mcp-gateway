import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const safeHTML = source.slice(source.indexOf("class Raw {"), source.indexOf("const short = "));
const fields = source.slice(source.indexOf("const field = {"), source.indexOf("function scopeFields("));
const approval = source.slice(source.indexOf("const ASSURANCE_LABELS = "), source.indexOf("async function showIntakeApproval("));
const context = vm.createContext({ URL });
vm.runInContext(`${safeHTML}\n${fields}\n
  const DATA_CLASS = {public:"공개",nonimportant:"내부",important:"중요"};
  const ACTION = {r:"읽기",w:"쓰기",x:"실행"};
  const RISK_TIER = {low:["allow","낮음"],high:["alert","높음"],very_high:["block","매우 높음"]};
  const VALIDITY = {30:"30일",90:"90일"}; const RISK_CHOICES = {};
  const chip = (tone,label) => html\`<span>\${label}</span>\`;
  const kv = (pairs) => html\`<dl>\${pairs.map(([k,v])=>html\`<dt>\${k}</dt><dd>\${v}</dd>\`)}</dl>\`;
  ${approval}
  globalThis.render = (out) => String(intakeApprovalFields(out));`, context);

const fixture = (tier) => ({ request: { display_name: "문서 검색", submitted_by: "직원", endpoint_url: "https://example.test/mcp",
  intake_kind: "remote-endpoint" }, gate: { scanners: [], critical: null },
  proposal: { endpoint: "https://example.test/mcp", purpose: "공개 문서 조회", server_id: "docs-12345678", data_class: "public",
    risk: { tier }, tools: { lookup: "r" }, catalog: { catalog_hash: "a".repeat(64), version: "1", tools: [{ name: "lookup",
      description: "조회", input_schema: { type: "object" }, warnings: [] }] }, supplier_assurance: {},
    parameter_constraints: { lookup: {} }, tool_reviews: { lookup: {} }, risk_input: {}, blockers: [], jurisdiction_pack_enabled: false } });

test("only the very high tier asks for the written reason, and the second administrator is asked too", () => {
  assert.match(context.render(fixture("very_high")), /name="risk_reason" required minlength="10"/);
  const second = fixture("very_high");
  second.pending = { approvers: ["admin-a"], scope: { tools: ["lookup"], valid_days: 90, residency: {}, supplier_assurance: {} } };
  assert.match(context.render(second), /name="risk_reason" required minlength="10"/);
  for (const tier of ["low", "high"]) assert.ok(!context.render(fixture(tier)).includes('name="risk_reason"'));
});

test("the approval request carries the reason", () => {
  assert.ok(source.includes('risk_reason: String(fd.get("risk_reason") || "").trim()'));
});
