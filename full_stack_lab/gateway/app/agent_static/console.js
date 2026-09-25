/* MCP Governance Console v2.
 *
 * The Console never calls an MCP tool. Tools are called by employees' AI agents on
 * their workstations, through the Gateway; this screen reads what happened and runs
 * the governance procedures around it - approvals, contract review and the
 * termination judgment. Every request carries the signed-in user's token and the
 * server decides what that user may see, so hiding a menu here is convenience only.
 */
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
  Allow: ["allow", "허용"], Alert: ["alert", "허용·경보"], Restrict: ["restrict", "제한 실행"],
  Approval: ["approval", "승인 대기"], Block: ["block", "차단"],
};
const SERVER_STATUS = { READY: "정상", DRIFT: "계약 변경 감지", PENDING: "확인 대기", DISABLED: "사용 중지", ERROR: "연결 오류" };
const LIFECYCLE = { OPERATING: "운영", TERMINATING: "종료 절차 중", RETIRED: "폐기" };
const GRADE = { T1: "종료", T2: "부분 종료", T3: "판단 불가" };
const CASE_STATUS = { OPEN: "진행", REVOKING: "회수 중", ASSESSED: "판정됨", CLOSED: "종결", REOPENED: "재개" };
const TARGET_KIND = {
  "gateway-route": "Gateway 강제 경로", "gateway-access": "이용 주체의 접근", "client-token": "클라이언트 토큰",
  "refresh-token": "갱신 토큰", "dynamic-registration": "동적 클라이언트 등록", session: "MCP 세션",
  "server-held-credential": "서버 보유 하위 자격", "endpoint-config": "단말 MCP 설정", "api-key": "API 키",
  webhook: "웹훅", "cached-artifact": "캐시된 산출물",
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
const ROLE = { admin: "관리자", employee: "직원", partner: "협력사 직원" };
const EXIT_TERMS = {
  provider_credential_disclosure: "제공자 보유 자격 고지",
  revocation_evidence: "폐기 기록 제출",
  audit_access_retained: "종료 후 감사 기록 접근",
};
const CRITERIA_SHORT = {
  C1: ["모집단", "회수 대상을 빠짐없이 열거했는가"],
  C2: ["수행 권한", "조치 권한이 있고 증거를 받을 수 있는가"],
  C3: ["연속성", "조치부터 전파까지 공백이 없는가"],
  C4: ["증거 접근", "증거가 대상·시점을 특정하는가"],
};

const chip = (tone, label) => html`<span class="chip ${tone}">${label}</span>`;
const decisionChip = (d) => chip(...(DECISION[d] || ["", d]));
const gradeChip = (g, prefix = "") => (g ? chip(g, `${prefix}${g} · ${GRADE[g]}`) : chip("outline", "미판정"));
const bool = (v, yes = "있음", no = "없음") => (v ? chip("allow", `✓ ${yes}`) : chip("block", `✗ ${no}`));

const pad = (n) => String(n).padStart(2, "0");
function when(value, { seconds = false } = {}) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}${seconds ? `:${pad(d.getSeconds())}` : ""}`;
  return d.toDateString() === new Date().toDateString() ? hm : `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`;
}
function ago(value) {
  if (!value) return "기록 없음";
  const s = Math.round((Date.now() - new Date(value).getTime()) / 1000);
  if (s < 60) return "방금";
  if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
  return `${Math.floor(s / 86400)}일 전`;
}
const json = (v) => html`<pre class="json">${JSON.stringify(v, null, 2)}</pre>`;
const kv = (pairs) => html`<dl class="kv">${pairs.filter(([, v]) => v !== undefined && v !== null && v !== "")
  .map(([k, v]) => html`<dt>${k}</dt><dd>${v}</dd>`)}</dl>`;

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

function openDrawer(title, body) {
  $("#drawer-title").textContent = title;
  $("#drawer-body").innerHTML = String(body);
  $("#drawer").classList.add("open");
  $("#drawer").setAttribute("aria-hidden", "false");
  $("#scrim").classList.add("show");
}
function closeDrawer() {
  // Drop the item from the address so clicking the same card again reopens it.
  if (/^#\/servers\/./.test(location.hash)) history.replaceState(null, "", "#/servers");
  $("#drawer").classList.remove("open");
  $("#drawer").setAttribute("aria-hidden", "true");
  $("#scrim").classList.remove("show");
}

/** Modal form. Resolves with the FormData, or null when cancelled. */
function ask({ title, body = "", fields = "", confirm = "확인", danger = false }) {
  const dialog = $("#dialog");
  const form = $("#dialog-form");
  form.innerHTML = String(html`<h3>${title}</h3>${body ? html`<p class="muted small">${body}</p>` : ""}${fields}
    <div class="row"><button class="btn" value="cancel" formnovalidate>취소</button>
    <button class="btn ${danger ? "danger solid" : "primary"}" value="ok">${confirm}</button></div>`);
  dialog.returnValue = "";
  dialog.showModal();
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "ok" ? new FormData(form) : null), { once: true });
  });
}

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
const badges = { approvals: 0, termination: 0 };

function renderNav(active) {
  const groups = new Map();
  for (const page of PAGES.filter((p) => viewer.pages.includes(p.id))) {
    if (!groups.has(page.group)) groups.set(page.group, []);
    groups.get(page.group).push(page);
  }
  $("#nav").innerHTML = String(html`${[...groups].map(([group, pages]) => html`<div class="group">${group}</div>${pages.map((p) => html`
    <a href="#/${p.id}" ${active === p.id ? raw('aria-current="page"') : ""}>${p.label}
      ${p.badge && badges[p.badge] ? html`<span class="count">${badges[p.badge]}</span>` : ""}</a>`)}`)}`);
}

async function route() {
  stopLive();
  closeDrawer();
  const [page = "", arg] = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  const id = viewer.pages.includes(page) ? page : viewer.pages[0];
  if (id !== page) { location.replace(`#/${id}`); return; }
  renderNav(id);
  const seq = ++routeSeq;
  const view = $("#view");
  if (!view.dataset.page || view.dataset.page !== id) view.innerHTML = '<p class="skeleton">불러오는 중…</p>';
  view.dataset.page = id;
  try {
    const out = await ROUTES[id](arg);
    if (seq !== routeSeq) return;  // the user already moved on
    view.innerHTML = String(out.html ?? out);
    out.after?.();
  } catch (error) {
    if (seq === routeSeq) view.innerHTML = String(html`<div class="note bad">${error.message}</div>`);
  }
}
const reload = () => route();

async function refreshBadges() {
  try {
    const o = await gw("overview");
    badges.approvals = o.pending_approvals;
    badges.termination = (o.termination?.open_cases || 0) + (o.termination?.awaiting_close || 0);
    renderNav($("#view").dataset.page);
  } catch { /* badges are a convenience; the pages show the real numbers */ }
}

// ── shared renderers ─────────────────────────────────────────────────────────
function serverCard(s) {
  const tone = { READY: "ok", DRIFT: "warn", PENDING: "warn" }[s.status] || "bad";
  const retired = s.lifecycle && s.lifecycle !== "OPERATING";
  return html`<a class="card server" href="#/servers/${s.id}">
    <div class="top"><span class="dot ${tone}"></span><b>${s.display_name}</b>
      ${s.deployment === "provider" ? chip("outline", "제공자 운영") : ""}
      ${retired ? chip(s.lifecycle === "RETIRED" ? "block" : "alert", LIFECYCLE[s.lifecycle] || s.lifecycle) : ""}</div>
    <div class="desc"><span class="mono">${s.id}</span> · ${SERVER_STATUS[s.status] || s.status}</div>
    ${s.calls !== undefined ? html`<div class="stats"><span>24h 호출 <b>${s.calls}</b></span>
      <span>차단 <b>${s.blocked}</b></span><span>도구 <b>${s.tools}</b></span></div>` : ""}
  </a>`;
}

