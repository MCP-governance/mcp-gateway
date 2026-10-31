import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import * as state from "../gateway/app/agent_static/console-state.mjs";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const service = readFileSync(new URL("../gateway/app/agent_service.py", import.meta.url), "utf8");
const adminPages = ["overview", "activity", "servers", "people", "endpoints", "policy", "intake", "termination", "consent", "connections"];
const employeePages = ["activity", "consent", "intake", "connections"];
const code = source.slice(0, source.indexOf("// ── wiring")).replace(/^import[\s\S]*?;\r?\n/gm, "");

function build(admin = true, extra = {}) {
  const calls = [], requests = [], timers = new Map(), elements = new Map();
  const inventory = { agents: [], entries: [], listeners: [], os_events: [], managed_events: [],
    coverage: { reporting_recently: 0 }, settings: {},
    pages: Object.fromEntries(["entries", "listeners", "os_events"].map((key) => [key, { total: 0, limit: 50, next_cursor: null }])) };
  const responses = {
    "/api/consents": { consents: [] }, "/approvals": { approvals: [], history: [] }, "/gw/dispatch-intents": { rows: [] },
    "/gw/registry": { servers: [], tools: [], registrations: {} },
    "/gw/policy/matrix": { capabilities: [], runtime_envelopes: [] },
    "/gw/enforcement": { enforcement: "enforce" },
    "/gw/policy/ledger": { policies: [] },
    "/gw/overview": { servers: [], workstations: [], pending_approvals: 2, unresolved_execution: 0, termination: {}, execution: {}, series: [], flows: [], top_policies: [] },
    "/gw/latency": {}, "/gw/endpoint/network-quality": {}, "/gw/health": {},
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
      classList: { contains: () => false, toggle() {} }, querySelector: () => null, querySelectorAll: () => [], focus() {} });
    return elements.get(key);
  };
  const context = vm.createContext({ ...state, URLSearchParams, FormData, AbortController, setTimeout, clearTimeout, encodeURIComponent, decodeURIComponent,
    lang: () => "ko", locale: () => "ko-KR", t: (v) => v,
    clockText: () => "12:00", dateTimeText: () => "10-27 12:00",
    localStorage: { getItem: () => "fixture-token" }, location: { hash: "#/activity", replace() {} },
    history: { replaceState() {} },
    document: { hidden: false, querySelector: node },
    charts: { DECISION_LABEL: {}, register() {}, mountVisible() {}, disposeAll() {} },
    setInterval(fn) { const id = timers.size + 1; timers.set(id, fn); return id; },
    clearInterval(id) { timers.delete(id); },
    fetch: async (url, options) => {
      calls.push(url);
      requests.push({ url, ...options });
      let value = responses[url];
      if (value === undefined && url.startsWith("/gw/activity/analysis?")) value = { total: 0 };
      if (value === undefined && url.startsWith("/gw/activity?")) value = { rows: [], total: 0, cursor: 0 };
      if (value === undefined && url.startsWith("/gw/audit/events?")) value = { events: [], has_more: false };
      assert.notEqual(value, undefined, `unexpected request: ${url}`);
      if (typeof value === "function") value = await value();
      if (value instanceof Error) throw value;
      return { ok: true, status: 200, headers: { get: () => null }, json: async () => value };
    },
  });
  vm.runInContext(`${code}\nviewer = ${JSON.stringify({ admin, pages: admin ? adminPages : employeePages })};
    globalThis.ui = { ROUTES, canonicalRoute, renderNav, refreshBadges, covPage, covPaging, badges, ACTIONS,
      stopLive, stopIntake, setCurrent(value) { current = value; }, pageModel(fn) { page = fn; },
      refreshApprovalLists, startApprovalRefresh, stopApprovalRefresh,
      analysisState() { return feed; },
      analysisHooks() { route = () => {}; },
      approvalState() { return { ...approvalPaging, failed: approvalFailed }; },
      approvalActions(askFn) { ask = askFn; route = () => {}; refreshBadges = () => {}; toast = () => {}; },
      activityHooks(render, start) { renderFeed = render; startLive = start; },
      refreshHook(fn) { refreshIntake = fn; }, policyDrawer(fn) { openDrawer = fn; } };`, context);
  context.ui.pageModel((value) => value);
  return { ...context.ui, context, calls, requests, timers, responses, inventory, node };
}

