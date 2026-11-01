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
    "/gw/policy/ledger": { policies: [] },
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
    document: { hidden: false, querySelector: node, querySelectorAll: () => [] },
    charts: { DECISION_LABEL: {}, register() {}, mountVisible() {}, disposeAll() {}, redraw() {} },
    setInterval(fn) { const id = timers.size + 1; timers.set(id, fn); return id; },
    clearInterval(id) { timers.delete(id); },
    fetch: async (url) => {
      calls.push(url);
      let value = responses[url];
      if (value === undefined && url.startsWith("/gw/activity/analysis?")) value = { total: 0 };
      if (value === undefined && url.startsWith("/gw/activity?")) value = { rows: [], total: 0, cursor: 0 };
      if (value === undefined && url.startsWith("/gw/audit/events?")) value = { events: [], has_more: false };
      if (value === undefined && url.startsWith("/gw/audit/alerts?")) value = { alerts: [], last_24h: 0 };
      if (value === undefined && url.startsWith("/gw/endpoint/tool-events?")) value = { rows: [], total: 0 };
      if (value === undefined && url === "/gw/endpoint/requests") value = { requests: [] };
      assert.notEqual(value, undefined, `unexpected request: ${url}`);
      if (value instanceof Error) throw value;
      return { ok: true, status: 200, headers: { get: () => null }, json: async () => value };
    },
  });
  vm.runInContext(`${code}\nviewer = ${JSON.stringify({ admin, pages: admin ? adminPages : employeePages })};
    globalThis.ui = { ROUTES, canonicalRoute, renderNav, refreshBadges, covPage, covPaging, badges, ACTIONS,
      validityChip, empty, renderFeed, renderFeedStatus, policyLabel, catalogResults,
      setFeed(value) { Object.assign(feed, value); },
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
  assert.deepEqual(Array.from(activity.html.tabs, (item) => item.key), ["live", "stats", "events", "alerts", "tools", "incidents", "siem"]);
  assert.match(String(activity.html.tabs[2].body), /audit-verify[^]*audit-export/);
  assert.ok(ui.calls.includes("/gw/audit/events?principal=alice&before=12&limit=100"));
  let rendered = 0, live = 0;
  ui.activityHooks(() => rendered++, () => live++); activity.after();
  assert.equal(rendered, 1); assert.equal(live, 1);
  const approvals = await ui.ROUTES.approvals("", "consent");
  assert.deepEqual(Array.from(approvals.html.tabs, (item) => item.key), ["queue", "unsent", "history", "consent"]);
  assert.match(String(approvals.html.tabs[3].body), /확인할 요청 없음[^]*동의 기록/);
  const servers = await ui.ROUTES.servers("", "shadow", new URLSearchParams());
  assert.deepEqual(Array.from(servers.html.tabs, (item) => item.key), ["servers", "vendor", "shadow", "tools", "contract", "items"]);
  assert.doesNotMatch(String(servers.html.tabs[1].body), /하네스 기능/);
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

test("새 신청이 검색보다 먼저이며 직행 값과 첫 필드 포커스를 보존한다", async () => {
  for (const source of ["https://github.com/org/repo", "https://example.test/mcp"]) {
    const ui = build();
    const query = new URLSearchParams({ name: '<서버 "A">', purpose: "공개 문서 검색 목적", source, asked: "request-1" });
    const out = await ui.ROUTES.intake("", "new", query);
    const markup = String(out.html.tabs.find((item) => item.key === "new").body);
    assert.ok(markup.indexOf('data-form="intake"') < markup.indexOf("<details"));
    assert.match(markup, /<details class="panel"><summary>기존 신청 검색<\/summary>/);
    assert.doesNotMatch(markup, /<details[^>]*\bopen\b/);
    assert.match(markup, /name="display_name"[^>]*value="&lt;서버 &quot;A&quot;&gt;"/);
    assert.match(markup, /공개 문서 검색 목적/);
    assert.match(markup, /name="endpoint_request_id" value="request-1"/);
    const addressField = source.includes("github.com") ? "repository_url" : "endpoint_url";
    assert.ok(markup.includes(`name="${addressField}" type="url" maxlength="${addressField === "repository_url" ? 300 : 500}" placeholder="${addressField === "repository_url" ? "https://github.com/org/repo" : "https://…/mcp"}" value="${source}"`));
    assert.match(markup, /value="streamable-http"[^>]*>웹 연결/);
    assert.match(markup, /value="stdio"[^>]*>프로세스 연결/);
    assert.match(markup, /value="sse"[^>]*>이벤트 스트림/);
    let focused = 0;
    ui.node('[data-form="intake"] [name="display_name"]').focus = () => focused++;
    out.after(); assert.equal(focused, 1); ui.stopIntake();
  }
});

