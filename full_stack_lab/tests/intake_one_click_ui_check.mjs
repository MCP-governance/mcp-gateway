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
  const RISK_TIER = {low:["allow","낮음"],high:["alert","높음"]};
  const VALIDITY = {30:"30일",90:"90일"}; const RISK_CHOICES = {};
  const chip = (tone,label) => html\`<span>\${label}</span>\`;
  const kv = (pairs) => html\`<dl>\${pairs.map(([k,v])=>html\`<dt>\${k}</dt><dd>\${v}</dd>\`)}</dl>\`;
  ${approval}
  globalThis.render = (out) => String(intakeApprovalFields(out));`, context);

const fixture = () => ({ request: { display_name: "문서 검색", purpose: "공개 문서 조회", submitted_by: "직원",
  endpoint_url: "https://example.test/mcp", intake_kind: "remote-endpoint" }, gate: { scanners: [], critical: null },
  proposal: { endpoint: "https://example.test/mcp", purpose: "공개 문서 조회", server_id: "docs-12345678", data_class: "public",
    risk: { tier: "low" }, tools: {lookup:"r"}, catalog: {catalog_hash:"a".repeat(64),version:"1",tools:[{name:"lookup",
      description:'<script>steal()</script>',input_schema:{type:"object"},warnings:[]}]}, supplier_assurance:{},
    parameter_constraints:{lookup:{}},tool_reviews:{lookup:{}},risk_input:{},blockers:[],jurisdiction_pack_enabled:false } });

test("display values are escaped, selected tools default on, optional supplier inputs are not required", () => {
  const rendered = context.render(fixture());
  assert.ok(rendered.includes("&lt;script&gt;steal()&lt;/script&gt;"));
  assert.ok(!rendered.includes("<script>"));
  assert.match(rendered, /name="approved_tool"[^>]*checked/);
  assert.match(rendered, /name="valid_days"/);
  assert.match(rendered, /value="90" selected/);
  assert.ok(!rendered.includes(" required"));
  assert.ok(rendered.includes("추가 정보(선택)"));
  assert.ok(rendered.includes("확인 안 됨"));
});

test("only critical findings ask for a required reason", () => {
  const out = fixture(); out.gate.critical = {count:1};
  assert.match(context.render(out), /name="critical_reason" required minlength="10"/);
  out.gate.critical = null; out.proposal.risk.tier = "high";
  assert.ok(!context.render(out).includes('name="critical_reason"'));
});

test("second administrator sees the frozen scope without editable expiry or supplier fields", () => {
  const out = fixture(); out.pending = {approvers:["admin-a"],scope:{tools:["lookup"],valid_days:90,residency:{},supplier_assurance:{}}};
  const rendered = context.render(out);
  assert.match(rendered, /name="approved_tool"[^>]*disabled/);
  assert.ok(!rendered.includes('name="valid_days"'));
  assert.ok(!rendered.includes('name="assurance_'));
});

test("failed scan prevents submit and a signed bundle can still be loaded", () => {
  const ask = source.slice(source.indexOf("function ask({"), source.indexOf("// ── tabs"));
  let formMarkup = "";
  const dialog = {returnValue:"",showModal(){},addEventListener(){}};
  const form = {set innerHTML(value){formMarkup=value;}};
  const local = vm.createContext({ $: (selector) => selector === "#dialog" ? dialog : form });
  vm.runInContext(`${safeHTML}\n${ask}\nask({title:"승인",disabled:true,reject:true,load:true});`, local);
  assert.match(formMarkup, /value="ok" disabled/);
  assert.match(formMarkup, /value="reject"/);
  assert.match(formMarkup, /value="load"/);
});

test("repository proposal shows a draft and optional signed bundle without pretending it is verified", () => {
  const out = fixture(); out.request.intake_kind="repository"; out.proposal.local_draft={image:"확인 안 됨"};
  out.proposal.endpoint=""; out.proposal.catalog=null; out.proposal.tools={};
  const rendered=context.render(out);
  assert.ok(rendered.includes("PC 격리 실행"));
  assert.ok(rendered.includes("매니페스트 제안값"));
  assert.match(rendered,/name="local_bundle"/);
});

test("intake form uses a data grade and tools rather than six risk questions", () => {
  const form=source.slice(source.indexOf('data-form="intake"'),source.indexOf('const TRANSPORT ='));
  assert.ok(form.includes('field.select("data_class"'));
  assert.ok(form.includes("data-requested-tools"));
  assert.ok(!form.includes("riskFields()"));
  assert.ok(!form.includes("???"));
});
