/* MCP Governance Console v3.
 *
 * The Console never calls an MCP tool. Employees' harnesses (Claude Code, Codex,
 * Gemini CLI, OpenCode) call tools through the Gateway; this screen reads what
 * happened and runs the procedures around it - approvals, contract review and the
 * termination judgment. Every request carries the signed-in user's token and the
 * server decides what that user may see, so hiding a menu here is convenience only.
 *
 * Layout (docs/ai/CONSOLE_UI.md): each page is a header, a KPI strip where it helps,
 * in-page tabs, and panels that lead with a chart. Details open in a drawer with its
 * own tabs. Words are labels; explanations live in the team's guideline documents.
 */
import { mergeRows, searchRows, liveLabel, hourBuckets, splitBy, sankeyData, harnessLabel, DECISIONS } from "./console-state.mjs";
import * as charts from "./charts.mjs";

const { DECISION_LABEL } = charts;
const TOKEN_KEY = "mcp-console-token";
const THEME_KEY = "mcp-console-theme";
const token = localStorage.getItem(TOKEN_KEY);
if (!token) location.replace("/login");

const $ = (selector, root = document) => root.querySelector(selector);

// ── safe HTML ────────────────────────────────────────────────────────────────
// Everything interpolated into html`` is escaped unless it is itself html`` or raw().
// Audit rows carry tool arguments an attacker controls (a prompt-injected agent
// writes them), so there is no other way to put data on this page.
class Raw { constructor(s) { this.s = s; } toString() { return this.s; } }
const raw = (s) => new Raw(String(s));
const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ESC[c]);
const part = (v) => (v instanceof Raw ? v.s : Array.isArray(v) ? v.map(part).join("")
  : v === null || v === undefined || v === false ? "" : esc(v));
