import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import * as state from "../gateway/app/agent_static/console-state.mjs";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const service = readFileSync(new URL("../gateway/app/agent_service.py", import.meta.url), "utf8");
const adminPages = ["overview", "approvals", "activity", "servers", "people", "policy", "intake", "termination", "connections"];
const employeePages = ["activity", "consent", "intake", "connections"];
const code = source.slice(0, source.indexOf("// ── wiring")).replace(/^import[\s\S]*?;\r?\n/gm, "");

function build(admin = true, extra = {}) {
  const calls = [], timers = new Map(), elements = new Map();
  const inventory = { agents: [], entries: [], listeners: [], os_events: [], managed_events: [],
    coverage: { reporting_recently: 0 }, settings: {},
    pages: Object.fromEntries(["entries", "listeners", "os_events"].map((key) => [key, { total: 0, limit: 50, next_cursor: null }])) };
  const responses = {
    "/api/consents": { consents: [] }, "/approvals": { approvals: [], history: [] }, "/gw/dispatch-intents": { rows: [] },
    "/gw/registry": { servers: [], tools: [], registrations: {} },
    "/gw/overview": { servers: [], workstations: [], pending_approvals: 2, termination: {} },
    "/api/integrations": { items: [], devices: [], summary: { devices: { bypass_possible: 0 } } },
    "/api/connectors": { items: [], summary: { pending: 3, expired: 1 } },
    "/api/connectors?summary=1": { summary: { pending: 3, expired: 1 } },
    "/gw/endpoint/inventory": inventory,
    "/gw/endpoint/inventory?classification=shadow,retired-residue": inventory,
    "/api/accounts": { accounts: [] }, "/api/accounts/deleted": { accounts: [] }, "/api/signup-requests": { requests: [] },
    "/api/identity": { provider: "local", bindings: [] }, "/gw/suspensions": { suspensions: [] },
    "/api/mcp-requests": { requests: [] }, "/api/approved-mcp": { servers: [] },
    "/api/mcp-catalog/search": { requests: [], registry: [] },
    "/gw/audit/siem": { pending: 1, retrying: 0 }, "/gw/audit/incidents": { incidents: [], timer_status: "정상" },
    ...extra,
  };
  const node = (key) => {
    if (!elements.has(key)) elements.set(key, { innerHTML: "", textContent: "", dataset: {},
      classList: { contains: () => false }, querySelector: () => null, querySelectorAll: () => [], focus() {} });
    return elements.get(key);
  };
  const context = vm.createContext({ ...state, URLSearchParams, FormData, encodeURIComponent, decodeURIComponent,
    lang: () => "ko", locale: () => "ko-KR", t: (v) => v,
    clockText: () => "12:00", dateTimeText: () => "10-27 12:00",
    localStorage: { getItem: () => "fixture-token" }, location: { hash: "#/activity", replace() {} },
    document: { hidden: false, querySelector: node },
    charts: { DECISION_LABEL: {}, register() {}, mountVisible() {}, disposeAll() {} },
    setInterval(fn) { const id = timers.size + 1; timers.set(id, fn); return id; },
    clearInterval(id) { timers.delete(id); },
    fetch: async (url) => {
      calls.push(url);
      let value = responses[url];
      if (value === undefined && url.startsWith("/gw/activity/analysis?")) value = { total: 0 };
      if (value === undefined && url.startsWith("/gw/activity?")) value = { rows: [], total: 0, cursor: 0 };
      if (value === undefined && url.startsWith("/gw/audit/events?")) value = { events: [], has_more: false };
      assert.notEqual(value, undefined, `unexpected request: ${url}`);
      if (value instanceof Error) throw value;
      return { ok: true, status: 200, headers: { get: () => null }, json: async () => value };
    },
  });
  vm.runInContext(`${code}\nviewer = ${JSON.stringify({ admin, pages: admin ? adminPages : employeePages })};
    globalThis.ui = { ROUTES, canonicalRoute, renderNav, refreshBadges, covPage, covPaging, badges, ACTIONS,
      stopLive, stopIntake, setCurrent(value) { current = value; }, pageModel(fn) { page = fn; },
      activityHooks(render, start) { renderFeed = render; startLive = start; },
      refreshHook(fn) { refreshIntake = fn; } };`, context);
  context.ui.pageModel((value) => value);
  return { ...context.ui, context, calls, timers, responses, inventory, node };
}