const overviewData = { servers: [], workstations: [], execution: {}, flows: [], series: [], top_policies: [], termination: {} };
test("처리할 일이 그래프보다 먼저이며 각 건수와 목적지가 일치한다", async () => {
  const ui = build(true, {
    "/gw/overview": { ...overviewData, pending_approvals: 0, endpoint_requests: 3 },
    "/gw/dispatch-intents": { rows: [{}, {}] },
    "/api/consents": { consents: [{ status: "PENDING", server_id: "a" }, { status: "PENDING", server_id: "a" }, { status: "GRANTED", server_id: "b" }] },
  });
  const markup = String((await ui.ROUTES.overview()).html.tabs[0].body);
  assert.ok(markup.indexOf("처리할 일") < markup.indexOf("시간대별 판정"));
  for (const [label, count, href] of [["승인 요청", 0, "#/approvals"], ["실행 확인", 2, "#/approvals?t=unsent"], ["이용 동의", 1, "#/approvals?t=consent"], ["엔드포인트 도입 요청", 3, "#/intake?t=requests"]]) {
    assert.ok(markup.includes(`href="${href}"><span>${label}</span><b class="n ${count > 0 ? "hot" : ""}">${count}</b>`));
  }
});

test("조회 실패와 누락된 대시보드 값은 0건이 되지 않는다", async () => {
  const ui = build(true, { "/gw/overview": overviewData, "/gw/dispatch-intents": new Error("실패"),
    "/api/consents": new Error("실패"), "/gw/audit/alerts?limit=6": new Error("실패") });
  const out = (await ui.ROUTES.overview()).html;
  const markup = String(out.tabs[0].body);
  for (const label of ["승인 요청", "실행 확인", "이용 동의", "엔드포인트 도입 요청"]) {
    assert.ok(markup.includes(`<span>${label}</span><b class="n ">—</b>`));
  }
  assert.match(markup, /role="alert">조회 실패/);
  assert.doesNotMatch(markup, /경보 없음/);
  assert.match(String(out.kpis), /24시간 경보<\/div><div class="value">—<\/div>/);
});

test("사용 기한은 실제 날짜로 계산하고 없거나 잘못된 날짜는 대시로 보인다", () => {
  const ui = build();
  vm.runInContext("Date.now = () => 1800000000000", ui.context);
  const at = (offset) => ({ valid_until: new Date(1800000000000 + offset).toISOString() });
  assert.match(String(ui.validityChip(at(90 * 86400000))), />90일 남음</);
  assert.match(String(ui.validityChip(at(1))), />1일 남음</);
  for (const value of [at(0), at(-1), { ...at(-86400000), risk_review: true }]) assert.match(String(ui.validityChip(value)), />만료</);
  for (const value of [null, {}, { valid_until: "invalid" }]) assert.equal(String(ui.validityChip(value)).replace(/<[^>]*>/g, ""), "—");
});

test("미등록 MCP는 혼합 합계 없이 설정·수신기·차단 건수를 분리한다", async () => {
  const ui = build();
  Object.assign(ui.inventory.pages.entries, { total: 7 });
  Object.assign(ui.inventory.pages.listeners, { total: 3 });
  Object.assign(ui.inventory.pages.os_events, { total: 0 });
  const shadow = (await ui.ROUTES.servers("", "shadow", new URLSearchParams())).html.tabs.find((item) => item.key === "shadow");
  assert.equal(shadow.n, undefined);
  const markup = String(shadow.body);
  for (const [label, value] of [["설정 기록", 7], ["수신기 관측", 3], ["엔드포인트 차단", 0]]) assert.ok(markup.includes(`<dt>${label}</dt><dd>${value}</dd>`));
  assert.match(markup, /표시 서버 0개/);
  const items = (await ui.ROUTES.servers("", "items", new URLSearchParams())).html.tabs.find((item) => item.key === "items");
  assert.match(String(items.body), /항목 없음/);
  const filtered = (await ui.ROUTES.servers("", "items", new URLSearchParams("q=missing"))).html.tabs.find((item) => item.key === "items");
  assert.match(String(filtered.body), /조건에 맞는 결과 없음/);
});