function feedItem(r) {
  return html`<li tabindex="0" data-act="decision" data-id="${r.id}">
    <span class="t">${when(r.at, { seconds: true })}</span>
    <span class="dec">${decisionChip(r.decision)}</span>
    <div>
      <div><span class="who">${r.who}</span>${r.department ? html`<span class="muted"> · ${r.department}</span>` : ""}
        ${r.agent === "termination-probe" ? html` ${chip("approval", "종료 절차의 차단 확인 · 관리자 실행")}`
          : r.workstation ? html` <span class="chip outline mono">${r.workstation}</span>` : ""}</div>
      <div class="what"><code>${r.server}.${r.tool}</code>${r.target ? html` → <code>${short(r.target, 90)}</code>` : ""}
        <span class="muted">· ${r.action_ko || "—"} · ${r.data_class_ko || "—"}</span></div>
      <div class="why">${r.policy_id} — ${short(r.reason, 150)} · <b>${r.outcome}</b>
        ${r.enforcement === "monitor" && r.would_decision ? html` · 집행 시 <b>${DECISION[r.would_decision]?.[1] || r.would_decision}</b>` : ""}</div>
      ${(r.privacy_types || []).length || (r.sequence_flags || []).length ? html`<div class="meta">
        ${(r.privacy_types || []).length ? chip("alert", `개인정보 ${r.privacy_types.join(" · ")}${r.executed ? " · 마스킹" : ""}`) : ""}
        ${(r.sequence_flags || []).includes("sensitive_read_then_send") ? chip("block", "열람→외부 전송 연쇄") : ""}</div>` : ""}
    </div></li>`;
}

// ── pages ────────────────────────────────────────────────────────────────────
const ROUTES = {};

ROUTES.overview = async () => {
  const [o, recent] = await Promise.all([gw("overview"), gw("activity?limit=8")]);
  feed.rows = recent.rows.slice().reverse();  // the detail drawer reads from here
  const t = o.today;
  const kpi = (label, value, tone = "") => html`<div class="kpi ${tone}"><div class="label">${label}</div><div class="value">${value}</div></div>`;
  const term = o.termination || {};
  return html`
  <div class="page-head"><div><h1>개요</h1>
    <p>직원 PC의 AI 에이전트가 오늘 어떤 MCP 도구를 썼고 Gateway가 무엇을 막았는지 봅니다.</p></div>
    <div class="actions">${chip(o.enforcement === "enforce" ? "allow" : "alert", o.enforcement === "enforce" ? "집행 모드 · 차단 적용" : "관찰 모드 · 기록만")}
      ${chip("outline", `카탈로그 ${o.catalog_version}`)}</div></div>
  <div class="kpis">${kpi("오늘 호출", t.total)}${kpi("허용", t.Allow, "allow")}${kpi("경보", t.Alert, "alert")}
    ${kpi("제한 실행", t.Restrict, "restrict")}${kpi("승인 대기", o.pending_approvals, "approval")}${kpi("차단", t.Block, "block")}</div>
  <div class="grid side-main">
    <div class="stack">
      <section class="card"><header><h2>직원 PC</h2><span class="sub">단말 에이전트 보고</span></header>
        <div class="body flush"><table class="data"><thead><tr><th>단말</th><th>사용자</th><th>섀도 MCP</th><th>마지막 호출</th></tr></thead><tbody>
        ${o.workstations.map((w) => html`<tr><td class="mono">${w.endpoint_id}</td><td>${w.display_name || w.owner_token}<div class="small muted">${w.department || ""}</div></td>
          <td>${Number(w.shadow) ? chip("block", `${w.shadow}건`) : chip("allow", "없음")}</td><td class="small">${ago(w.last_call)}</td></tr>`)}
        ${o.workstations.length ? "" : html`<tr><td colspan="4" class="empty">등록된 단말이 없습니다.</td></tr>`}
        </tbody></table></div></section>
      <section class="card"><header><h2>많이 걸린 정책</h2><span class="sub">최근 24시간 · 차단·경보</span></header>
        <div class="body flush"><table class="data"><tbody>
        ${o.top_policies.map((p) => html`<tr><td class="mono small">${p.policy_id}</td><td>${decisionChip(p.decision)}</td><td class="num">${p.n}</td></tr>`)}
        ${o.top_policies.length ? "" : html`<tr><td class="empty">최근 24시간에 차단·경보가 없습니다.</td></tr>`}
        </tbody></table></div></section>
      <section class="card"><header><h2>종료·폐기</h2><a class="small" href="#/termination" >열기 →</a></header>
        <div class="body">${kv([["진행 중 케이스", term.open_cases], ["종결 대기", term.awaiting_close],
          ["미해결 T2·T3", term.unresolved_grades], [`기한(${term.sla_days}일) 초과`, term.overdue],
          ["폐기 잔존 설정", term.retired_residue], ["섀도 MCP", term.shadow_endpoints]])}</div></section>
    </div>
    <div class="stack">
      <section class="card"><header><h2>MCP 서버</h2><span class="sub">${o.servers.length}종 · 최근 24시간</span>
        <div class="tools"><a class="btn sm" href="#/servers">관리</a></div></header>
        <div class="body"><div class="servers">${o.servers.map(serverCard)}</div></div></section>
      <section class="card"><header><h2>최근 활동</h2><div class="tools"><a class="btn sm" href="#/activity">전체 로그</a></div></header>
        <ul class="feed">${feed.rows.map(feedItem)}</ul>
        ${feed.rows.length ? "" : html`<p class="empty">아직 호출이 없습니다. <code>./console.sh workday</code>로 직원들의 업무를 시작하세요.</p>`}</section>
    </div>
  </div>`;
};

// Activity keeps its rows between renders so live updates and the detail drawer
// read from the same list.
const feed = { rows: [], cursor: 0, filters: { decision: "", server: "", person: "" }, live: true, servers: [] };
let liveTimer = null;
function stopLive() { clearInterval(liveTimer); liveTimer = null; }
const feedQuery = (extra) => new URLSearchParams({ ...Object.fromEntries(Object.entries(feed.filters).filter(([, v]) => v)), ...extra });

function startLive() {
  stopLive();
  if (!feed.live) return;
  liveTimer = setInterval(async () => {
    try {
      const data = await gw(`activity?${feedQuery({ after: feed.cursor, limit: 100 })}`);
      if (!data.rows.length) return;
      feed.cursor = data.cursor;
      const fresh = data.rows.slice().reverse();
      feed.rows = [...fresh, ...feed.rows].slice(0, 500);
      const list = $("#feed");
      if (!list) return;
      $("#feed-empty")?.remove();
      list.insertAdjacentHTML("afterbegin", fresh.map(feedItem).join(""));
    } catch { /* a transient error must not end the live view; the next tick retries */ }
  }, 3000);
}

ROUTES.activity = async () => {
  const data = await gw(`activity?${feedQuery({ limit: 200 })}`);
  feed.rows = data.rows.slice().reverse();
  feed.cursor = data.cursor;
  if (viewer.admin && !feed.servers.length) feed.servers = (await gw("registry")).servers.map((s) => s.id);
  const servers = viewer.admin ? feed.servers : [...new Set(feed.rows.map((r) => r.server))].sort();
  const option = (value, label, current) => html`<option value="${value}" ${value === current ? raw("selected") : ""}>${label}</option>`;
  const f = feed.filters;
  return {
    html: html`
    <div class="page-head"><div><h1>활동 로그</h1>
      <p>${viewer.admin ? "모든 직원" : "내"} AI 에이전트의 도구 호출과 Gateway 판정입니다. 한 줄이 호출 하나이고, 누르면 판정 근거가 열립니다.</p></div>
      <div class="actions">${viewer.admin ? html`<button class="btn" data-act="audit-verify">감사 체인 검증</button>` : ""}</div></div>
    <section class="card">
      <div class="filters">
        <select data-filter="decision" aria-label="판정">${option("", "모든 판정", f.decision)}
          ${Object.entries(DECISION).map(([k, [, label]]) => option(k, label, f.decision))}</select>
        <select data-filter="server" aria-label="서버">${option("", "모든 서버", f.server)}${servers.map((s) => option(s, s, f.server))}</select>
        ${viewer.admin ? html`<input data-filter="person" type="search" placeholder="사람 이름" value="${f.person}" aria-label="사람" />` : ""}
        <span class="live"><span class="dot ${feed.live ? "on" : ""}"></span>${feed.live ? "실시간" : "일시정지"}</span>
        <button class="btn sm" data-act="live">${feed.live ? "일시정지" : "실시간 켜기"}</button>
      </div>
      <ul class="feed" id="feed">${feed.rows.map(feedItem)}</ul>
      ${feed.rows.length ? "" : html`<p class="empty" id="feed-empty">조건에 맞는 호출이 없습니다.</p>`}
    </section>`,
    after: startLive,
  };
};