test("관리자는 확정된 9개 메뉴를 순서대로, 직원·협력사는 기존 4개를 본다", () => {
  const roles = service.slice(service.indexOf("PAGES_BY_ROLE ="), service.indexOf("ROLE_LABELS ="));
  const ids = (role) => [...roles.match(new RegExp(`"${role}": \\(([^)]+)\\)`))[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(ids("admin"), adminPages);
  for (const role of ["employee", "partner"]) assert.deepEqual(ids(role), employeePages);
  for (const admin of [true, false]) {
    const ui = build(admin); ui.renderNav("activity");
    const markup = ui.node("#nav").innerHTML;
    assert.deepEqual([...markup.matchAll(/href="#\/([\w-]+)"/g)].map((m) => m[1]), admin ? adminPages : employeePages);
    assert.match(markup, admin ? /호출·감사 기록/ : /호출 기록/);
  }
});

test("승인 배지는 승인과 동의 합계, MCP 서버 배지는 커넥터 검토 건수", async () => {
  const ui = build(true, { "/api/consents": { consents: [
    { status: "PENDING", server_id: "a" }, { status: "PENDING", server_id: "a" },
    { status: "PENDING", server_id: "b" }, { status: "GRANTED", server_id: "c" }] } });
  await ui.refreshBadges();
  const nav = ui.node("#nav").innerHTML;
  assert.match(nav, /href="#\/approvals"[^]*?<span class="count">4<\/span>/);
  assert.match(nav, /href="#\/servers"[^]*?<span class="count">4<\/span>/);
  assert.doesNotMatch(nav, /href="#\/consent"/);
});

test("옛 주소 네 종류와 세부 탭·필터를 새 위치로 보낸다", () => {
  const ui = build();
  for (const [page, tab, target, nextTab] of [
    ["audit", "", "activity", "events"], ["audit", "incidents", "activity", "incidents"],
    ["audit", "siem", "activity", "siem"], ["coverage", "", "servers", "items"],
    ["coverage", "devices", "people", "devices"], ["coverage", "shadow", "servers", "shadow"],
    ["coverage", "vendor", "servers", "vendor"], ["sbom-impact", "", "intake", "impact"],
    ["consent", "history", "approvals", "consent"],
  ]) {
    const at = { page, arg: "", query: new URLSearchParams({ t: tab, q: "a & b", before: "42" }) };
    const out = ui.canonicalRoute(at);
    assert.equal(out.page, target); assert.equal(out.query.get("t"), nextTab);
    assert.equal(out.query.get("q"), "a & b"); assert.equal(out.query.get("before"), "42");
    assert.equal(at.query.get("t"), tab);
  }
  for (const page of ["activity", "toString", "__proto__"]) {
    const at = { page, query: new URLSearchParams() }; assert.equal(ui.canonicalRoute(at), at);
  }
  const consent = { page: "consent", query: new URLSearchParams("t=history") };
  assert.equal(build(false).canonicalRoute(consent), consent);
  assert.doesNotMatch(source, /#\/(?:audit|coverage|sbom-impact)(?:[?"`/])/);
});

test("직원에게 감사·동의 관리·공급망 탭과 관리자 조회를 추가하지 않는다", async () => {
  const ui = build(false);
  const activity = await ui.ROUTES.activity("", "events", new URLSearchParams("t=events"));
  assert.deepEqual(Array.from(activity.html.tabs, (item) => item.key), ["live", "stats"]);
  const intake = await ui.ROUTES.intake("", "impact");
  assert.deepEqual(Array.from(intake.html.tabs, (item) => item.key), ["list", "approved", "new"]);
  const consent = await ui.ROUTES.consent("", "history");
  assert.deepEqual(Array.from(consent.tabs, (item) => item.key), ["pending", "history"]);
  assert.ok(ui.calls.every((path) => !/audit|supply-chain|integrations|approvals/.test(path)));
});

test("관리자 통합 탭은 기존 데이터와 필터·작업 버튼을 유지한다", async () => {
  const ui = build(true, { "/api/supply-chain/impact": { counts: { affected: 1, unaffected: 0, unknown: 0, no_data: 0 } } });
  const activity = await ui.ROUTES.activity("", "events", new URLSearchParams("t=events&principal=alice&before=12"));
  assert.deepEqual(Array.from(activity.html.tabs, (item) => item.key), ["live", "stats", "events", "incidents", "siem"]);
  assert.match(String(activity.html.tabs[2].body), /audit-verify[^]*audit-export/);
  assert.ok(ui.calls.includes("/gw/audit/events?principal=alice&before=12&limit=100"));
  let rendered = 0, live = 0;
  ui.activityHooks(() => rendered++, () => live++); activity.after();
  assert.equal(rendered, 1); assert.equal(live, 1);
  const approvals = await ui.ROUTES.approvals("", "consent");
  assert.deepEqual(Array.from(approvals.html.tabs, (item) => item.key), ["queue", "unsent", "history", "consent"]);
  assert.match(String(approvals.html.tabs[3].body), /확인할 요청 없음[^]*동의 기록/);
  const servers = await ui.ROUTES.servers("", "shadow", new URLSearchParams());
  assert.deepEqual(Array.from(servers.html.tabs, (item) => item.key), ["servers", "tools", "contract", "items", "shadow", "vendor"]);
  assert.doesNotMatch(String(servers.html.head), /통제 범위/);
  const people = await ui.ROUTES.people("", "devices");
  const devices = people.html.tabs.find((item) => item.key === "devices");
  assert.match(String(devices.body), /새 PC 활성화[^]*통제 점검[^]*엔드포인트 MCP 설정/);
  const intake = await ui.ROUTES.intake("", "impact", new URLSearchParams("package=alpha&range=%3E%3D1.0.0"));
  assert.equal(intake.html.tabs.at(-1).key, "impact");
  assert.match(String(intake.html.tabs.at(-1).body), /value="alpha"[^]*sbom-impact-stop/);
});

test("MCP 설정 다음 페이지는 사용자 화면의 전체 범위와 서버의 미등록 범위를 보존한다", async () => {
  const ui = build();
  ui.covPaging.entries.index = 1; ui.covPaging.entries.cursors.push("cursor-2");
  ui.responses["/gw/endpoint/inventory/entries?limit=50&cursor=cursor-2"] = { rows: [], next_cursor: null };
  ui.responses["/gw/endpoint/inventory/entries?limit=50&cursor=cursor-2&classification=shadow%2Cretired-residue"] = { rows: [], next_cursor: null };
  await ui.covPage(ui.inventory, "entries", ""); await ui.covPage(ui.inventory, "entries");
  assert.equal(ui.calls.length, 2);
  assert.ok(!ui.calls[0].includes("classification")); assert.match(ui.calls[1], /classification=shadow%2Cretired-residue/);
});

test("도입 신청 타이머는 기존 탭에서 갱신하고 공급망 폼·새 신청은 보존한다", async () => {
  const ui = build(); let refreshed = 0;
  ui.refreshHook(async () => { refreshed++; });
  const intake = await ui.ROUTES.intake("", "list"); intake.after();
  const tick = [...ui.timers.values()][0];
  for (const tab of ["list", "approved", "impact", "new"]) {
    ui.context.location.hash = `#/intake?t=${tab}`; tick();
  }
  assert.equal(refreshed, 2);
  ui.stopIntake(); assert.equal(ui.timers.size, 0);
});

test("감사 데이터 조회 실패를 정상 빈 목록으로 숨기지 않는다", async () => {
  const ui = build(true, { "/gw/audit/siem": new Error("관제 조회 실패") });
  await assert.rejects(ui.ROUTES.activity("", "siem", new URLSearchParams()), /관제 조회 실패/);
});