test("도구 출력 크기·정책 판정·업무 결과를 분리하고 경보 표시 범위를 밝힌다", async () => {
  const ui = build(true, {
    "/gw/policy/ledger": { policies: [{ policy_id: "P-ALLOW", name: "승인 범위 허용" }] },
    "/gw/audit/alerts?limit=200": { alerts: [{ created_at: "2020-01-01", kind: "policy-self-test-failed", evidence: { policy_id: "P-ALLOW" } }], last_24h: 0 },
    "/gw/endpoint/tool-events?limit=100": { total: 3, rows: [
      { decision: "Allow", policy_id: "P-ALLOW", failed: true, input_bytes: 0, output_bytes: 4096 },
      { decision: "Allow", failed: false, output_bytes: 0 },
      { failed: false, outcome_axes: { task: "<未確認>" } },
    ] },
  });
  const out = (await ui.ROUTES.activity("", "tools", new URLSearchParams())).html;
  const tools = String(out.tabs.find((item) => item.key === "tools").body);
  assert.match(tools, /<th>게이트웨이 판정<\/th><th>도구 업무<\/th>/);
  assert.match(tools, /<th class="num">출력 크기<\/th>/);
  assert.match(tools, /승인 범위 허용/);
  assert.match(tools, /도구 오류/);
  assert.match(tools, /4\.0 KB/);
  assert.match(tools, /0 B/);
  assert.doesNotMatch(tools, /업무 성공/);
  assert.match(tools, /&lt;未確認&gt;/);
  const alerts = out.tabs.find((item) => item.key === "alerts");
  assert.equal(alerts.n, undefined);
  assert.match(String(alerts.body), /최근 기록 · 표시 1건/);
  assert.doesNotMatch(String(alerts.body), /최근 24시간/);
  assert.equal(ui.policyLabel("P-ALLOW"), "승인 범위 허용");
  assert.equal(ui.policyLabel("unknown"), "unknown");
});

test("상하 페이지 제어는 같은 상태를 표시하고 빈 호출의 실패·조건·정상 상태를 구분한다", async () => {
  const ui = build(false);
  const out = await ui.ROUTES.activity("", "live", new URLSearchParams());
  const markup = String(out.html.tabs[0].body);
  assert.equal((markup.match(/data-feed-pager/g) || []).length, 2);
  const pagers = [{}, {}];
  ui.context.document.querySelectorAll = (selector) => selector === "[data-feed-pager]" ? pagers : [];
  ui.setFeed({ page: 2, pageSize: 50, filteredTotal: 101, analysis: { series: [], responses: [], servers: [], people: [] } }); ui.renderFeed();
  assert.equal(pagers[0].innerHTML, pagers[1].innerHTML);
  assert.match(pagers[0].innerHTML, /<span>2 \/ 3<\/span>/);
  assert.match(pagers[0].innerHTML, /data-page="1"/);
  assert.match(pagers[1].innerHTML, /data-page="3"/);
  ui.renderFeedStatus(); assert.match(ui.node("#feed-empty").innerHTML, /호출 없음/);
  ui.setFeed({ query: "missing" }); ui.renderFeedStatus();
  assert.match(ui.node("#feed-empty").innerHTML, /조건에 맞는 결과 없음/);
  assert.match(ui.node("#feed-empty").innerHTML, /조건 초기화/);
  ui.setFeed({ failing: true }); ui.renderFeedStatus();
  assert.match(ui.node("#feed-empty").innerHTML, /role="alert">조회 실패/);
  assert.doesNotMatch(ui.node("#feed-empty").innerHTML, /조건 초기화/);
  ui.setFeed({ failing: false, query: "" }); ui.renderFeedStatus();
  assert.match(ui.node("#feed-empty").innerHTML, /호출 없음/);
});

