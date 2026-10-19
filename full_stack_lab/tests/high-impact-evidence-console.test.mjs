import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const safe = source.slice(source.indexOf("class Raw {"), source.indexOf("// ── API"));
const show = source.slice(source.indexOf("async function showApproval"), source.indexOf("let registry ="));

test("evidence history shows escaped display names and a dash when a name is unavailable", async () => {
  let captured;
  const bundle = { explanation: {}, events: [
    {kind: "call-approve", actor: "internal-secret-1", actor_display_name: '<img src=x>심사자'},
    {kind: "call-reject", actor: "internal-secret-2", actor_display_name: null},
    {kind: "call-revoke", actor: "internal-secret-3"},
    {kind: "call-explanation-view", actor: "internal-secret-4", actor_display_name: ""},
  ] };
  const showApproval = runInNewContext(`${safe}
    const approvalRows = [{id: "case", explanation: {}}];
    ${show}
    showApproval;`, {
    gw: async () => bundle, impactExplanation: () => "", when: () => "시각",
    openDrawer: (title, controls, tabs) => { captured = String(tabs.find(t => t.key === "history").body); },
  });
  await showApproval("case");
  assert.ok(captured.includes("&lt;img src=x&gt;심사자"));
  assert.equal((captured.match(/<td>—<\/td>/g) || []).length, 7);
  assert.ok(!captured.includes("internal-secret"));
  assert.ok(!captured.includes("<img"));
});