function html(strings, ...values) {
  let out = strings[0];
  values.forEach((value, i) => { out += part(value) + strings[i + 1]; });
  return new Raw(out);
}
const short = (text, n = 120) => { const s = String(text ?? ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; };

// ── API ──────────────────────────────────────────────────────────────────────
function detailText(detail) {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join(" · ");
  return JSON.stringify(detail);
}

async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(path, {
    method,
    headers: { authorization: `Bearer ${token}`, ...(body === undefined ? {} : { "content-type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401) {
    localStorage.removeItem(TOKEN_KEY);
    location.replace("/login");
    throw new Error("로그인이 만료되었습니다.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(detailText(data.detail) || `요청이 거절되었습니다 (${response.status}).`);
  return data;
}
const gw = (path, options) => api(`/gw/${path}`, options);

// ── vocabulary ───────────────────────────────────────────────────────────────
const DECISION = {
  Allow: ["allow", "허용"], Alert: ["alert", "경보"], Restrict: ["restrict", "제한 실행"],
  Approval: ["approval", "승인 대기"], Block: ["block", "차단"],
};
const SERVER_STATUS = { READY: "정상", DRIFT: "계약 변경", PENDING: "확인 대기", DISABLED: "사용 중지", ERROR: "연결 오류" };
const LIFECYCLE = { OPERATING: "운영", TERMINATING: "종료 중", RETIRED: "폐기" };
const GRADE = { T1: "종료", T2: "부분 종료", T3: "판단 불가" };
const CASE_STATUS = { OPEN: "진행", REVOKING: "회수 중", ASSESSED: "판정됨", CLOSED: "종결", REOPENED: "재개" };
const TARGET_KIND = {
  "gateway-route": "Gateway 강제 경로", "gateway-access": "이용 주체 접근", "client-token": "클라이언트 토큰",
  "refresh-token": "갱신 토큰", "dynamic-registration": "동적 클라이언트 등록", session: "MCP 세션",
  "server-held-credential": "서버 보유 자격", "endpoint-config": "단말 MCP 설정", "api-key": "API 키",
  webhook: "웹훅", "cached-artifact": "캐시 산출물",
};
const HOLDER = { org: "조직", provider: "제공자", endpoint: "단말" };
const DISCOVERED = {
  "gateway-ledger": "Gateway 기록", "endpoint-agent": "단말 보고", "provider-disclosure": "제공자 고지",
  "operator-manual": "담당자 등록", "liveness-probe": "도달 확인",
};
const TARGET_STATUS = { OUTSTANDING: ["alert", "미회수"], REVOKED: ["allow", "회수됨"], EXPIRED: ["allow", "만료"], UNVERIFIABLE: ["block", "확인 불가"] };
const ENDPOINT_CLASS = { registered: ["allow", "Gateway 경유"], shadow: ["block", "섀도 MCP"], "retired-residue": ["alert", "폐기 잔존"] };
const ACTION = { r: "읽기", w: "쓰기", x: "외부전송·실행" };
const DATA_CLASS = { public: "공개", nonimportant: "내부", important: "중요" };
const ROLE = { admin: "관리자", employee: "직원", partner: "협력사" };
const EXIT_TERMS = {
  provider_credential_disclosure: "보유 자격 고지",
  revocation_evidence: "폐기 기록 제출",
  audit_access_retained: "종료 후 감사 접근",
};
const CRITERIA = { C1: "모집단", C2: "수행 권한", C3: "연속성", C4: "증거 접근" };
const APPROVAL_STATUS = {
  APPROVED: ["allow", "승인"], EXECUTED: ["allow", "실행됨"], REJECTED: ["block", "거부"], EXPIRED: ["outline", "만료"],
  NOT_EXECUTED: ["alert", "실행 안 됨"], UNCONFIRMED: ["alert", "실행 미확인"],
};
const INTAKE_STATUS = {
  HOLD: ["outline", "보류"], VALIDATION_QUEUED: ["approval", "검증 대기"], VALIDATING: ["approval", "검증 중"],
  VALIDATED: ["restrict", "검증 완료"], APPROVED: ["allow", "승인"], REJECTED: ["block", "거부"], FAILED: ["alert", "검증 실패"],
};

const chip = (tone, label) => html`<span class="chip ${tone}">${label}</span>`;
const decisionChip = (d) => chip(...(DECISION[d] || ["", d]));
const gradeChip = (g, prefix = "") => (g ? chip(g, `${prefix}${g} ${GRADE[g]}`) : chip("outline", "미판정"));
const bool = (v, label) => (v ? chip("allow", label) : chip("block", label));
const pad = (n) => String(n).padStart(2, "0");
function when(value, { seconds = false } = {}) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}${seconds ? `:${pad(d.getSeconds())}` : ""}`;
  return d.toDateString() === new Date().toDateString() ? hm : `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`;
}
function ago(value) {
  if (!value) return "—";
  const s = Math.round((Date.now() - new Date(value).getTime()) / 1000);
  if (s < 60) return "방금";
  if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
  return `${Math.floor(s / 86400)}일 전`;
}
const json = (v) => html`<pre class="json">${JSON.stringify(v, null, 2)}</pre>`;
const kv = (pairs) => html`<dl class="kv">${pairs.filter(([, v]) => v !== undefined && v !== null && v !== "")
  .map(([k, v]) => html`<dt>${k}</dt><dd>${v}</dd>`)}</dl>`;
const empty = (text) => html`<p class="empty">${text}</p>`;
const OUTCOME_TONE = [["차단", "Block"], ["승인", "Approval"], ["경보", "Alert"], ["제한", "Restrict"], ["허용", "Allow"]];
const outcomeDecision = (text) => (OUTCOME_TONE.find(([word]) => String(text || "").includes(word)) || [])[1];

// ── icons (Lucide, ISC licence) ──────────────────────────────────────────────
const ICON = {
  overview: '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
  activity: '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
  approvals: '<rect width="8" height="4" x="8" y="2" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
  servers: '<rect width="20" height="8" x="2" y="2" rx="2"/><rect width="20" height="8" x="2" y="14" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
  people: '<path d="M18 5a2 2 0 0 1 2 2v8.5a2 2 0 0 0 .2.9l1.1 2.1a1 1 0 0 1-.9 1.5H3.6a1 1 0 0 1-.9-1.5l1.1-2.1a2 2 0 0 0 .2-.9V7a2 2 0 0 1 2-2z"/><path d="M20 16H4"/>',
  intake: '<path d="M16 16h6M19 13v6"/><path d="M21 10V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l2-1.14"/><path d="M3.3 7 12 12l8.7-5M12 22V12"/>',
  termination: '<path d="m19 5 3-3M2 22l3-3"/><path d="M6.3 20.3a2.4 2.4 0 0 0 3.4 0L12 18l-6-6-2.3 2.3a2.4 2.4 0 0 0 0 3.4Z"/><path d="M7.5 13.5 10 11M10.5 16.5 13 14"/><path d="m12 6 6 6 2.3-2.3a2.4 2.4 0 0 0 0-3.4l-2.6-2.6a2.4 2.4 0 0 0-3.4 0Z"/>',
  policy: '<path d="m16 16 3-8 3 8c-.9.7-1.9 1-3 1s-2.1-.3-3-1Z"/><path d="m2 16 3-8 3 8c-.9.7-1.9 1-3 1s-2.1-.3-3-1Z"/><path d="M7 21h10M12 3v18M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
};
const icon = (name) => raw(`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[name] || ""}</svg>`);

// ── chrome: toast, drawer, dialog ────────────────────────────────────────────
let toastTimer;
function toast(message, bad = false) {
  const el = $("#toast");
  el.textContent = message;
  el.className = bad ? "toast bad" : "toast";
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, bad ? 8000 : 4000);
}

// Keyboard users land in the drawer when it opens and back on what opened it when it
// closes; a closed drawer is inert so Tab cannot wander into it off-screen.
let drawerReturn = null;
function setDrawer(open) {
  const drawer = $("#drawer");
  drawer.classList.toggle("open", open);
  drawer.setAttribute("aria-hidden", String(!open));
  drawer.inert = !open;
  $("#scrim").classList.toggle("show", open);
}
/** body is html; `tabs` (optional) is [{key, label, n, body}] shown as drawer tabs. */
function openDrawer(title, body, tabs = null) {
  if (!$("#drawer").classList.contains("open")) drawerReturn = document.activeElement;
  $("#drawer-title").textContent = title;
  $("#drawer-body").innerHTML = String(tabs ? html`${body}${tabBar(tabs, tabs[0].key, "d")}${tabs.map((t) => tabPanel(t.key, tabs[0].key, t.body, "d"))}` : body);
  setDrawer(true);
  $("#drawer .icon-btn").focus();
}
function closeDrawer() {
  if (/^#\/servers\/./.test(location.hash)) history.replaceState(null, "", "#/servers");
  const wasOpen = $("#drawer").classList.contains("open");
  setDrawer(false);
  if (wasOpen && drawerReturn?.isConnected) drawerReturn.focus();
  drawerReturn = null;
}

/** Modal form. Resolves with the FormData, or null when cancelled. */
function ask({ title, body = "", fields = "", confirm = "확인", danger = false }) {
  const dialog = $("#dialog");
  const form = $("#dialog-form");
  form.innerHTML = String(html`<h3>${title}</h3>${body ? html`<p>${body}</p>` : ""}${fields}
    <div class="row"><button class="btn" value="cancel" formnovalidate>취소</button>
    <button class="btn ${danger ? "danger solid" : "primary"}" value="ok">${confirm}</button></div>`);
  dialog.returnValue = "";
  dialog.showModal();
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "ok" ? new FormData(form) : null), { once: true });
  });
}

// ── tabs ─────────────────────────────────────────────────────────────────────
// WAI-ARIA tabs: one tab stop, arrows move between tabs. Panels stay in the DOM;
// charts in a hidden panel are drawn when it is first shown (they need a size).
function tabBar(tabs, active, scope = "p") {
  return html`<div class="tabs" role="tablist">${tabs.map((t) => html`<button class="tab" role="tab" type="button"
    id="${scope}-tab-${t.key}" aria-controls="${scope}-panel-${t.key}" aria-selected="${String(t.key === active)}"
    tabindex="${t.key === active ? 0 : -1}" data-act="tab" data-tab="${t.key}">${t.label}${t.n !== undefined && t.n !== null
      ? html`<span class="n ${t.hot ? "hot" : ""}">${t.n}</span>` : ""}</button>`)}</div>`;
}
function tabPanel(key, active, body, scope = "p") {
  return html`<section class="tabpanel" role="tabpanel" id="${scope}-panel-${key}" aria-labelledby="${scope}-tab-${key}"
    data-panel="${key}" ${key === active ? "" : raw("hidden")}>${body}</section>`;
}
/** A page: head, optional KPI strip, tab bar and panels. `tabs`: [{key, label, n, hot, body}] */
function page({ head, kpis = "", tabs, active }) {
  const current = tabs.some((t) => t.key === active) ? active : tabs[0].key;
  return html`${head}${kpis}${tabBar(tabs, current)}${tabs.map((t) => tabPanel(t.key, current, t.body))}`;
}
const head = (title, { status = "", actions = "", back = "" } = {}) => html`<div class="page-head">
  ${back}<h1>${title}</h1>${status ? html`<div class="status">${status}</div>` : ""}${actions ? html`<div class="actions">${actions}</div>` : ""}</div>`;
const kpiStrip = (items) => html`<div class="kpis">${items.map(([label, value, tone = "", href = ""]) => href
  ? html`<a class="kpi ${tone}" href="${href}"><div class="label">${label}</div><div class="value">${value ?? 0}</div></a>`
  : html`<div class="kpi ${tone}"><div class="label">${label}</div><div class="value">${value ?? 0}</div></div>`)}</div>`;
const panel = (title, body, { sub = "", tools = "", flush = false } = {}) => html`<section class="panel">
  <header><h2>${title}</h2>${sub ? html`<span class="sub">${sub}</span>` : ""}${tools ? html`<div class="tools">${tools}</div>` : ""}</header>
  <div class="body ${flush ? "flush" : ""}">${body}</div></section>`;
const chartBox = (id, label, size = "") => html`<div class="chart ${size}" id="${id}" role="img" aria-label="${label}"></div>`;

// ── routing ──────────────────────────────────────────────────────────────────
const PAGES = [
  { id: "overview", label: "개요", group: "운영" },
  { id: "activity", label: "활동 로그", group: "운영" },
  { id: "approvals", label: "승인 대기", group: "운영", badge: "approvals" },
  { id: "servers", label: "MCP 서버", group: "자산" },
  { id: "people", label: "직원·단말", group: "자산" },
  { id: "intake", label: "도입 신청", group: "자산" },
  { id: "termination", label: "종료·폐기", group: "전주기", badge: "termination" },
  { id: "policy", label: "정책", group: "전주기" },
];
let viewer = null;
let routeSeq = 0;
let current = { page: "", arg: "", query: new URLSearchParams() };
const badges = { approvals: 0, termination: 0 };

function renderNav(active) {
  const groups = new Map();
  for (const p of PAGES.filter((x) => viewer.pages.includes(x.id))) {
    if (!groups.has(p.group)) groups.set(p.group, []);
    groups.get(p.group).push(p);
  }
  $("#nav").innerHTML = String(html`${[...groups].map(([group, pages]) => html`<div class="group">${group}</div>${pages.map((p) => html`
    <a href="#/${p.id}" ${active === p.id ? raw('aria-current="page"') : ""}>${icon(p.id)}<span>${p.label}</span>
      ${p.badge && badges[p.badge] ? html`<span class="count">${badges[p.badge]}</span>` : ""}</a>`)}`)}`);
}

function parseHash() {
  const [path, query = ""] = location.hash.replace(/^#\/?/, "").split("?");
  const [page = "", arg = ""] = path.split("/").map(decodeURIComponent);
  return { page, arg, query: new URLSearchParams(query) };
}

async function route() {
  stopLive();
  closeDrawer();
  charts.disposeAll();
  const at = parseHash();
  const id = viewer.pages.includes(at.page) ? at.page : viewer.pages[0];
  if (id !== at.page) { location.replace(`#/${id}`); return; }
  current = at;
  renderNav(id);
  const seq = ++routeSeq;
  const view = $("#view");
  if (view.dataset.page !== id) view.innerHTML = '<p class="skeleton">불러오는 중…</p>';
  view.dataset.page = id;
  const moved = view.dataset.at !== `${id}/${at.arg}`;
  view.dataset.at = `${id}/${at.arg}`;
  try {
    const out = await ROUTES[id](at.arg, at.query.get("t") || "", at.query);
    if (seq !== routeSeq) return;  // the user already moved on
    view.innerHTML = String(out.html ?? out);
    charts.register(out.charts);
    charts.mountVisible(view);
    const h1 = $("h1", view);
    if (h1) {
      document.title = `${h1.textContent.trim()} · MCP Governance`;
      if (moved) { h1.tabIndex = -1; h1.focus(); }
    }
    out.after?.();
  } catch (error) {
    if (seq === routeSeq) view.innerHTML = String(html`<div class="note bad">${error.message}</div>`);
  }
}
const reload = () => route();

/** Remember the open tab in the address, without a reload. */
function rememberTab(key) {
  const q = new URLSearchParams(current.query);
  q.set("t", key);
  current.query = q;
  history.replaceState(null, "", `#/${current.page}${current.arg ? `/${encodeURIComponent(current.arg)}` : ""}?${q}`);
}

async function refreshBadges() {
  try {
    const o = await gw("overview");
    badges.approvals = o.pending_approvals;
    badges.termination = (o.termination?.open_cases || 0) + (o.termination?.awaiting_close || 0);
    renderNav($("#view").dataset.page);
  } catch { /* badges are a convenience; the pages show the real numbers */ }
}

// ── shared pieces ────────────────────────────────────────────────────────────
const modeChip = (mode) => chip(mode === "enforce" ? "allow" : "alert", mode === "enforce" ? "집행 모드" : "관찰 모드");

function decisionRow(r) {
  return html`<tr class="clickable" tabindex="0" data-act="decision" data-id="${r.id}">
    <td class="t">${when(r.at, { seconds: true })}</td>
    <td>${decisionChip(r.decision)}</td>
    <td class="who-cell"><b>${r.who}</b>${r.workstation ? html`<span class="sub mono">${r.workstation}</span>` : ""}</td>
    <td>${r.agent === "termination-probe" ? chip("approval", "종료 점검") : r.harness ? chip("plain", harnessLabel(r.harness)) : html`<span class="muted">—</span>`}</td>
    <td><code>${r.server}.${r.tool}</code></td>
    <td class="clip"><span class="muted">${r.target ? short(r.target, 70) : "—"}</span></td>
    <td class="mono small">${r.policy_id}</td></tr>`;
}
const decisionTable = (rows, id = "") => html`<table class="data"><thead><tr><th>시각</th><th>판정</th><th>사람</th><th>하네스</th>
  <th>도구</th><th>대상</th><th>정책</th></tr></thead><tbody ${id ? raw(`id="${id}"`) : ""}>${rows.map(decisionRow)}</tbody></table>`;

function serverTile(s) {
  const tone = { READY: "ok", DRIFT: "warn", PENDING: "warn" }[s.status] || "bad";
  const retired = s.lifecycle && s.lifecycle !== "OPERATING";
  return html`<a class="tile" href="#/servers/${s.id}">
    <div class="top"><span class="dot ${tone}"></span><b>${s.display_name}</b></div>
    <div class="row-actions"><span class="chip outline mono">${s.id}</span>
      ${s.status !== "READY" ? chip("alert", SERVER_STATUS[s.status] || s.status) : ""}
      ${s.deployment === "provider" ? chip("brand", "제공자 운영") : ""}
      ${retired ? chip(s.lifecycle === "RETIRED" ? "block" : "alert", LIFECYCLE[s.lifecycle] || s.lifecycle) : ""}</div>
    <div class="stats"><span><b>${s.calls ?? 0}</b>호출</span><span><b>${s.blocked ?? 0}</b>차단</span><span><b>${s.tools ?? 0}</b>도구</span></div>
  </a>`;
}

// ── pages ────────────────────────────────────────────────────────────────────
const ROUTES = {};

ROUTES.overview = async (_, tab) => {
  const [o, blocked] = await Promise.all([gw("overview"), gw("activity?limit=10&decision=Block")]);
  feed.rows = mergeRows([], blocked.rows);
  const t = o.today;
  const shadow = o.workstations.reduce((s, w) => s + Number(w.shadow || 0), 0);
  const buckets = hourBuckets(o.series);
  const byServer = splitBy(o.flows, "server", (r) => Number(r.n));
  const flowTotal = o.flows.reduce((s, f) => s + Number(f.n || 0), 0);
  const term = o.termination || {};
  const stations = o.workstations;
  return {
    html: page({
      head: head("개요", { status: html`${modeChip(o.enforcement)}${chip("outline", `카탈로그 ${o.catalog_version}`)}` }),
      kpis: kpiStrip([["오늘 호출", t.total], ["허용", t.Allow, "allow"], ["경보", t.Alert, "alert"], ["차단", t.Block, "block"],
        ["승인 대기", o.pending_approvals, "approval", "#/approvals"], ["섀도 MCP", shadow, shadow ? "block" : "", "#/people?t=configs"]]),
      active: tab || "traffic",
      tabs: [
        { key: "traffic", label: "트래픽", body: html`<div class="stack">
          ${panel("시간대별 판정", chartBox("c-traffic", "최근 24시간 시간대별 판정 건수", "lg"), { sub: "최근 24시간" })}
          <div class="grid c12">
            ${panel("판정 비율", chartBox("c-share", "오늘 판정 비율", "sm"), { sub: "오늘" })}
            ${panel("서버별 호출", chartBox("c-servers", "최근 24시간 서버별 호출과 판정", "sm"), { sub: `${byServer.length}개 서버 · 24시간` })}
          </div></div>` },
        { key: "flow", label: "하네스·서버", n: stations.length, body: html`<div class="stack">
          ${panel("하네스 → MCP 서버 → 판정", flowTotal ? chartBox("c-flow", "하네스에서 서버를 거쳐 판정까지의 호출 흐름", "xl") : empty("최근 24시간 호출 없음"), { sub: `${flowTotal}건 · 24시간` })}
          ${panel("직원 PC", html`<table class="data"><thead><tr><th>단말</th><th>사용자</th><th>하네스</th><th class="num">24시간 호출</th><th>섀도 MCP</th><th>마지막 호출</th></tr></thead><tbody>
            ${stations.map((w) => html`<tr><td class="mono">${w.endpoint_id}</td><td><b>${w.display_name || w.owner_token}</b><span class="sub">${w.department || ""}</span></td>
              <td>${w.harness ? chip("plain", harnessLabel(w.harness)) : html`<span class="muted">—</span>`}</td><td class="num">${w.calls}</td>
              <td>${Number(w.shadow) ? chip("block", `${w.shadow}건`) : chip("allow", "없음")}</td><td class="small">${ago(w.last_call)}</td></tr>`)}
            </tbody></table>${stations.length ? "" : empty("등록된 단말 없음")}`, { flush: true })}</div>` },
        { key: "risk", label: "위험", n: t.Block, hot: t.Block > 0, body: html`<div class="stack">
          <div class="grid c2">
            ${panel("많이 걸린 정책", o.top_policies.length ? chartBox("c-policies", "최근 24시간 차단·경보가 많은 정책") : empty("최근 24시간 차단·경보 없음"), { sub: "차단·경보 · 24시간" })}
            ${panel("종료·폐기", chartBox("c-term", "종료·폐기 현황"), { tools: html`<a class="btn sm" href="#/termination">열기</a>` })}
          </div>
          ${panel("최근 차단", feed.rows.length ? decisionTable(feed.rows) : empty("차단 기록 없음"), { flush: true, tools: html`<a class="btn sm" href="#/activity?decision=Block">전체</a>` })}
        </div>` },
      ],
    }),
    charts: {
      "c-traffic": () => charts.decisionColumns(buckets.map((b) => b.label), buckets),
      "c-share": () => charts.donut(DECISIONS.map((d) => ({ name: DECISION_LABEL[d], value: t[d], color: charts.color(d) }))),
      "c-servers": () => charts.decisionColumns(byServer.map((g) => g.key), byServer, {
        horizontal: true, onClick: (p) => { location.hash = `#/activity?server=${encodeURIComponent(p.name)}`; } }),
      "c-flow": () => charts.sankey(sankeyData(o.flows, (d) => DECISION_LABEL[d] || d)),
      "c-policies": () => charts.bars(o.top_policies.map((p) => ({ name: p.policy_id, value: Number(p.n), color: charts.color(p.decision) }))),
      "c-term": () => charts.columns([
        { name: "진행", value: term.open_cases }, { name: "종결 대기", value: term.awaiting_close },
        { name: "T2·T3", value: term.unresolved_grades, color: charts.color("Alert") }, { name: "기한 초과", value: term.overdue, color: charts.color("Block") },
        { name: "폐기 잔존", value: term.retired_residue, color: charts.color("Alert") }, { name: "섀도", value: term.shadow_endpoints, color: charts.color("Block") }]),
    },
  };
};

// Activity keeps its rows between renders so live updates and the detail drawer
// read from the same list. Paused, it keeps polling but holds new rows back and
// counts them, so the list stops moving without going stale.
const feed = { rows: [], pending: [], cursor: 0, filters: { decision: "", server: "", person: "" }, query: "",
  live: true, servers: [], lastOk: 0, failing: false, gen: 0 };
let liveTimer = null;
function stopLive() { clearInterval(liveTimer); liveTimer = null; feed.gen += 1; }
const feedQuery = (extra) => new URLSearchParams({ ...Object.fromEntries(Object.entries(feed.filters).filter(([, v]) => v)), ...extra });

/** Calls over the loaded span in at most ~30 buckets (1, 5, 10, 30 or 60 minutes). */
function minuteBuckets(rows) {
  if (!rows.length) return [];
  const times = rows.map((r) => new Date(r.at).getTime()).filter(Number.isFinite);
  const [start, end] = [Math.min(...times), Math.max(...times)];
  const step = [1, 5, 10, 30, 60, 180].find((m) => (end - start) / (m * 60e3) <= 30) * 60e3 || 360 * 60e3;
  const first = Math.floor(start / step) * step;
  const buckets = [];
  for (let at = first; at <= end; at += step) {
    const d = new Date(at);
    buckets.push({ at, label: `${pad(d.getHours())}:${pad(d.getMinutes())}`, ...Object.fromEntries(DECISIONS.map((x) => [x, 0])) });
  }
  for (const r of rows) {
    const b = buckets[Math.floor((new Date(r.at).getTime() - first) / step)];
    if (b && DECISIONS.includes(r.decision)) b[r.decision] += 1;
  }
  return buckets;
}

function renderFeedStatus() {
  const status = $("#feed-status");
  if (!status) return;
  const shown = searchRows(feed.rows, feed.query).length;
  status.textContent = `${shown}/${feed.rows.length}건 · ${liveLabel({ ...feed, pending: feed.pending.length })}`;
  $("#feed-dot").className = `dot ${feed.failing ? "bad" : feed.live ? "on" : ""}`;
}

function feedCharts() {
  const shown = searchRows(feed.rows, feed.query);
  const buckets = minuteBuckets(shown);
  return {
    "c-minutes": () => charts.decisionColumns(buckets.map((b) => b.label), buckets),
    "c-by-server": () => { const g = splitBy(shown, "server"); return charts.decisionColumns(g.map((x) => x.key), g, { horizontal: true }); },
    "c-by-person": () => { const g = splitBy(shown, "who"); return charts.decisionColumns(g.map((x) => x.key), g, { horizontal: true }); },
    "c-by-harness": () => charts.donut(splitBy(shown, (r) => harnessLabel(r.harness)).map((g, i) => ({
      name: g.key, value: g.total, color: ["#1f4287", "#2c5bb8", "#4f7fd6", "#86a8ff", "#9aa6b8", "#647085"][i % 6] }))),
  };
}

function renderFeed() {
  const body = $("#feed");
  if (!body) return;
  const focused = document.activeElement?.closest?.("#feed tr")?.dataset.id;
  const shown = searchRows(feed.rows, feed.query);
  body.innerHTML = String(html`${shown.map(decisionRow)}`);
  if (focused) $(`#feed tr[data-id="${CSS.escape(focused)}"]`)?.focus();
  const note = $("#feed-empty");
  note.hidden = shown.length > 0;
  note.innerHTML = String(feed.rows.length || feed.query || Object.values(feed.filters).some(Boolean)
    ? html`조건에 맞는 호출 없음 <button class="btn sm" type="button" data-act="feed-reset">조건 초기화</button>` : html`호출 없음`);
  for (const [id, build] of Object.entries(feedCharts())) charts.redraw(id, build);
  renderFeedStatus();
}

function startLive() {
  stopLive();
  const gen = feed.gen;
  liveTimer = setInterval(async () => {
    try {
      const data = await gw(`activity?${feedQuery({ after: feed.cursor, limit: 100 })}`);
      if (gen !== feed.gen) return;  // the page was rebuilt while this poll was in flight
      feed.cursor = Math.max(feed.cursor, data.cursor || 0);
      feed.lastOk = Date.now();
      feed.failing = false;
      if (feed.live) feed.rows = mergeRows(feed.rows, data.rows);
      else feed.pending = mergeRows(feed.pending, data.rows);
      if (feed.live && data.rows.length) renderFeed(); else renderFeedStatus();
    } catch {
      // A failed poll must not end the live view, and must not look like a quiet one.
      if (gen === feed.gen) { feed.failing = true; renderFeedStatus(); }
    }
  }, 3000);
}

ROUTES.activity = async (_, tab, query) => {
  for (const key of ["decision", "server", "person"]) if (query.has(key)) feed.filters[key] = query.get(key);
  const data = await gw(`activity?${feedQuery({ limit: 200 })}`);
  feed.rows = mergeRows([], data.rows);
  feed.pending = [];
  feed.cursor = data.cursor;
  feed.lastOk = Date.now();
  feed.failing = false;
  if (viewer.admin && !feed.servers.length) feed.servers = (await gw("registry")).servers.map((s) => s.id);
  const servers = viewer.admin ? feed.servers : [...new Set(feed.rows.map((r) => r.server))].sort();
  const option = (value, label, cur) => html`<option value="${value}" ${value === cur ? raw("selected") : ""}>${label}</option>`;
  const f = feed.filters;
  return {
    html: page({
      head: head("활동 로그", {
        status: html`<span class="live"><span class="dot" id="feed-dot"></span><span id="feed-status"></span></span>`,
        actions: html`<button class="btn" type="button" data-act="live" aria-pressed="${String(!feed.live)}">${feed.live ? "일시정지" : "실시간 재개"}</button>
          ${viewer.admin ? html`<button class="btn" data-act="audit-verify">감사 체인 검증</button>` : ""}`,
      }),
      active: tab || "live",
      tabs: [
        { key: "live", label: "호출", body: html`<section class="panel">
          <div class="filters">
            <input class="grow" data-feed-search type="search" maxlength="120" value="${feed.query}" placeholder="사람·단말·하네스·도구·대상·정책·trace" aria-label="불러온 기록에서 찾기" />
            <select data-filter="decision" aria-label="판정">${option("", "모든 판정", f.decision)}
              ${Object.entries(DECISION).map(([k, [, label]]) => option(k, label, f.decision))}</select>
            <select data-filter="server" aria-label="서버">${option("", "모든 서버", f.server)}${servers.map((s) => option(s, s, f.server))}</select>
            ${viewer.admin ? html`<input data-filter="person" type="search" placeholder="사람" value="${f.person}" aria-label="사람" />` : ""}
          </div>
          <div class="body">${chartBox("c-minutes", "불러온 호출의 시간 분포", "sm")}</div>
          <div class="body flush">${decisionTable([], "feed")}<p class="empty" id="feed-empty" hidden></p></div></section>` },
        { key: "stats", label: "분석", body: html`<div class="stack"><div class="grid c2">
          ${panel("서버별", chartBox("c-by-server", "불러온 호출의 서버별 판정"))}
          ${panel("하네스별", chartBox("c-by-harness", "불러온 호출의 하네스별 비율"))}</div>
          ${panel("사람별", chartBox("c-by-person", "불러온 호출의 사람별 판정", "lg"))}</div>` },
      ],
    }),
    charts: feedCharts(),
    after: () => { renderFeed(); startLive(); },
  };
};

function showDecision(id) {
  const r = feed.rows.find((row) => String(row.id) === String(id));
  if (!r) return;
  openDrawer(`판정 #${r.id}`, html`<div class="row-actions">${decisionChip(r.decision)}${chip("outline", r.outcome)}</div>`, [
    { key: "summary", label: "요약", body: html`<p class="note">${r.reason}</p>${kv([
      ["시각", new Date(r.at).toLocaleString("ko-KR")], ["사람", `${r.who}${r.department ? ` · ${r.department}` : ""}`],
      ["역할", ROLE[r.role] || r.role], ["단말", r.workstation], ["하네스", r.harness ? harnessLabel(r.harness) : r.agent],
      ["도구", html`<code>${r.server}.${r.tool}</code>`], ["대상", r.target ? html`<code>${r.target}</code>` : ""]])}` },
    { key: "policy", label: "분류·정책", body: kv([
      ["행위", `${r.action_ko || "—"} (${r.action || "?"})`], ["데이터 등급", r.data_class_ko], ["분류 근거", r.summary],
      ["위험 점수", `${r.risk_score ?? 0} / 100`], ["개인정보", (r.privacy_types || []).join(", ")], ["연쇄 표지", (r.sequence_flags || []).join(", ")],
      ["정책", html`<code>${r.policy_id}</code>`], ["예외", r.exception_id], ["승인 요청", r.approval_id],
      ["집행 모드", r.enforcement], ["집행 시 판정", r.would_decision]]) },
    { key: "trace", label: "추적", body: html`${kv([["trace", r.trace_id ? html`<code>${r.trace_id}</code>` : ""], ["오류", r.error], ["작업", r.task_id]])}${json(r)}` },
  ]);
}

let approvalRows = [];
ROUTES.approvals = async (_, tab) => {
  const { approvals, history } = await api("/approvals");
  approvalRows = approvals;
  const counted = splitBy(history, (h) => (APPROVAL_STATUS[h.status] || ["", h.status])[1]);
  const byServer = splitBy([...approvals, ...history], "server_id");
  const oldest = approvals.reduce((m, a) => Math.min(m, new Date(a.created_at).getTime()), Date.now());
  return {
    html: page({
      head: head("승인 대기"),
      kpis: kpiStrip([["대기", approvals.length, approvals.length ? "approval" : ""],
        ["가장 오래된 대기", approvals.length ? ago(oldest) : "—"], ["처리 이력", history.length]]),
      active: tab || "queue",
      tabs: [
        { key: "queue", label: "대기", n: approvals.length, hot: approvals.length > 0, body: panel("승인 요청", approvals.length ? html`<table class="data">
          <thead><tr><th>요청자</th><th>도구</th><th>행위 · 등급</th><th>하네스</th><th>요청</th><th>만료</th><th></th></tr></thead><tbody>
          ${approvals.map((a) => html`<tr class="clickable" tabindex="0" data-act="approval" data-id="${a.id}">
            <td class="who-cell"><b>${a.display_name || a.requested_by}</b><span class="sub">${a.department || ""}</span></td>
            <td><code>${a.server_id}.${a.tool}</code></td>
            <td>${ACTION[a.action] || a.action || "—"} · ${DATA_CLASS[a.data_class] || a.data_class || "—"}</td>
            <td>${a.client?.harness?.name ? chip("plain", harnessLabel(a.client.harness.name)) : "—"}</td>
            <td class="small">${ago(a.created_at)}</td><td class="small">${when(a.expires_at)}</td>
            <td class="num nowrap"><button class="btn sm danger" data-act="reject" data-id="${a.id}">거부</button>
              <button class="btn sm primary" data-act="approve" data-id="${a.id}">승인·실행</button></td></tr>`)}
          </tbody></table>` : empty("대기 중인 요청 없음"), { flush: true }) },
        { key: "history", label: "처리 이력", n: history.length, body: html`<div class="stack"><div class="grid c12">
          ${panel("결과", history.length ? chartBox("c-appr-status", "처리된 승인 요청의 결과 비율", "sm") : empty("이력 없음"))}
          ${panel("서버별 요청", byServer.length ? chartBox("c-appr-server", "서버별 승인 요청 수", "sm") : empty("요청 없음"))}</div>
          ${panel("이력", history.length ? html`<table class="data"><thead><tr><th>요청자</th><th>도구</th><th>결과</th><th>처리</th><th>검토자</th></tr></thead><tbody>
            ${history.map((h) => html`<tr><td class="who-cell"><b>${h.display_name || h.requested_by}</b><span class="sub">${h.department || ""}</span></td>
              <td><code>${h.server_id}.${h.tool}</code></td><td>${chip(...(APPROVAL_STATUS[h.status] || ["", h.status]))}</td>
              <td class="small">${when(h.reviewed_at || h.created_at)}</td><td class="small">${h.reviewed_by || "—"}</td></tr>`)}</tbody></table>` : "", { flush: true })}</div>` },
      ],
    }),
    charts: {
      "c-appr-status": () => charts.donut(counted.map((g) => ({ name: g.key, value: g.total,
        color: charts.color({ 승인: "Allow", 실행됨: "Allow", 거부: "Block" }[g.key] || "Alert") }))),
      "c-appr-server": () => charts.bars(byServer.map((g) => ({ name: g.key, value: g.total })), { tone: "--approval" }),
    },
  };
};

function showApproval(id) {
  const a = approvalRows.find((row) => row.id === id);
  if (!a) return;
  openDrawer(`${a.server_id}.${a.tool}`, html`<div class="row-actions">
    <button class="btn danger" data-act="reject" data-id="${a.id}">거부</button>
    <button class="btn primary" data-act="approve" data-id="${a.id}">승인·실행</button></div>`, [
    { key: "request", label: "요청", body: kv([["요청자", `${a.display_name || a.requested_by}${a.department ? ` · ${a.department}` : ""}`],
      ["단말", a.client?.workstation], ["하네스", a.client?.harness?.name ? harnessLabel(a.client.harness.name) : a.client?.agent],
      ["요청", when(a.created_at, { seconds: true })], ["만료", when(a.expires_at)]]) },
    { key: "args", label: "인자", body: json(a.arguments) },
    { key: "policy", label: "정책", body: html`${a.reason ? html`<p class="note">${a.reason}</p>` : ""}${kv([
      ["정책", html`<code>${a.policy_id || "—"}</code>`], ["행위", ACTION[a.action] || a.action], ["데이터 등급", DATA_CLASS[a.data_class] || a.data_class],
      ["분류 근거", a.summary]])}` },
  ]);
}

let registry = null;
ROUTES.servers = async (id, tab, query) => {
  const [reg, o] = await Promise.all([gw("registry"), gw("overview")]);
  registry = reg;
  const counts = Object.fromEntries(o.servers.map((s) => [s.id, s]));
  const servers = reg.servers.map((s) => ({ ...s, ...(counts[s.id] ? { calls: counts[s.id].calls, blocked: counts[s.id].blocked, tools: counts[s.id].tools } : {}) }));
  const byServer = splitBy(o.flows, "server", (r) => Number(r.n));
  const toolFilter = query.get("server") || "";
  const tools = reg.tools.filter((t) => !toolFilter || t.server_id === toolFilter);
  const actionSplit = reg.servers.map((s) => {
    const own = reg.tools.filter((t) => t.server_id === s.id && t.enabled);
    return { key: s.id, r: own.filter((t) => t.action === "r").length, w: own.filter((t) => t.action === "w").length, x: own.filter((t) => t.action === "x").length };
  });
  const contract = { ok: reg.tools.filter((t) => t.enabled && t.contract_ok).length,
    drift: reg.tools.filter((t) => t.enabled && t.pinned && !t.contract_ok).length, off: reg.tools.filter((t) => !t.enabled).length };
  const drifted = servers.filter((s) => s.status !== "READY");
  const option = (value, label) => html`<option value="${value}" ${value === toolFilter ? raw("selected") : ""}>${label}</option>`;
  return {
    html: page({
      head: head("MCP 서버", { status: chip("outline", `카탈로그 ${reg.catalog_version}`),
        actions: html`<button class="btn" data-act="catalog-refresh">계약 다시 확인</button>` }),
      active: tab || "servers",
      tabs: [
        { key: "servers", label: "서버", n: servers.length, body: html`<div class="stack">
          ${panel("서버별 호출", byServer.length ? chartBox("c-srv-calls", "최근 24시간 서버별 호출과 판정") : empty("최근 24시간 호출 없음"), { sub: "24시간" })}
          <div class="tiles">${servers.map(serverTile)}</div></div>` },
        { key: "tools", label: "도구", n: reg.tools.length, body: html`<div class="stack">
          ${panel("서버별 도구 (행위)", chartBox("c-srv-actions", "서버별 승인 도구 수를 읽기·쓰기·실행으로 나눈 막대"))}
          ${panel("도구", html`<table class="data"><thead><tr><th>서버</th><th>도구</th><th>행위</th><th>상태</th></tr></thead><tbody>
            ${tools.map((t) => html`<tr><td class="mono">${t.server_id}</td><td><code>${t.name}</code></td>
              <td>${chip({ r: "allow", w: "alert", x: "block" }[t.action] || "", ACTION[t.action] || t.action)}</td>
              <td>${!t.enabled ? chip("outline", "미승인") : t.contract_ok ? chip("allow", "계약 일치") : chip("alert", "계약 불일치")}</td></tr>`)}
            </tbody></table>`, { flush: true, sub: `${tools.length}개`,
            tools: html`<select data-act-change="tool-filter" aria-label="서버">${option("", "모든 서버")}${reg.servers.map((s) => option(s.id, s.id))}</select>` })}</div>` },
        { key: "contract", label: "계약", n: drifted.length, hot: drifted.length > 0, body: html`<div class="stack"><div class="grid c12">
          ${panel("도구 계약", chartBox("c-contract", "승인 도구의 계약 일치 비율", "sm"))}
          ${panel("서버 상태", html`<table class="data"><thead><tr><th>서버</th><th>상태</th><th>사유</th><th>마지막 확인</th><th></th></tr></thead><tbody>
            ${servers.map((s) => html`<tr><td><b>${s.display_name}</b><span class="sub mono">${s.id}</span></td>
              <td>${chip({ READY: "allow", DRIFT: "alert" }[s.status] || "block", SERVER_STATUS[s.status] || s.status)}</td>
              <td class="small clip">${s.status_reason || "—"}</td><td class="small">${ago(s.last_seen_at)}</td>
              <td class="num">${s.status === "DRIFT" ? html`<button class="btn sm primary" data-act="approve-contract" data-id="${s.id}">승인본 갱신</button>` : ""}</td></tr>`)}
            </tbody></table>`, { flush: true })}</div></div>` },
      ],
    }),
    charts: {
      "c-srv-calls": () => charts.decisionColumns(byServer.map((g) => g.key), byServer, { horizontal: true }),
      "c-srv-actions": () => charts.stacked(actionSplit.map((a) => a.key), [
        { name: "읽기", color: charts.color("Allow"), data: actionSplit.map((a) => a.r) },
        { name: "쓰기", color: charts.color("Alert"), data: actionSplit.map((a) => a.w) },
        { name: "외부전송·실행", color: charts.color("Block"), data: actionSplit.map((a) => a.x) }]),
      "c-contract": () => charts.donut([{ name: "계약 일치", value: contract.ok, color: charts.color("Allow") },
        { name: "계약 불일치", value: contract.drift, color: charts.color("Alert") }, { name: "미승인", value: contract.off, color: charts.color() }]),
    },
    after: () => id && showServer(id),
  };
};

function showServer(id) {
  const s = registry?.servers.find((row) => row.id === id);
  if (!s) return;
  const tools = registry.tools.filter((t) => t.server_id === id);
  const rels = registry.usage_relationships.filter((u) => u.server_id === id);
  const terms = s.exit_terms || {};
  const creds = s.server_held_credentials || [];
  openDrawer(s.display_name, html`<div class="row-actions">${chip({ READY: "allow", DRIFT: "alert" }[s.status] || "block", SERVER_STATUS[s.status] || s.status)}
      ${chip(s.lifecycle === "OPERATING" ? "outline" : "block", LIFECYCLE[s.lifecycle] || s.lifecycle)}
      ${chip("outline", s.deployment === "provider" ? "제공자 운영" : "사내 운영")}
      ${s.status === "DRIFT" ? html`<button class="btn sm primary" data-act="approve-contract" data-id="${s.id}">승인본 갱신</button>` : ""}</div>
    ${s.status_reason && s.status !== "READY" ? html`<p class="note warn">${s.status_reason}</p>` : ""}`, [
    { key: "info", label: "개요", body: kv([["id", html`<code>${s.id}</code>`], ["Gateway 경로", html`<code>/mcp/${s.id}/</code>`],
      ["패키지", html`<code>${s.source_ref || `${s.package}@${s.version}`}</code>`], ["upstream", html`<code>${s.endpoint}</code>`],
      ["공급자", s.supplier], ["라이선스", s.license], ["하위 시스템", s.downstream ? JSON.stringify(s.downstream) : ""],
      ["마지막 확인", s.last_seen_at ? `${when(s.last_seen_at)} · ${ago(s.last_seen_at)}` : ""]]) },
    { key: "tools", label: "도구", n: tools.length, body: html`<table class="data"><thead><tr><th>도구</th><th>행위</th><th>상태</th></tr></thead><tbody>
      ${tools.map((t) => html`<tr><td><code>${t.name}</code></td><td>${chip({ r: "allow", w: "alert", x: "block" }[t.action] || "", ACTION[t.action] || t.action)}</td>
        <td>${!t.enabled ? chip("outline", "미승인") : t.contract_ok ? chip("allow", "일치") : chip("alert", "불일치")}</td></tr>`)}</tbody></table>` },
    { key: "exit", label: "종료 조건", body: html`<div class="pill-list">${Object.entries(EXIT_TERMS).map(([k, label]) => bool(terms[k], label))}</div>
      ${creds.length ? kv([["보유 자격", html`${creds.map((c) => html`<code>${c.id}</code> `)}`]]) : ""}
      ${rels.length ? html`<h3>이용 관계</h3>${kv(rels.map((u) => [u.id, `${u.purpose} · ${u.organization} · ${u.status}`]))}
        <div class="row-actions"><a class="btn sm" href="#/termination">종료·폐기</a></div>` : ""}` },
  ]);
}

let peopleAccounts = [];
ROUTES.people = async (_, tab, query) => {
  const [{ accounts }, inv, o] = await Promise.all([api("/api/accounts"), gw("endpoint/inventory"), gw("overview")]);
  peopleAccounts = accounts;
  const cls = (c) => chip(...(ENDPOINT_CLASS[c] || ["", c]));
  const harnessOf = Object.fromEntries(o.workstations.map((w) => [w.endpoint_id, w]));
  const shadow = inv.entries.filter((e) => e.classification === "shadow").length;
  const residue = inv.entries.filter((e) => e.classification === "retired-residue").length;
  const only = query.get("class") || "";
  const entries = inv.entries.filter((e) => !only || e.classification === only);
  const byHarness = splitBy(o.flows, (f) => harnessLabel(f.harness), (f) => Number(f.n));
  const segment = (value, label) => html`<button type="button" data-act="class-filter" data-class="${value}" aria-pressed="${String(only === value)}">${label}</button>`;
  return {
    html: page({
      head: head("직원·단말", { actions: html`<button class="btn" type="button" data-act="device-issue">장치 자격 발급</button>` }),
      kpis: kpiStrip([["단말", inv.coverage.known_endpoints], ["최근 15분 보고", inv.coverage.reporting_recently],
        ["섀도 MCP", shadow, shadow ? "block" : ""], ["폐기 잔존", residue, residue ? "alert" : ""]]),
      active: tab || "devices",
      tabs: [
        { key: "devices", label: "단말", n: inv.agents.length, body: html`<div class="stack"><div class="grid c21">
          ${panel("단말별 호출", o.workstations.length ? chartBox("c-ws-calls", "최근 24시간 단말별 호출 수", "sm") : empty("단말 없음"), { sub: "24시간" })}
          ${panel("하네스", byHarness.length ? chartBox("c-harness", "최근 24시간 하네스별 호출 비율", "sm") : empty("호출 없음"), { sub: "24시간" })}</div>
          ${panel("단말", html`<table class="data"><thead><tr><th>단말</th><th>소유자</th><th>하네스</th><th class="num">설정</th><th>섀도</th><th>잔존</th><th>마지막 보고</th><th></th></tr></thead><tbody>
            ${inv.agents.map((a) => html`<tr><td class="mono">${a.endpoint_id}<span class="sub">${a.platform || ""}</span></td><td>${harnessOf[a.endpoint_id]?.display_name || a.owner_token || "—"}</td>
              <td>${harnessOf[a.endpoint_id]?.harness ? chip("plain", harnessLabel(harnessOf[a.endpoint_id].harness)) : "—"}</td><td class="num">${a.entries}</td>
              <td>${Number(a.shadow) ? chip("block", a.shadow) : "0"}</td><td>${Number(a.residue) ? chip("alert", a.residue) : "0"}</td>
              <td class="small">${ago(a.last_seen_at)}</td>
              <td class="num">${a.status === "revoked" ? chip("outline", "폐기됨") : html`<button class="btn sm danger" type="button" data-act="device-revoke" data-id="${a.endpoint_id}">자격 폐기</button>`}</td></tr>`)}
            </tbody></table>${inv.agents.length ? "" : empty("보고한 단말 없음")}`, { flush: true })}</div>` },
        { key: "configs", label: "MCP 설정", n: inv.entries.length, body: html`<div class="stack"><div class="grid c12">
          ${panel("분류", inv.entries.length ? chartBox("c-classes", "단말 MCP 설정의 분류 비율", "sm") : empty("보고된 설정 없음"))}
          ${panel("하네스 설정 파일", inv.entries.length ? chartBox("c-config-files", "설정 파일별 서버 항목 수", "sm") : empty("보고된 설정 없음"))}</div>
          ${panel("설정 항목", html`<table class="data"><thead><tr><th>단말</th><th>설정 파일</th><th>서버</th><th>연결</th><th>분류</th></tr></thead><tbody>
            ${entries.map((e) => html`<tr><td class="mono">${e.endpoint_id}</td><td class="small mono">${e.config_path}</td>
              <td><b>${e.server_label}</b>${e.registry_name ? html`<span class="sub">${e.registry_name}</span>` : ""}</td>
              <td class="small mono clip">${e.transport} ${short(e.endpoint_ref, 60)}</td><td>${cls(e.classification)}</td></tr>`)}
            </tbody></table>${entries.length ? "" : empty("항목 없음")}`, { flush: true,
            tools: html`<div class="seg" role="group" aria-label="분류">${segment("", "전체")}${segment("shadow", "섀도")}${segment("retired-residue", "잔존")}${segment("registered", "Gateway 경유")}</div>` })}</div>` },
        { key: "accounts", label: "계정", n: accounts.length, body: panel("계정", html`<table class="data"><thead><tr><th>이름</th><th>이메일</th><th>역할</th><th>부서</th><th>상태</th><th></th></tr></thead><tbody>
          ${accounts.map((a) => html`<tr><td><b>${a.display_name}</b><span class="sub">${a.job_title || ""}</span></td><td class="small">${a.email}</td>
            <td>${ROLE[a.role] || a.role}</td><td>${a.department}</td>
            <td>${chip({ active: "allow", disabled: "block", locked: "alert" }[a.status] || "", { active: "사용", disabled: "중지", locked: "잠김" }[a.status] || a.status)}</td>
            <td class="num">${a.user_id === viewer.user_id ? html`<span class="small muted">본인</span>`
              : html`<button class="btn sm" data-act="account-status" data-id="${a.user_id}" data-name="${a.display_name}" data-status="${a.status}">상태 변경</button>`}</td></tr>`)}
          </tbody></table>`, { flush: true }) },
      ],
    }),
    charts: {
      "c-ws-calls": () => charts.bars(o.workstations.map((w) => ({ name: `${w.endpoint_id} · ${w.display_name || ""}`, value: Number(w.calls) }))),
      "c-harness": () => charts.donut(byHarness.map((g, i) => ({ name: g.key, value: g.total,
        color: ["#1f4287", "#2c5bb8", "#4f7fd6", "#86a8ff", "#9aa6b8", "#647085"][i % 6] }))),
      "c-classes": () => charts.donut(Object.entries(ENDPOINT_CLASS).map(([k, [tone, label]]) => ({ name: label,
        value: inv.entries.filter((e) => e.classification === k).length, color: charts.color({ allow: "Allow", block: "Block", alert: "Alert" }[tone]) }))),
      "c-config-files": () => charts.bars(splitBy(inv.entries, (e) => e.config_path.split("/").slice(-2).join("/")).map((g) => ({ name: g.key, value: g.total }))),
    },
  };
};

// ── intake ───────────────────────────────────────────────────────────────────
ROUTES.intake = async (_, tab) => {
  const { requests } = await api("/api/mcp-requests");
  const byStatus = Object.entries(INTAKE_STATUS).map(([k, [tone, label]]) => ({ name: label, value: requests.filter((r) => r.status === k).length,
    color: charts.color({ allow: "Allow", block: "Block", alert: "Alert", approval: "Approval", restrict: "Restrict" }[tone]) }));
  return {
    html: page({
      head: head("도입 신청"),
      active: tab || "list",
      tabs: [
        { key: "list", label: viewer.admin ? "전체 신청" : "내 신청", n: requests.length, body: html`<div class="stack">
          ${panel("상태", requests.length ? chartBox("c-intake", "도입 신청의 상태별 건수", "sm") : empty("신청 없음"))}
          ${panel("신청", html`<table class="data"><thead><tr><th>서버</th><th>상태</th><th>종료 조건</th><th>신청</th>${viewer.admin ? html`<th></th>` : ""}</tr></thead><tbody>
          ${requests.map((r) => {
            const remote = r.requested_transport !== "stdio";
            const verified = termsVerified(r.exit_terms);
            const open = ["HOLD", "VALIDATION_QUEUED", "VALIDATING", "VALIDATED"].includes(r.status);
            return html`<tr><td><b>${r.display_name}</b><span class="sub mono">${r.repository_url}</span>
              <span class="sub">${r.requested_transport}${r.risk_level ? ` · 위험 ${r.risk_level}` : ""}${r.commit_sha ? ` · ${r.commit_sha.slice(0, 12)}` : ""}</span></td>
            <td>${chip(...(INTAKE_STATUS[r.status] || ["", r.status]))}</td>
            <td class="small">${!remote ? html`<span class="muted">로컬</span>` : r.exit_terms?.verified_by
              ? html`${chip(verified ? "allow" : "block", verified ? "검증됨" : "미충족")} <span class="muted">${Object.keys(EXIT_TERMS).filter((k) => r.exit_terms[k] === true).length}/3</span>`
              : chip("outline", "미검증")}</td>
            <td class="small">${when(r.created_at)}</td>
            ${viewer.admin ? html`<td class="num nowrap">
              ${r.status === "HOLD" ? html`<button class="btn sm" data-act="intake-queue" data-id="${r.id}">검증 시작</button>` : ""}
              ${remote && open ? html`<button class="btn sm" data-act="intake-terms" data-id="${r.id}" data-name="${r.display_name}">종료 조건</button>` : ""}
              ${r.status === "VALIDATED" && (!remote || verified) ? html`<button class="btn sm primary" data-act="intake-approve" data-id="${r.id}">승인</button>` : ""}
              ${["HOLD", "VALIDATION_QUEUED"].includes(r.status) ? html`<button class="btn sm danger" data-act="intake-reject" data-id="${r.id}">거부</button>` : ""}</td>` : ""}</tr>`;
          })}</tbody></table>${requests.length ? "" : empty("신청 없음")}`, { flush: true })}</div>` },
        { key: "new", label: "새 신청", body: panel("새 신청", html`<form class="stack form" data-form="intake">
          <label>이름<input name="display_name" required minlength="2" maxlength="80" placeholder="Slack MCP" /></label>
          <label>GitHub 저장소<input name="repository_url" required placeholder="https://github.com/org/repo" /></label>
          <label>연결 방식<select name="requested_transport"><option value="streamable-http">Streamable HTTP</option>
            <option value="stdio">stdio</option><option value="sse">SSE</option></select></label>
          <label>도입 목적<textarea name="purpose" required minlength="10" maxlength="1000"></textarea></label>
          <div class="row-actions"><button class="btn primary" type="submit">신청</button></div></form>`) },
      ],
    }),
    charts: { "c-intake": () => charts.columns(byStatus) },
  };
};
// The same rule agent_service.approve_mcp_request enforces; the button only mirrors it.
const termsVerified = (t) => Boolean(t?.verified_by && t?.evidence_url && Object.keys(EXIT_TERMS).every((k) => t[k] === true));

// ── termination ──────────────────────────────────────────────────────────────
ROUTES.termination = async (caseId, tab) => {
  if (caseId) return caseView(caseId, tab);
  const [{ relationships }, { cases, summary }] = await Promise.all([gw("termination/relationships"), gw("termination/cases")]);
  const grades = ["T1", "T2", "T3"].map((g) => ({ name: `${g} ${GRADE[g]}`, value: cases.filter((c) => c.grade === g).length,
    color: charts.color({ T1: "Allow", T2: "Alert", T3: "Block" }[g]) }));
  grades.push({ name: "미판정", value: cases.filter((c) => !c.grade).length, color: charts.color() });
  const readiness = ["T1", "T2", "T3"].map((g) => ({ name: `${g} ${GRADE[g]}`, value: relationships.filter((r) => r.readiness?.best_attainable_grade === g).length,
    color: charts.color({ T1: "Allow", T2: "Alert", T3: "Block" }[g]) }));
  return {
    html: page({
      head: head("종료·폐기"),
      kpis: kpiStrip([["진행 중", summary.open_cases], ["종결 대기", summary.awaiting_close, "approval"],
        ["미해결 T2·T3", summary.unresolved_grades, summary.unresolved_grades ? "alert" : ""],
        [`기한 ${summary.sla_days}일 초과`, summary.overdue, summary.overdue ? "block" : ""],
        ["폐기 잔존", summary.retired_residue, summary.retired_residue ? "alert" : ""], ["섀도 MCP", summary.shadow_endpoints, summary.shadow_endpoints ? "block" : ""]]),
      active: tab || "relationships",
      tabs: [
        { key: "relationships", label: "이용 관계", n: relationships.length, body: html`<div class="stack">
          ${panel("지금 끊으면 도달 가능한 등급", chartBox("c-readiness", "이용 관계별 최선 도달 등급 분포", "sm"))}
          <div class="rels">${relationships.map(relationshipCard)}</div>${relationships.length ? "" : empty("이용 관계 없음")}</div>` },
        { key: "cases", label: "케이스", n: cases.length, body: html`<div class="stack">
          ${panel("등급", cases.length ? chartBox("c-grades", "종료 케이스의 등급 분포", "sm") : empty("케이스 없음"))}
          ${panel("케이스", html`<table class="data"><thead><tr><th>이용 관계</th><th>상태</th><th>등급</th><th class="num">대상</th><th class="num">미회수</th><th class="num">증거</th><th>개시</th></tr></thead><tbody>
            ${cases.map((c) => html`<tr class="clickable" tabindex="0" data-act="open-case" data-id="${c.id}">
              <td><b>${c.display_name}</b><span class="sub mono">${c.relationship_id || c.server_id}</span></td>
              <td>${chip(c.status === "CLOSED" ? "outline" : "approval", CASE_STATUS[c.status] || c.status)}${c.overdue ? chip("block", "기한 초과") : ""}</td>
              <td>${gradeChip(c.grade)}</td><td class="num">${c.targets}</td><td class="num">${c.outstanding}</td><td class="num">${c.evidence}</td>
              <td class="small">${when(c.opened_at)}</td></tr>`)}
            </tbody></table>${cases.length ? "" : empty("케이스 없음")}`, { flush: true })}</div>` },
      ],
    }),
    charts: { "c-grades": () => charts.columns(grades), "c-readiness": () => charts.columns(readiness) },
  };
};

function relationshipCard(r) {
  const ready = r.readiness || {};
  const terms = r.exit_terms || {};
  const revoke = ready.would_revoke || {};
  return html`<article class="rel">
    <div class="line1"><b>${r.purpose}</b><span class="spacer"></span>${gradeChip(ready.best_attainable_grade)}</div>
    <div class="row-actions"><span class="chip outline mono">${r.id}</span>${chip("plain", r.display_name)}
      ${chip(r.deployment === "provider" ? "brand" : "outline", r.deployment === "provider" ? `제공자 ${r.provider}` : "사내")}
      ${r.status !== "ACTIVE" ? chip(r.status === "TERMINATED" ? "block" : "alert", r.status) : ""}</div>
    <div class="facts"><span><b>${r.users}</b>이용자</span><span><b>${r.calls}</b>호출</span>
      <span><b>${(revoke.gateway_access ?? 0) + (revoke.endpoint_configs ?? 0) + (revoke.server_held ?? 0)}</b>회수 대상</span></div>
    ${r.deployment === "provider" ? html`<div class="pill-list">${Object.entries(EXIT_TERMS).map(([k, label]) => bool(terms[k], label))}</div>` : ""}
    ${(ready.blockers || []).length ? html`<ul>${ready.blockers.map((b) => html`<li>${b}</li>`)}</ul>` : ""}
    <div class="row-actions">
      ${r.latest_case ? html`<a class="btn sm" href="#/termination/${r.latest_case}">최근 케이스</a>` : ""}
      ${r.lifecycle === "OPERATING" && r.status === "ACTIVE" ? html`<button class="btn sm danger" data-act="open-termination" data-id="${r.id}" data-name="${r.purpose}" data-grade="${ready.best_attainable_grade}">종료 시작</button>` : ""}
      ${r.lifecycle === "RETIRED" ? html`<button class="btn sm" data-act="lab-restore" data-id="${r.server_id}">실습 복원</button>` : ""}
    </div></article>`;
}

let currentCase = null;
const PROCEDURE = ["이용 관계 확정", "강제 경로 차단", "모집단 열거", "회수 조치", "상태 증거", "판정", "종결"];

function procedureState(d) {
  const c = d.case;
  const stateEvidence = d.evidence.some((e) => e.meaning?.state);
  const unverifiable = d.targets.some((t) => t.status === "UNVERIFIABLE");
  const done = [true, Boolean(c.cutover_at), d.targets.length > 0 && !unverifiable,
    d.targets.length > 0 && d.targets.every((t) => t.status !== "OUTSTANDING"), stateEvidence,
    Boolean(c.grade) && ["ASSESSED", "CLOSED"].includes(c.status), c.status === "CLOSED"];
  const gap = [false, false, unverifiable, false, false, false, false];
  const now = done.indexOf(false);
  return PROCEDURE.map((title, i) => ({ title, done: done[i], gap: gap[i], now: i === now }));
}

async function caseView(caseId, tab) {
  const d = await gw(`termination/cases/${caseId}`);
  currentCase = d;
  const c = d.case;
  const criteria = c.criteria || {};
  const closed = c.status === "CLOSED";
  const act = d.activity || {};
  const outstanding = d.targets.filter((t) => t.status === "OUTSTANDING").length;
  const stateEvidence = d.evidence.filter((e) => e.meaning?.state).length;
  const perCriterion = ["C1", "C2", "C3", "C4"].map((k) => ({ name: `${k} ${CRITERIA[k]}`, met: criteria[k]?.targets_met ?? 0 }));
  return {
    html: page({
      head: html`${head(c.engagement_label, {
        back: html`<a class="back" href="#/termination?t=cases">← 케이스</a>`,
        status: html`${chip(closed ? "outline" : "approval", CASE_STATUS[c.status] || c.status)}${gradeChip(c.grade)}${chip("plain", c.display_name)}`,
        actions: html`${!closed ? html`<button class="btn" data-act="collect">증거 수집</button><button class="btn primary" data-act="assess">판정</button>` : ""}
          ${c.grade ? html`<button class="btn" data-act="report">판정서</button>` : ""}
          ${c.deployment === "provider" ? html`<button class="btn" data-act="disclosure">고지 요청서</button>` : ""}
          ${c.status === "ASSESSED" ? html`<button class="btn danger solid" data-act="close-case">종결</button>` : ""}
          ${closed ? html`<button class="btn" data-act="reopen-case">재개</button><button class="btn" data-act="lab-restore" data-id="${c.server_id}">실습 복원</button>` : ""}` })}
        <ol class="stepper" aria-label="종료 판정 절차">${procedureState(d).map((s, i) => html`
          <li class="step ${s.done ? "done" : ""} ${s.now ? "now" : ""} ${s.gap ? "gap" : ""}"><span class="n">${s.done ? "✓" : i + 1}</span><b>${s.title}</b></li>`)}</ol>`,
      kpis: html`<div class="kpis">${[["회수 대상", d.targets.length], ["미회수", outstanding, outstanding ? "alert" : ""], ["상태 증거", stateEvidence],
        ["차단 후 실행", act.executed, act.executed ? "block" : ""], ["차단 후 거부", act.blocked, "allow"], ["단말 잔존", d.endpoint_residue, d.endpoint_residue ? "alert" : ""]]
        .map(([label, value, tone = ""]) => html`<div class="kpi ${tone}"><div class="label">${label}</div><div class="value">${value ?? 0}</div></div>`)}</div>`,
      active: tab || "verdict",
      tabs: [
        { key: "verdict", label: "판정", body: html`<div class="grid c12">
          ${panel("등급", html`${c.grade ? html`<div class="grade-big ${c.grade}">${c.grade} · ${GRADE[c.grade]}</div>` : html`<div class="grade-big">—</div>`}
            ${criteria.assessed_at ? html`<p class="muted small">${when(criteria.assessed_at)}</p>` : ""}
            ${c.grade && c.grade !== "T1" && (criteria.determined_by || []).length ? kv([["결정 대상", criteria.determined_by.join(", ")]]) : ""}
            ${(criteria.notes || []).map((n) => html`<p class="note bad">${n}</p>`)}
            ${kv([["위험 수용", c.risk_acceptance_note ? `${c.risk_acceptance_note} (${c.risk_accepted_by})` : ""], ["종결 사유", c.close_note],
              ["재개 사유", criteria.reopened_note]])}`)}
          ${panel("기준별 충족 대상", html`${chartBox("c-criteria", "네 기준별 충족한 회수 대상 수", "sm")}
            <div class="crit">${["C1", "C2", "C3", "C4"].map((k) => { const cr = criteria[k]; return html`<div class="c">
              <h4>${k} ${CRITERIA[k]} ${cr ? chip(cr.met ? "allow" : "block", cr.met ? "충족" : "미충족") : chip("outline", "미판정")}</h4>
              ${cr?.gaps?.length ? html`<ul>${cr.gaps.slice(0, 3).map((g) => html`<li>${g}</li>`)}${cr.gaps.length > 3 ? html`<li>+${cr.gaps.length - 3}</li>` : ""}</ul>` : ""}</div>`; })}</div>`,
            { sub: `대상 ${d.targets.length}개` })}</div>` },
        { key: "targets", label: "회수 대상", n: d.targets.length, hot: outstanding > 0, body: panel("회수 대상", html`<table class="data">
          <thead><tr><th>대상</th><th>상태</th><th>기준</th><th>등급</th><th></th></tr></thead><tbody>
          ${d.targets.map((t) => html`<tr class="clickable" tabindex="0" data-act="target" data-id="${t.id}">
            <td><b>${t.label}</b><span class="sub">${TARGET_KIND[t.kind] || t.kind} · ${HOLDER[t.holder] || t.holder} · ${DISCOVERED[t.discovered_by] || t.discovered_by}</span></td>
            <td>${chip(...(TARGET_STATUS[t.status] || ["", t.status]))}</td>
            <td>${t.criteria ? html`<span class="cdots">${["C1", "C2", "C3", "C4"].map((k) => html`<span class="${t.criteria[k]?.met ? "met" : ""}" title="${k}">${k}</span>`)}</span>` : html`<span class="small muted">—</span>`}</td>
            <td>${t.grade ? chip(t.grade, t.grade) : ""}</td>
            <td class="num nowrap">${!closed && t.kind === "server-held-credential" && t.verification === "gitea-token" && t.status === "OUTSTANDING"
              ? html`<button class="btn sm danger" data-act="revoke-credential" data-id="${t.id}">조직 권한으로 폐기</button>` : ""}
              ${!closed ? html`<button class="btn sm" data-act="target-status" data-id="${t.id}">상태 기록</button>` : ""}</td></tr>`)}
          </tbody></table>`, { flush: true, tools: closed ? "" : html`<button class="btn sm" data-act="add-target">대상 추가</button>` }) },
        { key: "evidence", label: "증거", n: d.evidence.length, body: panel("증거", html`<div class="evidence">${d.evidence.map(evidenceItem)}</div>
          ${d.evidence.length ? "" : empty("증거 없음")}`, { sub: `상태 증거 ${stateEvidence}`, tools: closed ? "" : html`<button class="btn sm" data-act="add-evidence">증거 등록</button>` }) },
        { key: "scope", label: "허용 자원", body: panel("허용됐던 자원", html`<div class="pill-list">${(c.allowed_resources || []).map((a) => (typeof a === "string"
          ? html`<span class="chip outline mono">${a}</span>` : html`<span class="chip outline mono">${a.name || JSON.stringify(a)}${a.action ? ` · ${ACTION[a.action] || a.action}` : ""}</span>`))}</div>
          ${kv([["개시", when(c.opened_at)], ["차단", when(c.cutover_at, { seconds: true })], ["마지막 시도", when(act.last_attempt, { seconds: true })], ["실행 미확인", act.unknown]])}`) },
      ],
    }),
    charts: { "c-criteria": () => charts.bars(perCriterion.map((p) => ({ name: p.name, value: p.met })), { unit: `/${d.targets.length}` }) },
  };
}

/** What this one piece of evidence observed - the kind says what it *can* prove. */
function evidenceResult(e) {
  const d = e.detail || {};
  switch (e.kind) {
    case "gateway-denial": return d.blocked ? chip("allow", `실행 전 차단 · ${d.policy_id}`) : chip("block", `차단 안 됨 · ${d.decision} ${d.policy_id || ""}`);
    case "credential-check": return d.present === false ? chip("allow", "자격 없음") : d.present ? chip("block", "자격 남음") : chip("alert", `확인 실패 · HTTP ${d.http_status}`);
    case "endpoint-inventory": return d.absent ? chip("allow", "설정 사라짐") : chip("block", `설정 남음 · ${when(d.last_report)}`);
    case "introspection": return d.active === false ? chip("allow", "비활성") : d.active ? chip("block", "활성") : "";
    case "revocation-response": return chip("outline", `HTTP ${d.http_status} · 처리 증거`);
    case "liveness-probe": return d.reachable ? chip("alert", `응답 · HTTP ${d.status_code}`) : chip("outline", "응답 없음");
    case "session-termination": return d.session_issued === false ? chip("outline", "세션 없음")
      : chip(d.session_still_works ? "block" : "outline", `DELETE ${d.delete_status ?? "?"}${d.session_still_works ? " · 세션 유지" : ""}`);
    default: return d.statement ? chip("outline", "진술") : "";
  }
}

function evidenceItem(e) {
  const m = e.meaning || {};
  const target = currentCase?.targets.find((t) => t.id === e.target_id);
  return html`<div class="e">
    <div class="head"><b>${m.label || e.kind}</b>${m.state ? chip("allow", "상태 증거") : chip("outline", "처리 증거")}
      ${evidenceResult(e)}<span class="small muted">${when(e.observed_at, { seconds: true })} · ${e.source}</span></div>
    <div class="small">${e.subject}${target && target.label !== e.subject ? html` <span class="muted">→ ${target.label}</span>` : ""}</div>
    <div class="proves">증명: ${m.proves || "—"} · <span class="no">못 함: ${m.not_proves || "—"}</span></div>
    <details><summary class="small">원본</summary>${json(e.detail)}</details></div>`;
}

function showTarget(id) {
  const t = currentCase?.targets.find((row) => row.id === id);
  if (!t) return;
  const own = currentCase.evidence.filter((e) => e.target_id === id);
  openDrawer(t.label, html`<div class="row-actions">${chip(...(TARGET_STATUS[t.status] || ["", t.status]))}${gradeChip(t.grade)}</div>`, [
    { key: "info", label: "대상", body: kv([["종류", TARGET_KIND[t.kind] || t.kind], ["보유 주체", HOLDER[t.holder] || t.holder],
      ["발견 경로", DISCOVERED[t.discovered_by] || t.discovered_by], ["식별자", t.subject_ref ? html`<code>${t.subject_ref}</code>` : ""],
      ["확인 방법", t.verification], ["만료", t.expires_at ? when(t.expires_at, { seconds: true }) : ""],
      ["회수 시각", t.revoked_at ? when(t.revoked_at, { seconds: true }) : ""], ["메모", t.note]]) },
    { key: "criteria", label: "기준", body: t.criteria ? html`<div class="crit">${["C1", "C2", "C3", "C4"].map((k) => html`<div class="c"><h4>${k} ${CRITERIA[k]}
      ${chip(t.criteria[k].met ? "allow" : "block", t.criteria[k].met ? "충족" : "미충족")}</h4>
      ${t.criteria[k].gaps.length ? html`<ul>${t.criteria[k].gaps.map((g) => html`<li>${g}</li>`)}</ul>` : ""}</div>`)}</div>` : empty("미판정") },
    { key: "evidence", label: "증거", n: own.length, body: html`<div class="evidence">${own.map(evidenceItem)}</div>${own.length ? "" : empty("증거 없음")}` },
  ]);
}

// ── policy ───────────────────────────────────────────────────────────────────
let policyLedger = [];
ROUTES.policy = async (_, tab) => {
  const [{ enforcement }, matrix, ledger] = await Promise.all([gw("enforcement"), gw("policy/matrix"), gw("policy/ledger")]);
  policyLedger = ledger.policies;
  const bundle = ledger.authorization || {};
  const names = (list, vocab) => (list || []).map((v) => vocab[v] || v).join(", ");
  const rows = matrix.roles.map((r) => ROLE[r] || r);
  const verb = { r: "읽기", w: "쓰기", x: "실행" };
  const cols = matrix.data_classes.flatMap((dc) => matrix.actions.map((a) => `${DATA_CLASS[dc] || dc}\n${verb[a] || a}`));
  const cells = matrix.cells.map((c) => ({ y: matrix.roles.indexOf(c.role),
    x: matrix.data_classes.indexOf(c.data_class) * matrix.actions.length + matrix.actions.indexOf(c.action), decision: c.decision }))
    .filter((c) => c.x >= 0 && c.y >= 0);
  const byOutcome = splitBy(ledger.policies, "outcome");
  const cell = (role, dc, action) => matrix.cells.find((c) => c.role === role && c.data_class === dc && c.action === action) || {};
  return {
    html: page({
      head: head("정책", { status: modeChip(enforcement), actions: html`<button class="btn ${enforcement === "enforce" ? "danger" : "primary"}" data-act="enforcement"
        data-mode="${enforcement === "enforce" ? "monitor" : "enforce"}">${enforcement === "enforce" ? "관찰 모드로 전환" : "집행 모드로 전환"}</button>` }),
      active: tab || "matrix",
      tabs: [
        { key: "matrix", label: "판정 행렬", body: html`<div class="stack">
          ${panel("역할 × 데이터 등급 × 행위", chartBox("c-matrix", "역할과 데이터 등급·행위 조합별 기본 판정", "lg"), { sub: `번들 ${bundle.bundle_id || "—"}` })}
          ${panel("정책 ID", html`<table class="data"><thead><tr><th>역할</th><th>데이터</th>${matrix.actions.map((a) => html`<th>${ACTION[a]}</th>`)}</tr></thead><tbody>
            ${matrix.roles.map((role) => matrix.data_classes.map((dc, i) => html`<tr>${i === 0 ? html`<td rowspan="${matrix.data_classes.length}"><b>${ROLE[role] || role}</b></td>` : ""}
              <td>${DATA_CLASS[dc] || dc}</td>${matrix.actions.map((a) => { const c = cell(role, dc, a); return html`<td>${decisionChip(c.decision)}<span class="sub mono">${c.policy_id || ""}</span></td>`; })}</tr>`))}
            </tbody></table>`, { flush: true })}</div>` },
        { key: "bundle", label: "권한 번들", n: (bundle.grants || []).length, body: panel(bundle.bundle_id || "배포 안 됨", html`<table class="data">
          <thead><tr><th>규칙</th><th>역할</th><th>데이터 등급</th><th>행위</th></tr></thead><tbody>
          ${(bundle.grants || []).map((g) => html`<tr><td class="mono small">${g.id}</td><td>${names(g.roles, ROLE)}</td>
            <td>${names(g.data_classes, DATA_CLASS)}</td><td>${names(g.actions, ACTION)}</td></tr>`)}
          </tbody></table>${(bundle.grants || []).length ? "" : empty("허용 규칙 없음 · 모든 조합 차단")}`, { flush: true, sub: `${bundle.scope || ""} · ${bundle.owner || ""}` }) },
        { key: "ledger", label: "관리대장", n: ledger.policies.length, body: html`<div class="stack">
          ${panel("결과별 정책 수", chartBox("c-outcomes", "정책 관리대장의 결과별 정책 수", "sm"), { sub: `환경 ${ledger.environment}` })}
          ${panel("정책", html`<table class="data"><thead><tr><th class="num">순위</th><th>정책</th><th>결과</th><th>상태</th><th>담당</th></tr></thead><tbody>
            ${ledger.policies.map((p) => html`<tr class="clickable" tabindex="0" data-act="policy" data-id="${p.policy_id}"><td class="num">${p.priority}</td>
              <td><code>${p.policy_id}</code><span class="sub">${p.name}</span></td><td>${outcomeDecision(p.outcome) ? decisionChip(outcomeDecision(p.outcome)) : chip("outline", p.outcome)}</td>
              <td class="small">${p.status} · v${p.version}</td><td class="small">${p.owner}</td></tr>`)}
            </tbody></table>`, { flush: true })}</div>` },
        { key: "exceptions", label: "예외", n: ledger.exceptions.length, body: html`<div class="stack">${ledger.exceptions.map((x) => panel(`${x.id} · ${x.title}`,
          html`<div class="row-actions">${decisionChip(x.effect)}${chip("outline", x.status)}</div>${kv([["사유", x.reason], ["대상 정책", html`<code>${x.policy_id}</code>`],
            ["범위", JSON.stringify(x.scope)], ["기한", when(x.valid_until)], ["보완 통제", (x.compensating_controls || []).join(" · ")],
            ["잔존 위험", x.residual_risk], ["종료 계획", x.exit_plan]])}`))}
          ${ledger.exceptions.length ? "" : empty("적용 중인 예외 없음")}</div>` },
      ],
    }),
    charts: {
      "c-matrix": () => charts.decisionGrid(rows, cols, cells),
      "c-outcomes": () => charts.bars(byOutcome.map((g) => ({ name: g.key, value: g.total, color: charts.color(outcomeDecision(g.key)) }))),
    },
  };
};

// ── actions ──────────────────────────────────────────────────────────────────
const field = {
  text: (name, label, attrs = "") => html`<label>${label}<input name="${name}" ${raw(attrs)} /></label>`,
  area: (name, label, attrs = "") => html`<label>${label}<textarea name="${name}" ${raw(attrs)}></textarea></label>`,
  select: (name, label, options, cur = "") => html`<label>${label}<select name="${name}">${Object.entries(options).map(([v, l]) =>
    html`<option value="${v}" ${v === cur ? raw("selected") : ""}>${Array.isArray(l) ? l[1] : l}</option>`)}</select></label>`,
};

const ACTIONS = {
  theme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem(THEME_KEY, next);
    charts.redrawAll();
  },
  async logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    localStorage.removeItem(TOKEN_KEY);
    location.replace("/login");
  },
  "close-drawer": closeDrawer,
  tab(el) {
    const key = el.dataset.tab;
    const bar = el.closest(".tabs");
    const scope = bar.parentElement;
    for (const b of bar.querySelectorAll(".tab")) {
      const on = b.dataset.tab === key;
      b.setAttribute("aria-selected", String(on));
      b.tabIndex = on ? 0 : -1;
    }
    for (const p of scope.querySelectorAll(":scope > .tabpanel")) p.hidden = p.dataset.panel !== key;
    if (!el.closest(".drawer")) rememberTab(key);
    charts.mountVisible(scope);
  },
  decision: (el) => showDecision(el.dataset.id),
  approval: (el) => showApproval(el.dataset.id),
  skip: () => $("#view").focus(),
  live(el) {
    feed.live = !feed.live;
    if (feed.live) { feed.rows = mergeRows(feed.rows, feed.pending); feed.pending = []; }
    el.textContent = feed.live ? "일시정지" : "실시간 재개";
    el.setAttribute("aria-pressed", String(!feed.live));
    renderFeed();
  },
  "feed-reset"() {
    feed.filters = { decision: "", server: "", person: "" };
    feed.query = "";
    location.hash = "#/activity";
    reload();
  },
  "class-filter"(el) {
    const q = new URLSearchParams(current.query);
    if (el.dataset.class) q.set("class", el.dataset.class); else q.delete("class");
    q.set("t", "configs");
    location.hash = `#/people?${q}`;
  },
  async "audit-verify"() {
    const r = await gw("audit/verify");
    if (r.intact) toast(`감사 체인 정상 · ${r.checked}건`);
    else toast(`감사 체인 손상 · #${r.broken_at ?? "끝부분"}: ${r.reason}`, true);
  },
  async approve(el) {
    const r = await api(`/approvals/${el.dataset.id}/approve`, { method: "POST" });
    toast(`승인했습니다 · ${DECISION[r.decision]?.[1] || r.decision || "처리됨"}`);
    reload(); refreshBadges();
  },
  async reject(el) {
    const fd = await ask({ title: "승인 요청 거부", fields: field.area("note", "사유", 'required maxlength="500"'), confirm: "거부", danger: true });
    if (!fd) return;
    await api(`/approvals/${el.dataset.id}/reject`, { method: "POST", body: { note: fd.get("note") } });
    toast("거부했습니다."); reload(); refreshBadges();
  },
  async "catalog-refresh"() {
    const { results } = await gw("catalog/refresh", { method: "POST" });
    const drift = Object.values(results || {}).filter((status) => status !== "READY").length;
    toast(drift ? `계약 변경 ${drift}개 서버` : "모든 서버 계약 일치", Boolean(drift));
    reload();
  },
  async "approve-contract"(el) {
    const fd = await ask({ title: "계약 변경 승인", fields: field.area("note", "검토 내용", 'required minlength="5" maxlength="500"'), confirm: "승인본 갱신" });
    if (!fd) return;
    await gw(`registry/${el.dataset.id}/approve-contract`, { method: "POST", body: { note: fd.get("note") } });
    toast("승인본을 갱신했습니다."); reload();
  },
  async "account-status"(el) {
    const fd = await ask({ title: `${el.dataset.name} 계정 상태`,
      fields: html`${field.select("status", "상태", { active: "사용", disabled: "중지", locked: "잠김" }, el.dataset.status)}${field.text("note", "메모", 'maxlength="300"')}` });
    if (!fd) return;
    const r = await api(`/api/accounts/${el.dataset.id}/status`, { method: "PUT", body: { status: fd.get("status"), note: fd.get("note") || "" } });
    toast(r.message); reload();
  },
  async "device-issue"() {
    const owners = Object.fromEntries([["", "지정 안 함"], ...peopleAccounts.filter((a) => a.status === "active")
      .map((a) => [a.token, `${a.display_name} · ${a.department || ROLE[a.role] || a.role}`])]);
    const fd = await ask({ title: "장치 자격 발급",
      fields: html`${field.text("endpoint_id", "엔드포인트 ID", 'required minlength="3" maxlength="120" pattern="[A-Za-z0-9._\\-]+" placeholder="endpoint-ysg-laptop"')}
        ${field.text("hostname", "호스트명", 'required maxlength="200" placeholder="ysg-laptop"')}
        ${field.select("platform", "플랫폼", { windows: "Windows", linux: "Linux", macos: "macOS", unknown: "기타" }, "windows")}
        ${field.select("owner_token", "소유자", owners)}
        <fieldset><legend>보고 범위</legend>
          <label class="check"><input type="checkbox" name="scopes" value="inventory" checked /> MCP 설정 인벤토리</label>
          <label class="check"><input type="checkbox" name="scopes" value="netscan" /> 내부망 MCP 리스너 탐색</label></fieldset>`,
      confirm: "발급" });
    if (!fd) return;
    const scopes = fd.getAll("scopes");
    if (!scopes.length) { toast("보고 범위를 하나 이상 고르세요.", true); return; }
    const r = await gw("endpoint/devices", { method: "POST", body: {
      endpoint_id: fd.get("endpoint_id").trim(), hostname: fd.get("hostname").trim(), platform: fd.get("platform"),
      owner_token: fd.get("owner_token") || null, scopes } });
    await reload();  // a reload closes the drawer, so the one-time key opens after it
    lastDocument = r.enrollment_key;
    openDrawer("장치 자격 발급됨", html`<p class="note warn">한 번만 표시되는 키</p>
      ${kv([["엔드포인트", html`<code>${r.endpoint_id}</code>`], ["범위", r.scopes.join(", ")], ["장치 키", html`<code>${r.enrollment_key}</code>`]])}
      <div class="row-actions"><button class="btn sm primary" type="button" data-act="copy-doc">키 복사</button></div>`);
  },
  async "device-revoke"(el) {
    const fd = await ask({ title: `장치 자격 폐기 · ${el.dataset.id}`, confirm: "폐기", danger: true });
    if (!fd) return;
    await gw(`endpoint/devices/${encodeURIComponent(el.dataset.id)}`, { method: "DELETE" });
    toast("장치 자격을 폐기했습니다."); reload();
  },
  async "intake-queue"(el) {
    const r = await api(`/api/mcp-requests/${el.dataset.id}/queue-validation`, { method: "POST" });
    toast(r.message); reload();
  },
  async "intake-terms"(el) {
    const fd = await ask({ title: `종료 조건 검증 · ${el.dataset.name}`,
      fields: html`<fieldset><legend>제공자 문서로 확인한 약속</legend>
          ${Object.entries(EXIT_TERMS).map(([k, label]) => html`<label class="check"><input type="checkbox" name="${k}" /> ${label}</label>`)}</fieldset>
        ${field.text("evidence_url", "근거 문서 (HTTPS)", 'type="url" required pattern="https://.+" maxlength="500"')}
        ${field.area("note", "확인 내용", 'required minlength="10" maxlength="1000"')}`,
      confirm: "검증 기록" });
    if (!fd) return;
    const body = { evidence_url: fd.get("evidence_url").trim(), note: fd.get("note").trim() };
    for (const k of Object.keys(EXIT_TERMS)) body[k] = fd.get(k) === "on";
    const r = await api(`/api/mcp-requests/${el.dataset.id}/exit-terms`, { method: "PUT", body });
    toast(r.message); reload();
  },
  async "intake-approve"(el) {
    const r = await api(`/api/mcp-requests/${el.dataset.id}/approve`, { method: "POST" });
    toast(r.message); reload();
  },
  async "intake-reject"(el) {
    const fd = await ask({ title: "도입 신청 거부", fields: field.area("note", "사유", 'required minlength="2" maxlength="500"'), confirm: "거부", danger: true });
    if (!fd) return;
    await api(`/api/mcp-requests/${el.dataset.id}/reject`, { method: "POST", body: { note: fd.get("note") } });
    toast("거부했습니다."); reload();
  },
  policy(el) {
    const p = policyLedger.find((row) => row.policy_id === el.dataset.id);
    if (!p) return;
    openDrawer(p.policy_id, html`<div class="row-actions">${outcomeDecision(p.outcome) ? decisionChip(outcomeDecision(p.outcome)) : chip("outline", p.outcome)}
      ${chip("outline", `${p.status} · v${p.version}`)}</div><p><b>${p.name}</b></p>`, [
      { key: "rule", label: "규칙", body: html`${p.purpose ? html`<p class="note">${p.purpose}</p>` : ""}${kv([["조건", p.condition], ["결과", p.outcome],
        ["집행", p.enforcement], ["집행 주체", p.enforced_by], ["예외 허용", p.exceptionable ? "가능" : "불가"], ["의무", (p.obligations || []).join(", ")]])}` },
      { key: "trace", label: "관리대장", body: kv([["위험", (p.risk_ids || []).join(", ")], ["통제", (p.control_ids || []).join(", ")],
        ["요구사항", (p.requirement_ids || []).join(", ")], ["담당", p.owner], ["시행", when(p.effective_from)]]) },
    ]);
  },
  async enforcement(el) {
    const mode = el.dataset.mode;
    const fd = await ask({ title: mode === "monitor" ? "관찰 모드로 전환" : "집행 모드로 전환", confirm: "전환", danger: mode === "monitor" });
    if (!fd) return;
    await gw("enforcement", { method: "PUT", body: { mode } });
    toast("전환했습니다."); reload();
  },
  "open-case": (el) => { location.hash = `#/termination/${el.dataset.id}`; },
  async "open-termination"(el) {
    const grade = el.dataset.grade;
    const fd = await ask({
      title: `종료 시작 · ${el.dataset.name}`, body: `즉시 모든 호출 차단 · 최선 등급 ${grade} ${GRADE[grade] || ""}`,
      fields: field.area("reason", "종료 사유", 'required minlength="10" maxlength="1000"'),
      confirm: "차단하고 종료 시작", danger: true });
    if (!fd) return;
    const d = await gw("termination/cases", { method: "POST", body: { relationship_id: el.dataset.id, reason: fd.get("reason") } });
    toast(`차단했습니다 · 회수 대상 ${d.targets.length}개`);
    refreshBadges();
    location.hash = `#/termination/${d.case.id}`;
  },
  target: (el) => showTarget(el.dataset.id),
  async collect() {
    const kinds = { gateway: "Gateway 차단 확인", endpoint: "단말 설정 대조", credentials: "하위 시스템 자격 확인",
      liveness: "endpoint 도달 확인", session: "세션 종료 요청" };
    const fd = await ask({ title: "증거 수집",
      fields: html`<fieldset>${Object.entries(kinds).map(([k, label]) => html`<label class="check"><input type="checkbox" name="kinds" value="${k}" ${["gateway", "endpoint", "credentials"].includes(k) ? raw("checked") : ""} /> ${label}</label>`)}</fieldset>`,
      confirm: "수집" });
    if (!fd) return;
    const chosen = fd.getAll("kinds");
    if (!chosen.length) { toast("하나 이상 고르세요.", true); return; }
    const r = await gw(`termination/cases/${currentCase.case.id}/collect`, { method: "POST", body: { kinds: chosen } });
    toast(`증거 ${r.collected.length}건 기록`); reload();
  },
  async assess() {
    const d = await gw(`termination/cases/${currentCase.case.id}/assess`, { method: "POST" });
    toast(`판정: ${d.case.grade} · ${GRADE[d.case.grade]}`, d.case.grade === "T3"); reload(); refreshBadges();
  },
  async "revoke-credential"(el) {
    const fd = await ask({ title: "조직 권한으로 하위 자격 폐기", confirm: "폐기하고 확인", danger: true });
    if (!fd) return;
    await gw(`termination/targets/${el.dataset.id}/revoke-credential`, { method: "POST" });
    toast("폐기하고 상태를 확인했습니다."); reload();
  },
  async "target-status"(el) {
    const t = currentCase.targets.find((row) => row.id === el.dataset.id);
    const fd = await ask({ title: `상태 기록 · ${t.label}`,
      fields: html`${field.select("status", "상태", TARGET_STATUS, t.status)}${field.area("note", "메모", 'maxlength="1000"')}`, confirm: "기록" });
    if (!fd) return;
    await gw(`termination/targets/${t.id}`, { method: "PUT", body: { status: fd.get("status"), note: fd.get("note") || null } });
    toast("기록했습니다."); reload();
  },
  async "add-target"() {
    const kinds = Object.fromEntries(Object.entries(TARGET_KIND).filter(([k]) => !["gateway-route", "gateway-access"].includes(k)));
    const fd = await ask({ title: "회수 대상 추가",
      fields: html`${field.select("kind", "종류", kinds)}${field.text("label", "이름", 'required maxlength="300"')}
        ${field.select("holder", "보유 주체", HOLDER, "provider")}${field.select("discovered_by", "발견 경로", DISCOVERED, "provider-disclosure")}
        ${field.area("note", "메모", 'maxlength="1000"')}`, confirm: "추가" });
    if (!fd) return;
    await gw(`termination/cases/${currentCase.case.id}/targets`, { method: "POST",
      body: { kind: fd.get("kind"), label: fd.get("label"), holder: fd.get("holder"), discovered_by: fd.get("discovered_by"), note: fd.get("note") || null } });
    toast("대상을 추가했습니다."); reload();
  },
  async "add-evidence"() {
    const kinds = Object.fromEntries(Object.entries(currentCase.evidence_kinds).map(([k, m]) => [k, `${m.label}${m.state ? "" : " (처리 증거)"}`]));
    const targets = Object.fromEntries([["", "케이스 전체"], ...currentCase.targets.map((t) => [t.id, t.label])]);
    const fd = await ask({ title: "증거 등록",
      fields: html`${field.select("kind", "종류", kinds, "provider-attestation")}${field.select("target_id", "대상", targets)}
        ${field.text("subject", "대상·식별자", 'required maxlength="300"')}${field.text("source", "출처", 'required maxlength="300"')}
        ${field.area("statement", "내용", 'maxlength="1000"')}`, confirm: "등록" });
    if (!fd) return;
    await gw(`termination/cases/${currentCase.case.id}/evidence`, { method: "POST", body: {
      kind: fd.get("kind"), subject: fd.get("subject"), source: fd.get("source"), target_id: fd.get("target_id") || null,
      detail: fd.get("statement") ? { statement: fd.get("statement") } : {} } });
    toast("증거를 등록했습니다."); reload();
  },
  async "close-case"() {
    const t3 = currentCase.case.grade === "T3";
    const fd = await ask({ title: `종결 · ${currentCase.case.grade} ${GRADE[currentCase.case.grade]}`,
      fields: html`${field.area("note", "종결 사유", 'required maxlength="1000"')}${t3 ? field.area("risk_acceptance", "위험 수용 근거", 'required maxlength="1000"') : ""}`,
      confirm: "종결", danger: true });
    if (!fd) return;
    await gw(`termination/cases/${currentCase.case.id}/close`, { method: "POST", body: { note: fd.get("note"), risk_acceptance: fd.get("risk_acceptance") || null } });
    toast("종결했습니다."); reload(); refreshBadges();
  },
  async "reopen-case"() {
    const fd = await ask({ title: "케이스 재개", fields: field.area("reason", "재개 사유", 'required maxlength="1000"'), confirm: "재개" });
    if (!fd) return;
    await gw(`termination/cases/${currentCase.case.id}/reopen`, { method: "POST", body: { reason: fd.get("reason") } });
    toast("재개했습니다."); reload(); refreshBadges();
  },
  async "lab-restore"(el) {
    const fd = await ask({ title: "실습 복원", confirm: "복원" });
    if (!fd) return;
    const r = await gw(`lab/restore/${el.dataset.id}`, { method: "POST" });
    toast(r.follow_up?.length ? `복원했습니다. ${r.follow_up.join(" ")}` : "복원했습니다.", Boolean(r.follow_up?.length));
    location.hash = "#/termination";
  },
  async report() {
    const r = await gw(`termination/cases/${currentCase.case.id}/report`);
    lastDocument = r;
    openDrawer("종료 판정서", html`<div class="grade-big ${r.grade}">${r.grade || "—"} · ${r.grade_label}</div>
      <div class="row-actions"><button class="btn sm" data-act="save-json" data-name="termination-report-${r.case_id}.json">JSON 저장</button></div>`, [
      { key: "verdict", label: "판정", body: html`<p>${r.rationale}</p>${kv([["이용 관계", `${r.relationship_id || ""} · ${r.engagement}`], ["제공자", r.relationship.provider],
        ["사유", r.reason], ["차단", when(r.cutover_at, { seconds: true })], ["판정", when(r.assessed_at)], ["종결", when(r.closed_at)],
        ["위험 수용", r.risk_acceptance_note ? `${r.risk_acceptance_note} (${r.risk_accepted_by})` : ""]])}` },
      { key: "criteria", label: "기준", body: html`${r.criteria.map((c) => html`<p><b>${c.criterion}</b> ${chip(c.met ? "allow" : "block", c.met ? "충족" : "미충족")} <span class="small muted">${c.label}</span></p>
        ${c.gaps.length ? html`<ul class="small">${c.gaps.map((g) => html`<li>${g}</li>`)}</ul>` : ""}`)}` },
      { key: "targets", label: "대상", n: r.targets.length, body: html`${r.targets.map((t) => html`<p class="small">${t.grade ? chip(t.grade, t.grade) : ""} ${t.label} · ${TARGET_STATUS[t.status]?.[1] || t.status}</p>`)}
        ${kv([["증거", r.evidence.length], ["차단 후 실행", r.gateway_observed.executed], ["차단 후 거부", r.gateway_observed.blocked], ["실행 미확인", r.gateway_observed.unknown]])}` },
    ]);
  },
  async disclosure() {
    const r = await gw(`termination/cases/${currentCase.case.id}/disclosure-request`);
    lastDocument = r.markdown;
    openDrawer("제공자 고지 요청서", html`<div class="row-actions">${chip(r.has_contract_basis ? "allow" : "alert", r.has_contract_basis ? "계약 근거 있음" : "계약 근거 없음")}
      ${chip("outline", `미회수 제공자 대상 ${r.outstanding_provider_targets}`)}<button class="btn sm primary" data-act="copy-doc">복사</button></div>
      <pre class="json">${r.markdown}</pre>`);
  },
  async "copy-doc"() {
    await navigator.clipboard.writeText(String(lastDocument));
    toast("복사했습니다.");
  },
  "save-json"(el) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(lastDocument, null, 2)], { type: "application/json" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: el.dataset.name });
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
let lastDocument = null;

