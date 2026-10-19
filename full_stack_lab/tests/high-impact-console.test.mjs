import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const safe = source.slice(source.indexOf("class Raw {"), source.indexOf("// ── API"));
const explanation = source.slice(source.indexOf("const IMPACT_DOMAIN ="), source.indexOf("async function showApproval"));
const fields = source.slice(source.indexOf("const field ="), source.indexOf("const ACTIONS ="));
const api = runInNewContext(`${safe}
const DATA_CLASS = {public: "공개", nonimportant: "일반"};
const ACTION = {w: "쓰기"}; const DECISION = {Allow: ["allow", "허용"]};
const kv = (rows) => html\`<dl>\${rows.map(([k, v]) => html\`<dt>\${k}</dt><dd>\${v ?? "—"}</dd>\`)}</dl>\`;
${explanation}
${fields}
({collectScopes, scopeFields, impactExplanation});`);

test("new reviews default to no impact and per-tool domains override the common choice", () => {
  const fd = new Map([["scope_purpose", "자료 검토 목적"], ["scope_asset", "자료"]]);
  assert.equal(api.collectScopes(fd, ["read"]).read.high_impact, false);
  fd.set("scope_impact", "employment"); fd.set("impact:read", "none"); fd.set("impact:write", "credit");
  const rows = api.collectScopes(fd, ["read", "write", "other"]);
  assert.equal(rows.read.high_impact, false);
  assert.equal(rows.write.impact_domains.join(), "credit");
  assert.equal(rows.other.impact_domains.join(), "employment");
});

test("review form shows Korean domains and escapes tool names", () => {
  const rendered = String(api.scopeFields(['<img src=x onerror="attack()">']));
  for (const label of ["중대 영향", "고용·급여", "신용", "법적 효력", "급부", "계약", "서비스 접근"]) assert.ok(rendered.includes(label));
  assert.ok(rendered.includes("&lt;img")); assert.ok(!rendered.includes("<img"));
});

test("explanations show argument categories and policy grounds without raw enum values", () => {
  const e = {summary: "중대 영향 도구 호출", impact_domains: ["employment"], server_id: '<img src=x>', tool: "update",
    arguments: {object: 1, string: 2}, data_class: "public", action: "w", policy_id: "P-HIGH-IMPACT-001",
    basis_policy_id: "P-AUTHZ-ALLOW-001", basis_decision: "Allow"};
  const rendered = String(api.impactExplanation(e));
  for (const label of ["고용·급여", "객체 1", "문자 2", "공개", "쓰기", "선행 정책", "기존 실행 효과 복구", "미지원"]) assert.ok(rendered.includes(label));
  for (const raw of ["employment", "object", "string", "Allow", "<img"]) assert.ok(!rendered.includes(raw));
});
