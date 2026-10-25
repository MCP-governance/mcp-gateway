import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const safeHTML = source.slice(source.indexOf("class Raw {"), source.indexOf("const short = "));
const fields = source.slice(source.indexOf("const field = {"), source.indexOf("function scopeFields("));
const audience = source.slice(source.indexOf("const AUDIENCE = "), source.indexOf("function validityChip("));
const approval = source.slice(source.indexOf("const ASSURANCE_LABELS = "), source.indexOf("async function showIntakeApproval("));
const context = vm.createContext({ URL });
vm.runInContext(`${safeHTML}\n${fields}\n
  const DATA_CLASS = {public:"공개",nonimportant:"내부",important:"중요"};
  const ACTION = {r:"읽기",w:"쓰기",x:"실행"};
  const RISK_TIER = {low:["allow","낮음"],high:["alert","높음"],very_high:["block","매우 높음"]};
  const VALIDITY = {30:"30일",90:"90일"}; const RISK_CHOICES = {};
  const chip = (tone,label) => html\`<span>\${label}</span>\`;
  const kv = (pairs) => html\`<dl>\${pairs.map(([k,v])=>html\`<dt>\${k}</dt><dd>\${v}</dd>\`)}</dl>\`;
  const NONE = "—"; ${audience}
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

// D-189 추가 판단 2·3: 근거 없는 신청은 보류로 보이고, 받지 못한 공급자 항목은 「확인 안 됨」으로 보인다.
const risky = source.slice(source.indexOf("function riskCell("), source.indexOf("const supportStatus"));
const shown = source.slice(source.indexOf("const supportStatus"), source.indexOf("const ASSURANCE_LABELS"))
  + source.slice(source.indexOf("const UNCONFIRMED"), source.indexOf("function intakeApprovalFields("));
const list = vm.createContext({ URL, viewer: { admin: true } });
vm.runInContext(`${safeHTML}
  const NONE = html\`<span>—</span>\`; const RISK_TIER = {low:["allow","낮음"],high:["alert","높음"]};
  const chip = (tone,label) => html\`<span>\${label}</span>\`;
  const kv = (pairs) => html\`<dl>\${pairs.filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k,v])=>html\`<dt>\${k}</dt><dd>\${v}</dd>\`)}</dl>\`;
  const empty = (t) => html\`<p>\${t}</p>\`; const panel = (t, b) => b;
  ${risky}\n${shown}
  globalThis.cell = (r) => String(riskCell(r)); globalThis.view = (r) => String(riskView(r));
  globalThis.rows = (a) => String(kv(assuranceRows(a)));`, list);

test("a request without a stated input or proposal shows a hold, never a tier or a count", () => {
  const hold = { status: "HOLD", risk: { status: "hold", tier: null, score: null, missing: [], required: null, approvals: 0 } };
  assert.equal(list.cell(hold), "<span>보류</span><span class=\"sub\">승인 —</span>");
  assert.ok(!list.cell({ ...hold, status: "APPROVED" }).includes("승인"));
  assert.ok(!list.cell(hold).includes("입력 필요"));
  assert.ok(list.view(hold.risk).includes("보류"));
  assert.ok(list.view(hold.risk).includes("산정 점수</dt><dd>—"));
});

test("supplier items that were not received read 확인 안 됨, never blank, undefined or a claim", () => {
  const empty = list.rows({});
  assert.equal(empty.split("확인 안 됨").length - 1, 10);
  assert.ok(!empty.includes("undefined") && !empty.includes("<a "));
  const partial = list.rows({ legal_entity: "예시 주식회사", vex_submitted: false, subprocessors: "미확인" });
  assert.ok(partial.includes("예시 주식회사") && partial.includes("미제출"));
  assert.equal(partial.split("확인 안 됨").length - 1, 8);
});
