import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { makeTranslator } from "../gateway/app/agent_static/i18n.mjs";
import { EN } from "../gateway/app/agent_static/i18n-en.mjs";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const safe = source.slice(source.indexOf("class Raw {"), source.indexOf("// ── API"));
const table = source.slice(source.indexOf("function approvedMcpTable("), source.indexOf("ROUTES.intake ="));
const render = runInNewContext(`${safe}
const when = (v) => v || "—";
const empty = (v) => html\`<div>\${v}</div>\`;
${table}
approvedMcpTable;`);
const row = { server_id: "notes", display_name: "Notes", source_url: "https://github.com/example/notes",
  commit_sha: "a".repeat(40), valid_until: "2027-01-01T00:00:00+00:00", execution: "pc",
  source_available: true, connection_url: "/mcp/notes/" };

test("approved sources show their fixed commit, expiry, mode and download action", () => {
  const result = String(render([row]));
  for (const value of ["출처", "고정 커밋", "승인 기한", "실행 방식", "PC 격리", "소스 받기", row.source_url, row.commit_sha, row.valid_until]) {
    assert.ok(result.includes(value), value);
  }
  assert.ok(result.includes('data-act="mcp-source-download"'));
  assert.ok(result.includes(`data-commit="${row.commit_sha}"`));
  assert.ok(!result.includes("/git/"));
});

test("remote services have connection information and no source action", () => {
  const result = String(render([{ ...row, execution: "remote", source_available: false, commit_sha: null }]));
  for (const value of ["원격", "MCP 주소", "/mcp/notes/", "—"]) assert.ok(result.includes(value));
  assert.ok(!result.includes("mcp-source-download"));
  assert.ok(!result.includes("<button"));
  assert.ok(String(render([{ ...row, execution: "runtime" }])).includes("솔루션 런타임"));
});

test("approved source values are escaped, missing values use a dash and the empty state has no action", () => {
  const attack = '<img src=x onerror="attack()">';
  const result = String(render([{ ...row, display_name: attack, server_id: attack, source_url: attack, commit_sha: attack }]));
  assert.ok(!result.includes("<img"));
  assert.ok(result.includes("&lt;img"));
  assert.ok(!result.includes("style="));
  assert.ok(String(render([{ execution: "new-mode" }])).includes("—"));
  assert.ok(!String(render([])).includes("<button"));
});

test("approved source labels translate into English", () => {
  const english = makeTranslator(EN).translate;
  for (const label of ["승인된 MCP", "승인된 MCP 없음", "고정 커밋", "승인 기한", "실행 방식", "원격", "PC 격리", "솔루션 런타임", "소스 받기", "소스 다운로드"]) {
    assert.notEqual(english(label), label);
    assert.ok(!/[가-힣]/.test(english(label)));
  }
});

test("employee navigation and intake rows do not link to Gitea", () => {
  const nav = source.slice(source.indexOf("function renderNav("), source.indexOf("function setNavCollapsed("));
  const run = runInNewContext(`${safe}
let output;
const viewer = {admin: false, git_url: "/git/mcp", pages: []};
const PAGES = [], badges = {};
const $ = () => ({set innerHTML(v) {output = v;}});
const sameSite = (v) => v, icon = () => "";
${nav}
renderNav("intake"); output;`);
  assert.ok(!run.includes("/git/"));
  const catalog = source.slice(source.indexOf("function catalogResults("), source.indexOf("const CONSENT_STATUS ="));
  const result = runInNewContext(`${safe}
const viewer = {admin: false}, NONE = "—", INTAKE_STATUS = {APPROVED: ["", "승인"]};
const chip = (_, label) => label, sameSite = (v) => v;
const empty = (v) => v;
${catalog}
String(catalogResults({requests: [{status: "APPROVED", internal_repo_url: "/git/mcp/notes"}]}));`);
  assert.ok(!result.includes("/git/"));
  assert.ok(source.includes('viewer.admin && r.internal_repo_url ? html`<a'));
});

test("source download uses the console route, bearer header and fixed filename", async () => {
  const action = source.slice(source.indexOf('  async "mcp-source-download"('), source.indexOf('  async "intake-download"('));
  const calls = [], links = [];
  const actions = runInNewContext(`const token = "console-only";
const URL = {createObjectURL: () => "blob:source", revokeObjectURL() {}};
const document = {createElement: () => ({click() {}})};
const fetch = async (path, options) => { calls.push({path, options}); return {ok: true, blob: async () => "source"}; };
const Object = {assign: (a, b) => { links.push(b); return globalObject.assign(a, b); }};
({${action}});`, { calls, links, globalObject: Object, setTimeout: (fn) => fn() });
  await actions["mcp-source-download"]({ dataset: { id: "notes/path", commit: row.commit_sha } });
  assert.equal(calls[0].path, `/api/approved-mcp/notes%2Fpath/source?commit=${row.commit_sha}`);
  assert.equal(calls[0].options.headers.authorization, "Bearer console-only");
  assert.equal(links[0].download, `notes/path-${"a".repeat(12)}.zip`);
});