test("연결 해제와 검토 종료는 대상 확인 취소 시 쓰기를 보내지 않는다", async () => {
  const ui = build(); const prompts = [];
  ui.context.ask = async (value) => { prompts.push(value); return null; };
  const el = { dataset: { id: "id/1", name: "<서버>", account: "직원", endpoint: "PC-1" } };
  await ui.ACTIONS.disconnect(el); await ui.ACTIONS["endpoint-request-close"](el);
  assert.equal(ui.calls.length, 0);
  assert.match(String(prompts[0].fields), /&lt;서버&gt;[^]*직원[^]*결과/);
  assert.match(String(prompts[1].fields), /&lt;서버&gt;[^]*PC-1[^]*도입 요청 검토 종료/);
  assert.equal(prompts[1].confirm, "검토 종료");
  ui.context.ask = async () => new FormData();
  ui.setCurrent({ page: "intake" }); ui.context.location.hash = "#/intake?t=list";
  ui.refreshHook(async () => {}); ui.context.toast = () => {}; ui.context.refreshBadges = () => {};
  ui.responses["/api/my-connections/id%2F1"] = {};
  ui.responses["/gw/endpoint/requests/id%2F1/close"] = { closed: true };
  await ui.ACTIONS.disconnect(el); await ui.ACTIONS["endpoint-request-close"](el);
  assert.deepEqual(ui.calls, ["/api/my-connections/id%2F1", "/gw/endpoint/requests/id%2F1/close"]);
});

test("표는 한글 상태·서버명과 시각을 보존하고 주소·해시만 강제 줄바꿈한다", () => {
  const css = readFileSync(new URL("../gateway/app/agent_static/console.css", import.meta.url), "utf8");
  assert.match(css, /table\.data td\{[^}]*word-break:keep-all;overflow-wrap:normal/);
  assert.match(css, /table\.data \.chip\{word-break:keep-all;overflow-wrap:normal/);
  assert.match(css, /\.nowrap\{white-space:nowrap;font-variant-numeric:tabular-nums/);
  assert.match(css, /table\.data \.address,table\.data \.hash\{word-break:normal;overflow-wrap:anywhere/);
});

test("기존 신청 검색은 실패와 복구를 구분하고 늦은 실패가 새 결과를 덮지 않는다", async () => {
  const ui = build(); let tick, rejectFirst;
  ui.context.setTimeout = (fn) => { tick = fn; };
  ui.context.clearTimeout = () => {};
  const input = { value: "first", isConnected: true, matches: () => true };
  const branch = source.slice(source.indexOf('  if (event.target.matches("[data-catalog-search]")) {'), source.indexOf('  if (event.target.matches("[data-coverage-search]")) {'));
  vm.runInContext(`globalThis.searchInput = (event) => { ${branch} };`, ui.context);
  ui.context.api = () => new Promise((resolve, reject) => { rejectFirst = reject; });
  ui.context.searchInput({ target: input }); const first = tick();
  input.value = "second";
  ui.context.api = async () => ({ query: "second", requests: [], registry: [{ display_name: "두 번째 결과" }] });
  ui.context.searchInput({ target: input }); await tick();
  const latest = ui.node("#catalog-results").innerHTML;
  rejectFirst(new Error("실패")); await first;
  assert.equal(ui.node("#catalog-results").innerHTML, latest);
  assert.match(latest, /두 번째 결과/);
  ui.context.api = async () => { throw new Error("실패"); };
  ui.context.searchInput({ target: input }); await tick();
  assert.match(ui.node("#catalog-results").innerHTML, /조회 실패/);
  ui.context.api = async () => ({ query: "second", requests: [], registry: [] });
  ui.context.searchInput({ target: input }); await tick();
  assert.match(ui.node("#catalog-results").innerHTML, /조건에 맞는 결과 없음/);
  assert.doesNotMatch(ui.node("#catalog-results").innerHTML, /조회 실패/);
});
