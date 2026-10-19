import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const safeHtml = source.slice(source.indexOf("class Raw {"), source.indexOf("// ── API"));
const render = source.slice(source.indexOf("const OUTCOME_LABELS ="), source.indexOf("const decisionTable ="));
const chips = runInNewContext(`${safeHtml}
const chip = (tone, value) => html\`<span class="chip \${tone}">\${value}</span>\`;
${render}
outcomeChips;`);

test("outcome labels and Korean values remain separate and missing data is a dash", () => {
  const rendered = String(chips({connection: "연결 성공", decision: "허용", task: "제공자 한도 초과", effect: "미확인"}));
  for (const label of ["연결", "정책 판정", "도구 업무", "독립 효과", "제공자 한도 초과"]) assert.ok(rendered.includes(label));
  assert.equal((String(chips(null)).match(/—/g) || []).length, 4);
});

test("outcome text always uses the production HTML escaping", () => {
  const rendered = String(chips({task: '<img src=x onerror="attack()">'}));
  assert.ok(rendered.includes("&lt;img"));
  assert.ok(!rendered.includes("<img"));
});