function showDecision(id) {
  const r = feed.rows.find((row) => String(row.id) === String(id));
  if (!r) return;
  openDrawer(`판정 #${r.id}`, html`
    <div>${decisionChip(r.decision)} <b>${r.decision_ko}</b> · ${r.outcome}</div>
    <p class="note">${r.reason}</p>
    ${kv([["시각", new Date(r.at).toLocaleString("ko-KR")], ["사람", `${r.who}${r.department ? ` (${r.department})` : ""}`],
      ["역할", ROLE[r.role] || r.role], ["단말", r.workstation], ["에이전트", r.agent], ["작업", r.task_id],
      ["도구", html`<code>${r.server}.${r.tool}</code>`], ["대상", r.target ? html`<code>${r.target}</code>` : ""],
      ["행위", `${r.action_ko || "—"} (${r.action || "?"})`], ["데이터 등급", r.data_class_ko], ["분류 근거", r.summary],
      ["위험 점수", `${r.risk_score ?? 0} / 100 (조사용 — 판정 근거는 정책)`],
      ["개인정보", (r.privacy_types || []).join(", ")], ["연쇄 표지", (r.sequence_flags || []).join(", ")],
      ["정책", html`<code>${r.policy_id}</code>`], ["예외", r.exception_id], ["승인 요청", r.approval_id],
      ["집행 모드", r.enforcement], ["집행 시 판정", r.would_decision], ["오류", r.error], ["trace", r.trace_id ? html`<code>${r.trace_id}</code>` : ""]])}
    <p class="small muted">판정은 실행 전에 내려지고, 이 행은 해시 체인으로 묶여 있어 사후에 고치면 감사 체인 검증에서 드러납니다.</p>`);
}

ROUTES.approvals = async () => {
  const { approvals } = await api("/approvals");
  return html`
  <div class="page-head"><div><h1>승인 대기</h1>
    <p>정책이 "사람이 확인한 뒤 실행"으로 판정한 호출입니다. 승인하면 Gateway가 그 호출을 한 번 실행합니다.</p></div></div>
  <div class="stack">${approvals.map((a) => html`
    <section class="card"><header><h2>${a.display_name || a.requested_by}</h2><span class="sub">${a.department || ""} · ${ago(a.created_at)} · ${when(a.expires_at)} 만료</span>
      <div class="tools"><button class="btn sm danger" data-act="reject" data-id="${a.id}">거부</button>
      <button class="btn sm primary" data-act="approve" data-id="${a.id}">승인하고 실행</button></div></header>
      <div class="body stack">
        ${kv([["도구", html`<code>${a.server_id}.${a.tool}</code>`], ["행위", `${ACTION[a.action] || a.action || "—"} · ${DATA_CLASS[a.data_class] || a.data_class || "—"}`],
          ["단말", a.client?.workstation], ["정책", html`<code>${a.policy_id || "—"}</code>`], ["사유", a.reason], ["분류", a.summary]])}
        <details><summary>인자</summary>${json(a.arguments)}</details>
      </div></section>`)}
    ${approvals.length ? "" : html`<div class="card"><p class="empty">대기 중인 승인 요청이 없습니다.</p></div>`}
  </div>`;
};

