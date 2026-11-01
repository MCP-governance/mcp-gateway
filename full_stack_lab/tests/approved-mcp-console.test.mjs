import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { makeTranslator } from "../gateway/app/agent_static/i18n.mjs";
import { EN } from "../gateway/app/agent_static/i18n-en.mjs";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const safe = source.slice(source.indexOf("class Raw {"), source.indexOf("// ── API"));
const table = source.slice(source.indexOf("function approvedMcpTable("), source.indexOf("ROUTES.intake ="));
const ui = runInNewContext(`${safe}
const when = (v) => v || "—", viewer = {kit: true}, location = {origin:"https://console.example"};
const ACTION = {r:"읽기",w:"쓰기",x:"외부전송 및 실행"};
const empty = (v) => html\`<div>\${v}</div>\`;
const chip = (_, label) => html\`<span>\${label}</span>\`;
const kv = (pairs) => html\`<dl>\${pairs.map(([k,v]) => html\`<dt>\${k}</dt><dd>\${v}</dd>\`)}</dl>\`;
let drawer;
const openDrawer = (title,controls,tabs) => {drawer={title,controls,tabs};};
${table}
({render:approvedMcpTable, show(server){showAvailableMcp(server);return drawer;}, address:approvedMcpAddress});`, {URL});
const render = ui.render;
const row = {server_id:"notes",display_name:"Notes",purpose:"문서 검색",source_url:"https://github.com/example/notes",
  commit_sha:"a".repeat(40),valid_until:"2027-01-01T00:00:00+00:00",execution:"pc",source_available:true,connection_url:"/mcp/notes/",
  tools:[{name:"search",action:"r",purpose:"문서 조회",scope_reviewed:true}]};

test("available MCP list prioritizes purpose, tools, expiry and usage over technical provenance", () => {
  const result = String(render([row]));
  for (const value of ["사용 목적","제공 도구","사용 기한","이용 방법",row.purpose,row.valid_until]) assert.ok(result.includes(value), value);
  for (const value of ["고정 커밋",row.commit_sha,row.source_url,"mcp-source-download"]) assert.ok(!result.includes(value), value);
  assert.ok(result.includes('data-act="available-mcp"'));
  const filtered = String(render([row], "missing"));
  assert.match(filtered, /<tr[^>]*hidden/);
  assert.doesNotMatch(String(render([row], "search")), /<tr[^>]*hidden/);
});

test("usage details expose only the gateway address and retain approved tools and source download", () => {
  const detail = ui.show(row);
  assert.deepEqual(Array.from(detail.tabs, (t) => t.key), ["usage","tools","source"]);
  assert.match(String(detail.controls), /available-mcp-copy/);
  assert.match(String(detail.tabs[0].body), /https:\/\/console.example\/mcp\/notes\//);
  assert.match(String(detail.tabs[1].body), /search[^]*읽기[^]*문서 조회[^]*심사 완료/);
  assert.match(String(detail.tabs[2].body), /mcp-source-download[^]*data-commit="a{40}"/);
  const remote = ui.show({...row,execution:"remote",source_available:false,commit_sha:null});
  assert.doesNotMatch(String(remote.tabs[2].body), /mcp-source-download/);
  const reapproval = ui.show({...row,execution:"reapproval"});
  assert.match(String(reapproval.tabs[0].body), /엔드포인트 실행으로 재승인 필요/);
  assert.doesNotMatch(String(reapproval.controls), /available-mcp-copy/);
  assert.match(String(render([{...row,execution:"reapproval"}])), /엔드포인트 실행으로 재승인 필요/);
  assert.equal(ui.address({...row,connection_url:"https://outside.example/mcp/notes/"}), "");
  assert.equal(ui.address({...row,connection_url:"javascript:alert(1)"}), "");
});

test("available MCP values are escaped, missing values use a dash and empty state remains compact", () => {
  const attack = '<img src=x onerror="attack()">';
  const result = String(render([{...row,display_name:attack,purpose:attack,server_id:attack}]));
  assert.ok(!result.includes("<img")); assert.ok(result.includes("&lt;img"));
  assert.ok(!result.includes("style="));
  const detail = ui.show({...row,source_url:attack,tools:[{name:attack,purpose:attack}]});
  assert.ok(!String(detail.tabs.map((t) => t.body)).includes("<img"));
  assert.ok(String(render([{}])).includes("—"));
  assert.match(String(render([])), /사용 가능한 MCP 없음/);
  assert.doesNotMatch(String(render([])), /href=/);
});

test("available MCP labels translate into English", () => {
  const english = makeTranslator(EN).translate;
  for (const label of ["사용 가능한 MCP","사용 가능한 MCP 없음","이용 방법","제공 도구","MCP 주소 복사"]) {
    assert.notEqual(english(label),label); assert.ok(!/[가-힣]/.test(english(label)));
  }
});

// D-262 정정: 직원도 바로가기로 사내 저장소를 읽는다(다운로드는 /auth/gitea가 막는다). 신청 행에는 저장소 링크가 없다.
test("employee navigation shows the internal repository shortcut; intake rows do not link to Gitea", () => {
  const nav = source.slice(source.indexOf("function renderNav("), source.indexOf("function setNavCollapsed("));
  const run = runInNewContext(`${safe}
let output;
const viewer = {admin: false, git_url: "/git/mcp", pages: []};
const PAGES = [], badges = {};
const $ = () => ({set innerHTML(v) {output = v;}});
const sameSite = (v) => v, icon = () => "";
${nav}
renderNav("intake"); output;`);
  assert.ok(run.includes("/git/mcp"));
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
