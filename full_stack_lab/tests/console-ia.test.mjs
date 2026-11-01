import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import * as state from "../gateway/app/agent_static/console-state.mjs";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const service = readFileSync(new URL("../gateway/app/agent_service.py", import.meta.url), "utf8");
const adminPages = ["overview", "approvals", "activity", "servers", "people", "policy", "intake", "termination", "connections"];
const employeePages = ["activity", "consent", "intake", "connections"];
const code = source.slice(0, source.indexOf("document.addEventListener(\"click\", (event) => {")).replace(/^import[\s\S]*?;\r?\n/gm, "");

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
      classList: { contains: () => false, toggle() {} }, querySelector: () => null, querySelectorAll: () => [], focus() {},
      setAttribute(key, value) { this[key] = value; }, showModal() { this.open = true; }, close() { this.open = false; } });
    return elements.get(key);
  };
  const context = vm.createContext({ ...state, URLSearchParams, FormData, encodeURIComponent, decodeURIComponent,
    lang: () => "ko", locale: () => "ko-KR", t: (v) => v,
    clockText: () => "12:00", dateTimeText: () => "10-27 12:00",
    localStorage: { getItem: () => "fixture-token" }, location: { hash: "#/activity", replace() {} },
    history: { state: null, replaceState() {}, pushState() {}, back() {} },
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
      rememberDetail, closeDrawer, openDrawer, decisionAction, shadowLink, alertGroups, markAlertsSeen, alertsSeen,
      refreshAlertBell, resetIntakeTools, FORMS, intakeStatus, rememberFeed, showDecision, route,
      setFeed(value) { Object.assign(feed, value); },
      stopLive, stopIntake, setCurrent(value) { current = value; }, pageModel(fn) { page = fn; },
      activityHooks(render, start) { renderFeed = render; startLive = start; },
      refreshHook(fn) { refreshIntake = fn; } };`, context);
  context.ui.pageModel((value) => value);
  return { ...context.ui, context, calls, timers, responses, inventory, node };
}

test("상세는 최초 1회 push, 전환·탭은 replace, 닫기는 목록 기록으로 돌아간다", async () => {
  const ui = build(false), writes = [];
  ui.setCurrent({ page: "activity", arg: "", query: new URLSearchParams("q=lookup&page=3&decision=Block") });
  Object.assign(ui.context.history, {
    pushState(state, _, url) { this.state = state; writes.push(["push", url]); },
    replaceState(state, _, url) { this.state = state; writes.push(["replace", url]); },
    back() { writes.push(["back"]); },
  });
  ui.rememberDetail(41); ui.rememberDetail(42); ui.rememberDetail(42);
  assert.deepEqual(writes.map((x) => x[0]), ["push", "replace"]);
  assert.match(writes[0][1], /q=lookup&page=3&decision=Block&d=41/);
  const scope = { querySelectorAll: () => [] };
  const bar = { parentElement: scope, querySelectorAll: () => [] };
  await ui.ACTIONS.tab({ dataset: { tab: "execution" }, closest: (selector) => selector === ".tabs" ? bar : {} });
  assert.match(writes.at(-1)[1], /dt=execution/);
  ui.closeDrawer(); assert.equal(writes.at(-1)[0], "back");
  ui.context.history.state = null;
  ui.rememberDetail(42); ui.closeDrawer(); assert.equal(writes.at(-1)[0], "replace");
  assert.doesNotMatch(writes.at(-1)[1], /[?&](d|dt)=/);
});

test("새로고침 목록의 검색·필터·페이지는 URL이 정본이며 이전 조건을 남기지 않는다", async () => {
  const ui = build(false);
  await ui.ROUTES.activity("", "live", new URLSearchParams("q=lookup&page=3&decision=Block&endpoint=ep1"));
  let request = new URL(ui.calls.find((url) => url.startsWith("/gw/activity?")), "https://unit.test");
  assert.equal(request.searchParams.get("page"), "3");
  assert.equal(request.searchParams.get("q"), "lookup");
  assert.equal(request.searchParams.get("decision"), "Block");
  ui.calls.length = 0;
  await ui.ROUTES.activity("", "live", new URLSearchParams());
  request = new URL(ui.calls.find((url) => url.startsWith("/gw/activity?")), "https://unit.test");
  assert.equal(request.searchParams.get("page"), "1");
  assert.equal(request.searchParams.has("q"), false);
  assert.equal(request.searchParams.has("decision"), false);
});

test("늦은 첫 상세 응답은 나중에 연 호출의 상세와 기록을 덮지 않는다", async () => {
  const ui = build(false), pending = new Map(), writes = [];
  ui.setCurrent({ page: "activity", arg: "", query: new URLSearchParams() });
  ui.context.history.pushState = (_, __, url) => writes.push(url);
  ui.context.history.replaceState = (_, __, url) => writes.push(url);
  ui.context.fetch = (url) => new Promise((resolve) => pending.set(new URL(url, "https://unit.test").searchParams.get("decision_id"), resolve));
  const first = ui.showDecision(1), second = ui.showDecision(2);
  const response = (id) => ({ ok: true, status: 200, headers: { get: () => null }, json: async () => ({ rows: [{
    id, decision: "Allow", server: "files", tool: "read", planes: ["gateway"], outcome_axes: { task: "업무 성공" },
  }] }) });
  pending.get("2")(response(2)); await second;
  pending.get("1")(response(1)); await first;
  assert.equal(ui.node("#drawer-title").textContent, "호출 #2");
  assert.equal(writes.length, 1); assert.match(writes[0], /d=2/);
});

test("미등록 MCP 조치는 엔드포인트·근거 기록을 보존하고 동의는 역할별 도구로 좁힌다", () => {
  const ui = build(true);
  const shadow = String(ui.decisionAction({ decision: "Block", policy_id: "MCP-SHADOW-001", device_id: "pc/<1>",
    evidence: { record_kind: "listener", record_id: 73 }, reason: '<script>x</script>' }));
  assert.match(shadow, /endpoint=pc%2F%3C1%3E/); assert.match(shadow, /record_kind=listener/); assert.match(shadow, /record_id=73/);
  assert.doesNotMatch(shadow, /<script>/); assert.match(shadow, /사유/); assert.match(shadow, /실행 안 함/);
  for (const admin of [true, false]) {
    const part = String(build(admin).decisionAction({ decision: "Block", policy_id: "PAC-CONSENT-001", server: "files/a", tool: "read x" }));
    assert.match(part, admin ? /#\/approvals\?t=consent/ : /#\/consent\?/);
    assert.match(part, /server=files%2Fa/); assert.match(part, /tool=read\+x/);
  }
});

test("경보는 종류·대상·사유로 묶고 모든 원본과 최초·최근 시각을 유지한다", () => {
  const ui = build(), row = { kind: "unapproved-endpoint-mcp", evidence: { endpoint_id: "ep1", label: "files", reason: "미등록" } };
  const alerts = [{ ...row, id: 3, created_at: "2026-11-01T10:00:00Z" }, { ...row, id: 1, created_at: "2026-11-01T09:00:00Z" },
    { ...row, id: 4, created_at: "2026-11-01T11:00:00Z", evidence: { ...row.evidence, label: "other" } }];
  const groups = ui.alertGroups(alerts);
  assert.equal(groups.length, 2); assert.equal(groups[0].rows.length, 2);
  assert.equal(groups[0].first, alerts[1].created_at); assert.equal(groups[0].last, alerts[0].created_at);
  assert.deepEqual(Array.from(groups.flatMap((g) => g.rows), (r) => r.id).sort(), [1, 3, 4]);
});

test("필터된 경보만 읽음으로 기록하고 종은 전체 미열람 수를 서버에서 받는다", async () => {
  const ui = build(), storage = new Map();
  Object.assign(ui.context.localStorage, { getItem: (k) => storage.get(k) || null, setItem: (k,v) => storage.set(k,v) });
  ui.responses["/gw/audit/alerts?limit=1&read_ranges=1%2C3"] = { unread_count: 1200 };
  ui.markAlertsSeen([{ id: 1 }, { id: 3 }]);
  await ui.refreshAlertBell();
  assert.deepEqual(JSON.parse(JSON.stringify(ui.alertsSeen())), [[1, 1], [3, 3]]);
  assert.equal(ui.node("#alert-count").textContent, "99+");
  assert.equal(ui.node("#alert-bell")["aria-label"], "읽지 않음 1200건");
});

test("경보 기간 API와 감사 표시 건수는 URL 및 응답 범위에 맞는다", async () => {
  const ui = build();
  const out = (await ui.ROUTES.activity("", "events", new URLSearchParams("hours=24"))).html;
  assert.ok(ui.calls.includes("/gw/audit/alerts?limit=200&hours=24"));
  const events = out.tabs.find((x) => x.key === "events");
  assert.equal(events.n, undefined); assert.match(String(events.body), /표시 0건/);
  assert.match(String(out.tabs.find((x) => x.key === "alerts").body), /최근 24시간/);
});

test("동의 직행 필터와 도구별 조작·일괄 확인 취소는 범위를 보존한다", async () => {
  const ui = build(false, { "/api/consents": { consents: [
    { id: 1, server_id: "files", tool_name: "read", status: "PENDING", grade: "important", terms: { destinations: ["docs.example.test"] } },
    { id: 2, server_id: "files", tool_name: "write", status: "PENDING" },
  ] } });
  const page = await ui.ROUTES.consent("", "pending", new URLSearchParams("server=files&tool=read"));
  const body = String(page.tabs[0].body);
  assert.match(body, /data-id="1" data-decision="grant"/); assert.match(body, /data-id="1" data-decision="deny"/);
  assert.doesNotMatch(body, /files.write/);
  let confirmation;
  vm.runInContext("ask = globalThis.confirmation;", Object.assign(ui.context, { confirmation: async (v) => { confirmation = v; return null; } }));
  await ui.ACTIONS["consent-server"]({ dataset: { id: "files", consents: "1", decision: "grant" } });
  assert.match(String(confirmation.fields), /도구 수/); assert.match(String(confirmation.fields), /docs.example.test/); assert.match(String(confirmation.fields), /중요/);
  assert.equal(ui.calls.filter((url) => url.startsWith("/api/consents/server")).length, 0);
});

test("도구 조회 중복·이전 주소의 늦은 응답·실패 뒤 재시도를 처리한다", async () => {
  const ui = build(false), status = { textContent: "", setAttribute() {} }, tools = { innerHTML: "", replaceChildren() { this.innerHTML = ""; } };
  const endpoint = { value: "https://one.example/mcp", setAttribute() {} };
  const form = { dataset: {}, elements: { endpoint_url: endpoint, namedItem: () => endpoint }, querySelector: (s) => s === "[data-requested-tools]" ? tools : status };
  const button = { disabled: false, closest: () => form };
  let resolve, requests = 0;
  ui.context.fetch = () => { requests++; return new Promise((done) => { resolve = done; }); };
  const first = ui.ACTIONS["intake-discover"](button);
  await ui.ACTIONS["intake-discover"](button); assert.equal(requests, 1); assert.equal(button.disabled, true);
  endpoint.value = "https://two.example/mcp"; ui.resetIntakeTools(form);
  resolve({ ok: true, status: 200, headers: { get: () => null }, json: async () => ({ tools: [{ name: "stale" }] }) });
  await first; assert.equal(tools.innerHTML, ""); assert.equal(button.disabled, false); assert.equal(form.dataset.discoveredEndpoint, undefined);
  ui.context.fetch = async () => { throw new Error("offline"); };
  await ui.ACTIONS["intake-discover"](button); assert.equal(status.textContent, "도구 조회 실패");
  ui.context.fetch = async () => ({ ok: true, status: 200, headers: { get: () => null }, json: async () => ({ tools: [{ name: "fresh" }] }) });
  await ui.ACTIONS["intake-discover"](button);
  assert.match(String(tools.innerHTML), /fresh/); assert.equal(form.dataset.discoveredEndpoint, endpoint.value);
});

test("신청 실패는 입력과 도구 선택을 남기고 해당 필드를 접근성 오류로 표시한다", async () => {
  const ui = build(false), values = { intake_kind: "remote-endpoint", endpoint_url: "https://one.example/mcp", display_name: "원래 이름", purpose: "원래 목적", requested_tool: "read" };
  class Data { get(k) { return values[k] || null; } getAll(k) { return values[k] ? [values[k]] : []; } }
  ui.context.FormData = Data;
  const elements = new Map(), messages = new Map();
  const item = (m,k) => { if (!m.has(k)) m.set(k, { textContent: "", setAttribute(n,v) { this[n] = v; } }); return m.get(k); };
  const form = { dataset: { discoveredEndpoint: values.endpoint_url }, elements: { namedItem: (k) => k in values ? item(elements,k) : null }, querySelector: (s) => item(messages,s) };
  ui.context.fetch = async () => ({ ok: false, status: 422, headers: { get: () => null }, json: async () => ({ detail: [{ loc: ["body", "display_name"], msg: "validation" }] }) });
  await ui.FORMS.intake(form);
  assert.equal(values.display_name, "원래 이름"); assert.equal(values.requested_tool, "read");
  assert.equal(item(elements,"display_name")["aria-invalid"], "true");
  assert.equal(item(messages,'[data-field-error="display_name"]').textContent, "입력 확인 필요");
  assert.equal(form.dataset.submitting, "false");
});

test("엔드포인트 검색·상태·선택은 세 표를 같은 ID로 좁히고 식별값을 분리한다", async () => {
  const ui = build(), q = new URLSearchParams("t=devices&q=kim&state=pending&endpoint=ep1");
  ui.setCurrent({ page: "people", arg: "", query: q });
  const inventory = { ...ui.inventory, agents: [{ endpoint_id: "ep1", hostname: "host-one", owner_name: "직원 이름", managed_state: "pending", local_username: "pc-user", status: "active" }] };
  ui.responses["/gw/endpoint/inventory?q=kim&state=pending&endpoint=ep1"] = inventory;
  ui.responses["/api/integrations"] = { items: [], devices: [
    { endpoint_id: "ep1", hostname: "host-one", account: "pc-user", state: "observed_only", checks: {} },
    { endpoint_id: "ep2", hostname: "host-other", account: "other-user", state: "observed_only", checks: {} },
  ] };
  const out = await ui.ROUTES.people("", "devices", q);
  const body = String(out.html.tabs.find((tab) => tab.key === "devices").body);
  assert.match(body, /選択|선택 기기/); assert.match(body, /<dl class="kv">/);
  assert.match(body, /<dt>호스트<\/dt><dd>host-one/); assert.match(body, /<dt>PC 계정<\/dt><dd>pc-user/);
  assert.match(body, /직원 이름/); assert.doesNotMatch(body, /host-other|other-user/);
  assert.match(body, /name="q"[^>]*value="kim"/); assert.match(body, /value="pending" selected/);
});

test("미등록 근거 직행 URL은 해당 엔드포인트 목록과 기존 기록 상세를 함께 연다", async () => {
  const ui = build();
  ui.context.matchMedia = () => ({ matches: false });
  ui.context.location.hash = "#/servers?t=shadow&endpoint=ep1&record_kind=listener&record_id=73&dt=source";
  ui.responses["/gw/endpoint/inventory?classification=shadow,retired-residue&endpoint=ep1"] = ui.inventory;
  ui.responses["/gw/endpoint/records/listener/73"] = { id: 73, record_kind: "listener", endpoint_id: "ep1", address: "127.0.0.1", provenance: {} };
  ui.responses["/gw/endpoint/correlation?kind=listener&record_id=73"] = { records: [] };
  await ui.route();
  assert.ok(ui.calls.includes("/gw/endpoint/records/listener/73"));
  assert.match(String(ui.node("#drawer-body").innerHTML), /d-panel-source/);
  assert.match(String(ui.node("#drawer-body").innerHTML), /d-tab-source[^>]*aria-selected="true"/);
});

test("종료 목록의 예상·실제 결과와 케이스 근거 링크는 별도 열이다", async () => {
  const ui = build(true, {
    "/gw/termination/relationships": { relationships: [{ id: "rel1", display_name: "문서 서버", status: "ACTIVE", lifecycle: "OPERATING", latest_case: "case1", readiness: { best_attainable_grade: "T1" } }] },
    "/gw/termination/cases": { cases: [{ id: "case1", relationship_id: "rel1", display_name: "문서 서버", grade: "T2", status: "ASSESSED" }], summary: {} },
  });
  const out = await ui.ROUTES.termination();
  for (const tab of out.html.tabs) {
    const body = String(tab.body);
    assert.match(body, /<th>예상 결과<\/th><th>실제 결과<\/th><th>근거<\/th>/);
    assert.match(body, /완전 종료/); assert.match(body, /부분 종료/);
    assert.match(body, /href="#\/termination\/case1\?t=evidence"/);
  }
});

test("브라우저 배포 소스는 개발 주석을 포함하지 않고 만료창은 라벨과 값이다", () => {
  for (const name of ["console.js", "console-state.mjs", "charts.mjs", "i18n-en.mjs", "i18n.mjs", "login.js"]) {
    const body = readFileSync(new URL(`../gateway/app/agent_static/${name}`, import.meta.url), "utf8");
    assert.doesNotMatch(body, /^\s*\/\/|^\s*\/\*/m);
  }
  assert.match(source, /\["만료 시각",/); assert.match(source, /\["만료 사유",/); assert.match(source, /\["재로그인",/);
});

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
  ui.setCurrent({ page: "servers", arg: "", query: new URLSearchParams("entries_cursor=&entries_cursor=42&entries_page=1") });
  ui.responses["/gw/endpoint/inventory/entries?limit=50&cursor=42"] = { rows: [], next_cursor: null };
  ui.responses["/gw/endpoint/inventory/entries?limit=50&cursor=42&classification=shadow%2Cretired-residue"] = { rows: [], next_cursor: null };
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
    assert.ok(markup.includes(`name="${addressField}" aria-invalid="false" aria-describedby="intake-${addressField}-error" type="url" maxlength="${addressField === "repository_url" ? 300 : 500}" placeholder="${addressField === "repository_url" ? "https://github.com/org/repo" : "https://…/mcp"}" value="${source}"`));
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
  assert.match(tools, /<th>게이트웨이 판정<\/th><th>도구 실행<\/th><th>업무 결과<\/th>/);
  assert.match(tools, /<th class="num">출력 크기<\/th>/);
  assert.match(tools, /승인 범위 허용/);
  assert.match(tools, /도구 오류/);
  assert.match(tools, /4\.0 KB/);
  assert.match(tools, /0 B/);
  assert.doesNotMatch(tools, /업무 성공/);
  assert.match(tools, /&lt;未確認&gt;/);
  const alerts = out.tabs.find((item) => item.key === "alerts");
  assert.equal(alerts.n, undefined);
  assert.match(String(alerts.body), /<dt>표시<\/dt><dd>1건<\/dd>/);
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
  // A long id without the address/hash class still breaks instead of widening the table; Hangul words stay whole.
  assert.match(css, /table\.data td\{[^}]*word-break:keep-all;overflow-wrap:break-word/);
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
