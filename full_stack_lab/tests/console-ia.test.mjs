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
  const calls = [], timers = new Map(), elements = new Map();
  const inventory = { agents: [], entries: [], listeners: [], os_events: [], managed_events: [],
    coverage: { reporting_recently: 0 }, settings: {},
    pages: Object.fromEntries(["entries", "listeners", "os_events"].map((key) => [key, { total: 0, limit: 50, next_cursor: null }])) };
  const responses = {
    "/api/consents": { consents: [] }, "/approvals": { approvals: [], history: [] }, "/gw/dispatch-intents": { rows: [] },
    "/gw/registry": { servers: [], tools: [], registrations: {} },
    "/gw/policy/matrix": { capabilities: [], runtime_envelopes: [] },
    "/gw/enforcement": { enforcement: "enforce" },
    "/gw/policy/ledger": { policies: [] },
    "/gw/overview": { servers: [], workstations: [], pending_approvals: 2, termination: {}, execution: {}, series: [], flows: [], top_policies: [] },
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
      refreshHook(fn) { refreshIntake = fn; }, policyDrawer(fn) { openDrawer = fn; } };`, context);
  context.ui.pageModel((value) => value);
  return { ...context.ui, context, calls, timers, responses, inventory, node };
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
  const out = await ui.ROUTES.overview("", "approvals");
  assert.equal(out.html.active, "approvals");
  const summary = String(out.html.tabs.find((t) => t.key === "summary").body);
  const queue = String(out.html.tabs.find((t) => t.key === "approvals").body);
  assert.equal((summary.match(/data-act="approval"/g) || []).length, 5);
  assert.equal((queue.match(/data-act="approval"/g) || []).length, 7);
  assert.match(summary, /href="#\/overview\?t=approvals"/);
  assert.match(summary, /href="#\/people\?t=signups"[^]*?가입 승인<\/span><b class="n">1<\/b>/);
  assert.match(summary, /엔드포인트 활성화<\/span><b class="n">1<\/b>/);
  assert.match(queue, /&lt;img/);
  assert.doesNotMatch(queue, /data-act="approve" data-id="call-0"/);
  assert.match(queue, /data-act="approve" data-id="call-1"/);
  assert.match(queue, /data-act="reject"/);
  assert.doesNotMatch(queue, /intent-resolve|consent-decide/);
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