let registry = null;
ROUTES.servers = async (id) => {
  registry = await gw("registry");
  const byDeployment = (d) => registry.servers.filter((s) => (s.deployment || "internal") === d);
  return {
    html: html`
    <div class="page-head"><div><h1>MCP 서버</h1>
      <p>조직이 승인한 MCP 서버와 도구입니다. 도구 설명·스키마는 승인 시점의 해시로 고정되고, 달라지면 호출 전에 막힙니다.</p></div>
      <div class="actions">${chip("outline", `카탈로그 ${registry.catalog_version}`)}<button class="btn" data-act="catalog-refresh">계약 다시 확인</button></div></div>
    <section class="card"><header><h2>사내 운영</h2><span class="sub">조직 내부망에서 실행</span></header>
      <div class="body"><div class="servers">${byDeployment("internal").map(serverCard)}</div></div></section>
    <section class="card"><header><h2>제공자 운영</h2><span class="sub">원격 서비스 · 종료 시 제공자 보유 자격이 쟁점</span></header>
      <div class="body"><div class="servers">${byDeployment("provider").map(serverCard)}</div></div></section>`,
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
  openDrawer(s.display_name, html`
    <div>${chip({ READY: "allow", DRIFT: "alert" }[s.status] || "block", SERVER_STATUS[s.status] || s.status)}
      ${chip(s.lifecycle === "OPERATING" ? "outline" : "block", LIFECYCLE[s.lifecycle] || s.lifecycle)}
      ${chip("outline", s.deployment === "provider" ? "제공자 운영" : "사내 운영")}</div>
    ${s.status_reason ? html`<p class="note ${s.status === "READY" ? "" : "warn"}">${s.status_reason}</p>` : ""}
    ${kv([["id", html`<code>${s.id}</code>`], ["패키지", html`<code>${s.source_ref || `${s.package}@${s.version}`}</code>`],
      ["endpoint", html`<code>${s.endpoint}</code>`], ["공급자", s.supplier], ["라이선스", s.license],
      ["하위 시스템", s.downstream ? JSON.stringify(s.downstream) : ""], ["마지막 확인", s.last_seen_at ? `${when(s.last_seen_at)} (${ago(s.last_seen_at)})` : ""]])}
    ${s.status === "DRIFT" ? html`<div class="note warn">도구 계약이 승인본과 다릅니다. 변경 내용을 검토했다면 승인본으로 올릴 수 있습니다.
      <div class="row-actions"><button class="btn sm primary" data-act="approve-contract" data-id="${s.id}">검토 완료 · 승인본 갱신</button></div></div>` : ""}
    <h3>도구 ${tools.length}개</h3>
    <table class="data"><thead><tr><th>도구</th><th>행위</th><th>상태</th></tr></thead><tbody>
      ${tools.map((t) => html`<tr><td><code>${t.name}</code><div class="small muted">${short(t.description, 140)}</div></td>
        <td>${chip({ r: "allow", w: "alert", x: "block" }[t.action] || "", ACTION[t.action] || t.action)}</td>
        <td>${!t.enabled ? chip("block", "미승인") : t.contract_ok ? chip("allow", "계약 일치") : chip("alert", "계약 불일치")}</td></tr>`)}
    </tbody></table>
    <h3>종료 조건 (도입 시 약속)</h3>
    <div class="pill-list">${Object.entries(EXIT_TERMS).map(([k, label]) => bool(terms[k], label, label))}</div>
    ${creds.length ? html`<p class="small">고지된 서버 보유 자격: ${creds.map((c) => html`<code>${c.id}</code> `)}</p>` : ""}
    ${rels.length ? html`<h3>이용 관계</h3>${rels.map((u) => html`<p class="small"><b>${u.id}</b> · ${u.purpose} · ${u.organization} · ${u.status}</p>`)}
      <a class="btn sm" href="#/termination">종료 준비도 보기 →</a>` : ""}`);
}

ROUTES.people = async () => {
  const [{ accounts }, inv] = await Promise.all([api("/api/accounts"), gw("endpoint/inventory")]);
  const cls = (c) => chip(...(ENDPOINT_CLASS[c] || ["", c]));
  return html`
  <div class="page-head"><div><h1>직원·단말</h1>
    <p>누가 어떤 PC에서 AI 에이전트를 쓰는지, 그 PC에 Gateway를 거치지 않는 MCP 설정(섀도 MCP)이 있는지 봅니다.</p></div></div>
  <div class="stack">
    <section class="card"><header><h2>계정</h2><span class="sub">신원 관리대장 · 상태를 바꾸면 발급된 토큰도 다음 요청부터 막힙니다</span></header>
      <div class="body flush"><table class="data"><thead><tr><th>이름</th><th>이메일</th><th>역할</th><th>부서</th><th>상태</th><th></th></tr></thead><tbody>
      ${accounts.map((a) => html`<tr><td><b>${a.display_name}</b><div class="small muted">${a.job_title || ""}</div></td><td class="small">${a.email}</td>
        <td>${ROLE[a.role] || a.role}</td><td>${a.department}</td>
        <td>${chip({ active: "allow", disabled: "block", locked: "alert" }[a.status] || "", { active: "사용", disabled: "중지", locked: "잠김" }[a.status] || a.status)}</td>
        <td class="num">${a.user_id === viewer.user_id ? html`<span class="small muted">본인</span>`
          : html`<button class="btn sm" data-act="account-status" data-id="${a.user_id}" data-name="${a.display_name}" data-status="${a.status}">상태 변경</button>`}</td></tr>`)}
      </tbody></table></div></section>
    <section class="card"><header><h2>단말</h2><span class="sub">${inv.coverage.known_endpoints}대 · 최근 15분 보고 ${inv.coverage.reporting_recently}대</span></header>
      <div class="body flush"><table class="data"><thead><tr><th>단말</th><th>소유자</th><th>설정 항목</th><th>섀도</th><th>폐기 잔존</th><th>마지막 보고</th></tr></thead><tbody>
      ${inv.agents.map((a) => html`<tr><td class="mono">${a.endpoint_id}<div class="small muted">${a.platform || ""}</div></td><td>${a.owner_token || "—"}</td>
        <td class="num">${a.entries}</td><td>${Number(a.shadow) ? chip("block", a.shadow) : "0"}</td><td>${Number(a.residue) ? chip("alert", a.residue) : "0"}</td>
        <td class="small">${ago(a.last_seen_at)}</td></tr>`)}
      ${inv.agents.length ? "" : html`<tr><td colspan="6" class="empty">보고한 단말이 없습니다.</td></tr>`}
      </tbody></table></div></section>
    <section class="card"><header><h2>단말의 MCP 설정</h2><span class="sub">단말 에이전트가 AI 클라이언트 설정 파일에서 찾은 서버</span></header>
      <div class="body flush"><table class="data"><thead><tr><th>단말</th><th>설정 파일</th><th>서버</th><th>연결</th><th>분류</th></tr></thead><tbody>
      ${inv.entries.map((e) => html`<tr><td class="mono">${e.endpoint_id}</td><td class="small mono">${e.config_path}</td>
        <td><b>${e.server_label}</b>${e.registry_name ? html`<div class="small muted">등록 서버: ${e.registry_name}</div>` : ""}</td>
        <td class="small mono">${e.transport} ${short(e.endpoint_ref, 60)}</td><td>${cls(e.classification)}</td></tr>`)}
      ${inv.entries.length ? "" : html`<tr><td colspan="5" class="empty">보고된 설정이 없습니다.</td></tr>`}
      </tbody></table></div></section>
  </div>`;
};

// ── intake ───────────────────────────────────────────────────────────────────
const INTAKE_STATUS = {
  HOLD: ["outline", "보류"], VALIDATION_QUEUED: ["approval", "검증 대기"], VALIDATING: ["approval", "검증 중"],
  VALIDATED: ["restrict", "검증 완료"], APPROVED: ["allow", "승인"], REJECTED: ["block", "거부"], FAILED: ["alert", "검증 실패"],
};
ROUTES.intake = async () => {
  const { requests } = await api("/api/mcp-requests");
  return html`
  <div class="page-head"><div><h1>도입 신청</h1>
    <p>쓰고 싶은 MCP 서버를 신청합니다. 격리 환경에서 SBOM·취약점·정적 분석을 거친 뒤 관리자가 승인합니다.</p></div></div>
  <div class="grid side-main">
    <section class="card"><header><h2>새 신청</h2></header>
      <form class="body stack form" data-form="intake">
        <label>이름<input name="display_name" required minlength="2" maxlength="80" placeholder="예: Slack MCP" /></label>
        <label>GitHub 저장소<input name="repository_url" required placeholder="https://github.com/조직/저장소" /></label>
        <label>연결 방식<select name="requested_transport"><option value="streamable-http">Streamable HTTP (원격)</option>
          <option value="stdio">stdio (로컬 실행)</option><option value="sse">SSE (구형 원격)</option></select></label>
        <label>도입 목적<textarea name="purpose" required minlength="10" maxlength="1000" placeholder="어떤 업무에, 어떤 데이터에 쓰는지"></textarea></label>
        <fieldset><legend>종료 조건 — 제공자와 도입 전에 합의해야 합니다</legend>
          ${Object.entries(EXIT_TERMS).map(([k, label]) => html`<label class="check"><input type="checkbox" name="${k}" /> ${label}</label>`)}
          <p class="small muted">원격 서버가 하위 시스템 자격을 고지하지 않으면, 이용을 끝낼 때 회수 대상 모집단을 열거할 수 없어 종료 판정이 T3(판단 불가)로 고정됩니다. 이 증거는 종료 시점에 소급해 얻을 수 없습니다.</p>
        </fieldset>
        <button class="btn primary" type="submit">신청</button>
      </form></section>
    <section class="card"><header><h2>${viewer.admin ? "전체 신청" : "내 신청"}</h2><span class="sub">${requests.length}건</span></header>
      <div class="body flush"><table class="data"><thead><tr><th>서버</th><th>상태</th><th>종료 조건</th><th>신청</th>${viewer.admin ? html`<th></th>` : ""}</tr></thead><tbody>
      ${requests.map((r) => html`<tr><td><b>${r.display_name}</b><div class="small mono muted">${r.repository_url}</div>
          <div class="small muted">${r.requested_transport}${r.risk_level ? ` · 위험 ${r.risk_level}` : ""}${r.commit_sha ? ` · ${r.commit_sha.slice(0, 12)}` : ""}</div>
          ${r.review_note ? html`<div class="small">검토: ${r.review_note}</div>` : ""}</td>
        <td>${chip(...(INTAKE_STATUS[r.status] || ["", r.status]))}</td>
        <td class="small">${Object.keys(EXIT_TERMS).filter((k) => r.exit_terms?.[k]).length}/3</td>
        <td class="small">${when(r.created_at)}</td>
        ${viewer.admin ? html`<td class="num nowrap">
          ${r.status === "HOLD" ? html`<button class="btn sm" data-act="intake-queue" data-id="${r.id}">검증 시작</button>` : ""}
          ${r.status === "VALIDATED" ? html`<button class="btn sm primary" data-act="intake-approve" data-id="${r.id}">승인</button>` : ""}
          ${["HOLD", "VALIDATION_QUEUED"].includes(r.status) ? html`<button class="btn sm danger" data-act="intake-reject" data-id="${r.id}">거부</button>` : ""}</td>` : ""}</tr>`)}
      ${requests.length ? "" : html`<tr><td colspan="5" class="empty">신청이 없습니다.</td></tr>`}
      </tbody></table></div></section>
  </div>`;
};

// ── termination ──────────────────────────────────────────────────────────────
ROUTES.termination = async (caseId) => {
  if (caseId) return caseView(caseId);
  const [{ relationships }, { cases, summary }] = await Promise.all([gw("termination/relationships"), gw("termination/cases")]);
  const kpi = (label, value, tone = "") => html`<div class="kpi ${tone}"><div class="label">${label}</div><div class="value">${value}</div></div>`;
  return html`
  <div class="page-head"><div><h1>종료·폐기</h1>
    <p>MCP 서비스를 끊는 일을 "끄기"가 아니라 <b>이용 관계</b> 단위의 권한 회수로 다루고, 회수가 끝났다고 말할 수 있는지를 네 기준으로 판정합니다.</p></div></div>
  <div class="note">
    <b>판정 규칙</b> — C1 모집단과 C4 증거 접근은 판단의 <b>전제</b>입니다. 하나라도 미충족이면 잔존 범위를 산정할 수 없어 <b>T3 판단 불가</b>.
    전제가 서면 C2 수행 권한·C3 연속성이 <b>정도</b>를 정합니다. 미충족이면 잔존 상한만 설정 가능한 <b>T2 부분 종료</b>, 모두 충족이면 <b>T1 종료</b>.
    케이스 등급은 회수 대상 중 가장 낮은 등급입니다. RFC 7009 폐기 응답(200)은 처리 사실만 증명하므로 상태 증거로 치지 않습니다.
  </div>
  <div class="kpis">${kpi("진행 중", summary.open_cases)}${kpi("종결 대기", summary.awaiting_close, "approval")}
    ${kpi("미해결 T2·T3", summary.unresolved_grades, summary.unresolved_grades ? "alert" : "")}
    ${kpi(`기한 ${summary.sla_days}일 초과`, summary.overdue, summary.overdue ? "block" : "")}
    ${kpi("폐기 잔존 설정", summary.retired_residue, summary.retired_residue ? "alert" : "")}${kpi("섀도 MCP", summary.shadow_endpoints, summary.shadow_endpoints ? "block" : "")}</div>
  <div class="grid cols-2">
    <section class="card"><header><h2>이용 관계와 종료 준비도</h2><span class="sub">지금 끊으면 도달할 수 있는 최선 등급</span></header>
      <div class="body flush">${relationships.map(relationshipRow)}
      ${relationships.length ? "" : html`<p class="empty">등록된 이용 관계가 없습니다.</p>`}</div></section>
    <section class="card"><header><h2>종료 케이스</h2><span class="sub">${cases.length}건</span></header>
      <div class="body flush"><table class="data"><thead><tr><th>이용 관계</th><th>상태</th><th>등급</th><th>대상</th><th>개시</th></tr></thead><tbody>
      ${cases.map((c) => html`<tr class="clickable" tabindex="0" data-act="open-case" data-id="${c.id}">
        <td><b>${c.display_name}</b><div class="small muted">${c.relationship_id || c.server_id}</div></td>
        <td>${chip(c.status === "CLOSED" ? "outline" : "approval", CASE_STATUS[c.status] || c.status)}${c.overdue ? chip("block", "기한 초과") : ""}</td>
        <td>${gradeChip(c.grade)}</td><td class="small">${c.targets}개 · 미회수 ${c.outstanding}<br />증거 ${c.evidence}</td>
        <td class="small">${when(c.opened_at)}</td></tr>`)}
      ${cases.length ? "" : html`<tr><td colspan="5" class="empty">아직 연 케이스가 없습니다.</td></tr>`}
      </tbody></table></div></section>
  </div>`;
};

function relationshipRow(r) {
  const ready = r.readiness || {};
  const terms = r.exit_terms || {};
  return html`<div class="rel">
    <div class="line1"><b>${r.purpose}</b>${chip("outline", r.id)}${r.status !== "ACTIVE" ? chip(r.status === "TERMINATED" ? "block" : "alert", r.status) : ""}
      <span class="spacer"></span>${gradeChip(ready.best_attainable_grade, "최선 ")}</div>
    <div class="small muted">${r.display_name} · ${r.deployment === "provider" ? `제공자 ${r.provider}` : "사내 운영"} · ${r.organization} (${r.owner_department})</div>
    <div class="small">이용 주체 ${r.users}명 · 실행된 호출 ${r.calls}건 · 끊으면 회수할 것: Gateway 접근 ${ready.would_revoke?.gateway_access ?? 0} · 단말 설정 ${ready.would_revoke?.endpoint_configs ?? 0} · 서버 보유 자격 ${ready.would_revoke?.server_held ?? 0}</div>
    ${r.deployment === "provider" ? html`<div class="pill-list">${Object.entries(EXIT_TERMS).map(([k, label]) => bool(terms[k], label, label))}</div>` : ""}
    ${(ready.blockers || []).length ? html`<ul>${ready.blockers.map((b) => html`<li>${b}</li>`)}</ul>` : ""}
    <div class="row-actions">
      ${r.latest_case ? html`<a class="btn sm" href="#/termination/${r.latest_case}">최근 케이스</a>` : ""}
      ${r.lifecycle === "OPERATING" && r.status === "ACTIVE" ? html`<button class="btn sm danger" data-act="open-termination" data-id="${r.id}" data-name="${r.purpose}" data-grade="${ready.best_attainable_grade}">종료 시작</button>` : ""}
      ${r.lifecycle === "RETIRED" ? html`<button class="btn sm" data-act="lab-restore" data-id="${r.server_id}">실습 복원</button>` : ""}
    </div></div>`;
}

let currentCase = null;
const PROCEDURE = [
  ["이용 관계 확정", "관계·제공자·허용 자원"],
  ["강제 경로 차단", "Gateway가 모든 호출을 거부"],
  ["모집단 열거", "C1 · 회수 대상 목록"],
  ["회수 조치", "C2 · 대상별 폐기"],
  ["상태 증거 수집", "C4 · 대상·시점 특정"],
  ["판정", "C1–C4 → T1·T2·T3"],
  ["종결", "T3는 위험 수용 필요"],
];

function procedureState(d) {
  const c = d.case;
  const stateEvidence = d.evidence.some((e) => e.meaning?.state);
  const unverifiable = d.targets.some((t) => t.status === "UNVERIFIABLE");
  const done = [true, Boolean(c.cutover_at), d.targets.length > 0 && !unverifiable,
    d.targets.length > 0 && d.targets.every((t) => t.status !== "OUTSTANDING"), stateEvidence,
    Boolean(c.grade) && ["ASSESSED", "CLOSED"].includes(c.status), c.status === "CLOSED"];
  const gap = [false, false, unverifiable, false, false, false, false];
  const now = done.indexOf(false);
  return PROCEDURE.map(([title, sub], i) => ({ title, sub, done: done[i], gap: gap[i], now: i === now }));
}

async function caseView(caseId) {
  const d = await gw(`termination/cases/${caseId}`);
  currentCase = d;
  const c = d.case;
  const criteria = c.criteria || {};
  const closed = c.status === "CLOSED";
  const steps = procedureState(d);
  const act = d.activity || {};
  return html`
  <div class="page-head"><div><a class="small" href="#/termination">← 종료·폐기</a>
    <h1>${c.engagement_label}</h1>
    <p>${c.display_name} · ${c.deployment === "provider" ? `제공자 ${c.provider}` : "사내 운영"} · 개시 ${when(c.opened_at)} ·
      차단 ${when(c.cutover_at, { seconds: true })} ${chip(closed ? "outline" : "approval", CASE_STATUS[c.status] || c.status)}</p></div>
    <div class="actions">
      ${!closed ? html`<button class="btn" data-act="collect">증거 수집</button><button class="btn primary" data-act="assess">판정</button>` : ""}
      ${c.grade ? html`<button class="btn" data-act="report">판정서</button>` : ""}
      ${c.deployment === "provider" ? html`<button class="btn" data-act="disclosure">제공자 고지 요청서</button>` : ""}
      ${c.status === "ASSESSED" ? html`<button class="btn danger solid" data-act="close-case">종결</button>` : ""}
      ${closed ? html`<button class="btn" data-act="reopen-case">재개</button><button class="btn" data-act="lab-restore" data-id="${c.server_id}">실습 복원</button>` : ""}
    </div></div>
  <ol class="stepper" aria-label="종료 판정 절차">${steps.map((s, i) => html`
    <li class="step ${s.done ? "done" : ""} ${s.now ? "now" : ""} ${s.gap ? "gap" : ""}"><div class="n">${s.done ? "✓" : i + 1} 단계</div><b>${s.title}</b><div class="small muted">${s.sub}</div></li>`)}</ol>
  <div class="grid side-main">
    <div class="stack">
      <section class="card"><header><h2>판정</h2>${criteria.assessed_at ? html`<span class="sub">${when(criteria.assessed_at)}</span>` : ""}</header>
        <div class="body stack">
          ${c.grade ? html`<div class="grade-big ${c.grade}">${c.grade} · ${GRADE[c.grade]}</div><p>${criteria.rationale}</p>`
            : html`<p class="muted">아직 판정하지 않았습니다. 증거를 모은 뒤 <b>판정</b>을 누르세요.${criteria.reopened_note ? html`<br />재개 사유: ${criteria.reopened_note}` : ""}</p>`}
          ${c.grade && c.grade !== "T1" && (criteria.determined_by || []).length ? html`<p class="small">등급을 정한 대상: ${criteria.determined_by.join(", ")}</p>` : ""}
          ${(criteria.notes || []).map((n) => html`<p class="note bad small">${n}</p>`)}
          ${kv([["차단 후 실행", act.executed], ["차단 후 거부", act.blocked], ["실행 여부 미확인", act.unknown], ["마지막 시도", when(act.last_attempt, { seconds: true })],
            ["단말 잔존 설정", d.endpoint_residue], ["위험 수용", c.risk_acceptance_note ? `${c.risk_acceptance_note} (${c.risk_accepted_by})` : ""], ["종결 사유", c.close_note]])}
        </div></section>
      <section class="card"><header><h2>허용됐던 자원</h2></header>
        <div class="body small">${(c.allowed_resources || []).map((a) => (typeof a === "string" ? html`<code>${a}</code> `
          : html`<code>${a.name || JSON.stringify(a)}</code>${a.action ? html` <span class="muted">(${ACTION[a.action] || a.action})</span>` : ""} `))}</div></section>
    </div>
    <div class="stack">
      <section class="card"><header><h2>네 기준</h2><span class="sub">케이스 전체 · 대상별 충족 수</span></header>
        <div class="body"><div class="crit">${Object.entries(CRITERIA_SHORT).map(([k, [name, question]]) => {
          const cr = criteria[k];
          return html`<div class="c"><h4>${k} ${name} ${cr ? chip(cr.met ? "allow" : "block", cr.met ? "충족" : "미충족") : chip("outline", "미판정")}</h4>
            <p>${question}</p>${cr ? html`<p class="small muted">대상 ${cr.targets_met}/${d.targets.length} 충족</p>
            ${cr.gaps.length ? html`<ul>${cr.gaps.slice(0, 4).map((g) => html`<li>${g}</li>`)}${cr.gaps.length > 4 ? html`<li>외 ${cr.gaps.length - 4}건</li>` : ""}</ul>` : ""}` : ""}</div>`;
        })}</div></div></section>
      <section class="card"><header><h2>회수 대상</h2><span class="sub">${d.targets.length}개 · 미회수 ${d.targets.filter((t) => t.status === "OUTSTANDING").length}</span>
        ${closed ? "" : html`<div class="tools"><button class="btn sm" data-act="add-target">대상 추가</button></div>`}</header>
        <div class="body flush"><table class="data"><thead><tr><th>대상</th><th>상태</th><th>기준</th><th>등급</th><th></th></tr></thead><tbody>
        ${d.targets.map((t) => html`<tr class="clickable" tabindex="0" data-act="target" data-id="${t.id}">
          <td><b>${t.label}</b><div class="small muted">${TARGET_KIND[t.kind] || t.kind} · 보유 ${HOLDER[t.holder] || t.holder} · ${DISCOVERED[t.discovered_by] || t.discovered_by}</div></td>
          <td>${chip(...(TARGET_STATUS[t.status] || ["", t.status]))}</td>
          <td>${t.criteria ? html`<span class="cdots">${["C1", "C2", "C3", "C4"].map((k) => html`<span class="${t.criteria[k]?.met ? "met" : ""}" title="${k}">${k}</span>`)}</span>` : html`<span class="small muted">미판정</span>`}</td>
          <td>${t.grade ? chip(t.grade, t.grade) : ""}</td>
          <td class="num nowrap">${!closed && t.kind === "server-held-credential" && t.verification === "gitea-token" && t.status === "OUTSTANDING"
            ? html`<button class="btn sm danger" data-act="revoke-credential" data-id="${t.id}">조직 권한으로 폐기</button>` : ""}
            ${!closed ? html`<button class="btn sm" data-act="target-status" data-id="${t.id}">상태 기록</button>` : ""}</td></tr>`)}
        </tbody></table></div></section>
      <section class="card"><header><h2>증거</h2><span class="sub">${d.evidence.length}건 · 상태 증거 ${d.evidence.filter((e) => e.meaning?.state).length}</span>
        ${closed ? "" : html`<div class="tools"><button class="btn sm" data-act="add-evidence">증거 등록</button></div>`}</header>
        <div class="body"><div class="evidence">${d.evidence.map(evidenceItem)}
        ${d.evidence.length ? "" : html`<p class="empty">아직 증거가 없습니다. <b>증거 수집</b>으로 조직이 스스로 얻을 수 있는 증거를 모으세요.</p>`}</div></div></section>
    </div>
  </div>`;
}

/** What this one piece of evidence observed - the kind says what it *can* prove. */
function evidenceResult(e) {
  const d = e.detail || {};
  switch (e.kind) {
    case "gateway-denial": return d.blocked ? chip("allow", `실행 전 차단 · ${d.policy_id}`) : chip("block", `차단되지 않음 · ${d.decision} ${d.policy_id || ""}`);
    case "credential-check": return d.present === false ? chip("allow", "자격 없음") : d.present ? chip("block", "자격이 아직 있음") : chip("alert", `확인 실패 · HTTP ${d.http_status}`);
    case "endpoint-inventory": return d.absent ? chip("allow", "설정 사라짐") : chip("block", `설정 남아 있음 · ${when(d.last_report)} 보고`);
    case "introspection": return d.active === false ? chip("allow", "비활성") : d.active ? chip("block", "아직 활성") : "";
    case "revocation-response": return chip("outline", `HTTP ${d.http_status} · 처리만 증명`);
    case "liveness-probe": return d.reachable ? chip("alert", `응답함 · HTTP ${d.status_code}`) : chip("outline", "응답 없음");
    case "session-termination": return d.session_issued === false ? chip("outline", "세션 없음(상태 비저장)")
      : chip(d.session_still_works ? "block" : "outline", `DELETE ${d.delete_status ?? "?"}${d.session_still_works ? " · 세션 계속 동작" : ""}`);
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
    <div class="proves">증명: ${m.proves || "—"} · <span class="no">증명 못 함: ${m.not_proves || "—"}</span></div>
    <details><summary class="small">원본 기록</summary>${json(e.detail)}</details></div>`;
}

function showTarget(id) {
  const t = currentCase?.targets.find((row) => row.id === id);
  if (!t) return;
  const own = currentCase.evidence.filter((e) => e.target_id === id);
  openDrawer(t.label, html`
    <div>${chip(...(TARGET_STATUS[t.status] || ["", t.status]))} ${t.grade ? gradeChip(t.grade) : chip("outline", "미판정")}</div>
    ${kv([["종류", TARGET_KIND[t.kind] || t.kind], ["보유 주체", HOLDER[t.holder] || t.holder], ["발견 경로", DISCOVERED[t.discovered_by] || t.discovered_by],
      ["식별자", t.subject_ref ? html`<code>${t.subject_ref}</code>` : ""], ["확인 방법", t.verification], ["만료", t.expires_at ? when(t.expires_at, { seconds: true }) : ""],
      ["회수 시각", t.revoked_at ? when(t.revoked_at, { seconds: true }) : ""], ["메모", t.note]])}
    ${t.criteria ? html`<div class="crit">${["C1", "C2", "C3", "C4"].map((k) => html`<div class="c"><h4>${k} ${CRITERIA_SHORT[k][0]}
      ${chip(t.criteria[k].met ? "allow" : "block", t.criteria[k].met ? "충족" : "미충족")}</h4>
      ${t.criteria[k].gaps.length ? html`<ul>${t.criteria[k].gaps.map((g) => html`<li>${g}</li>`)}</ul>` : ""}</div>`)}</div>` : ""}
    <h3>이 대상의 증거 ${own.length}건</h3><div class="evidence">${own.map(evidenceItem)}</div>`);
}

ROUTES.policy = async () => {
  const [{ enforcement }, matrix, ledger] = await Promise.all([gw("enforcement"), gw("policy/matrix"), gw("policy/ledger")]);
  const cell = (role, dc, action) => matrix.cells.find((c) => c.role === role && c.data_class === dc && c.action === action) || {};
  return {
    html: html`
    <div class="page-head"><div><h1>정책</h1>
      <p>모든 호출은 실행 전에 OPA 정책으로 판정됩니다. 역할 × 데이터 등급 × 행위(r/w/x)가 기본 틀이고, 그 위에 계약·SSRF·DLP·종료 정책이 우선합니다.</p></div>
      <div class="actions">${chip(enforcement === "enforce" ? "allow" : "alert", enforcement === "enforce" ? "집행 모드" : "관찰 모드")}
        <button class="btn ${enforcement === "enforce" ? "danger" : "primary"}" data-act="enforcement" data-mode="${enforcement === "enforce" ? "monitor" : "enforce"}">
        ${enforcement === "enforce" ? "관찰 모드로 전환" : "집행 모드로 전환"}</button></div></div>
    <div class="stack">
      <section class="card"><header><h2>기본 판정 행렬</h2><span class="sub">계약이 정상일 때 · 승인 없이</span></header>
        <div class="body flush"><table class="data"><thead><tr><th>역할</th><th>데이터</th>${matrix.actions.map((a) => html`<th>${ACTION[a]} (${a})</th>`)}</tr></thead><tbody>
        ${matrix.roles.map((role) => matrix.data_classes.map((dc, i) => html`<tr>${i === 0 ? html`<td rowspan="${matrix.data_classes.length}"><b>${ROLE[role] || role}</b></td>` : ""}
          <td>${DATA_CLASS[dc] || dc}</td>${matrix.actions.map((a) => { const c = cell(role, dc, a); return html`<td>${decisionChip(c.decision)}<div class="small mono muted">${c.policy_id || ""}</div></td>`; })}</tr>`))}
        </tbody></table></div></section>
      <section class="card"><header><h2>정책 관리대장</h2><span class="sub">${ledger.policies.length}개 · 우선순위 순 · 환경 ${ledger.environment}</span></header>
        <div class="body flush"><table class="data"><thead><tr><th class="num">순위</th><th>정책</th><th>결과</th><th>상태</th><th>담당</th></tr></thead><tbody>
        ${ledger.policies.map((p) => html`<tr class="clickable" tabindex="0" data-act="policy" data-id="${p.policy_id}"><td class="num">${p.priority}</td>
          <td><code>${p.policy_id}</code><div class="small">${p.name}</div></td><td>${p.outcome}</td><td>${p.status} · v${p.version}</td><td class="small">${p.owner}</td></tr>`)}
        </tbody></table></div></section>
      <section class="card"><header><h2>예외</h2><span class="sub">기한과 보완 통제가 붙은 허용</span></header>
        <div class="body stack">${ledger.exceptions.map((x) => html`<div class="e"><b>${x.id} · ${x.title}</b> ${decisionChip(x.effect)} ${chip("outline", x.status)}
          <p class="small">${x.reason}</p>${kv([["대상 정책", x.policy_id], ["범위", JSON.stringify(x.scope)], ["기한", when(x.valid_until)],
            ["보완 통제", (x.compensating_controls || []).join(" · ")], ["잔존 위험", x.residual_risk], ["종료 계획", x.exit_plan]])}</div>`)}
        ${ledger.exceptions.length ? "" : html`<p class="empty">적용 중인 예외가 없습니다.</p>`}</div></section>
    </div>`,
    after: () => { policyLedger = ledger.policies; },
  };
};
let policyLedger = [];

// ── actions ──────────────────────────────────────────────────────────────────
const field = {
  text: (name, label, attrs = "") => html`<label>${label}<input name="${name}" ${raw(attrs)} /></label>`,
  area: (name, label, attrs = "") => html`<label>${label}<textarea name="${name}" ${raw(attrs)}></textarea></label>`,
  select: (name, label, options, current = "") => html`<label>${label}<select name="${name}">${Object.entries(options).map(([v, l]) =>
    html`<option value="${v}" ${v === current ? raw("selected") : ""}>${Array.isArray(l) ? l[1] : l}</option>`)}</select></label>`,
};

const ACTIONS = {
  theme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem(THEME_KEY, next);
  },
  async logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    localStorage.removeItem(TOKEN_KEY);
    location.replace("/login");
  },
  "close-drawer": closeDrawer,
  decision: (el) => showDecision(el.dataset.id),
  live() { feed.live = !feed.live; reload(); },
  async "audit-verify"() {
    const r = await gw("audit/verify");
    if (r.intact) toast(`감사 체인 정상 — ${r.checked}건 연결 확인`);
    else toast(`감사 체인 손상 — #${r.broken_at ?? "끝부분"}: ${r.reason}`, true);
  },
  async approve(el) {
    const r = await api(`/approvals/${el.dataset.id}/approve`, { method: "POST" });
    toast(`승인했습니다 — ${DECISION[r.decision]?.[1] || r.decision || "처리됨"}`);
    reload(); refreshBadges();
  },
  async reject(el) {
    const fd = await ask({ title: "승인 요청 거부", body: "거부 사유는 요청자에게 그대로 전달되고 감사 기록에 남습니다.",
      fields: field.area("note", "사유", 'required maxlength="500"'), confirm: "거부", danger: true });
    if (!fd) return;
    await api(`/approvals/${el.dataset.id}/reject`, { method: "POST", body: { note: fd.get("note") } });
    toast("거부했습니다."); reload(); refreshBadges();
  },
  async "catalog-refresh"() {
    const { results } = await gw("catalog/refresh", { method: "POST" });
    const drift = Object.values(results || {}).filter((status) => status !== "READY").length;
    toast(drift ? `${drift}개 서버의 계약이 승인본과 다릅니다.` : "모든 서버의 계약이 승인본과 일치합니다.", Boolean(drift));
    reload();
  },
  async "approve-contract"(el) {
    const fd = await ask({ title: "계약 변경 승인", body: "현재 서버가 광고하는 도구 설명·스키마를 새 승인본으로 고정합니다. 무엇을 검토했는지 남기세요.",
      fields: field.area("note", "검토 내용", 'required minlength="5" maxlength="500"'), confirm: "승인본 갱신" });
    if (!fd) return;
    await gw(`registry/${el.dataset.id}/approve-contract`, { method: "POST", body: { note: fd.get("note") } });
    toast("승인본을 갱신했습니다."); reload();
  },
  async "account-status"(el) {
    const fd = await ask({ title: `${el.dataset.name} 계정 상태`, body: "중지·잠금은 이미 발급된 토큰에도 다음 요청부터 적용됩니다.",
      fields: html`${field.select("status", "상태", { active: "사용", disabled: "중지", locked: "잠김" }, el.dataset.status)}${field.text("note", "메모", 'maxlength="300"')}` });
    if (!fd) return;
    const r = await api(`/api/accounts/${el.dataset.id}/status`, { method: "PUT", body: { status: fd.get("status"), note: fd.get("note") || "" } });
    toast(r.message); reload();
  },
  async "intake-queue"(el) {
    const r = await api(`/api/mcp-requests/${el.dataset.id}/queue-validation`, { method: "POST" });
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
    openDrawer(p.policy_id, html`<p><b>${p.name}</b></p><p class="note">${p.purpose}</p>
      ${kv([["조건", p.condition], ["결과", p.outcome], ["집행", p.enforcement], ["집행 주체", p.enforced_by], ["상태", `${p.status} · v${p.version}`],
        ["위험", (p.risk_ids || []).join(", ")], ["통제", (p.control_ids || []).join(", ")], ["요구사항", (p.requirement_ids || []).join(", ")],
        ["예외 허용", p.exceptionable ? "가능" : "불가"], ["의무", (p.obligations || []).join(", ")], ["담당", p.owner], ["시행", when(p.effective_from)]])}`);
  },
  async enforcement(el) {
    const mode = el.dataset.mode;
    const fd = await ask({ title: mode === "monitor" ? "관찰 모드로 전환" : "집행 모드로 전환",
      body: mode === "monitor" ? "관찰 모드에서는 차단 판정도 실행됩니다. 판정은 기록되고, 로그에 '집행 시 판정'으로 남습니다. 도입 초기 측정용입니다."
        : "집행 모드에서는 차단·승인 판정이 실제로 적용됩니다.", confirm: "전환", danger: mode === "monitor" });
    if (!fd) return;
    await gw("enforcement", { method: "PUT", body: { mode } });
    toast("전환했습니다."); reload();
  },
  "open-case": (el) => { location.hash = `#/termination/${el.dataset.id}`; },
  async "open-termination"(el) {
    const grade = el.dataset.grade;
    const fd = await ask({
      title: `종료 시작 — ${el.dataset.name}`,
      body: `케이스를 여는 즉시 Gateway가 이 이용 관계의 모든 호출을 거부합니다(MCP-DECOMM-001). 회수보다 차단을 먼저 하는 이유는, 순서가 바뀌면 그 사이가 C3가 세는 공백이 되기 때문입니다. 지금 계약으로 도달 가능한 최선 등급은 ${grade} · ${GRADE[grade] || ""}입니다.`,
      fields: field.area("reason", "종료 사유", 'required minlength="10" maxlength="1000" placeholder="예: 계약 만료, 제공자 보안 사고, 대체 서비스 전환"'),
      confirm: "차단하고 종료 시작", danger: true });
    if (!fd) return;
    const d = await gw("termination/cases", { method: "POST", body: { relationship_id: el.dataset.id, reason: fd.get("reason") } });
    toast(`차단했습니다. 회수 대상 ${d.targets.length}개를 열거했습니다.`);
    refreshBadges();
    location.hash = `#/termination/${d.case.id}`;
  },
  target: (el) => showTarget(el.dataset.id),
  async collect() {
    const kinds = { gateway: "Gateway 차단 확인 (대상별 실제 호출로 확인)", endpoint: "단말 설정 보고 대조", credentials: "하위 시스템 자격 확인",
      liveness: "endpoint 도달 확인 (처리 증거)", session: "세션 종료 요청 (E2, 처리 증거)" };
    const fd = await ask({ title: "증거 수집", body: "조직이 제공자 협조 없이 스스로 얻을 수 있는 증거를 모읍니다. 상태 증거만 C4를 충족합니다.",
      fields: html`<fieldset>${Object.entries(kinds).map(([k, label]) => html`<label class="check"><input type="checkbox" name="kinds" value="${k}" ${["gateway", "endpoint", "credentials"].includes(k) ? raw("checked") : ""} /> ${label}</label>`)}</fieldset>`,
      confirm: "수집" });
    if (!fd) return;
    const chosen = fd.getAll("kinds");
    if (!chosen.length) { toast("하나 이상 고르세요.", true); return; }
    const r = await gw(`termination/cases/${currentCase.case.id}/collect`, { method: "POST", body: { kinds: chosen } });
    toast(`증거 ${r.collected.length}건을 기록했습니다.`); reload();
  },
  async assess() {
    const d = await gw(`termination/cases/${currentCase.case.id}/assess`, { method: "POST" });
    toast(`판정: ${d.case.grade} · ${GRADE[d.case.grade]}`, d.case.grade === "T3"); reload(); refreshBadges();
  },
  async "revoke-credential"(el) {
    const fd = await ask({ title: "조직 권한으로 하위 자격 폐기",
      body: "제공자가 고지한 서버 보유 자격을, 조직이 관리하는 하위 시스템(corp-git)의 관리자 권한으로 직접 폐기하고 그 상태를 다시 확인합니다. 폐기 응답은 처리 증거일 뿐이라 상태 확인을 함께 기록합니다.",
      confirm: "폐기하고 확인", danger: true });
    if (!fd) return;
    await gw(`termination/targets/${el.dataset.id}/revoke-credential`, { method: "POST" });
    toast("폐기하고 상태를 확인했습니다."); reload();
  },
  async "target-status"(el) {
    const t = currentCase.targets.find((row) => row.id === el.dataset.id);
    const fd = await ask({ title: `상태 기록 — ${t.label}`, body: "상태를 바꾸는 것은 조치의 기록입니다. 그 상태를 뒷받침하는 증거는 따로 등록해야 판정에 반영됩니다.",
      fields: html`${field.select("status", "상태", TARGET_STATUS, t.status)}${field.area("note", "메모", 'maxlength="1000"')}`, confirm: "기록" });
    if (!fd) return;
    await gw(`termination/targets/${t.id}`, { method: "PUT", body: { status: fd.get("status"), note: fd.get("note") || null } });
    toast("기록했습니다. 다시 판정하세요."); reload();
  },
  async "add-target"() {
    const kinds = Object.fromEntries(Object.entries(TARGET_KIND).filter(([k]) => !["gateway-route", "gateway-access"].includes(k)));
    const fd = await ask({ title: "회수 대상 추가", body: "제공자 고지나 담당자 확인으로 새로 알게 된 대상을 모집단에 넣습니다. 추가하면 기존 판정은 무효가 됩니다.",
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
    const fd = await ask({ title: "증거 등록", body: "제공자 증명서처럼 조직 밖에서 받은 증거를 기록합니다. 무엇을 증명하고 무엇을 증명하지 못하는지가 함께 저장됩니다.",
      fields: html`${field.select("kind", "종류", kinds, "provider-attestation")}${field.select("target_id", "대상", targets)}
        ${field.text("subject", "대상·식별자", 'required maxlength="300"')}${field.text("source", "출처", 'required maxlength="300" placeholder="예: 제공자 공문 2026-09-24"')}
        ${field.area("statement", "내용", 'maxlength="1000"')}`, confirm: "등록" });
    if (!fd) return;
    await gw(`termination/cases/${currentCase.case.id}/evidence`, { method: "POST", body: {
      kind: fd.get("kind"), subject: fd.get("subject"), source: fd.get("source"), target_id: fd.get("target_id") || null,
      detail: fd.get("statement") ? { statement: fd.get("statement") } : {} } });
    toast("증거를 등록했습니다. 다시 판정하세요."); reload();
  },
  async "close-case"() {
    const t3 = currentCase.case.grade === "T3";
    const fd = await ask({ title: `종결 — ${currentCase.case.grade} · ${GRADE[currentCase.case.grade]}`,
      body: t3 ? "T3는 잔존 범위를 산정할 수 없는 상태입니다. 누가 어떤 위험을 받아들이는지 이름으로 남겨야 종결할 수 있습니다." : "종결하면 서버가 폐기 상태가 되고 이용 관계가 끝납니다.",
      fields: html`${field.area("note", "종결 사유", 'required maxlength="1000"')}${t3 ? field.area("risk_acceptance", "위험 수용 근거", 'required maxlength="1000" placeholder="예: 제공자 고지 거부. 해당 자격의 잔존 위험을 보안책임자가 수용하며 90일 뒤 재점검"') : ""}`,
      confirm: "종결", danger: true });
    if (!fd) return;
    await gw(`termination/cases/${currentCase.case.id}/close`, { method: "POST", body: { note: fd.get("note"), risk_acceptance: fd.get("risk_acceptance") || null } });
    toast("종결했습니다."); reload(); refreshBadges();
  },
  async "reopen-case"() {
    const fd = await ask({ title: "케이스 재개", body: "종결 뒤 새 대상이나 잔존 설정이 발견되면 재개합니다. 판정은 지워지고 다시 해야 합니다.",
      fields: field.area("reason", "재개 사유", 'required maxlength="1000"'), confirm: "재개" });
    if (!fd) return;
    await gw(`termination/cases/${currentCase.case.id}/reopen`, { method: "POST", body: { reason: fd.get("reason") } });
    toast("재개했습니다."); reload(); refreshBadges();
  },
  async "lab-restore"(el) {
    const fd = await ask({ title: "실습 복원", body: "실습을 반복하려고 폐기한 서버를 운영 상태로 되돌립니다. 실제 조직이라면 새 도입 심사입니다.", confirm: "복원" });
    if (!fd) return;
    const r = await gw(`lab/restore/${el.dataset.id}`, { method: "POST" });
    toast(r.follow_up?.length ? `복원했습니다. ${r.follow_up.join(" ")}` : "복원했습니다.", Boolean(r.follow_up?.length));
    location.hash = "#/termination";
  },
  async report() {
    const r = await gw(`termination/cases/${currentCase.case.id}/report`);
    openDrawer("종료 판정서", html`
      <div class="grade-big ${r.grade}">${r.grade || "—"} · ${r.grade_label}</div><p>${r.rationale}</p>
      ${kv([["이용 관계", `${r.relationship_id || ""} · ${r.engagement}`], ["제공자", r.relationship.provider], ["사유", r.reason],
        ["차단", when(r.cutover_at, { seconds: true })], ["판정", when(r.assessed_at)], ["종결", when(r.closed_at)],
        ["위험 수용", r.risk_acceptance_note ? `${r.risk_acceptance_note} (${r.risk_accepted_by})` : ""]])}
      <h3>기준</h3>${r.criteria.map((c) => html`<p><b>${c.criterion}</b> ${chip(c.met ? "allow" : "block", c.met ? "충족" : "미충족")} <span class="small muted">${c.label}</span></p>
        ${c.gaps.length ? html`<ul class="small">${c.gaps.map((g) => html`<li>${g}</li>`)}</ul>` : ""}`)}
      <h3>대상 ${r.targets.length}개</h3>${r.targets.map((t) => html`<p class="small">${t.grade ? chip(t.grade, t.grade) : ""} ${t.label} · ${TARGET_STATUS[t.status]?.[1] || t.status}</p>`)}
      <p class="small muted">증거 ${r.evidence.length}건 · Gateway 관찰: 차단 후 실행 ${r.gateway_observed.executed} · 거부 ${r.gateway_observed.blocked} · 미확인 ${r.gateway_observed.unknown}</p>
      <div class="row-actions"><button class="btn sm" data-act="save-json" data-name="termination-report-${r.case_id}.json">JSON 저장</button></div>`);
    lastDocument = r;
  },
  async disclosure() {
    const r = await gw(`termination/cases/${currentCase.case.id}/disclosure-request`);
    openDrawer("제공자 고지 요청서", html`
      <p class="small muted">${r.has_contract_basis ? "도입 시 합의한 종료 조건을 근거로 요청합니다." : "계약상 근거가 없어 점검 절차에 근거한 요청입니다."}
        미회수 제공자 대상 ${r.outstanding_provider_targets}개.</p>
      <pre class="json">${r.markdown}</pre>
      <div class="row-actions"><button class="btn sm primary" data-act="copy-doc">복사</button></div>`);
    lastDocument = r.markdown;
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
    for (const k of Object.keys(EXIT_TERMS)) body[k] = fd.get(k) === "on";
    const r = await api("/api/mcp-requests", { method: "POST", body });
    toast(r.message);
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
  if (el.tagName === "BUTTON") el.disabled = true;
  Promise.resolve(fn(el)).catch((error) => toast(error.message, true)).finally(() => { if (el.isConnected && el.tagName === "BUTTON") el.disabled = false; });
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
  const el = event.target.closest("[data-filter]");
  if (!el) return;
  feed.filters[el.dataset.filter] = el.value.trim();
  reload();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
  // Clickable rows are focusable (tabindex) and open with Enter like a button.
  if (event.key === "Enter" && event.target.matches("li[data-act], tr[data-act]")) event.target.click();
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