const FORMS = {
  async intake(form) {
    const fd = new FormData(form);
    const body = Object.fromEntries(["display_name", "repository_url", "requested_transport", "purpose"].map((k) => [k, String(fd.get(k) || "").trim()]));
    const r = await api("/api/mcp-requests", { method: "POST", body });
    toast(r.message);
    location.hash = "#/intake?t=list";
    reload();
  },
};

// ── wiring ───────────────────────────────────────────────────────────────────
document.addEventListener("click", (event) => {
  const el = event.target.closest("[data-act]");
  if (!el) return;
  // A control inside a clickable row handles itself.
  const inner = event.target.closest("a[href], button, summary, input, select, textarea, label");
  if (inner && inner !== el && el.contains(inner)) return;
  const fn = ACTIONS[el.dataset.act];
  if (!fn) return;
  event.preventDefault();
  const busy = el.tagName === "BUTTON" && el.dataset.act !== "tab";
  if (busy) el.disabled = true;
  Promise.resolve(fn(el)).catch((error) => toast(error.message, true)).finally(() => { if (busy && el.isConnected) el.disabled = false; });
});
document.addEventListener("submit", (event) => {
  const form = event.target.closest("form[data-form]");
  if (!form) return;
  event.preventDefault();
  const button = form.querySelector('[type="submit"]');
  if (button) button.disabled = true;
  Promise.resolve(FORMS[form.dataset.form](form)).catch((error) => toast(error.message, true)).finally(() => { if (button?.isConnected) button.disabled = false; });
});
document.addEventListener("change", (event) => {
  const filter = event.target.closest("[data-filter]");
  if (filter) {
    feed.filters[filter.dataset.filter] = filter.value.trim();
    reload();
    return;
  }
  if (event.target.matches('[data-act-change="tool-filter"]')) {
    const q = new URLSearchParams({ t: "tools" });
    if (event.target.value) q.set("server", event.target.value);
    location.hash = `#/servers?${q}`;
  }
});
// Search narrows what is already loaded, so it re-renders the list without a request.
document.addEventListener("input", (event) => {
  if (!event.target.matches("[data-feed-search]")) return;
  feed.query = event.target.value;
  renderFeed();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
  // Clickable rows are focusable (tabindex) and open with Enter like a button.
  if (event.key === "Enter" && !event.isComposing && event.target.matches("tr[data-act]")) event.target.click();
  if (event.target.matches('[role="tab"]') && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
    const tabs = [...event.target.closest(".tabs").querySelectorAll('[role="tab"]')];
    const i = tabs.indexOf(event.target);
    const next = { ArrowLeft: i - 1, ArrowRight: i + 1, Home: 0, End: tabs.length - 1 }[event.key];
    const target = tabs[(next + tabs.length) % tabs.length];
    event.preventDefault();
    target.focus();
    target.click();
  }
});

(function applyTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  document.documentElement.dataset.theme = saved || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
})();

async function boot() {
  viewer = await api("/auth/me");
  viewer.admin = viewer.roles.includes("admin");
  $("#who").innerHTML = String(html`<b>${viewer.name}</b>${viewer.department} · ${viewer.role_label}`);
  window.addEventListener("hashchange", route);
  await route();
  if (viewer.admin) { refreshBadges(); setInterval(refreshBadges, 30000); }
}
boot().catch((error) => { $("#view").innerHTML = String(html`<div class="note bad">${error.message}</div>`); });