test("관리자는 분리된 관리 메뉴를 순서대로, 직원과 협력사는 기존 4개를 본다", () => {
  const roles = service.slice(service.indexOf("PAGES_BY_ROLE ="), service.indexOf("ROLE_LABELS ="));
  const ids = (role) => [...roles.match(new RegExp(`"${role}": \\(([^)]+)\\)`))[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(ids("admin"), adminPages);
  for (const role of ["employee", "partner"]) assert.deepEqual(ids(role), employeePages);
  for (const admin of [true, false]) {
    const ui = build(admin); ui.renderNav("activity");
    const markup = ui.node("#nav").innerHTML;
    assert.deepEqual([...markup.matchAll(/href="#\/([\w-]+)"/g)].map((m) => m[1]), admin ? adminPages : ["activity", "intake", "consent", "connections"]);
    assert.match(markup, admin ? /호출·감사 기록/ : /호출 기록/);
  }
});

test("대시보드 호출 승인과 내 계정 이용 동의 배지를 분리한다", async () => {
  const ui = build(true, { "/api/consents": { consents: [
    { status: "PENDING", server_id: "a" }, { status: "PENDING", server_id: "a" },
    { status: "PENDING", server_id: "b" }, { status: "GRANTED", server_id: "c" }] } });
  await ui.refreshBadges();
  const nav = ui.node("#nav").innerHTML;
  assert.match(nav, /href="#\/overview"[^]*?<span class="count">2<\/span>/);
  assert.match(nav, /href="#\/consent"[^]*?<span class="count">2<\/span>/);
  assert.match(nav, /href="#\/servers"[^]*?<span class="count">4<\/span>/);
  assert.doesNotMatch(nav, /href="#\/coverage"/);
  assert.doesNotMatch(nav, /href="#\/approvals"/);
});

test("옛 주소 네 종류와 세부 탭·필터를 새 위치로 보낸다", () => {
  const ui = build();
  for (const [page, tab, target, nextTab] of [
    ["overview", "planes", "servers", "items"],
    ["overview", "traffic", "activity", "stats"],
    ["audit", "", "activity", "events"], ["audit", "incidents", "activity", "incidents"],
    ["audit", "siem", "activity", "siem"], ["coverage", "", "servers", "items"],
    ["coverage", "devices", "endpoints", "devices"], ["coverage", "shadow", "endpoints", "shadow"],
    ["coverage", "vendor", "servers", "vendor"], ["sbom-impact", "", "intake", "impact"],
    ["servers", "shadow", "endpoints", "shadow"],
    ["people", "devices", "endpoints", "devices"], ["people", "managed", "endpoints", "managed"],
    ["approvals", "", "overview", "approvals"], ["approvals", "queue", "overview", "approvals"],
    ["approvals", "unsent", "activity", "unsent"], ["approvals", "history", "activity", "approval-history"],
    ["approvals", "consent", "consent", "pending"],
    ["policy", "capabilities", "servers", "capabilities"],
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
  assert.equal(ui.canonicalRoute(consent), consent);
  assert.equal(build(false).canonicalRoute(consent), consent);
  assert.doesNotMatch(source, /#\/(?:audit|sbom-impact)(?:[?"`/])/);
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
  assert.deepEqual(Array.from(activity.html.tabs, (item) => item.key), ["live", "stats", "unsent", "approval-history", "events", "incidents", "siem"]);
  assert.match(String(activity.html.tabs[4].body), /audit-verify[^]*audit-export/);
  assert.ok(ui.calls.includes("/gw/audit/events?principal=alice&before=12&limit=100"));
  let rendered = 0, live = 0;
  ui.activityHooks(() => rendered++, () => live++); activity.after();
  assert.equal(rendered, 1); assert.equal(live, 1);
  assert.equal(ui.ROUTES.approvals, undefined);
  const consent = await ui.ROUTES.consent("", "pending");
  assert.match(String(consent.tabs[0].body), /확인할 요청 없음/);
  assert.match(String(consent.tabs[1].body), /동의 기록/);
  const servers = await ui.ROUTES.servers("", "servers", new URLSearchParams());
  assert.deepEqual(Array.from(servers.html.tabs, (item) => item.key), ["servers", "tools", "contract", "capabilities", "items", "vendor"]);
  assert.doesNotMatch(String(servers.html.head), /통제 범위/);
  assert.match(String(servers.html.head), /AI 연결 관리/);
  assert.equal(ui.ROUTES.coverage, undefined);
  const people = await ui.ROUTES.endpoints("", "devices");
  const devices = people.html.tabs.find((item) => item.key === "devices");
  assert.deepEqual(Array.from(people.html.tabs, (item) => item.key), ["devices", "shadow", "managed"]);
  assert.match(String(people.html.tabs[1].body), /엔드포인트 MCP 설정[^]*엔드포인트 수신기[^]*관측 수집 상태[^]*엔드포인트 차단/);
  assert.match(String(devices.body), /새 PC 활성화[^]*통제 점검[^]*엔드포인트 MCP 설정/);
  const intake = await ui.ROUTES.intake("", "impact", new URLSearchParams("package=alpha&range=%3E%3D1.0.0"));
  assert.equal(intake.html.tabs.at(-1).key, "impact");
  assert.match(String(intake.html.tabs.at(-1).body), /value="alpha"[^]*sbom-impact-stop/);
});

test("대시보드는 승인 미리보기와 전체 목록, 각 관리 작업으로의 이동을 제공한다", async () => {
  const approvals = Array.from({ length: 7 }, (_, i) => ({ id: `call-${i}`, server_id: "docs", tool: "read",
    requested_by: "<img src=x>", created_at: "2026-10-31T00:00:00Z", expires_at: "2026-11-01T00:00:00Z", own: i === 0 }));
  const ui = build(true, { "/approvals": { approvals, history: [] },
    "/api/signup-requests": { requests: [{ status: "pending" }, { status: "approved" }] } });
  ui.inventory.agents.push({ managed_state: "pending", policy_hash: "hash" },
    { managed_state: "quarantined" }, { managed_state: "pending", status: "revoked", policy_hash: "hash" });
  Object.assign(ui.responses["/gw/overview"], { unresolved_execution: 305,
    termination: { action_required: 9, overdue: 3 },
    execution: { tool_calls: 20, executed: 12, blocked: 6, unknown: 2 } });
  const out = await ui.ROUTES.overview("", "approvals");
  assert.equal(out.html.active, "approvals");
  const summary = String(out.html.tabs.find((t) => t.key === "summary").body);
  const queue = String(out.html.tabs.find((t) => t.key === "approvals").body);
  assert.match(String(out.html.kpis), /오늘 도구 호출/);
  assert.match(String(out.html.kpis), /전체 호출<\/div><div class="value">20/);
  assert.match(String(out.html.kpis), /차단된 호출<\/div><div class="value">6/);
  assert.doesNotMatch(String(out.html.kpis), /오늘 운영 현황|현재 상태|통제 적용 엔드포인트|실행된 호출/);
  assert.match(String(out.html.kpis), /href="#\/activity\?t=unsent"><div class="label">실행 확인 필요<\/div><div class="value">305/);
  assert.match(String(out.html.kpis), /종료 조치 필요<\/div><div class="value">9/);
  assert.match(String(out.html.kpis), /attention=overdue"><span>기한 초과<\/span><b>3/);
  assert.doesNotMatch(summary, /실행 확인 필요|종료 기한 초과/);
  assert.equal((summary.match(/<tr[^>]+data-act="approval"/g) || []).length, 5);
  assert.equal((queue.match(/<tr[^>]+data-act="approval"/g) || []).length, 7);
  assert.match(summary, /href="#\/overview\?t=approvals"/);
  assert.match(summary, /href="#\/people\?t=signups"[^]*?가입 승인<\/span><b class="n">1<\/b>/);
  assert.match(summary, /엔드포인트 활성화<\/span><b class="n">1<\/b>/);
  assert.match(queue, /&lt;img/);
  assert.doesNotMatch(queue, /data-act="approve" data-id="call-0"/);
  assert.doesNotMatch(queue, /data-act="approve"|data-act="reject"/);
  assert.match(queue, /data-act="approval" data-id="call-1">검토/);
  assert.doesNotMatch(queue, /intent-resolve|consent-decide/);
});

test("MCP 점검 목록은 대시보드와 같은 세 상태만 표시한다", async () => {
  const servers = ["READY", "DISABLED", "ERROR", "DRIFT", "PENDING"].map((status) => ({ id: status, display_name: status, status }));
  const ui = build(true, { "/gw/registry": { servers, tools: [], registrations: {} } });
  ui.responses["/gw/overview"].servers = servers;
  const overview = await ui.ROUTES.overview("", "summary");
  assert.match(String(overview.html.kpis), /attention=required"><div class="label">MCP 점검 필요<\/div><div class="value">3/);
  const result = await ui.ROUTES.servers("", "servers", new URLSearchParams("attention=required"));
  const body = String(result.html.tabs[0].body);
  assert.equal(result.html.tabs[0].n, 3);
  for (const status of ["ERROR", "DRIFT", "PENDING"]) assert.ok(body.includes(`#/servers/${status}`));
  for (const status of ["READY", "DISABLED"]) assert.ok(!body.includes(`#/servers/${status}`));
  assert.match(body, /href="#\/servers\?t=servers">전체 보기/);
});

test("통제 분포는 AI 연결 관리에서만 표시하고 그래프 선택을 연결 필터로 전달한다", async () => {
  const ui = build(true, { "/api/integrations": { devices: [], items: [
    { key: "gateway:docs", class: "gateway_mcp", name: "Docs", state: "gateway_enforced" },
    { key: "vendor:a", item_key: "vendor", class: "vendor_native_connector", name: "Vendor", state: "observed_only" },
    { key: "vendor:b", item_key: "vendor", class: "vendor_native_connector", name: "Vendor", state: "bypass_possible" },
  ] } });
  const overview = await ui.ROUTES.overview("", "summary");
  assert.deepEqual(Array.from(overview.html.tabs, (t) => t.key), ["summary", "approvals", "latency"]);
  assert.doesNotMatch(String(overview.html.tabs[0].body), /조직 통제 의존 경로|c-connections-matrix/);
  assert.equal(overview.charts["c-ov-matrix"], undefined);
  assert.match(String(overview.html.kpis), /href="#\/servers\?t=items&state=bypass_possible"/);
  const result = await ui.ROUTES.servers("", "items", new URLSearchParams());
  const body = String(result.html.tabs.find((t) => t.key === "items").body);
  assert.match(body, /연결 유형별 통제 현황[^]*연결 항목 수[^]*MCP·커넥터·플러그인/);
  assert.match(body, /id="c-connections-matrix"/);
  let captured;
  ui.context.charts.color = (tone) => tone;
  ui.context.charts.stacked = (labels, series, options) => { captured = { labels, series, options }; };
  result.charts["c-connections-matrix"]();
  assert.equal(captured.series[5].data[2], 1);
  assert.equal(captured.series.reduce((sum, s) => sum + s.data.reduce((a, b) => a + b, 0), 0), 2);
  captured.options.onClick({ dataIndex: 2, seriesIndex: 5 });
  assert.equal(ui.context.location.hash, "#/servers?t=items&class=vendor_native_connector&state=bypass_possible");
});

test("호출 승인 전체 건수와 페이지는 요약의 첫 5건과 독립적이다", async () => {
  const row = (id) => ({ id, server_id: "docs", tool: "read", summary: "<img src=x>", reason: "검토 필요" });
  const ui = build(true, {
    "/approvals": { approvals: Array.from({ length: 30 }, (_, i) => row(`first-${i}`)), history: [], total: 65, page: 1, page_size: 30 },
    "/approvals?page=3": { approvals: Array.from({ length: 5 }, (_, i) => row(`last-${i}`)), history: [], total: 65, page: 3, page_size: 30 },
  });
  const out = await ui.ROUTES.overview("", "approvals", new URLSearchParams("t=approvals&approval_page=3"));
  const full = out.html.tabs.find((t) => t.key === "approvals");
  const preview = String(out.html.tabs.find((t) => t.key === "summary").body);
  assert.equal(full.n, 65);
  assert.match(String(full.body), /approval_page=2/);
  assert.doesNotMatch(String(full.body), /approval_page=4|first-0/);
  assert.match(String(full.body), /last-4/);
  assert.match(preview, /first-4/); assert.doesNotMatch(preview, /first-5|last-0/);
  assert.match(String(full.body), /&lt;img/);
  assert.match(String(full.body), /승인 사유/);
  assert.doesNotMatch(preview, /<th>승인 사유<\/th>|<th>하네스<\/th>/);
});

test("통합 호출 분석은 목록과 같은 기간 및 필터를 쓰고 과거 엔드포인트도 표시한다", async () => {
  const ui = build();
  const query = new URLSearchParams({ t: "stats", since: "2026-10-30T00:00:00Z", until: "2026-10-31T00:00:00Z", event_kind: "tools/call", server: "docs" });
  const suffix = new URLSearchParams({ server: "docs", since: "2026-10-30T00:00:00.000Z", until: "2026-10-31T00:00:00.000Z", event_kind: "tools/call" }).toString();
  ui.responses[`/gw/activity/analysis?${suffix}`] = { total: 2, series: [], servers: [], people: [], responses: [],
    policies: [{ key: "P-1", Block: 1, Alert: 0 }],
    endpoints: [{ key: "<retired>", total: 1, Block: 1 }, { key: "", total: 1, Allow: 1 }],
    flows: [{ harness: "codex", server: "docs", decision: "Block", n: 1 }] };
  const out = await ui.ROUTES.activity("", "stats", query);
  const stats = String(out.html.tabs.find((t) => t.key === "stats").body);
  assert.match(stats, /data-filter="since"/);
  assert.match(stats, /data-filter="event_kind"/);
  assert.match(stats, /정책별 차단 및 경보/);
  assert.match(stats, /&lt;retired&gt;/); assert.match(stats, /엔드포인트 미확인/);
  assert.doesNotMatch(stats, /통제 상태|최근 하네스/);
  assert.match(stats, /하네스별 호출 판정/);
  const listRequest = new URL(ui.calls.find((p) => p.startsWith("/gw/activity?")), "http://test");
  const analysisRequest = new URL(ui.calls.find((p) => p.startsWith("/gw/activity/analysis?")), "http://test");
  for (const key of ["since", "until", "event_kind", "server"]) assert.equal(listRequest.searchParams.get(key), analysisRequest.searchParams.get(key));
  assert.equal(ui.analysisState().analysis.total, 2);
});

test("호출 분석 기본 범위와 기간 전환은 목록과 공유하고 주소에 보존한다", async () => {
  const ui = build(false);
  const query = new URLSearchParams("t=stats");
  ui.setCurrent({ page: "activity", query });
  await ui.ROUTES.activity("", "stats", query);
  assert.equal(ui.analysisState().filters.event_kind, "tools/call");
  assert.ok(Date.now() - new Date(ui.analysisState().filters.since).getTime() >= 86400000);
  ui.analysisHooks();
  ui.ACTIONS["feed-window"]({ dataset: { hours: "0" } });
  assert.equal(ui.analysisState().filters.since, "");
  assert.equal(ui.analysisState().filters.event_kind, "tools/call");
  ui.calls.length = 0;
  await ui.ROUTES.activity("", "stats", new URLSearchParams("t=stats&since=&event_kind=tools%2Fcall"));
  assert.ok(!new URL(ui.calls.find((p) => p.startsWith("/gw/activity?")), "http://test").searchParams.has("since"));
  ui.ACTIONS["feed-reset"]();
  assert.ok(ui.analysisState().filters.since);
  assert.equal(ui.analysisState().page, 1);
});

test("통합 분석 새로고침은 표도 갱신하고 이전 필터의 늦은 응답은 적용하지 않는다", async () => {
  const ui = build();
  const query = new URLSearchParams("t=stats&since=&event_kind=tools%2Fcall");
  ui.setCurrent({ page: "activity", query });
  await ui.ROUTES.activity("", "stats", query);
  ui.context.charts.redraw = () => {};
  const url = "/gw/activity/analysis?event_kind=tools%2Fcall";
  ui.responses[url] = { total: 1, endpoints: [{ key: "historic", total: 1, Block: 1 }] };
  await ui.ACTIONS["analysis-refresh"]();
  assert.match(ui.node("#analysis-endpoints").innerHTML, /historic/);
  assert.equal(ui.analysisState().analysis.total, 1);
  ui.responses[url] = () => {
    ui.analysisState().filters.server = "new-filter";
    return { total: 999, endpoints: [] };
  };
  await ui.ACTIONS["analysis-refresh"]();
  assert.equal(ui.analysisState().analysis.total, 1);
  assert.match(ui.node("#analysis-endpoints").innerHTML, /historic/);
});

test("성능 탭은 호출 시간과 엔드포인트 연결 측정을 분리하고 표본과 기간을 표시한다", async () => {
  const lat = { calls: 10, dispatched: 6, total: { p50: 100, p95: 200 }, gateway: { p50: 20, p95: 40 }, upstream: { p50: 80, p95: 160 },
    checked_at: "2026-10-31T00:00:00Z", window_start: "2026-10-30T00:00:00Z", window_end: "2026-10-31T00:00:00Z",
    stages: [{ stage: "policy", n: 10, p50: 2, p95: 5 }], servers: [{ server_id: "docs", n: 6, p50: 80, p95: 160, failed: 1 }] };
  const ui = build(true, { "/gw/latency": lat, "/gw/endpoint/network-quality": {
    summary: { p50_ms: 99999, p95_ms: 999999 }, devices: [
      { endpoint_id: "fresh", state: "fresh", rtt_p50_ms: 12, rtt_p95_ms: 18, jitter_ms: 2, failure_pct: 0, probes: 6 },
      { endpoint_id: "stale", state: "stale", rtt_p50_ms: 8888, rtt_p95_ms: 9999, probes: 6 },
      { endpoint_id: "unmeasured", state: "unknown" },
      { endpoint_id: "failed", state: "fresh", rtt_p50_ms: null, rtt_p95_ms: null, failure_pct: 100, probes: 6 },
    ] } });
  const out = await ui.ROUTES.overview("", "latency");
  const tab = out.html.tabs.find((t) => t.key === "latency"), body = String(tab.body);
  assert.equal(tab.label, "성능");
  assert.match(body, /호출 처리 성능[^]*전체 처리[^]*100 ms[^]*200 ms/);
  assert.match(body, /정책 판정<\/td><td class="num">10/);
  assert.match(body, /95백분위 높은 순, 최대 12개/);
  assert.doesNotMatch(body, /99999|MCP 서버 응답|엔드포인트 왕복/);
  assert.match(body, /엔드포인트 통신 상태[^]*연결 시간 중앙값[^]*점검 실패율[^]*점검 횟수/);
  const stale = body.split("<tr>").find((row) => row.includes('title="stale"'));
  assert.match(stale, /측정 만료/); assert.doesNotMatch(stale, /8888|8\.9 s|9999/);
  assert.match(body, /미측정/); assert.match(body, /100%[^]*측정 실패/);
  const href = body.match(/data-href="([^"]+)"/)[1].replaceAll("&amp;", "&");
  const query = new URL(href.slice(1), "http://test").searchParams;
  assert.equal(query.get("since"), lat.window_start); assert.equal(query.get("until"), lat.window_end);
  assert.equal(query.get("event_kind"), "tools/call");
});

test("성능 조회 실패는 측정 없음으로 표시하지 않고 두 데이터 조회는 독립적이다", async () => {
  const failed = build(true, { "/gw/latency": new Error("unavailable"), "/gw/endpoint/network-quality": { devices: [{ endpoint_id: "available", state: "fresh", rtt_p50_ms: 0, rtt_p95_ms: 0, failure_pct: 0 }] } });
  const out = await failed.ROUTES.overview("", "latency");
  const body = String(out.html.tabs.find((t) => t.key === "latency").body);
  assert.match(body, /note bad">조회 실패/); assert.doesNotMatch(body, /측정된 호출 없음/);
  assert.match(body, /available/); assert.match(body, /0 ms/);
  const empty = build(true, { "/gw/latency": { calls: 0 }, "/gw/endpoint/network-quality": new Error("unavailable") });
  const result = await empty.ROUTES.overview("", "latency");
  const emptyBody = String(result.html.tabs.find((t) => t.key === "latency").body);
  assert.match(emptyBody, /측정된 호출 없음/); assert.match(emptyBody, /엔드포인트 통신 상태[^]*조회 실패/);
  assert.doesNotMatch(emptyBody, /측정 대상 엔드포인트 없음/);
});

test("승인 상세에서만 실행 버튼을 제공하고 본인 요청과 취소는 실행하지 않는다", async () => {
  const ui = build(true, { "/approvals": { approvals: [
    { id: "own", server_id: "docs", tool: "read", own: true },
    { id: "other", server_id: "docs", tool: "read", reason: "범위 확인" },
  ], history: [] }, "/approvals/other/approve": { decision: "Allow" } });
  await ui.ROUTES.overview("", "approvals");
  let detail, asked;
  ui.policyDrawer((title, controls, tabs) => { detail = { controls: String(controls), tabs }; });
  await ui.ACTIONS.approval({ dataset: { id: "own" } });
  assert.match(detail.controls, /본인 요청/); assert.doesNotMatch(detail.controls, /data-act="approve"/);
  await ui.ACTIONS.approval({ dataset: { id: "other" } });
  assert.match(detail.controls, /data-act="approve"/);
  assert.deepEqual(Array.from(detail.tabs, (t) => t.key), ["request", "args", "policy"]);
  ui.approvalActions(async (options) => { asked = options; return null; });
  await ui.ACTIONS.approve({ dataset: { id: "other" } });
  assert.equal(asked.confirm, "승인·실행");
  assert.ok(!ui.calls.includes("/approvals/other/approve"));
  ui.approvalActions(async () => new Map());
  await ui.ACTIONS.approve({ dataset: { id: "own" } });
  assert.ok(!ui.calls.includes("/approvals/own/approve"));
  await ui.ACTIONS.approve({ dataset: { id: "other" } });
  assert.equal(ui.calls.filter((url) => url === "/approvals/other/approve").length, 1);
});

test("승인 목록 자동 갱신은 검토와 확인창 및 화면 이동을 방해하지 않는다", async () => {
  const ui = build();
  await ui.ROUTES.overview("", "approvals");
  ui.setCurrent({ page: "overview", query: new URLSearchParams("t=approvals") });
  ui.responses["/approvals"] = { approvals: [{ id: "new", server_id: "docs", tool: "read" }], history: [], total: 1 };
  ui.startApprovalRefresh(); assert.equal(ui.timers.size, 1);
  await ui.refreshApprovalLists();
  assert.equal(ui.approvalState().total, 1);
  assert.match(ui.node("#approval-queue").innerHTML, /data-id="new"/);
  const reads = ui.calls.length;
  ui.node("#drawer").classList.contains = () => true;
  await ui.refreshApprovalLists(); assert.equal(ui.calls.length, reads);
  ui.node("#drawer").classList.contains = () => false;
  ui.node("#dialog").open = true;
  await ui.refreshApprovalLists(); assert.equal(ui.calls.length, reads);
  ui.node("#dialog").open = false;
  ui.responses["/approvals"] = () => { ui.node("#drawer").classList.contains = () => true; return { approvals: [], history: [], total: 0 }; };
  await ui.refreshApprovalLists(); assert.equal(ui.approvalState().total, 1);
  ui.node("#drawer").classList.contains = () => false;
  ui.responses["/approvals"] = () => { ui.stopApprovalRefresh(); return { approvals: [], history: [], total: 0 }; };
  await ui.refreshApprovalLists();
  assert.equal(ui.approvalState().total, 1); assert.equal(ui.timers.size, 0);
});

test("중대 영향 호출은 상세 검토와 기존 증빙 확인을 거쳐 승인한다", async () => {
  const explanation = { impact_domains: [], arguments: { string: 1 }, summary: "범위 검토" };
  const ui = build(true, { "/approvals": { approvals: [{ id: "impact", explanation, own: false }], history: [] },
    "/gw/approvals/impact/evidence": { explanation, events: [], evidence_sha256: "evidence-proof" },
    "/gw/approvals/impact/approve": { decision: "Allow" } });
  await ui.ROUTES.overview("", "approvals");
  let controls, asked;
  ui.policyDrawer((title, body) => { controls = String(body); });
  await ui.ACTIONS.approval({ dataset: { id: "impact" } });
  assert.match(controls, /data-act="approve"/);
  ui.approvalActions(async (options) => { asked = options; return new Map([["confirmed", "on"]]); });
  await ui.ACTIONS.approve({ dataset: { id: "impact" } });
  assert.match(String(asked.fields), /name="confirmed" required/);
  const request = ui.requests.find((r) => r.url === "/gw/approvals/impact/approve");
  assert.equal(request.method, "POST");
  assert.deepEqual(JSON.parse(request.body), { evidence_sha256: "evidence-proof", reason: "scope_confirmed" });
});

test("승인 목록 갱신 실패를 빈 목록으로 숨기지 않고 복구하며 빈 마지막 페이지를 되돌린다", async () => {
  const ui = build(true, { "/approvals": { approvals: [], history: [], total: 31, page: 1 },
    "/approvals?page=2": { approvals: [{ id: "last", server_id: "docs", tool: "read" }], history: [], total: 31, page: 2 } });
  await ui.ROUTES.overview("", "approvals", new URLSearchParams("approval_page=2"));
  const query = new URLSearchParams("t=approvals&approval_page=2");
  ui.setCurrent({ page: "overview", query });
  ui.responses["/approvals"] = new Error("offline");
  await ui.refreshApprovalLists();
  assert.equal(ui.approvalState().failed, true);
  assert.match(ui.node("#approval-queue").innerHTML, /갱신 실패[^]*data-id="last"/);
  ui.responses["/approvals"] = { approvals: [], history: [], total: 0, page: 1 };
  ui.responses["/approvals?page=2"] = { approvals: [], history: [], total: 0, page: 2 };
  await ui.refreshApprovalLists();
  assert.equal(ui.approvalState().failed, false);
  assert.equal(ui.approvalState().page, 1);
  assert.equal(query.get("approval_page"), "1");
});

test("종료 조치 필터와 페이지 이동을 서버에 전달하고 기한 초과 필터를 제공한다", async () => {
  const ui = build(true, { "/gw/termination/relationships": { relationships: [] },
    "/gw/termination/cases?attention=required&page=2": { cases: [], summary: {}, page: 2, page_size: 50, total: 101 },
    "/gw/termination/cases?attention=overdue": { cases: [], summary: {}, page: 1, page_size: 50, total: 0 } });
  const result = await ui.ROUTES.termination("", "cases", new URLSearchParams("attention=required&page=2"));
  const cases = result.html.tabs.find((t) => t.key === "cases");
  assert.equal(cases.n, 101);
  assert.match(String(cases.body), /종료 조치 필요/);
  assert.match(String(cases.body), /attention=required&amp;page=1/);
  assert.match(String(cases.body), /attention=required&amp;page=3/);
  const overdue = await ui.ROUTES.termination("", "cases", new URLSearchParams("attention=overdue"));
  assert.match(String(overdue.html.tabs.find((t) => t.key === "cases").body), /종료 기한 초과/);
  assert.ok(ui.calls.includes("/gw/termination/cases?attention=overdue"));
});

test("실행 확인과 승인 번복 버튼은 감사 기록의 해당 탭에 유지한다", async () => {
  const ui = build(true, { "/approvals": { approvals: [], history: [{ id: "past", requested_by: "alice",
    server_id: "docs", tool: "read", status: "EXECUTED", explanation: {}, can_revoke: true }] },
    "/gw/dispatch-intents": { rows: [{ request_id: "uncertain", server_id: "docs", tool_name: "read", action: "r" }] } });
  const out = await ui.ROUTES.activity("", "unsent", new URLSearchParams());
  assert.equal(out.html.active, "unsent");
  const unsent = String(out.html.tabs.find((t) => t.key === "unsent").body);
  assert.match(unsent, /data-act="intent-resolve" data-id="uncertain" data-outcome="not_executed"/);
  assert.match(unsent, /data-outcome="executed"/);
  const history = String(out.html.tabs.find((t) => t.key === "approval-history").body);
  assert.match(history, /data-act="approval" data-id="past"/);
  assert.match(history, /data-act="approval-revoke" data-id="past"/);
  assert.ok(!ui.calls.includes("/api/consents"));
});

test("접근 권한은 AI 연결 관리에서만 조회하고 정책은 기존 목록과 집행 모드를 유지한다", async () => {
  const ui = build(true, { "/gw/policy/matrix": {
    capabilities: [{ id: "permission-1", principals: ["alice"], servers: ["docs"], actions: ["r"], path_roots: ["/docs"], valid_until: null }],
    runtime_envelopes: [{ server_id: "docs", principals: ["*"], tools: { read_file: {} }, valid_until: null }],
  } });
  const connections = await ui.ROUTES.servers("", "capabilities", new URLSearchParams());
  const access = connections.html.tabs.find((tab) => tab.key === "capabilities");
  assert.equal(access.label, "접근 권한");
  assert.equal(access.n, 2);
  assert.match(String(access.body), /permission-1[^]*alice[^]*docs[^]*\/docs[^]*read_file/);
  ui.calls.length = 0;
  const policy = await ui.ROUTES.policy("", "");
  assert.equal(policy.html.active, "ledger");
  assert.deepEqual(Array.from(policy.html.tabs, (tab) => tab.key), ["organization", "ledger"]);
  assert.match(String(policy.html.head), /관찰 모드로 전환/);
  assert.ok(!ui.calls.includes("/gw/policy/matrix"));
});

test("정책 목록은 관리 상태와 원장 근거를 구분하고 명시적 POL 연결만 표시한다", async () => {
  const policy = { policy_id: "P-1", name: "<img src=x>", status: "운영", enforced_by: "opa", outcome: "차단",
    purpose: "목적", scope: "<script>bad</script>", condition: "조건", enforcement: "거부", monitor_behavior: "protected",
    requirement_ids: ["REQ-03"], pol_ids: ["POL-001", "REQ-03", "POL-001"],
    recent: { count: 2, last_seen_at: "2026-10-31T00:00:00Z" } };
  const ui = build(true, { "/gw/policy/ledger": { policies: [policy], source_state: "loaded",
    checked_at: "2026-10-31T01:00:00Z", record_window_hours: 24,
    deployment: { rules_match: true, data_match: false } } });
  const out = await ui.ROUTES.policy("", "");
  const body = String(out.html.tabs.find((tab) => tab.key === "ledger").body);
  assert.match(body, /정책 로드 상태[^]*룰셋 일치 여부[^]*일치[^]*정책 데이터 일치 여부[^]*불일치[^]*조회 기준 시각/);
  assert.match(body, /등록 상태[^]*최근 24시간 판정[^]*운영[^]*기록 있음[^]*POL-001/);
  assert.ok(body.includes("&lt;img"));
  assert.ok(!body.includes("<img"));
  let detail;
  ui.policyDrawer((title, actions, tabs) => { detail = { title, actions: String(actions), tabs }; });
  ui.ACTIONS.policy({ dataset: { id: "P-1" } });
  assert.deepEqual(Array.from(detail.tabs, (tab) => tab.key), ["definition", "evidence", "mapping"]);
  assert.match(String(detail.tabs[0].body), /&lt;script&gt;/);
  assert.match(String(detail.tabs[1].body), /집행 경로 시험[^]*미수행/);
  assert.match(String(detail.tabs[1].body), /관찰 모드에서도 차단 유지/);
  assert.doesNotMatch(String(detail.tabs[1].body), /독립 효과 검증|현재 집행 경로 검증/);
  assert.match(detail.actions, /policy=P-1[^]*since=2026-10-30T01%3A00%3A00.000Z/);
  assert.ok(!body.includes("REQ-03"));
});

test("정책 조회 실패와 기록 없음은 집행 성공이나 정상 빈 목록으로 표시하지 않는다", async () => {
  const unavailable = build(true, { "/gw/policy/ledger": { policies: [], source_state: "unavailable", deployment: null } });
  const failed = await unavailable.ROUTES.policy("", "");
  assert.match(String(failed.html.tabs.find((tab) => tab.key === "ledger").body), /정책 원본 조회 실패/);
  assert.doesNotMatch(String(failed.html.tabs.find((tab) => tab.key === "ledger").body), /등록된 정책 없음/);
  const unverified = build(true, { "/gw/policy/ledger": { policies: [{ policy_id: "P-2", name: "두 번째", status: "운영",
    enforced_by: "untrusted", recent: { count: 0 }, requirement_ids: ["POL-090"] }], source_state: "loaded", deployment: {} } });
  const result = await unverified.ROUTES.policy("", "");
  const body = String(result.html.tabs.find((tab) => tab.key === "ledger").body);
  assert.match(body, /미확인[^]*기록 없음[^]*매핑 미확인/);
  assert.doesNotMatch(body, /untrusted|POL-090|집행 중/);
});

test("조직 정책은 코드 존재를 적용 성공으로 표시하지 않으며 규칙 후보만 연결한다", async () => {
  const ui = build(true, { "/gw/policy/ledger": { source_state: "unavailable", policies: [{ policy_id: "MCP-CATALOG-001", name: "계약 검사" }],
    organization: { source_state: "available", policies: [{ id: "POL-004", name: "<img src=x>", stage: "도입 검토",
      implementation: "rego+sensor", category: "pac", has_rule: true, has_test_definition: true,
      content: "<script>bad</script>", candidate_rule_ids: ["MCP-CATALOG-001", "MISSING-001"] }] } } });
  const out = await ui.ROUTES.policy("", "organization");
  assert.equal(out.html.active, "organization");
  const tab = out.html.tabs.find((t) => t.key === "organization");
  assert.equal(tab.n, 1);
  assert.match(String(tab.body), /POL-004[^]*&lt;img[^]*판정 코드 있음[^]*미확인/);
  let detail;
  ui.policyDrawer((title, actions, tabs) => { detail = tabs; });
  ui.ACTIONS["organization-policy"]({ dataset: { id: "POL-004" } });
  assert.match(String(detail[0].body), /&lt;script&gt;/);
  assert.match(String(detail[1].body), /시험 정의 있음[^]*시험 실행 확인[^]*미확인[^]*조직 적용 확인[^]*미확인/);
  assert.match(String(detail[2].body), /data-act="policy" data-id="MCP-CATALOG-001"/);
  assert.doesNotMatch(String(detail[2].body), /MISSING-001/);
  assert.doesNotMatch(String(tab.body), /적용 중|시험 통과/);
});

test("조직 정책 원본이 없으면 정상 빈 목록으로 숨기지 않는다", async () => {
  const ui = build(true, { "/gw/policy/ledger": { policies: [], organization: { source_state: "unavailable", policies: [] } } });
  const out = await ui.ROUTES.policy("", "organization");
  assert.match(String(out.html.tabs[0].body), /조직 정책 원본 조회 실패/);
  assert.doesNotMatch(String(out.html.tabs[0].body), /등록된 조직 정책 없음/);
});

test("정책 조회 배지는 제목 옆에 상태 색상을 표시하고 기간은 작은 보조 글씨로 표시한다", async () => {
  for (const [state, tone, label] of [["loaded", "allow", "조회 확인"], ["unavailable", "block", "조회 실패"], [undefined, "outline", "미확인"]]) {
    const ui = build(true, { "/gw/policy/ledger": { policies: [], source_state: state, record_window_hours: 24 } });
    const result = await ui.ROUTES.policy("", "ledger");
    const body = String(result.html.tabs.find((tab) => tab.key === "ledger").body);
    assert.match(body, new RegExp(`<h2><span class="policy-load-title"><span>정책 로드 상태</span><span class="sub">최근 24시간</span></span></h2><span class="chip ${tone}">${label}</span>`));
    assert.doesNotMatch(body, /<dt>정책 원본 조회<\/dt>|<dt>판정 기록 조회 기간<\/dt>/);
  }
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

test("전체 설정과 발견 항목의 페이지 커서는 독립적이다", async () => {
  const ui = build();
  ui.covPaging.full_entries.index = 1; ui.covPaging.full_entries.cursors.push("all-2");
  ui.covPaging.entries.index = 1; ui.covPaging.entries.cursors.push("shadow-2");
  ui.responses["/gw/endpoint/inventory/entries?limit=50&cursor=all-2"] = { rows: [], next_cursor: "all-3" };
  ui.responses["/gw/endpoint/inventory/entries?limit=50&cursor=shadow-2&classification=shadow%2Cretired-residue"] = { rows: [], next_cursor: "shadow-3" };
  await ui.ROUTES.endpoints("", "shadow");
  assert.equal(ui.covPaging.full_entries.next, "all-3");
  assert.equal(ui.covPaging.entries.next, "shadow-3");
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
