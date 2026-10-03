/* MCP Governance console.
 *
 * The console never calls an MCP tool. Harnesses call tools through the gateway; this
 * screen reads what happened and runs the procedures around it. Every request carries
 * the signed-in user's token and the server decides what that user may see, so hiding
 * a menu here is convenience only.
 */
import { mergeRows, searchRows, liveLabel, hourBuckets, splitBy, sankeyData, harnessLabel, DECISIONS,
  statusView, dedupeItems, pipelineOf, EVIDENCE } from "./console-state.mjs";
import * as charts from "./charts.mjs";

const { DECISION_LABEL } = charts;
const TOKEN_KEY = "mcp-console-token";
const THEME_KEY = "mcp-console-theme";
const NAV_KEY = "mcp-console-nav-v4";
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

const entityRef = (value, n = 24) => html`<span class="entity-ref mono" title="${value || ""}">${short(value || "—", n)}</span>`;
const listToolbar = (id, placeholder) => html`<label class="list-search"><input type="search" data-list-search="${id}" placeholder="${placeholder}" aria-label="${placeholder}" maxlength="120" /><span class="result-count" data-list-count="${id}" role="status"></span></label>`;

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
  const accountStatus = response.headers.get("x-account-status");
  if (response.status === 401 || accountStatus) {
    localStorage.removeItem(TOKEN_KEY);
    location.replace(accountStatus ? `/login?account=${encodeURIComponent(accountStatus)}` : "/login");
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
const NONE = html`<span class="muted">—</span>`;
const SERVER_STATUS = { READY: "정상", DRIFT: "계약 변경", PENDING: "확인 대기", DISABLED: "사용 중지", ERROR: "연결 오류" };
const LIFECYCLE = { OPERATING: "운영", TERMINATING: "종료 중", RETIRED: "폐기" };
const GRADE = { T1: "종료", T2: "부분 종료", T3: "판단 불가" };
const CASE_STATUS = { OPEN: "진행", REVOKING: "회수 중", ASSESSED: "판정됨", CLOSED: "종결", REOPENED: "재개" };
const TARGET_KIND = {
  "gateway-route": "게이트웨이 경로", "gateway-access": "사용자 접근", "client-token": "클라이언트 토큰",
  "refresh-token": "갱신 토큰", "dynamic-registration": "동적 클라이언트 등록", session: "MCP 세션",
  "server-held-credential": "서버 보유 자격", "endpoint-config": "엔드포인트 MCP 설정", "api-key": "API 키",
  webhook: "웹훅", "cached-artifact": "캐시 산출물",
};
const HOLDER = { org: "조직", provider: "제공자", endpoint: "엔드포인트" };
const DISCOVERED = {
  "gateway-ledger": "게이트웨이 기록", "endpoint-agent": "엔드포인트 보고", "provider-disclosure": "제공자 고지",
  "operator-manual": "수동 등록", "liveness-probe": "도달 확인",
};
const VERIFICATION = {
  "gateway-probe": "게이트웨이 차단 확인", "endpoint-report": "엔드포인트 보고", "gitea-token": "조직 직접 확인",
  "provider-attestation": "제공자 증명", stateless: "만료 시각",
};
const TARGET_STATUS = { OUTSTANDING: ["alert", "미회수"], REVOKED: ["allow", "회수됨"], EXPIRED: ["allow", "만료"], UNVERIFIABLE: ["block", "확인 불가"] };
const ENDPOINT_CLASS = { registered: ["allow", "등록 서버"], shadow: ["block", "미등록 MCP"], "retired-residue": ["alert", "폐기 잔존"] };
// Observed is never shown as blocked.
const CONTROL_STATE = {
  gateway_enforced: ["allow", "게이트웨이 통제"], endpoint_enforced: ["allow", "엔드포인트 통제"],
  vendor_enforced: ["restrict", "벤더 통제"], observed_only: ["alert", "관찰만"],
  unknown_not_enrolled: ["outline", "미등록"], bypass_possible: ["block", "우회 가능"],
};
const INTEGRATION_CLASS = {
  gateway_mcp: "게이트웨이 MCP", gateway_backend_connector: "게이트웨이 경유 SaaS", vendor_native_connector: "벤더 커넥터",
  local_plugin_or_stdio: "로컬 플러그인", shadow_or_unknown: "미등록 MCP",
};
const MANAGED_BY = { gateway: "게이트웨이", endpoint: "엔드포인트", vendor: "벤더", none: "—" };
const APPROVAL_STATE = {
  approved: "승인", pending: "미승인", unapproved: "미승인", expired: "기한 만료", denied: "거부", default: "재검토",
  drift: "계약 변경", disabled: "사용 중지", error: "연결 오류", blocked_supply_chain: "공급망 차단",
};
const PLATFORM = { linux: "Linux", windows: "Windows", wsl: "WSL", macos: "macOS", other: "기타", unknown: "기타" };
const RESPONSE = {
  returned: ["allow", "응답 반환"], masked: ["restrict", "마스킹 반환"], withheld: ["block", "응답 보류"],
  unknown: ["alert", "결과 미확인"], not_executed: ["outline", "실행 안 함"],
};
const controlChip = (s) => chip(...(CONTROL_STATE[s] || ["", s]));
const TONE_DECISION = { allow: "Allow", restrict: "Restrict", alert: "Alert", approval: "Approval", block: "Block", outline: "" };
const responseChip = (s) => chip(...(RESPONSE[s] || ["", s]));
const stateLabel = (s) => (CONTROL_STATE[s] || [, s])[1];
const approvalLabel = (s) => (s ? APPROVAL_STATE[String(s).toLowerCase()] || s : "—");

function statusPair(item) {
  const v = statusView(item);
  return html`<span class="pair">${chip(v.tone, stateLabel(v.state))}<span class="ev ${v.stale ? "stale" : ""}">${v.evLabel}</span></span>`;
}
function flow3(r) {
  if (r.decision === "Approval" && !r.attempted) return chip("approval", "승인 대기");
  const label = r.executed ? "실행됨" : r.attempted ? "실행 미확인" : "실행 안 함";
  return html`<span class="flow3">${label}</span>${r.executed || r.attempted ? responseChip(r.response) : ""}`;
}
const UPSTREAM = { executed: ["allow", "실행됨"], unknown: ["alert", "실행 미확인"], not_sent: ["outline", "실행 안 함"] };
/** The five stops of one call. */
function pipeline(r, device) {
  const [, gate, endpoint, upstream, response] = pipelineOf(r);
  const hash = (h) => h ? html`<code title="${h}">${String(h).slice(0, 12)}</code>` : "";
  const stage = (n, title, body, cls = "") => html`<li class="${cls}"><span class="step-no" aria-hidden="true">${n}</span><b>${title}</b><div class="stage-body">${body}</div></li>`;
  return html`<ol class="pipe" aria-label="호출 경로">
    ${stage(1, "요청", html`<span>${r.harness ? harnessLabel(r.harness) : r.agent || "—"}</span>
      <span class="v">엔드포인트 <code>${r.workstation || "—"}</code></span>`)}
    ${stage(2, "게이트웨이", html`${decisionChip(r.decision)}<code>${r.policy_id}</code>
      <span class="v">${gate.state === "refused-connection" ? "연결 거부" : html`감사 기록 #${r.id} ${hash(r.evidence_sha256)}`}</span>`, r.decision === "Block" ? "stop" : "")}
    ${stage(3, "엔드포인트", endpoint.state === "bound" ? html`${chip("brand", "인증된 엔드포인트")}${device ? statusPair(device) : ""}`
      : chip("outline", "인증 없음"), endpoint.state === "bound" ? "" : "off")}
    ${stage(4, "도구 실행", chip(...UPSTREAM[upstream.state]), upstream.state === "not_sent" ? "off" : "")}
    ${stage(5, "응답", html`${responseChip(response.state)}
      ${r.response_bytes != null ? html`<span class="v">${r.response_bytes} byte · ${(r.response_types || []).join(", ") || "—"} ${hash(r.response_sha256)}</span>` : ""}
      ${(r.masked_types || []).length ? html`<span class="v">마스킹 ${r.masked_types.join(", ")}</span>` : ""}`, response.state === "withheld" ? "stop" : "")}
    </ol>`;
}

// /api/integrations is admin-only and several pages read it; one fetch serves a 15 s window.
let planesCache = { at: 0, data: null };
async function planes() {
  if (!viewer.admin) return null;
  if (!planesCache.data || Date.now() - planesCache.at > 15000) planesCache = { at: Date.now(), data: await api("/api/integrations") };
  return planesCache.data;
}
const ACTION = { r: "읽기", w: "쓰기", x: "외부 전송·실행" };
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
  HOLD: ["outline", "검토 대기"], REMOTE_REVIEWED: ["approval", "계약 검토 완료"], VALIDATION_QUEUED: ["approval", "검증 대기"], VALIDATING: ["approval", "검증 중"],
  VALIDATED: ["restrict", "검증 완료"], APPROVED: ["allow", "승인"], REJECTED: ["block", "거부"], FAILED: ["alert", "검증 실패"],
};

const chip = (tone, label) => html`<span class="chip ${tone}">${label}</span>`;
const decisionChip = (d) => chip(...(DECISION[d] || ["", d]));
const gradeChip = (g, prefix = "") => (g ? chip(g, `${prefix}${g} ${GRADE[g]}`) : chip("outline", "미판정"));
const REL_STATUS = { ACTIVE: ["outline", "이용 중"], TERMINATED: ["block", "종료"], TERMINATING: ["alert", "종료 중"], SUSPENDED: ["alert", "중지"] };
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
  audit: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="m9 15 2 2 4-4"/>',
  approvals: '<rect width="8" height="4" x="8" y="2" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
  servers: '<rect width="20" height="8" x="2" y="2" rx="2"/><rect width="20" height="8" x="2" y="14" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
  coverage: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  people: '<path d="M18 5a2 2 0 0 1 2 2v8.5a2 2 0 0 0 .2.9l1.1 2.1a1 1 0 0 1-.9 1.5H3.6a1 1 0 0 1-.9-1.5l1.1-2.1a2 2 0 0 0 .2-.9V7a2 2 0 0 1 2-2z"/><path d="M20 16H4"/>',
  intake: '<path d="M16 16h6M19 13v6"/><path d="M21 10V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l2-1.14"/><path d="M3.3 7 12 12l8.7-5M12 22V12"/>',
  termination: '<path d="m19 5 3-3M2 22l3-3"/><path d="M6.3 20.3a2.4 2.4 0 0 0 3.4 0L12 18l-6-6-2.3 2.3a2.4 2.4 0 0 0 0 3.4Z"/><path d="M7.5 13.5 10 11M10.5 16.5 13 14"/><path d="m12 6 6 6 2.3-2.3a2.4 2.4 0 0 0 0-3.4l-2.6-2.6a2.4 2.4 0 0 0-3.4 0Z"/>',
  git: '<line x1="6" x2="6" y1="3" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
  plug: '<path d="M12 22v-5"/><path d="M9 8V2"/><path d="M15 8V2"/><path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z"/>',
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
  if (open && !drawer.open) drawer.showModal();
  if (!open && drawer.open) drawer.close();
}
/** body is html; `tabs` (optional) is [{key, label, n, body}] shown as drawer tabs. */
function openDrawer(title, body, tabs = null) {
  if (!$("#drawer").classList.contains("open")) drawerReturn = document.activeElement;
  $("#drawer-title").textContent = title;
  $("#drawer-body").innerHTML = String(tabs ? html`${body}${tabBar(tabs, tabs[0].key, "d")}${tabs.map((t) => tabPanel(t.key, tabs[0].key, t.body, "d"))}` : body);
  setDrawer(true);
  $("#drawer-body").scrollTop = 0;
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
  // The confirm button comes first in the DOM so Enter in a field confirms: implicit submission
  // uses the form's first submit button, and with 취소 first Enter silently cancelled (a status
  // change with a memo never applied). CSS shows 취소 on the left.
  form.innerHTML = String(html`<h3 id="dialog-title">${title}</h3>${body ? html`<p>${body}</p>` : ""}${fields}
    <div class="row"><button class="btn ${danger ? "danger solid" : "primary"}" value="ok">${confirm}</button>
    <button class="btn" value="cancel" formnovalidate>취소</button></div>`);
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
  ${back}<div class="heading"><h1>${title}</h1>${status ? html`<div class="status">${status}</div>` : ""}</div>
  ${actions ? html`<div class="actions">${actions}</div>` : ""}</div>`;
// A zero is not news: it stays in ink colour, and only a count that needs attention takes the decision colour.
const kpiStrip = (items) => html`<div class="kpis kpis-${items.length}">${items.map(([label, value, tone = "", href = ""]) => [label, value,
  value === 0 || value === "0" ? "" : tone, href]).map(([label, value, tone, href]) => href
  ? html`<a class="kpi ${tone}" href="${href}"><div class="label">${label}</div><div class="value">${value ?? 0}</div></a>`
  : html`<div class="kpi ${tone}"><div class="label">${label}</div><div class="value">${value ?? 0}</div></div>`)}</div>`;
const panel = (title, body, { sub = "", tools = "", flush = false, end = "" } = {}) => html`<section class="panel">
  <header><h2>${title}</h2>${sub ? html`<span class="sub">${sub}</span>` : ""}${end ? html`<div class="tools-end">${end}</div>` : ""}</header>
  ${tools ? html`<div class="tools">${tools}</div>` : ""}
  <div class="body ${flush ? "flush" : ""}">${body}</div></section>`;
const chartBox = (id, label, size = "") => html`<div class="chart ${size}" id="${id}" role="img" aria-label="${label}"></div>`;

// ── routing ──────────────────────────────────────────────────────────────────
const PAGES = [
  { id: "overview", label: "운영 현황", group: "모니터링" },
  { id: "activity", label: "호출 로그", group: "모니터링" },
  { id: "audit", label: "감사 기록", group: "모니터링" },
  { id: "approvals", label: "승인 대기", group: "모니터링", badge: "approvals" },
  { id: "coverage", label: "통제 범위", group: "접근·통제", badge: "coverage" },
  { id: "servers", label: "MCP 서버", group: "접근·통제" },
  { id: "people", label: "사용자·엔드포인트", group: "접근·통제" },
  { id: "intake", label: "도입 신청", group: "수명주기" },
  { id: "termination", label: "종료·폐기", group: "수명주기", badge: "termination" },
  { id: "policy", label: "정책", group: "수명주기" },
];
let viewer = null;
let routeSeq = 0;
let current = { page: "", arg: "", query: new URLSearchParams() };
const badges = { approvals: 0, termination: 0, coverage: 0 };

function renderNav(active) {
  const groups = new Map();
  for (const p of PAGES.filter((x) => viewer.pages.includes(x.id))) {
    if (!groups.has(p.group)) groups.set(p.group, []);
    groups.get(p.group).push(p);
  }
  const shortcuts = [
    viewer.git_url && html`<a href="${viewer.git_url}" target="_blank" rel="noopener" aria-label="내부 저장소 (새 탭)" title="내부 저장소">${icon("git")}<span>내부 저장소</span><span class="ext" aria-hidden="true">↗</span></a>`,
    viewer.kit && html`<a href="#" data-act="pc-kit" aria-label="내 PC 연결" title="내 PC 연결">${icon("plug")}<span>내 PC 연결</span></a>`,
  ].filter(Boolean);
  $("#nav").innerHTML = String(html`${[...groups].map(([group, pages]) => html`<div class="group">${group}</div>${pages.map((p) => html`
    <a href="#/${p.id}" title="${p.label}" aria-label="${p.label}" ${active === p.id ? raw('aria-current="page"') : ""}>${icon(p.id)}<span>${p.label}</span>
      ${p.badge && badges[p.badge] ? html`<span class="count">${badges[p.badge]}</span>` : ""}</a>`)}`)}
    ${shortcuts.length ? html`<div class="group">바로가기</div>${shortcuts}` : ""}`);
}

function setNavCollapsed(closed) {
  document.documentElement.classList.toggle("nav-collapsed", closed);
  const button = document.querySelector('[data-act="sidebar"]');
  button.setAttribute("aria-expanded", String(!closed));
  button.setAttribute("aria-label", closed ? "메뉴 펼치기" : "메뉴 접기");
  button.title = closed ? "메뉴 펼치기" : "메뉴 접기";
}

function parseHash() {
  const [path, query = ""] = location.hash.replace(/^#\/?/, "").split("?");
  const [page = "", arg = ""] = path.split("/").map(decodeURIComponent);
  return { page, arg, query: new URLSearchParams(query) };
}

async function route() {
  if (matchMedia("(max-width: 900px)").matches) setNavCollapsed(true);
  stopLive();
  stopIntake();
  // Only hide the drawer: closeDrawer() also rewrites #/servers/<id> to #/servers, which here
  // would drop the id this route is about to open (a server row never opened its drawer).
  setDrawer(false);
  charts.disposeAll();
  const at = parseHash();
  const id = viewer.pages.includes(at.page) ? at.page : viewer.pages[0];
  // Canonicalize synchronously: a later hashchange would close first-login setup.
  if (id !== at.page) { history.replaceState(null, "", `#/${id}`); return route(); }
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
    if (id === "intake") intakeRendered = String(out.html);
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
const reload = () => current.page === "intake" && parseHash().page === "intake"
  && parseHash().query.get("t") !== "new" ? refreshIntake() : route();

/** Remember the open tab in the address, without a reload. */
function rememberTab(key) {
  const q = new URLSearchParams(current.query);
  q.set("t", key);
  current.query = q;
  history.replaceState(null, "", `#/${current.page}${current.arg ? `/${encodeURIComponent(current.arg)}` : ""}?${q}`);
}

async function refreshBadges() {
  try {
    const [o, conn] = await Promise.all([gw("overview"), api("/api/connectors?summary=1")]);
    badges.approvals = o.pending_approvals;
    badges.termination = (o.termination?.open_cases || 0) + (o.termination?.awaiting_close || 0);
    badges.coverage = conn.summary.pending + conn.summary.expired;
    renderNav($("#view").dataset.page);
  } catch { /* badges are a convenience; the pages show the real numbers */ }
}

// ── shared pieces ────────────────────────────────────────────────────────────
const modeChip = (mode) => chip(mode === "enforce" ? "allow" : "alert", mode === "enforce" ? "집행 모드" : "관찰 모드");

function decisionRow(r) {
  return html`<tr class="clickable" tabindex="0" data-act="decision" data-id="${r.id}">
    <td class="t">${when(r.at, { seconds: true })}</td>
    <td>${decisionChip(r.decision)}<span class="sub mono">${r.policy_id}</span></td>
    <td class="who-cell"><b>${r.who}</b><span class="sub">${r.workstation ? html`${entityRef(r.workstation, 18)} · ` : ""}${r.agent === "termination-probe" ? "종료 점검" : r.harness ? harnessLabel(r.harness) : "—"}</span></td>
    <td>${r.event_kind === "mcp-connection" ? chip("block", "연결 거부") : ""}<code>${r.server}.${r.tool}</code>${r.target ? html`<span class="sub muted" title="${r.target}">${short(r.target, 60)}</span>` : ""}</td>
    <td>${flow3(r)}</td></tr>`;
}
const decisionTable = (rows, id = "") => html`<table class="data call-table"><thead><tr><th>시각</th><th>판정·정책</th><th>사용자·엔드포인트</th>
  <th>도구·대상</th><th>실행 결과</th></tr></thead><tbody ${id ? raw(`id="${id}"`) : ""}>${rows.map(decisionRow)}</tbody></table>`;

// A registration is approved until a date; past it the calls are blocked.
const VALIDITY = { 1: "1일", 30: "30일", 90: "90일", 180: "180일", 365: "1년" };
function validityChip(registration) {
  if (!registration?.valid_until) return "";
  const days = Math.ceil((new Date(registration.valid_until).getTime() - Date.now()) / 86400000);
  return days <= 0 ? chip("block", "사용 기한 만료") : chip(days <= 14 ? "alert" : "outline", `D-${days}`);
}

// ── pages ────────────────────────────────────────────────────────────────────
const ROUTES = {};

ROUTES.overview = async (_, tab) => {
  const [o, blocked, pl] = await Promise.all([gw("overview"), gw("activity?limit=10&decision=Block"), planes()]);
  feed.rows = mergeRows([], blocked.rows);
  const t = o.today, x = o.execution, term = o.termination || {};
  const buckets = hourBuckets(o.series);
  const byServer = splitBy(o.flows, "server", (r) => Number(r.n));
  const flowTotal = o.flows.reduce((s, f) => s + Number(f.n || 0), 0);
  const stations = o.workstations;
  const items = dedupeItems(pl?.items || []);
  const count = (s) => items.filter((i) => i.state === s).length;
  const devices = (pl?.devices || []).filter((d) => d.endpoint_id);
  const deviceOf = Object.fromEntries(devices.map((d) => [d.endpoint_id, d]));
  const outside = items.filter((i) => !i.class.startsWith("gateway_")).length;
  const bypass = items.filter((i) => i.state === "bypass_possible").sort((a, b) => (b.bypass || []).length - (a.bypass || []).length).slice(0, 8);
  // decision -> sent? -> executed? -> response, for today's tool calls.
  const RESP = Object.fromEntries(Object.entries(RESPONSE).map(([k, [, label]]) => [k, label]));
  const pipe = { nodes: new Map(), links: new Map() };
  const node = (name) => { if (!pipe.nodes.has(name)) pipe.nodes.set(name, { name }); return name; };
  const link = (a, b, n) => { const k = `${a}|${b}`; pipe.links.set(k, { source: a, target: b, value: (pipe.links.get(k)?.value || 0) + n }); };
  for (const r of o.pipeline || []) {
    const n = Number(r.n) || 0, d = node(DECISION_LABEL[r.decision] || r.decision);
    const sent = node(r.attempted ? "전송" : "실행 안 함");
    link(d, sent, n);
    if (!r.attempted) continue;
    const ran = node(r.executed ? "실행됨" : "실행 미확인");
    link(sent, ran, n);
    if (r.executed) link(ran, node(RESP[r.response] || r.response), n);
  }
  return {
    html: page({
      head: head("운영 현황", { status: modeChip(o.enforcement) }),
      kpis: kpiStrip([["게이트웨이 경유 호출", x.tool_calls, "", "#/activity?event_kind=tools/call"],
        ["통제 중인 엔드포인트", devices.filter((d) => d.account_state === "endpoint_enforced").length, "", "#/coverage?t=devices"],
        ["실행된 호출", x.executed, "allow", "#/activity?execution=executed"],
        ["응답 보류", x.withheld, "block", "#/activity?execution=withheld"],
        ["우회 가능", count("bypass_possible"), "block", "#/coverage?t=items&state=bypass_possible"],
        ["미해결 T2·T3", term.unresolved_grades, "alert", "#/termination"]]),
      active: tab || "summary",
      tabs: [
        { key: "summary", label: "요약", body: html`<div class="stack">
          <div class="overview-hero">
            ${panel("최근 24시간 호출", chartBox("c-summary-traffic", "최근 24시간 시간대별 판정", "sm"), { end: html`<a class="btn sm" href="#/activity">호출 로그</a>` })}
            ${panel("확인 필요", html`<div class="action-list">
              <a class="action-link" href="#/approvals"><span>승인 대기</span><b class="n">${o.pending_approvals || 0}</b></a>
              <a class="action-link" href="#/coverage?t=items&state=bypass_possible"><span>우회 가능</span><b class="n">${count("bypass_possible")}</b></a>
              <a class="action-link" href="#/termination"><span>진행 중인 종료</span><b class="n">${term.open_cases || 0}</b></a>
            </div>`)}
          </div>
          ${panel("최근 차단", feed.rows.length ? decisionTable(feed.rows) : empty("차단된 호출 없음"), { flush: true, end: html`<a class="btn sm" href="#/activity?decision=Block">전체</a>` })}
        </div>` },
        { key: "planes", label: "통제 현황", n: count("bypass_possible"), hot: count("bypass_possible") > 0, body: html`<div class="stack"><div class="grid c21">
          ${panel("분류별 통제 상태", items.length ? chartBox("c-ov-matrix", "분류별 통제 상태 항목 수", "lg") : empty("항목 없음"), { sub: `게이트웨이 밖 ${outside}건` })}
          ${panel("확인 근거", items.length ? chartBox("c-ov-evidence", "통제 상태의 확인 근거", "sm") : empty("항목 없음"))}</div>
          ${panel("우회 가능 항목", bypass.length ? html`<table class="data"><thead><tr><th>항목</th><th>분류</th><th>상태</th><th class="num">우회 경로</th></tr></thead><tbody>
            ${bypass.map((i) => html`<tr class="clickable" tabindex="0" data-act="goto" data-href="#/coverage?t=items&state=bypass_possible&q=${encodeURIComponent(i.name)}">
              <td><b>${i.name}</b><span class="sub mono">${short(i.target || "", 50)}</span></td><td class="small">${INTEGRATION_CLASS[i.class] || i.class}</td>
              <td>${statusPair(i)}</td><td class="num bad-text">${(i.bypass || []).length}</td></tr>`)}</tbody></table>` : empty("우회 가능 항목 없음"),
            { flush: true, end: html`<a class="btn sm" href="#/coverage?t=items&state=bypass_possible">전체</a>` })}</div>` },
        { key: "exec", label: "실행·응답", n: x.withheld, hot: x.withheld > 0, body: html`<div class="stack">
          ${panel("판정에서 응답까지", (o.pipeline || []).length ? chartBox("c-ov-pipeline", "오늘 도구 호출의 판정에서 응답 처리까지의 흐름", "xl") : empty("오늘 도구 호출 없음"), { sub: "오늘" })}
          <div class="grid c2">
            ${panel("응답 처리", chartBox("c-ov-response", "오늘 실행된 호출의 응답 처리 비율", "sm"), { sub: `마스킹 ${x.masked} · 보류 ${x.withheld}` })}
            ${panel("실행 여부", chartBox("c-ov-sent", "오늘 호출의 실행 여부", "sm"), { sub: `미확인 ${x.unknown}` })}</div></div>` },
        { key: "traffic", label: "트래픽", body: html`<div class="stack">
          ${panel("시간대별 판정", chartBox("c-traffic", "최근 24시간 시간대별 판정 건수", "lg"), { sub: "최근 24시간" })}
          <div class="grid c12">
            ${panel("판정 비율", chartBox("c-share", "오늘 판정 비율", "sm"), { sub: "오늘" })}
            ${panel("서버별 호출", chartBox("c-servers", "최근 24시간 서버별 호출과 판정", "sm"), { sub: `${byServer.length}개 서버 · 24시간` })}
          </div>
          ${panel("하네스 → MCP 서버 → 판정", flowTotal ? chartBox("c-flow", "하네스에서 서버를 거쳐 판정까지의 호출 흐름", "xl") : empty("최근 24시간 호출 없음"), { sub: `${flowTotal}건 · 24시간` })}
          ${panel("엔드포인트", html`<table class="data"><thead><tr><th>엔드포인트</th><th>사용자</th><th>하네스</th><th class="num">24시간 호출</th><th>통제 상태</th><th>마지막 호출</th></tr></thead><tbody>
            ${stations.map((w) => html`<tr><td>${entityRef(w.endpoint_id)}</td><td><b>${w.display_name || w.owner_token}</b><span class="sub">${w.department || ""}</span></td>
              <td>${w.harness ? chip("plain", harnessLabel(w.harness)) : NONE}</td><td class="num">${w.calls}</td>
              <td>${deviceOf[w.endpoint_id] ? statusPair(deviceOf[w.endpoint_id]) : chip("outline", "관찰만")}</td><td class="small">${ago(w.last_call)}</td></tr>`)}
            </tbody></table>${stations.length ? "" : empty("엔드포인트 없음")}`, { flush: true })}</div>` },
        { key: "risk", label: "위험·종료", n: t.Block, hot: t.Block > 0, body: html`<div class="grid c2">
            ${panel("자주 걸린 정책", o.top_policies.length ? chartBox("c-policies", "최근 24시간 차단·경보가 많은 정책") : empty("최근 24시간 차단·경보 없음"), { sub: "최근 24시간" })}
            ${panel("종료·폐기", chartBox("c-term", "종료·폐기 현황"), { end: html`<a class="btn sm" href="#/termination">열기</a>` })}
          </div>` },
      ],
    }),
    charts: {
      "c-summary-traffic": () => charts.decisionColumns(buckets.map((b) => b.label), buckets),
      "c-ov-matrix": () => charts.stacked(Object.values(INTEGRATION_CLASS),
        Object.entries(CONTROL_STATE).map(([k, [, label]]) => ({ name: label, color: charts.color(STATE_DECISION[k]),
          data: Object.keys(INTEGRATION_CLASS).map((c) => items.filter((i) => i.class === c && i.state === k).length) })),
        { horizontal: true, onClick: (e) => { const c = Object.keys(INTEGRATION_CLASS)[e.dataIndex]; const st = Object.keys(CONTROL_STATE)[e.seriesIndex];
          if (c && st) location.hash = `#/coverage?t=items&class=${c}&state=${st}`; } }),
      "c-ov-evidence": () => charts.donut(Object.entries(EVIDENCE).map(([k, ev]) => ({ name: ev.label,
        value: items.filter((i) => (i.evidence_kind || "none") === k).length,
        color: charts.color(["", "Alert", "Restrict", "Allow", "Allow"][ev.level]) })).filter((g) => g.value)),
      "c-ov-pipeline": () => charts.sankey({ nodes: [...pipe.nodes.values()], links: [...pipe.links.values()] }),
      "c-ov-response": () => charts.donut([
        { name: "응답 반환", value: Math.max(0, x.executed - x.masked - x.withheld), color: charts.color("Allow") },
        { name: "마스킹 반환", value: Number(x.masked), color: charts.color("Restrict") },
        { name: "응답 보류", value: Number(x.withheld), color: charts.color("Block") }].filter((g) => g.value)),
      "c-ov-sent": () => charts.donut([
        { name: "실행됨", value: Number(x.executed), color: charts.color("Allow") },
        { name: "실행 미확인", value: Number(x.unknown), color: charts.color("Alert") },
        { name: "실행 안 함", value: Number(x.not_sent), color: charts.color("") }].filter((g) => g.value)),
      "c-traffic": () => charts.decisionColumns(buckets.map((b) => b.label), buckets),
      "c-share": () => charts.donut(DECISIONS.map((d) => ({ name: DECISION_LABEL[d], value: t[d], color: charts.color(d) }))),
      "c-servers": () => charts.decisionColumns(byServer.map((g) => g.key), byServer, {
        horizontal: true, grouped: true, onClick: (e) => { location.hash = `#/activity?server=${encodeURIComponent(e.name)}`; } }),
      "c-flow": () => charts.sankey(sankeyData(o.flows, (d) => DECISION_LABEL[d] || d)),
      "c-policies": () => charts.bars(o.top_policies.map((p) => ({ name: p.policy_id, value: Number(p.n), color: charts.color(p.decision) }))),
      "c-term": () => charts.columns([
        { name: "진행", value: term.open_cases }, { name: "종결 대기", value: term.awaiting_close },
        { name: "T2·T3", value: term.unresolved_grades, color: charts.color("Alert") }, { name: "기한 초과", value: term.overdue, color: charts.color("Block") },
        { name: "폐기 잔존", value: term.retired_residue, color: charts.color("Alert") }, { name: "미등록 MCP", value: term.shadow_endpoints, color: charts.color("Block") }]),
    },
  };
};

// Activity keeps its rows between renders so live updates and the detail drawer
// read from the same list. Paused, it keeps polling but holds new rows back and
// counts them, so the list stops moving without going stale.
const FEED_FILTERS = ["decision", "server", "person", "event_kind", "execution"];
const feed = { rows: [], pending: [], cursor: 0, filters: { decision: "", server: "", person: "", event_kind: "", execution: "" }, query: "",
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
    "c-by-server": () => { const g = splitBy(shown, "server"); return charts.decisionColumns(g.map((x) => x.key), g, { horizontal: true, grouped: true }); },
    "c-by-person": () => { const g = splitBy(shown, "who"); return charts.decisionColumns(g.map((x) => x.key), g, { horizontal: true, grouped: true }); },
    "c-by-response": () => charts.donut(Object.entries(RESPONSE).map(([k, [tone, label]]) => ({ name: label,
      value: shown.filter((r) => (r.response || "not_executed") === k).length, color: charts.color(TONE_DECISION[tone]) })).filter((g) => g.value)),
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
  // A link that names a filter (an overview KPI) replaces the whole set; keeping the
  // others would AND a stale filter with the new one into an empty list.
  if (FEED_FILTERS.some((key) => query.has(key))) for (const key of FEED_FILTERS) feed.filters[key] = query.get(key) || "";
  if (query.has("q")) feed.query = query.get("q");
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
      head: head("호출 로그", {
        status: html`<span class="live"><span class="dot" id="feed-dot"></span><span id="feed-status"></span></span>`,
        actions: html`<button class="btn" type="button" data-act="live" aria-pressed="${String(!feed.live)}">${feed.live ? "일시정지" : "실시간 재개"}</button>`,
      }),
      active: tab || "live",
      tabs: [
        { key: "live", label: "호출 목록", body: html`<section class="panel">
          <div class="filters">
            <label class="grow">검색<input data-feed-search type="search" maxlength="120" value="${feed.query}" placeholder="사용자·엔드포인트·도구·정책" aria-label="호출 검색" /></label>
            <label>판정<select data-filter="decision" aria-label="판정">${option("", "모든 판정", f.decision)}
              ${Object.entries(DECISION).map(([k, [, label]]) => option(k, label, f.decision))}</select></label>
            <label>MCP 서버<select data-filter="server" aria-label="서버">${option("", "모든 서버", f.server)}${servers.map((s) => option(s, s, f.server))}</select></label>
            <label>이벤트<select data-filter="event_kind" aria-label="이벤트 종류">${option("", "모든 이벤트", f.event_kind)}${option("tools/call", "도구 호출", f.event_kind)}${option("mcp-connection", "연결 거부", f.event_kind)}</select></label>
            <label>실행 결과<select data-filter="execution" aria-label="실행 결과">${option("", "모든 실행 결과", f.execution)}${option("executed", "실행됨", f.execution)}${option("not-sent", "실행 안 함", f.execution)}${option("unknown", "실행 미확인", f.execution)}${option("withheld", "응답 보류", f.execution)}</select></label>
            ${viewer.admin ? html`<label>사용자<input data-filter="person" type="search" placeholder="이름 또는 계정" value="${f.person}" aria-label="사용자" /></label>` : ""}
          </div>
          <div class="body flush">${decisionTable([], "feed")}<p class="empty" id="feed-empty" hidden></p></div></section>` },
        { key: "stats", label: "분석", body: html`<div class="stack">
          ${panel("시간대별 호출", chartBox("c-minutes", "불러온 호출의 시간 분포", "sm"))}<div class="grid c2">
          ${panel("응답 처리", chartBox("c-by-response", "불러온 호출의 응답 처리 비율", "sm"))}
          ${panel("하네스별", chartBox("c-by-harness", "불러온 호출의 하네스별 비율", "sm"))}</div>
          ${panel("서버별", chartBox("c-by-server", "불러온 호출의 서버별 판정"))}
          ${panel("사용자별", chartBox("c-by-person", "불러온 호출의 사용자별 판정", "lg"))}</div>` },
      ],
    }),
    charts: feedCharts(),
    after: () => { renderFeed(); startLive(); },
  };
};

async function showDecision(id) {
  const r = feed.rows.find((row) => String(row.id) === String(id));
  if (!r) return;
  // The device's current state, beside (never instead of) what the call itself carried.
  const device = viewer.admin && r.device_id ? (await planes().catch(() => null))?.devices.find((d) => d.endpoint_id === r.device_id) : null;
  const conflictChip = (c) => chip((DECISION[c.decision] || [""])[0], `${(DECISION[c.decision] || [, c.decision])[1]} ${c.policy_id}`);
  openDrawer(`호출 #${r.id}`, html`<div class="drawer-summary"><span class="tool">${r.server}.${r.tool}</span>
    ${decisionChip(r.decision)}${flow3(r)}<span class="muted small">${new Date(r.at).toLocaleString("ko-KR")}</span></div>`, [
    { key: "flow", label: "호출 경로", body: html`${pipeline(r, device)}<blockquote class="quote">${r.reason}</blockquote>` },
    { key: "summary", label: "요약", body: html`<blockquote class="quote">${r.reason}</blockquote>${kv([
      ["시각", new Date(r.at).toLocaleString("ko-KR")], ["사용자", `${r.who}${r.department ? ` · ${r.department}` : ""}`],
      ["역할", ROLE[r.role] || r.role], ["엔드포인트", r.workstation], ["하네스", r.harness ? harnessLabel(r.harness) : r.agent],
      ["이벤트", r.event_kind === "mcp-connection" ? "연결 거부" : "도구 호출"],
      ["도구", html`<code>${r.server}.${r.tool}</code>`], ["대상", r.target ? html`<code>${r.target}</code>` : ""]])}` },
    { key: "policy", label: "정책", n: (r.pac_failures || []).length, body: kv([
      ["최종 정책", html`<code>${r.policy_id}</code>`],
      ["실행 권한 위반", (r.pac_failures || []).length ? html`${r.pac_failures.map((x) => chip("block", x))}` : "없음"],
      ["함께 해당한 정책", (r.conflicts || []).length ? html`${r.conflicts.map(conflictChip)}` : "없음"],
      ["행위", r.action_ko || ACTION[r.action] || "—"], ["데이터 등급", r.data_class_ko], ["분류 근거", r.summary],
      ["개인정보", (r.privacy_types || []).join(", ")], ["연쇄 탐지", (r.sequence_flags || []).join(", ")],
      ["승인 요청", r.approval_id], ["집행 모드", r.enforcement === "monitor" ? "관찰" : r.enforcement === "enforce" ? "집행" : r.enforcement],
      ["집행 모드 판정", r.would_decision ? (DECISION[r.would_decision]?.[1] || r.would_decision) : ""]]) },
    { key: "trace", label: "추적", body: html`${kv([["감사 해시", r.evidence_sha256 ? html`<code>${r.evidence_sha256}</code>` : ""],
      ["Trace ID", r.trace_id ? html`<code>${r.trace_id}</code>` : ""], ["오류", r.error], ["작업", r.task_id]])}
      <details><summary>원본</summary>${json(r)}</details>` },
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
        { key: "history", label: "처리 이력", n: history.length, body: html`<div class="stack">
          ${panel("이력", history.length ? html`<table class="data"><thead><tr><th>요청자</th><th>도구</th><th>결과</th><th>처리</th><th>검토자</th></tr></thead><tbody>
            ${history.map((h) => html`<tr><td class="who-cell"><b>${h.display_name || h.requested_by}</b><span class="sub">${h.department || ""}</span></td>
              <td><code>${h.server_id}.${h.tool}</code></td><td>${chip(...(APPROVAL_STATUS[h.status] || ["", h.status]))}</td>
              <td class="small">${when(h.reviewed_at || h.created_at)}</td><td class="small">${h.reviewed_by || "—"}</td></tr>`)}</tbody></table>` : "", { flush: true })}<details class="analysis"><summary>승인 처리 분석</summary><div class="grid c12">
          ${panel("결과", history.length ? chartBox("c-appr-status", "처리된 승인 요청의 결과 비율", "sm") : empty("이력 없음"))}
          ${panel("서버별 요청", byServer.length ? chartBox("c-appr-server", "서버별 승인 요청 수", "sm") : empty("요청 없음"))}</div></details></div>` },
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
      ["엔드포인트", a.client?.workstation], ["하네스", a.client?.harness?.name ? harnessLabel(a.client.harness.name) : a.client?.agent],
      ["요청", when(a.created_at, { seconds: true })], ["만료", when(a.expires_at)]]) },
    { key: "args", label: "인자", body: json(a.arguments) },
    { key: "policy", label: "정책", body: html`${a.reason ? html`<p class="note">${a.reason}</p>` : ""}${kv([
      ["정책", html`<code>${a.policy_id || "—"}</code>`], ["행위", ACTION[a.action] || a.action], ["데이터 등급", DATA_CLASS[a.data_class] || a.data_class],
      ["분류 근거", a.summary]])}` },
  ]);
}

let registry = null;
ROUTES.servers = async (id, tab, query) => {
  const [reg, o, pl] = await Promise.all([gw("registry"), gw("overview"), planes()]);
  registry = reg;
  const counts = Object.fromEntries(o.servers.map((s) => [s.id, s]));
  const plane = Object.fromEntries((pl?.items || []).filter((i) => i.key.startsWith("gateway:")).map((i) => [i.key.slice(8), i]));
  const servers = reg.servers.map((s) => ({ ...s, registration: reg.registrations?.[s.id], plane: plane[s.id],
    ...(counts[s.id] ? { calls: counts[s.id].calls, blocked: counts[s.id].blocked, tools: counts[s.id].tools } : {}) }));
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
      head: head("MCP 서버", { actions: html`<button class="btn" data-act="catalog-refresh">계약 다시 확인</button>` }),
      active: tab || "servers",
      tabs: [
        { key: "servers", label: "서버 목록", n: servers.length, body: html`<div class="stack">
          ${panel("등록된 MCP 서버", servers.length ? html`<table class="data"><thead><tr><th>서버</th><th>상태</th><th>통제</th><th>사용 기한</th><th class="num">도구</th><th class="num">24시간 호출</th></tr></thead><tbody id="server-list">
            ${servers.map((s) => html`<tr class="clickable" tabindex="0" data-act="goto" data-href="#/servers/${encodeURIComponent(s.id)}">
              <td><b>${s.display_name}</b><span class="sub mono">${s.id}</span></td>
              <td>${chip(s.status === "READY" ? "allow" : s.status === "DISABLED" ? "outline" : "alert", SERVER_STATUS[s.status] || s.status)}
                ${s.lifecycle && s.lifecycle !== "OPERATING" ? chip(s.lifecycle === "RETIRED" ? "block" : "alert", LIFECYCLE[s.lifecycle] || s.lifecycle) : ""}
                <span class="sub">${s.deployment === "provider" ? "제공자 운영" : "사내 운영"}</span></td>
              <td>${s.plane ? statusPair(s.plane) : NONE}</td>
              <td>${validityChip(s.registration) || NONE}</td>
              <td class="num">${s.tools ?? reg.tools.filter((t) => t.server_id === s.id && t.enabled).length}</td><td class="num">${s.calls || 0}</td></tr>`)}</tbody></table><p class="empty" data-list-empty="server-list" hidden>검색 결과 없음</p>`
            : html`${empty("등록된 MCP 서버 없음")}<div class="row-actions center"><a class="btn primary" href="#/intake">도입 신청</a></div>`,
            { flush: true, tools: listToolbar("server-list", "서버 검색") })}
          <details class="analysis"><summary>서버별 호출</summary>${chartBox("c-srv-calls", "최근 24시간 서버별 호출과 판정")}</details>
        </div>` },
        { key: "tools", label: "도구", n: reg.tools.length, body: html`<div class="stack">
          ${panel("도구", html`<table class="data"><thead><tr><th>서버</th><th>도구</th><th>행위</th><th>상태</th></tr></thead><tbody>
            ${tools.map((t) => html`<tr><td class="mono">${t.server_id}</td><td><code>${t.name}</code></td>
              <td>${chip({ r: "allow", w: "alert", x: "block" }[t.action] || "", ACTION[t.action] || t.action)}</td>
              <td>${!t.enabled ? chip("outline", "미승인") : t.contract_ok ? chip("allow", "계약 일치") : chip("alert", "계약 불일치")}</td></tr>`)}
            </tbody></table>`, { flush: true, sub: `${tools.length}개`,
            tools: html`<select data-act-change="tool-filter" aria-label="서버">${option("", "모든 서버")}${reg.servers.map((s) => option(s.id, s.id))}</select>` })}<details class="analysis"><summary>도구 권한 분포</summary>${chartBox("c-srv-actions", "서버별 승인 도구 수를 읽기·쓰기·실행으로 나눈 막대")}</details></div>` },
        { key: "contract", label: "계약", n: drifted.length, hot: drifted.length > 0, body: html`<div class="stack"><div class="grid c12">
          ${panel("도구 계약", chartBox("c-contract", "승인 도구의 계약 일치 비율", "sm"), { sub: html`<span class="mono">${reg.catalog_version}</span>` })}
          ${panel("서버 상태", html`<table class="data"><thead><tr><th>서버</th><th>상태</th><th>사유</th><th>마지막 확인</th><th></th></tr></thead><tbody>
            ${servers.map((s) => html`<tr><td><b>${s.display_name}</b><span class="sub mono">${s.id}</span></td>
              <td>${chip({ READY: "allow", DRIFT: "alert" }[s.status] || "block", SERVER_STATUS[s.status] || s.status)}</td>
              <td class="small clip">${s.status_reason || "—"}</td><td class="small">${ago(s.last_seen_at)}</td>
              <td class="num">${s.status === "DRIFT" && !s.registration ? html`<button class="btn sm primary" data-act="approve-contract" data-id="${s.id}">승인본 갱신</button>` : ""}</td></tr>`)}
            </tbody></table>`, { flush: true })}</div></div>` },
      ],
    }),
    charts: {
      "c-srv-calls": () => charts.decisionColumns(byServer.map((g) => g.key), byServer, { horizontal: true }),
      "c-srv-actions": () => charts.stacked(actionSplit.map((a) => a.key), [
        { name: "읽기", color: charts.color("Allow"), data: actionSplit.map((a) => a.r) },
        { name: "쓰기", color: charts.color("Alert"), data: actionSplit.map((a) => a.w) },
        { name: "외부 전송·실행", color: charts.color("Block"), data: actionSplit.map((a) => a.x) }]),
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
  const registration = registry.registrations?.[id];
  openDrawer(s.display_name, html`<div class="row-actions">${chip({ READY: "allow", DRIFT: "alert" }[s.status] || "block", SERVER_STATUS[s.status] || s.status)}
      ${chip(s.lifecycle === "OPERATING" ? "outline" : "block", LIFECYCLE[s.lifecycle] || s.lifecycle)}
      ${chip("outline", s.deployment === "provider" ? "제공자 운영" : "사내 운영")}
      ${validityChip(registration)}
      ${s.status === "DRIFT" && !registration ? html`<button class="btn sm primary" data-act="approve-contract" data-id="${s.id}">승인본 갱신</button>` : ""}
      ${s.lifecycle !== "RETIRED" ? html`<button class="btn sm" type="button" data-act="server-check" data-id="${s.id}">연결 확인</button>` : ""}
      ${registration && !registration.intake_id ? chip("block", "도입 신청 없음 · 차단") : ""}
      ${registration ? html`<button class="btn sm danger" type="button" data-act="server-deregister" data-id="${s.id}">등록 해제</button>` : ""}</div>
    ${s.status_reason && s.status !== "READY" ? html`<p class="note warn">${s.status_reason}</p>` : ""}`, [
    { key: "info", label: "개요", body: kv([["ID", html`<code>${s.id}</code>`], ["게이트웨이 경로", html`<code>/mcp/${s.id}/</code>`],
      ["패키지", html`<code>${s.source_ref || `${s.package}@${s.version}`}</code>`], ["원격 주소", html`<code>${s.endpoint}</code>`],
      ["공급자", s.supplier], ["라이선스", s.license], ["하위 시스템", downstreamText(s.downstream)],
      ["사용 기한", registration ? `${when(registration.valid_until)} · ${DATA_CLASS[registration.data_class] || ""}` : ""],
      ["등록", registration ? `${registration.registered_by} · ${when(registration.registered_at)}` : ""],
      ["마지막 확인", s.last_seen_at ? `${when(s.last_seen_at)} · ${ago(s.last_seen_at)}` : ""]]) },
    { key: "tools", label: "도구", n: tools.length, body: html`<table class="data"><thead><tr><th>도구</th><th>행위</th><th>상태</th></tr></thead><tbody>
      ${tools.map((t) => html`<tr><td><code>${t.name}</code></td><td>${chip({ r: "allow", w: "alert", x: "block" }[t.action] || "", ACTION[t.action] || t.action)}</td>
        <td>${!t.enabled ? chip("outline", "미승인") : t.contract_ok ? chip("allow", "일치") : chip("alert", "불일치")}</td></tr>`)}</tbody></table>` },
    { key: "exit", label: "종료 조건", body: html`<div class="pill-list">${Object.entries(EXIT_TERMS).map(([k, label]) => bool(terms[k], label))}</div>
      ${creds.length ? kv([["보유 자격", html`${creds.map((c) => html`<code>${c.id}</code> `)}`]]) : ""}
      ${rels.length ? html`<h3>이용 관계</h3>${kv(rels.map((u) => [u.purpose, html`${u.organization} · ${(REL_STATUS[u.status] || [, u.status])[1]}
        <span class="sub">허용 자원 ${(u.allowed_resources || []).map(resourceName).join(", ") || "—"}</span>`]))}
        <div class="row-actions"><a class="btn sm" href="#/termination">종료·폐기</a></div>` : ""}` },
  ]);
}
const resourceName = (a) => (typeof a === "string" ? a : a?.name || JSON.stringify(a));
function downstreamText(d) {
  if (!d) return "";
  if (typeof d !== "object") return String(d);
  return Object.entries(d).map(([k, v]) => `${k} ${Array.isArray(v) ? v.join(", ") : typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ");
}

// ── harness inventory: a reported state is not enforcement evidence ──
const CONNECTOR_KIND = { connector: "claude.ai 커넥터", plugin: "플러그인", server: "직접 추가", app: "ChatGPT 앱", feature: "기본 기능" };
const CONNECTOR_STATE = { pending: ["approval", "미승인"], expired: ["block", "검토 기한 만료"], denied: ["block", "거부"],
  approved: ["allow", "승인"], default: ["outline", "재검토"] };
const FEATURE_LABEL = { web_search: "웹 검색", apps: "ChatGPT 앱 전체", plugins: "플러그인", browser_use: "브라우저 조작",
  computer_use: "컴퓨터 조작", image_generation: "이미지 생성", memories: "메모리" };
const connectorName = (g) => (g.kinds.includes("feature") ? FEATURE_LABEL[g.names[0]] || g.names[0] : g.names.join(" · "));
const connectorTarget = (g) => (g.key.split(":")[1] === "stdio" ? "stdio" : g.key.split(":").slice(2).join(":"));
// What the harness said about the item on that PC, in words (Claude Code prints English symbols).
const HARNESS_STATUS = [[/Connected/, "연결됨"], [/Needs authentication/, "인증 필요"], [/Failed/, "연결 실패"],
  [/Not configured/, "설정 안 됨"], [/^(enabled|on)$/, "켜짐"], [/^disabled$/, "꺼짐"], [/^absent$/, "미관측"]];
const harnessStatus = (s) => (HARNESS_STATUS.find(([re]) => re.test(s || "")) || [null, s || "켜짐"])[1];
function connectorState(g) {
  const [tone, label] = CONNECTOR_STATE[g.state] || ["", g.state];
  const days = g.due ? Math.ceil((new Date(g.due).getTime() - Date.now()) / 86400000) : null;
  return chip(tone, g.state === "pending" && days !== null ? `${label} D-${Math.max(days, 0)}` : label);
}
const connectorButtons = (g) => g.decision
  ? html`<button class="btn sm" data-act="connector-decide" data-key="${g.key}" data-decision="reset">되돌리기</button>`
  : html`${g.state === "default" ? "" : html`<button class="btn sm primary" data-act="connector-decide" data-key="${g.key}" data-decision="approved">승인</button>`}
    <button class="btn sm danger" data-act="connector-deny" data-key="${g.key}" data-name="${connectorName(g)}">거부</button>`;
let connectorGroups = [];

// Which control governs each integration and endpoint, with what evidence.
const STATE_DECISION = { gateway_enforced: "Allow", endpoint_enforced: "Allow", vendor_enforced: "Restrict",
  observed_only: "Alert", unknown_not_enrolled: "", bypass_possible: "Block" };
ROUTES.coverage = async (_, tab, query) => {
  const [p, inv, conn] = await Promise.all([planes(), gw("endpoint/inventory"), api("/api/connectors")]);
  connectorGroups = conn.items;
  const items = dedupeItems(p.items);
  integrationItems = items;
  const state = query.get("state") || "", cls = query.get("class") || "", q = (query.get("q") || "").toLowerCase();
  const rows = items.filter((i) => (!state || i.state === state) && (!cls || i.class === cls)
    && (!q || `${i.name} ${i.target || ""} ${(i.owners || []).join(" ")}`.toLowerCase().includes(q)));
  const count = (s) => items.filter((i) => i.state === s).length;
  const review = conn.summary.pending + conn.summary.expired;
  const coverageSelect = (key, label, choices, cur) => html`<label class="list-search">${label}<select data-coverage-filter="${key}" aria-label="${label}">
    <option value="">전체</option>${Object.entries(choices).map(([k,v]) => html`<option value="${k}" ${k === cur ? raw("selected") : ""}>${Array.isArray(v) ? v[1] : v}</option>`)}</select></label>`;
  const shadowRows = inv.entries.filter((e) => e.classification !== "registered");
  return {
    html: page({
      head: head("통제 범위", { actions: html`<button class="btn" type="button" data-act="connector-policy">커넥터 정책 내보내기</button>` }),
      kpis: kpiStrip([["전체", items.length, "", "#/coverage?t=items"],
        ["게이트웨이 통제", count("gateway_enforced"), "allow", "#/coverage?t=items&state=gateway_enforced"],
        ["엔드포인트 통제", count("endpoint_enforced"), "allow", "#/coverage?t=items&state=endpoint_enforced"],
        ["벤더 통제", count("vendor_enforced"), "restrict", "#/coverage?t=items&state=vendor_enforced"],
        ["관찰만·미등록", count("observed_only") + count("unknown_not_enrolled"), "alert", "#/coverage?t=items&state=observed_only"],
        ["우회 가능", count("bypass_possible"), "block", "#/coverage?t=items&state=bypass_possible"]]),
      active: tab || "items",
      tabs: [
        { key: "items", label: "MCP·커넥터", n: items.length, body: html`<div class="stack">
          ${panel("MCP·커넥터·플러그인", html`<table class="data"><thead><tr><th>항목</th><th>분류</th><th>관리 주체</th><th>상태</th><th>승인</th><th class="num">우회 경로</th><th>발견</th></tr></thead><tbody>
            ${rows.map((i) => html`<tr class="clickable" tabindex="0" data-act="integration" data-key="${i.key}">
              <td><b>${i.name}</b><span class="sub">${entityRef(i.target || "", 48)}</span>${i.pcs > 1 ? html`<span class="sub">PC ${i.pcs}대</span>` : ""}</td>
              <td class="small">${INTEGRATION_CLASS[i.class] || i.class}${i.harness ? html`<span class="sub">${i.harness === "claude" ? "Claude Code" : "Codex"}</span>` : ""}</td>
              <td>${MANAGED_BY[i.managed_by] || i.managed_by}</td><td>${statusPair(i)}</td>
              <td class="small">${approvalLabel(i.approval?.state)}${i.approval?.expires_at ? html`<span class="sub">${when(i.approval.expires_at)}까지</span>` : ""}</td>
              <td class="num">${(i.bypass || []).length ? html`<span class="bad-text">${i.bypass.length}</span>` : NONE}</td>
              <td class="small">${i.discovered_from}${i.discovered_at ? html`<span class="sub">${when(i.discovered_at)}</span>` : ""}</td></tr>`)}
            </tbody></table>${rows.length ? "" : empty("조건에 맞는 항목 없음")}`, { flush: true,
            tools: html`<input type="search" data-coverage-search maxlength="80" value="${query.get("q") || ""}" placeholder="이름·대상·사용자" aria-label="항목 검색" />
              ${coverageSelect("state", "상태", CONTROL_STATE, state)}
              ${coverageSelect("class", "분류", INTEGRATION_CLASS, cls)}<span class="small muted">${rows.length}/${items.length}건</span>` })}<details class="analysis"><summary>통제 상태 분포</summary><div class="grid c21">
          ${panel("분류별 상태", items.length ? chartBox("c-cov-matrix", "분류별 통제 상태 항목 수", "lg") : empty("항목 없음"))}
          ${panel("확인 근거", items.length ? chartBox("c-cov-evidence", "항목 상태의 확인 근거 비율", "sm") : empty("항목 없음"))}</div></details></div>` },
        { key: "devices", label: "엔드포인트", n: p.devices.length, hot: p.summary.devices.bypass_possible > 0, body: panel("엔드포인트",
          html`<table class="data"><thead><tr><th>엔드포인트</th><th>사용자</th><th>플랫폼</th><th>상태</th><th>관리 계정</th><th>점검</th><th>우회 경로</th></tr></thead><tbody>
            ${p.devices.map((d) => html`<tr><td>${d.endpoint_id ? entityRef(d.endpoint_id) : NONE}<span class="sub">${d.hostname || ""}${d.account ? ` · ${d.account}` : ""}</span></td>
              <td>${d.owner || "—"}</td><td>${PLATFORM[d.platform] || d.platform || "—"}</td><td>${statusPair(d)}</td>
              <td>${d.account_state ? controlChip(d.account_state) : NONE}</td>
              <td>${checksChip(d.checks)}</td>
              <td class="small">${(d.bypass || []).length ? html`<div class="pill-list">${d.bypass.map((b) => chip("block", b))}</div>` : NONE}
                ${d.kernel_denials_24h ? html`<span class="sub">엔드포인트 차단 24시간 ${d.kernel_denials_24h}건</span>` : ""}</td></tr>`)}
            </tbody></table>${p.devices.length ? "" : empty("엔드포인트 없음")}`, { flush: true }) },
        { key: "shadow", label: "미등록·잔존", n: shadowRows.length + (inv.os_events || []).length, hot: shadowRows.length > 0, body: html`<div class="stack">
          ${panel("발견·차단", (shadowRows.length || (inv.os_events || []).length) ? chartBox("c-cov-shadow", "엔드포인트별 발견한 미등록·잔존 설정과 엔드포인트 차단 수", "sm") : empty("발견·차단 없음"))}
          ${panel("엔드포인트 MCP 설정", html`<table class="data"><thead><tr><th>엔드포인트</th><th>설정 파일</th><th>서버</th><th>연결</th><th>분류</th></tr></thead><tbody>
            ${inv.entries.map((e) => html`<tr><td>${entityRef(e.endpoint_id)}</td><td class="small mono">${e.config_path}</td>
              <td><b>${e.server_label}</b>${e.registry_name ? html`<span class="sub">${e.registry_name}</span>` : ""}</td>
              <td class="small mono clip">${e.transport} ${short(e.endpoint_ref, 60)}</td><td>${chip(...(ENDPOINT_CLASS[e.classification] || ["", e.classification]))}</td></tr>`)}
            </tbody></table>${inv.entries.length ? "" : empty("보고된 설정 없음")}`, { flush: true })}
          ${panel("엔드포인트 차단", html`<table class="data"><thead><tr><th>시각</th><th>엔드포인트</th><th>종류</th><th>대상</th></tr></thead><tbody>
            ${(inv.os_events || []).map((e) => html`<tr><td>${when(e.observed_at)}</td><td>${entityRef(e.endpoint_id)}</td>
              <td>${chip("block", e.kind === "network-denied" ? "네트워크 차단" : "실행 차단")}</td>
              <td class="mono small">${osEventTarget(e)}</td></tr>`)}
            </tbody></table>${(inv.os_events || []).length ? "" : empty("엔드포인트 차단 없음")}`, { flush: true })}</div>` },
        { key: "vendor", label: "벤더 커넥터", n: review, hot: review > 0, body: panel("하네스 커넥터·앱·기능",
          conn.items.length ? html`<table class="data"><thead><tr><th>이름</th><th>하네스</th><th>종류</th><th class="num">사용 PC</th><th>승인</th><th>벤더 콘솔</th><th></th></tr></thead><tbody>
            ${conn.items.map((g) => { const vendor = items.find((i) => i.item_key === g.key)?.vendor_control; return html`<tr class="clickable" tabindex="0" data-act="connector" data-key="${g.key}">
              <td><b>${connectorName(g)}</b><span class="sub mono">${connectorTarget(g)}</span></td>
              <td>${chip("plain", g.harness === "claude" ? "Claude Code" : "Codex")}</td>
              <td class="small">${g.kinds.map((k) => CONNECTOR_KIND[k] || k).join(" · ")}</td>
              <td class="num">${g.active_pcs}<span class="sub">${g.people}명</span></td>
              <td>${connectorState(g)}${g.violation ? chip("block", "미승인 사용") : ""}</td>
              <td class="small">${vendor ? html`${chip("restrict", VENDOR_CONSOLE[vendor.console_state] || vendor.console_state)}<span class="sub">${vendor.verified_by} · ${when(vendor.verified_at)}</span>` : NONE}</td>
              <td class="num nowrap">${connectorButtons(g)}</td></tr>`; })}</tbody></table>`
            : empty("보고된 커넥터 없음"), { flush: true, sub: conn.review_days ? `검토 기한 ${conn.review_days}일` : "" }) },
      ],
    }),
    charts: {
      "c-cov-matrix": () => charts.stacked(Object.values(INTEGRATION_CLASS),
        Object.entries(CONTROL_STATE).map(([k, [, label]]) => ({ name: label, color: charts.color(STATE_DECISION[k]),
          data: Object.keys(INTEGRATION_CLASS).map((c) => items.filter((i) => i.class === c && i.state === k).length) })),
        { horizontal: true, onClick: (e) => { const c = Object.keys(INTEGRATION_CLASS)[e.dataIndex]; const st = Object.keys(CONTROL_STATE)[e.seriesIndex];
          if (c && st) location.hash = `#/coverage?t=items&class=${c}&state=${st}`; } }),
      "c-cov-evidence": () => charts.donut(Object.entries(EVIDENCE).map(([k, ev]) => ({ name: ev.label,
        value: items.filter((i) => (i.evidence_kind || "none") === k).length,
        color: charts.color(["", "Alert", "Restrict", "Allow", "Allow"][ev.level]) })).filter((g) => g.value)),
      "c-cov-shadow": () => { const ids = [...new Set([...shadowRows.map((e) => e.endpoint_id), ...(inv.os_events || []).map((e) => e.endpoint_id)])];
        return charts.stacked(ids.map((id) => id.slice(0, 18)), [
          { name: "발견", color: charts.color("Alert"), data: ids.map((id) => shadowRows.filter((e) => e.endpoint_id === id).length) },
          { name: "엔드포인트 차단", color: charts.color("Block"), data: ids.map((id) => (inv.os_events || []).filter((e) => e.endpoint_id === id).length) }],
          { horizontal: true }); },
    },
  };
};

const VENDOR_CONSOLE = { blocked: "차단", limited: "제한 허용", allowed: "허용", unknown: "확인 불가" };
const CHECK_LABEL = { apparmor_enforcing: "실행 통제", nftables_active: "네트워크 통제", protected_configs: "설정 보호", ordinary_account: "일반 계정" };
function checksChip(checks) {
  const entries = Object.entries(checks || {});
  if (!entries.length) return NONE;
  const failed = entries.filter(([, v]) => !v).map(([k]) => CHECK_LABEL[k] || k);
  return failed.length ? chip("block", `미충족 ${failed.join(", ")}`) : chip("allow", `정상 ${entries.length}/${entries.length}`);
}
function osEventTarget(e) {
  const d = e.details || {};
  if (e.kind === "network-denied") return `${d.destination_ip || "—"}${d.destination_port ? `:${d.destination_port}` : ""}${d.protocol ? ` ${d.protocol}` : ""}`;
  return d.executable || d.operation || "—";
}
const MANAGED_STATE = { active: "활성", pending: "활성화 대기", quarantined: "격리" };
const SIGNUP_STATUS = { pending: ["approval", "대기"], approved: ["allow", "승인"], rejected: ["block", "거부"] };
const MANAGED_EVENT = {
  "kit-issued": ["outline", "설치 키트 발급"], enrolled: ["approval", "설치 보고"], activated: ["allow", "활성화"],
  quarantined: ["block", "격리"], revoked: ["outline", "등록 해제"], "unmanaged-login-denied": ["block", "미관리 로그인 거부"],
  "token-denied": ["block", "토큰 거부"], "mcp-auth-denied": ["block", "MCP 인증 거부"],
};
const managedEventDetail = (d) => (d && (d.reason || d.note || (d.actor ? `처리 ${d.actor}` : "") || (d.expires_at ? `${when(d.expires_at)}까지` : ""))) || "—";

// Users and the endpoints they enrolled; what controls them is on the coverage page.
let peopleAccounts = [];
let integrationItems = [];
ROUTES.people = async (_, tab) => {
  const [{ accounts }, { requests: signups }, inv, o, p, identity] = await Promise.all([
    api("/api/accounts"), api("/api/signup-requests"), gw("endpoint/inventory"), gw("overview"), planes(), api("/api/identity").catch(() => ({ provider: "local", bindings: [] }))]);
  peopleAccounts = accounts;
  const deviceState = Object.fromEntries(p.devices.filter((d) => d.endpoint_id).map((d) => [d.endpoint_id, d]));
  const harnessOf = Object.fromEntries(o.workstations.map((w) => [w.endpoint_id, w]));
  const byHarness = splitBy(o.flows, (f) => harnessLabel(f.harness), (f) => Number(f.n));
  const managed = inv.agents.filter((a) => a.managed_state && a.managed_state !== "unmanaged");
  return {
    html: page({
      head: head("사용자·엔드포인트", { actions: html`<button class="btn primary" type="button" data-act="account-invite">사용자 초대</button><button class="btn" type="button" data-act="device-issue">엔드포인트 등록</button>` }),
      kpis: kpiStrip([["사용자", accounts.length], ["엔드포인트", inv.coverage.known_endpoints], ["최근 15분 보고", inv.coverage.reporting_recently],
        ["활성", managed.filter((a) => a.managed_state === "active").length, "allow"],
        ["격리", managed.filter((a) => a.managed_state === "quarantined").length, "block"],
        ["활성화 대기", managed.filter((a) => a.managed_state === "pending").length, "approval"]]),
      active: tab || "accounts",
      tabs: [
        { key: "accounts", label: "사용자", n: accounts.length, body: panel("사용자", html`<table class="data"><thead><tr><th>이름</th><th>이메일</th><th>역할</th><th>부서</th><th>상태</th><th></th></tr></thead><tbody id="account-list">
          ${accounts.map((a) => html`<tr><td><b>${a.display_name}</b><span class="sub">${a.job_title || ""}</span></td><td class="small">${a.email}</td>
            <td>${ROLE[a.role] || a.role}</td><td>${a.department}</td>
            <td>${chip({ active: "allow", disabled: "block", locked: "alert" }[a.status] || "", { active: "사용", disabled: "중지", locked: "잠김" }[a.status] || a.status)}</td>
            <td class="num">${a.user_id === viewer.user_id ? html`<span class="small muted">본인</span>`
              : html`<button class="btn sm" data-act="account-status" data-id="${a.user_id}" data-name="${a.display_name}" data-status="${a.status}">상태 변경</button>
                ${a.user_id !== "root" ? html`<button class="btn sm danger" data-act="account-delete" data-id="${a.user_id}" data-name="${a.display_name}">삭제</button>` : ""}`}</td></tr>`)}
          </tbody></table><p class="empty" data-list-empty="account-list" hidden>검색 결과 없음</p>`, { flush: true, tools: listToolbar("account-list", "이름·이메일·부서 검색") }) },
        { key: "devices", label: "엔드포인트", n: inv.agents.length, body: html`<div class="stack">
          ${panel("엔드포인트", html`<table class="data"><thead><tr><th>엔드포인트</th><th>사용자</th><th>하네스</th><th>상태</th><th>마지막 보고</th><th></th></tr></thead><tbody>
            ${inv.agents.map((a) => html`<tr><td>${entityRef(a.endpoint_id)}<span class="sub">${PLATFORM[String(a.platform || "").toLowerCase()] || a.platform || ""}</span></td><td>${harnessOf[a.endpoint_id]?.display_name || a.owner_token || "—"}</td>
              <td>${harnessOf[a.endpoint_id]?.harness ? chip("plain", harnessLabel(harnessOf[a.endpoint_id].harness)) : NONE}</td>
              <td>${deviceState[a.endpoint_id] ? statusPair(deviceState[a.endpoint_id]) : chip("outline", "관찰만")}
                ${a.managed_state && a.managed_state !== "unmanaged" ? html`<span class="sub">${MANAGED_STATE[a.managed_state] || a.managed_state}</span>` : ""}</td>
              <td class="small">${ago(a.last_seen_at)}</td>
              <td class="num nowrap">${["pending", "quarantined"].includes(a.managed_state) && a.policy_hash ? html`<button class="btn sm primary" type="button" data-act="device-activate" data-id="${a.endpoint_id}" data-hash="${a.policy_hash}">활성화</button>` : ""}
                ${a.status === "revoked" ? chip("outline", "등록 해제됨") : html`<button class="btn sm danger" type="button" data-act="device-revoke" data-id="${a.endpoint_id}">등록 해제</button>`}</td></tr>`)}
            </tbody></table>${inv.agents.length ? "" : empty("엔드포인트 없음")}`, { flush: true })}<details class="analysis"><summary>엔드포인트·하네스별 호출</summary><div class="grid c21">
          ${panel("엔드포인트별 호출", o.workstations.length ? chartBox("c-ws-calls", "최근 24시간 엔드포인트별 호출 수", "sm") : empty("엔드포인트 없음"), { sub: "24시간" })}
          ${panel("하네스", byHarness.length ? chartBox("c-harness", "최근 24시간 하네스별 호출 비율", "sm") : empty("호출 없음"), { sub: "24시간" })}</div></details></div>` },
        { key: "signups", label: "가입 요청", n: signups.filter((s) => s.status === "pending").length,
          body: panel("가입 요청", html`<table class="data"><thead><tr><th>아이디</th><th>이름</th><th>요청</th><th>상태</th><th></th></tr></thead><tbody>
          ${signups.map((s) => html`<tr><td class="mono">${s.username}</td><td>${s.display_name}</td><td>${when(s.requested_at)}</td>
            <td>${chip(...(SIGNUP_STATUS[s.status] || ["", s.status]))}</td>
            <td class="num nowrap">${s.status === "pending" ? html`<button class="btn sm primary" data-act="signup-approve" data-id="${s.id}">승인</button>
              <button class="btn sm danger" data-act="signup-reject" data-id="${s.id}">거부</button>` : ""}</td></tr>`)}
          </tbody></table>${signups.length ? "" : empty("가입 요청 없음")}`, { flush: true }) },
        { key: "managed", label: "연결 이력", n: (inv.managed_events || []).length,
          body: panel("연결 이력", html`<table class="data"><thead><tr><th>시각</th><th>사용자·엔드포인트</th><th>내용</th><th>사유</th></tr></thead><tbody>
            ${(inv.managed_events || []).map((e) => html`<tr><td>${when(e.observed_at)}</td><td>${e.owner_token}<span class="sub mono">${e.endpoint_id || "—"}</span></td>
              <td>${chip(...(MANAGED_EVENT[e.kind] || ["", e.kind]))}</td><td class="small">${managedEventDetail(e.detail)}</td></tr>`)}</tbody></table>
            ${(inv.managed_events || []).length ? "" : empty("연결 이력 없음")}`, { flush: true }) },
        ...(identity.provider === "oidc" ? [{ key: "sso", label: "SSO", n: identity.bindings.length, body: html`<div class="stack">
          ${panel("SSO", kv([["로그인 방식", identity.label || "SSO"], ["상태", identity.configured ? "사용" : "설정 필요"], ["발급자", identity.issuer || "—"]]),
            { end: identity.configured ? html`<button class="btn sm primary" data-act="identity-bind">SSO 계정 연결</button>` : "" })}
          ${panel("연결된 SSO 계정", identity.bindings.length ? html`<table class="data"><thead><tr><th>사용자</th><th>SSO 계정</th><th>연결</th><th></th></tr></thead><tbody>${identity.bindings.map((b) => html`<tr><td>${b.principal}</td><td class="mono">${b.subject}</td><td>${b.linked_by}<span class="sub">${when(b.linked_at)}</span></td><td class="num"><button class="btn sm danger" data-act="identity-unbind" data-id="${b.id}">연결 해제</button></td></tr>`)}</tbody></table>` : empty("연결된 계정 없음"), { flush: true })}</div>` }] : []),
      ],
    }),
    charts: {
      "c-ws-calls": () => charts.bars(o.workstations.map((w) => ({ name: `${w.endpoint_id} · ${w.display_name || ""}`, value: Number(w.calls) }))),
      "c-harness": () => charts.donut(byHarness.map((g, i) => ({ name: g.key, value: g.total,
        color: ["#1f4287", "#2c5bb8", "#4f7fd6", "#86a8ff", "#9aa6b8", "#647085"][i % 6] }))),
    },
  };
};

// ── intake ───────────────────────────────────────────────────────────────────
let intakeTimer = null;
let intakeRendered = "";
function stopIntake() { clearInterval(intakeTimer); intakeTimer = null; }
let intakeRefreshing = false;
function patchIntakePanel(view, next, key) {
  const oldPanel = view.querySelector(`#p-panel-${key}`);
  const newPanel = next.querySelector(`#p-panel-${key}`);
  if (!oldPanel || !newPanel) return;
  const oldStack = oldPanel.querySelector(":scope > .stack");
  const newStack = newPanel.querySelector(":scope > .stack");
  if (!oldStack || !newStack) { oldPanel.replaceWith(newPanel); return; }
  const oldSections = [...oldStack.children];
  const newSections = [...newStack.children];
  const title = (section) => section.querySelector(":scope > header > h2")?.textContent;
  for (const [index, section] of newSections.entries()) {
    const previous = oldSections.find((item) => title(item) === title(section));
    if (previous) {
      if (!previous.querySelector(".chart") || !section.querySelector(".chart")) previous.replaceWith(section);
    } else {
      const following = newSections.slice(index + 1).map((item) => oldSections.find((old) => title(old) === title(item)))
        .find((item) => item?.isConnected);
      oldStack.insertBefore(section, following || null);
    }
  }
  for (const section of oldSections) if (!newSections.some((item) => title(item) === title(section))) section.remove();
}
async function refreshIntake() {
  if (intakeRefreshing) return;
  intakeRefreshing = true;
  const seq = routeSeq;
  try {
    const out = await ROUTES.intake("", parseHash().query.get("t") || "list");
    if (seq !== routeSeq || parseHash().page !== "intake") return;
    const markup = String(out.html);
    if (markup === intakeRendered) return;
    const next = document.createElement("div");
    next.innerHTML = markup;
    const view = $("#view");
    for (const key of ["list"]) {
      patchIntakePanel(view, next, key);
      const oldCount = view.querySelector(`#p-tab-${key} .n`);
      const newCount = next.querySelector(`#p-tab-${key} .n`);
      if (oldCount && newCount) oldCount.replaceWith(newCount);
    }
    intakeRendered = markup;
    for (const [id, build] of Object.entries(out.charts)) charts.update(id, build);
    charts.mountVisible(view);
  } finally { intakeRefreshing = false; }
}
function catalogResults(data) {
  const requests = data.requests || [], registry = data.registry || [];
  return html`${requests.length ? html`<table class="data"><thead><tr><th>MCP</th><th>신청자</th><th>상태</th><th>사내 저장소</th></tr></thead><tbody>
    ${requests.map((r) => html`<tr><td><b>${r.display_name}</b><span class="sub mono">${r.repository_url || r.endpoint_url || ""}</span></td>
      <td>${r.submitted_by_name}</td><td>${chip(...(INTAKE_STATUS[r.status] || ["", r.status]))}</td>
      <td>${r.internal_repo_url ? html`<a href="${r.internal_repo_url}" target="_blank" rel="noopener noreferrer">열기 ↗</a>` : NONE}</td></tr>`)}</tbody></table>` : empty(data.query ? "일치하는 신청 없음" : "신청 없음")}
    ${registry.length ? html`<p class="small muted">등록된 MCP: ${registry.map((r) => r.display_name).join(", ")}</p>` : ""}`;
}
ROUTES.intake = async (_, tab) => {
  const [{ requests }, catalog] = await Promise.all([api("/api/mcp-requests"),
    tab === "new" ? api("/api/mcp-catalog/search") : Promise.resolve(null)]);
  // Colours are read when the chart is drawn, so a theme switch redraws them in the new palette.
  const byStatus = () => Object.entries(INTAKE_STATUS).map(([k, [tone, label]]) => ({ name: label, value: requests.filter((r) => r.status === k).length,
    color: charts.color({ allow: "Allow", block: "Block", alert: "Alert", approval: "Approval", restrict: "Restrict" }[tone]) }));
  return {
    html: page({
      head: head("도입 신청", { actions: html`<button class="btn" data-act="reload">새로고침</button><a class="btn primary" href="#/intake?t=new">새 MCP 신청</a>` }),
      active: tab || "list",
      tabs: [
        { key: "list", label: viewer.admin ? "전체 신청" : "내 신청", n: requests.length, body: html`<div class="stack">
          ${panel("신청", html`<table class="data"><thead><tr><th>서버</th><th>상태</th><th>종료 조건</th><th>신청</th>${viewer.admin ? html`<th></th>` : ""}</tr></thead><tbody>
          ${requests.map((r) => {
            const remote = r.requested_transport !== "stdio";
            const grade = r.evidence?.exit_terms_conclusion?.grade;
            const clear = !remote || termsVerified(r.exit_terms) || grade === "T1";
            return html`<tr><td><b>${r.display_name}</b><span class="sub">${entityRef(r.endpoint_url || r.repository_url, 52)}</span>
              <span class="sub">${r.intake_kind === "remote-endpoint" ? "원격 MCP" : "소스 코드"} · ${TRANSPORT[r.requested_transport] || r.requested_transport}${r.commit_sha ? ` · ${r.commit_sha.slice(0, 12)}` : ""}</span>
              ${r.internal_repo_url ? html`<a class="sub" href="${r.internal_repo_url}" target="_blank" rel="noopener noreferrer">사내 저장소 ↗</a>` : ""}
              ${r.registered_server_id ? html`<span class="sub">${chip("allow", "게이트웨이 등록")} <code>/mcp/${r.registered_server_id}/</code></span>` : ""}</td>
            <td>${chip(...(INTAKE_STATUS[r.status] || ["", r.status]))}</td>
            <td class="small">${exitConclusionChip(r)}</td>
            <td class="small">${when(r.created_at)}</td>
            ${viewer.admin ? html`<td><div class="row-actions">
              ${r.intake_kind === "remote-endpoint" && ["HOLD", "REMOTE_REVIEWED"].includes(r.status) ? html`<button class="btn sm primary" data-act="intake-register" data-review="true" data-id="${r.id}"
                data-name="${r.display_name}" data-repo="${r.endpoint_url}" data-principal="${r.submitted_by}">계약·사용 범위 검토</button>` : ""}
              ${r.intake_kind !== "remote-endpoint" && ["HOLD", "FAILED"].includes(r.status) ? html`<button class="btn sm primary" data-act="intake-queue" data-id="${r.id}">${r.status === "FAILED" ? "재검증" : "검증 시작"}</button>` : ""}
              ${["VALIDATED", "REMOTE_REVIEWED"].includes(r.status) ? (clear ? html`<button class="btn sm primary" data-act="intake-approve" data-id="${r.id}">승인</button>`
                : html`<button class="btn sm primary" data-act="intake-approve-risk" data-id="${r.id}" data-name="${r.display_name}"
                  data-summary="${r.evidence?.exit_terms_conclusion?.summary || "종료 조건 확인 결과 없음"}">위험 수용 후 승인</button>`) : ""}
              ${r.status === "APPROVED" && !r.registered_server_id ? html`<button class="btn sm primary" data-act="intake-register" data-id="${r.id}"
                data-name="${r.display_name}" data-repo="${r.endpoint_url || r.repository_url}" data-kind="${r.intake_kind}">게이트웨이 등록</button>` : ""}
              <button class="btn sm" data-act="intake-report" data-id="${r.id}">보고서</button>
              ${["HOLD", "VALIDATION_QUEUED", "VALIDATED", "REMOTE_REVIEWED", "FAILED"].includes(r.status) ? html`<button class="btn sm danger" data-act="intake-reject" data-id="${r.id}">거부</button>` : ""}</div></td>` : ""}</tr>`;
          })}</tbody></table>${requests.length ? "" : empty("신청 없음")}`, { flush: true })}<details class="analysis"><summary>상태별 신청</summary>${panel("상태", requests.length ? chartBox("c-intake", "도입 신청의 상태별 건수", "sm") : empty("신청 없음"))}</details></div>` },
        { key: "new", label: "새 신청", body: html`<div class="stack">
          ${panel("기존 신청 검색", html`<div class="filters"><input class="grow" type="search" data-catalog-search
            aria-label="MCP 이름 또는 저장소 검색" placeholder="MCP 이름 또는 저장소" /></div>
            <div id="catalog-results" aria-live="polite">${catalogResults(catalog || { requests: [], registry: [] })}</div>`, { flush: true })}
          ${panel("새 신청", html`<form class="stack form" data-form="intake">
          <fieldset><legend>서비스</legend>
            <label>서비스 이름<input name="display_name" required minlength="2" maxlength="80" placeholder="GitHub MCP" /></label>
            <label>사용 목적<textarea name="purpose" required minlength="10" maxlength="1000"></textarea></label>
          </fieldset>
          <fieldset><legend>연결</legend><div class="grid c2">
            <label>유형<select name="intake_kind" data-intake-kind><option value="remote-endpoint">원격 MCP</option><option value="repository">소스 코드</option></select></label>
            <label>연결 방식<select name="requested_transport"><option value="streamable-http">Streamable HTTP</option><option value="stdio">stdio</option><option value="sse">SSE</option></select></label>
            <label data-intake-field="remote-endpoint">MCP 주소<input name="endpoint_url" type="url" maxlength="500" placeholder="https://…/mcp" /></label>
            <label data-intake-field="repository" hidden>저장소<input name="repository_url" type="url" maxlength="300" placeholder="https://github.com/org/repo" /></label>
          </div></fieldset>
          <div class="row-actions"><button class="btn primary" type="submit">신청</button></div></form>`)}</div>` },
      ],
    }),
    charts: { "c-intake": () => charts.columns(byStatus()) },
    after: () => {
      intakeTimer = setInterval(() => {
        // Do not close a report drawer, reset an unfinished form or interrupt a review.
        if (!document.hidden && parseHash().page === "intake" && parseHash().query.get("t") !== "new"
          && !$("#drawer").classList.contains("open") && !$("#dialog").open)
          refreshIntake().catch((error) => toast(error.message, true));
      }, 5000);
    },
  };
};
const TRANSPORT = { "streamable-http": "Streamable HTTP", sse: "SSE", stdio: "stdio" };

// The same rule agent_service.approve_mcp_request enforces; the button only mirrors it.
const termsVerified = (t) => Boolean(t?.verified_by && t?.evidence_url && Object.keys(EXIT_TERMS).every((k) => t[k] === true));

// Evidence lines are raw README text; markdown and HTML markup only get in the way of reading them.
const plainLine = (s) => String(s || "").replace(/<[^>]*>/g, " ").replace(/[*_`#|>]+/g, " ").replace(/\s+/g, " ").trim();
const evidenceLink = (url, label) => /^https:\/\/github\.com\//.test(String(url || ""))
  ? html`<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>` : html`${label}`;

// ── exit terms: the platform's conclusion first ─────────────────────────────
const VERDICT = { met: ["allow", "충족"], unmet: ["block", "미충족"], unclear: ["alert", "불명확"] };
const EXIT_TERM_CRITERION = { provider_credential_disclosure: "C1", revocation_evidence: "C2", audit_access_retained: "C4" };
const CHECKING = ["VALIDATION_QUEUED", "VALIDATING"];
/** One wording everywhere a grade is expected: 예상 T1 종료, 예상 T2 부분 종료, 예상 T3 판단 불가. */
function exitConclusionChip(r) {
  const c = r.evidence?.exit_terms_conclusion;
  if (r.requested_transport === "stdio") return NONE;
  if (r.exit_terms?.verified_by) return termsVerified(r.exit_terms) ? chip("allow", "확인 완료") : chip("block", "조건 미충족");
  if (r.exit_terms?.risk_accepted_by) return chip("alert", "위험 수용");
  if (c?.grade) return gradeChip(c.grade, "예상 ");
  return CHECKING.includes(r.status) ? chip("outline", "확인 중") : NONE;
}
function exitTermsView(id, r, investigation, c) {
  const open = ["HOLD", "VALIDATION_QUEUED", "VALIDATING", "VALIDATED"].includes(r.status);
  const record = open && r.requested_transport !== "stdio"
    ? html`<div class="row-actions"><button class="btn sm" data-act="intake-terms" data-id="${id}" data-name="${r.display_name}">직접 확인 기록</button></div>` : "";
  if (!c?.grade) return html`<div class="stack">${empty(CHECKING.includes(r.status) ? "확인 중" : "확인 결과 없음")}
    ${open && !CHECKING.includes(r.status) ? html`<div class="row-actions center"><button class="btn primary" data-act="intake-queue" data-id="${id}">다시 확인</button></div>` : ""}${record}</div>`;
  return html`<div class="stack">
    <div class="row-actions">${gradeChip(c.grade, "예상 ")}<span class="small muted">문서 ${investigation?.scanned_files ?? 0}개</span></div>
    ${c.summary ? html`<p>${c.summary}</p>` : ""}
    <table class="data"><thead><tr><th>조건</th><th>판정</th><th>근거</th></tr></thead><tbody>
      ${Object.keys(EXIT_TERM_CRITERION).filter((key) => c.terms?.[key]).map((key) => [key, c.terms[key]]).map(([key, t]) => html`<tr>
        <td class="nowrap"><b>${EXIT_TERM_CRITERION[key]}</b> ${EXIT_TERMS[key]}</td>
        <td>${chip(...(VERDICT[t.verdict] || ["", t.verdict]))}</td>
        <td class="small">${(t.evidence || []).length ? t.evidence.map((e) => html`<div>${evidenceLink(e.url, `${e.path}:${e.line}`)}<span class="sub">${short(plainLine(e.excerpt), 140)}</span></div>`) : NONE}</td></tr>`)}
    </tbody></table>
    ${r.exit_terms?.verified_by ? panel("직접 확인", html`${chip(termsVerified(r.exit_terms) ? "allow" : "block", termsVerified(r.exit_terms) ? "충족" : "미충족")}
      <p>${r.exit_terms.note}</p><p class="small">${evidenceLink(r.exit_terms.evidence_url, r.exit_terms.evidence_url)}</p>`) : ""}
    ${r.exit_terms?.risk_accepted_by ? panel("위험 수용", html`<p>${r.exit_terms.risk_acceptance}</p>
      <p class="small muted">${r.exit_terms.risk_accepted_by} · ${when(r.exit_terms.risk_accepted_at)}</p>`) : ""}
    ${record}
  </div>`;
}

async function showIntakeReport(id) {
  const report = await api(`/api/mcp-requests/${id}/report`);
  const r = report.request, evidence = r.evidence || {}, investigation = report.exit_terms_discovery;
  lastDocument = report;
  if (r.intake_kind === "remote-endpoint") {
    const review = evidence.remote_contract, approval = evidence.remote_approval;
    openDrawer(`원격 MCP 검토 · ${r.display_name}`, chip(...(INTAKE_STATUS[r.status] || ["", r.status])), [
      {key: "contract", label: "계약·범위", body: html`<div class="stack">
        ${panel("서비스", kv([["MCP 주소", html`<span class="mono">${r.endpoint_url}</span>`], ["사용 목적", r.purpose]]))}
        ${panel("계약 검토", review ? kv([["검토 내용", review.review_note], ["검토자", `${review.reviewed_by} · ${when(review.reviewed_at)}`],
          ["허용 사용자", review.allowed_principals.join(", ")], ["사용 기한", when(review.valid_until)],
          ["서버", `${review.advertised_name} ${review.version}`], ["계약 해시", html`<code>${review.registration.catalog_hash}</code>`],
          ["승인 도구", Object.keys(review.registration.tools || {}).join(", ")]]) : empty("검토 전"))}
        ${panel("허용 인자 범위", review ? html`<pre>${JSON.stringify(review.parameter_constraints || {}, null, 2)}</pre>` : empty("검토 전"))}
        ${panel("도입 승인", approval ? kv([["승인", `${approval.actor} · ${when(approval.at)}`], ["위험 수용", approval.risk_acceptance],
          ["검토 해시", html`<code>${approval.review_digest}</code>`]]) : empty("승인 전"))}
      </div>`},
      {key: "definitions", label: "승인 도구 계약", body: review ? html`<pre>${JSON.stringify(review.tools, null, 2)}</pre>` : empty("검토 전")},
    ]);
    return;
  }
  const scanners = Object.entries(evidence.scanners || {});
  const allFindings = report.reports.flatMap((scan) => (scan.summary?.findings || []).map((f) => ({ ...f, scanner: scan.scanner })));
  const findings = allFindings.filter((f) => f.scanner !== "Gitleaks");
  const secretFindings = allFindings.filter((f) => f.scanner === "Gitleaks");
  const inventory = report.reports.find((scan) => scan.scanner === "Syft")?.summary || {};
  openDrawer(`검증 보고서 · ${r.display_name}`, html`<div class="row-actions">
    ${chip(...(INTAKE_STATUS[r.status] || ["", r.status]))}
    <button class="btn sm" data-act="intake-report" data-id="${id}">새로고침</button>
    <button class="btn sm" data-act="save-json" data-name="intake-${id}-report.json">보고서 JSON 저장</button>
  </div>`, [
    { key: "summary", label: "요약", body: html`<div class="stack">
      ${panel("검증 결과", html`<p>${r.review_note || "검증 대기"}</p>
        <p class="mono small">${r.repository_url}<br />${r.commit_sha || "—"}</p>
        ${kpiStrip([["SBOM 구성요소", evidence.sbom_components ?? "—"], ["Critical", evidence.critical ?? "—", "block"],
          ["High", evidence.high ?? "—", "alert"], ["Medium", evidence.medium ?? "—"]])}`)}
      ${panel("검사 단계", scanners.length ? html`<table class="data"><thead><tr><th>검사기</th><th>결과</th><th>오류</th></tr></thead>
        <tbody>${scanners.map(([name, s]) => html`<tr><td>${name}</td><td>${chip(s.status === "DONE" ? "allow" : "block", s.status === "DONE" ? "완료" : "실패")}</td><td>${s.error || "—"}</td></tr>`)}</tbody></table>` : empty("검사 대기"))}
      ${panel("원본 보고서", report.artifacts.length ? html`<div class="row-actions">${report.artifacts.map((a) => html`
        <button class="btn sm" data-act="intake-download" data-id="${id}" data-kind="${a.kind}" data-name="${a.filename}">${a.kind} JSON</button>`)}</div>` : empty("생성된 보고서 없음"))}
    </div>` },
    { key: "findings", label: "취약점·코드 검사", n: findings.length, body: html`
      ${report.reports.some((s) => s.summary?.truncated && s.scanner !== "Syft") ? html`<p class="small muted">검사기별 최대 200건</p>` : ""}
      ${findings.length ? html`<table class="data"><thead><tr><th>검사기·등급</th><th>발견</th><th>대상</th><th>설치 → 수정 버전</th></tr></thead>
      <tbody>${findings.map((f) => html`<tr><td>${f.scanner}<span class="sub">${f.severity}</span></td>
        <td><b>${f.id}</b><span class="sub">${f.title}</span></td><td>${f.target}<span class="sub">${f.package || ""}</span></td>
        <td>${f.installed_version || "—"} → ${f.fixed_version || "—"}</td></tr>`)}</tbody></table>`
        : empty(scanners.some(([, s]) => s.status === "FAILED") || r.status === "FAILED" ? "검사 실패" : ["VALIDATED", "APPROVED", "REJECTED"].includes(r.status) ? "발견 없음" : "검사 대기")}` },
    {key: "secrets", label: "Secret 검사", n: secretFindings.length, body: html`
      ${secretFindings.length ? html`<table class="data"><thead><tr><th>규칙·등급</th><th>파일</th><th>행</th></tr></thead><tbody>${secretFindings.map((f) => html`<tr><td>${f.id}<span class="sub">${f.severity}</span></td><td>${f.target}</td><td>${f.line || "—"}</td></tr>`)}</tbody></table>` : empty(evidence.scanners?.gitleaks?.status === "DONE" ? "발견 없음" : "검사 대기")}`},
    { key: "sbom", label: "SBOM", n: inventory.components, body: html`
      ${inventory.truncated ? html`<p class="small muted">최대 200개</p>` : ""}
      ${(inventory.inventory || []).length ? html`<table class="data"><thead><tr><th>이름</th><th>버전</th><th>유형</th><th>식별자·라이선스</th></tr></thead>
        <tbody>${inventory.inventory.map((c) => html`<tr><td>${c.name}</td><td>${c.version || "—"}</td><td>${c.type}</td>
          <td class="small">${c.purl || "—"}<span class="sub">${(c.licenses || []).map((l) => l.expression || l.license?.id || l.license?.name || "미상").join(", ")}</span></td></tr>`)}</tbody></table>`
        : empty(inventory.components === 0 ? "구성요소 없음" : r.status === "FAILED" ? "생성 실패" : "생성 대기")}` },
    { key: "exit", label: "종료 조건", body: exitTermsView(id, r, investigation, evidence.exit_terms_conclusion) },
  ]);
}

// ── termination ──────────────────────────────────────────────────────────────
ROUTES.termination = async (caseId, tab) => {
  if (caseId) return caseView(caseId, tab);
  const [{ relationships }, { cases, summary }] = await Promise.all([gw("termination/relationships"), gw("termination/cases")]);
  const grades = () => [...["T1", "T2", "T3"].map((g) => ({ name: `${g} ${GRADE[g]}`, value: cases.filter((c) => c.grade === g).length,
    color: charts.color({ T1: "Allow", T2: "Alert", T3: "Block" }[g]) })),
    { name: "미판정", value: cases.filter((c) => !c.grade).length, color: charts.color() }];
  const readiness = () => ["T1", "T2", "T3"].map((g) => ({ name: `${g} ${GRADE[g]}`, value: relationships.filter((r) => r.readiness?.best_attainable_grade === g).length,
    color: charts.color({ T1: "Allow", T2: "Alert", T3: "Block" }[g]) }));
  termRelationships = relationships;
  return {
    html: page({
      head: head("종료·폐기"),
      kpis: kpiStrip([["진행 중", summary.open_cases], ["종결 대기", summary.awaiting_close, "approval"],
        ["미해결 T2·T3", summary.unresolved_grades, summary.unresolved_grades ? "alert" : ""],
        [`기한 ${summary.sla_days}일 초과`, summary.overdue, summary.overdue ? "block" : ""],
        ["폐기 잔존", summary.retired_residue, summary.retired_residue ? "alert" : ""], ["미등록 MCP", summary.shadow_endpoints, summary.shadow_endpoints ? "block" : ""]]),
      active: tab || "relationships",
      tabs: [
        { key: "relationships", label: "이용 관계", n: relationships.length, body: html`<div class="stack">
          ${panel("이용 관계", relationships.length ? html`<table class="data"><thead><tr><th>이용 관계</th><th>운영</th><th class="num">이용자</th><th class="num">호출</th><th class="num">회수 대상</th><th>예상 등급</th><th></th></tr></thead><tbody>
            ${relationships.map(relationshipRow)}</tbody></table>` : empty("이용 관계 없음"), { flush: true })}
          <details class="analysis"><summary>예상 등급 분포</summary>${chartBox("c-readiness", "이용 관계별 예상 등급 분포", "sm")}</details></div>` },
        { key: "cases", label: "케이스", n: cases.length, body: html`<div class="stack">
          ${panel("케이스", html`<table class="data"><thead><tr><th>이용 관계</th><th>상태</th><th>등급</th><th class="num">회수 대상</th><th class="num">미회수</th><th class="num">증거</th><th>시작</th></tr></thead><tbody>
            ${cases.map((c) => html`<tr class="clickable" tabindex="0" data-act="open-case" data-id="${c.id}">
              <td><b>${c.display_name}</b><span class="sub mono">${c.relationship_id || c.server_id}</span></td>
              <td>${chip(c.status === "CLOSED" ? "outline" : "approval", CASE_STATUS[c.status] || c.status)}${c.overdue ? chip("block", "기한 초과") : ""}</td>
              <td>${gradeChip(c.grade)}</td><td class="num">${c.targets}</td><td class="num">${c.outstanding}</td><td class="num">${c.evidence}</td>
              <td class="small">${when(c.opened_at)}</td></tr>`)}
            </tbody></table>${cases.length ? "" : empty("케이스 없음")}`, { flush: true })}<details class="analysis"><summary>등급 분포</summary>${chartBox("c-grades", "종료 케이스의 등급 분포", "sm")}</details></div>` },
      ],
    }),
    charts: { "c-grades": () => charts.columns(grades()), "c-readiness": () => charts.columns(readiness()) },
  };
};

let termRelationships = [];
const REVOKE_KEY = { gateway_access: "게이트웨이 접근", endpoint_configs: "엔드포인트 설정", server_held: "서버 보유 자격" };
const revokeTotal = (revoke = {}) => Object.keys(REVOKE_KEY).reduce((sum, k) => sum + (Number(revoke[k]) || 0), 0);
const operatorLabel = (r) => (r.deployment === "provider" ? `제공자 ${r.provider || ""}`.trim() : "사내");
function relationshipRow(r) {
  const ready = r.readiness || {};
  const startable = r.lifecycle === "OPERATING" && r.status === "ACTIVE";
  return html`<tr class="clickable" tabindex="0" data-act="relationship" data-id="${r.id}">
    <td><b>${r.purpose}</b><span class="sub">${r.display_name}</span></td>
    <td>${operatorLabel(r)}${r.status !== "ACTIVE" ? html`<span class="sub">${chip(...(REL_STATUS[r.status] || ["", r.status]))}</span>` : ""}</td>
    <td class="num">${r.users ?? 0}</td><td class="num">${r.calls ?? 0}</td><td class="num">${revokeTotal(ready.would_revoke)}</td>
    <td>${gradeChip(ready.best_attainable_grade, "예상 ")}</td>
    <td class="num nowrap">${startable ? html`<button class="btn sm danger" data-act="open-termination" data-id="${r.id}" data-name="${r.purpose}" data-grade="${ready.best_attainable_grade || ""}">종료 시작</button>`
      : r.latest_case ? html`<a class="btn sm" href="#/termination/${r.latest_case}">케이스</a>` : ""}</td></tr>`;
}
function showRelationship(id) {
  const r = termRelationships.find((row) => row.id === id);
  if (!r) return;
  const ready = r.readiness || {};
  const terms = r.exit_terms || {};
  openDrawer(r.purpose, html`<div class="row-actions">${gradeChip(ready.best_attainable_grade, "예상 ")}${chip(...(REL_STATUS[r.status] || ["", r.status]))}
    ${r.latest_case ? html`<a class="btn sm" href="#/termination/${r.latest_case}">최근 케이스</a>` : ""}</div>`, [
    { key: "info", label: "개요", body: kv([["ID", html`<code>${r.id}</code>`], ["서버", r.display_name], ["운영", operatorLabel(r)],
      ["이용자", r.users ?? 0], ["호출", r.calls ?? 0],
      ["허용 자원", (r.allowed_resources || []).map(resourceName).join(", ")]]) },
    { key: "revoke", label: "회수 대상", n: revokeTotal(ready.would_revoke), body: kv(Object.entries(REVOKE_KEY).map(([k, label]) => [label, ready.would_revoke?.[k] ?? 0])) },
    ...(r.deployment === "provider" ? [{ key: "terms", label: "종료 조건", body: html`<div class="pill-list">${Object.entries(EXIT_TERMS).map(([k, label]) => bool(terms[k], label))}</div>
      ${(ready.blockers || []).length ? html`<ul class="small">${ready.blockers.map((b) => html`<li>${b}</li>`)}</ul>` : ""}` }] : []),
  ]);
}

let currentCase = null;
const PROCEDURE = ["이용 관계 확정", "강제 경로 차단", "모집단 열거", "회수 조치", "상태 증거", "판정", "종결"];

/** Steps complete in order: a step counts as done only when every earlier step is done,
 * so the bar never shows a later step finished while an earlier one is still open. */
function procedureState(d) {
  const c = d.case;
  const closed = c.status === "CLOSED";
  const stateEvidence = d.evidence.some((e) => e.meaning?.state);
  const unverifiable = d.targets.some((t) => t.status === "UNVERIFIABLE");
  const flags = [true, Boolean(c.cutover_at), d.targets.length > 0 && !unverifiable,
    d.targets.length > 0 && d.targets.every((t) => t.status !== "OUTSTANDING"), stateEvidence,
    Boolean(c.grade) && ["ASSESSED", "CLOSED"].includes(c.status), closed];
  const now = closed ? -1 : flags.indexOf(false);
  return PROCEDURE.map((title, i) => ({ title, done: closed || i < now, now: i === now, gap: i === now && i === 2 && unverifiable }));
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
        back: html`<a class="back" href="#/termination?t=cases">← 종료·폐기</a>`,
        status: html`${chip(closed ? "outline" : "approval", CASE_STATUS[c.status] || c.status)}${gradeChip(c.grade)}`,
        actions: html`${!closed ? html`<button class="btn" data-act="collect">증거 수집</button><button class="btn primary" data-act="assess">판정</button>` : ""}
          ${c.grade ? html`<button class="btn" data-act="report">판정서</button>` : ""}
          ${c.deployment === "provider" ? html`<button class="btn" data-act="disclosure">고지 요청서</button>` : ""}
          ${c.status === "ASSESSED" ? html`<button class="btn danger solid" data-act="close-case">종결</button>` : ""}
          ${closed ? html`<button class="btn" data-act="reopen-case">재개</button>` : ""}` })}
        <ol class="stepper" aria-label="종료 판정 절차">${procedureState(d).map((s, i) => html`
          <li class="step ${s.done ? "done" : ""} ${s.now ? "now" : ""} ${s.gap ? "gap" : ""}"><span class="n">${s.done ? "✓" : i + 1}</span><b>${s.title}</b></li>`)}</ol>`,
      kpis: html`<div class="kpis">${[["회수 대상", d.targets.length], ["미회수", outstanding, outstanding ? "alert" : ""], ["상태 증거", stateEvidence],
        ["차단 후 실행", act.executed, act.executed ? "block" : ""], ["차단 후 거부", act.blocked, ""], ["엔드포인트 잔존", d.endpoint_residue, d.endpoint_residue ? "alert" : ""]]
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
        { key: "scope", label: "허용 자원", body: panel("허용 자원", html`<div class="pill-list">${(c.allowed_resources || []).map((a) => (typeof a === "string"
          ? html`<span class="chip outline mono">${a}</span>` : html`<span class="chip outline mono">${a.name || JSON.stringify(a)}${a.action ? ` · ${ACTION[a.action] || a.action}` : ""}</span>`))}</div>
          ${kv([["시작", when(c.opened_at)], ["차단", when(c.cutover_at, { seconds: true })], ["마지막 시도", when(act.last_attempt, { seconds: true })], ["실행 미확인", act.unknown]])}`) },
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
    case "revocation-response": return chip("outline", `처리 응답 ${d.http_status ?? ""}`.trim());
    case "liveness-probe": return d.reachable ? chip("alert", `응답함 ${d.status_code ?? ""}`.trim()) : chip("outline", "응답 없음");
    case "session-termination": return d.session_issued === false ? chip("outline", "세션 없음")
      : d.session_still_works ? chip("block", "세션 유지됨") : chip("outline", "세션 종료 요청");
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
    ${Object.keys(e.detail || {}).length ? html`<details><summary class="small">상세</summary>${json(e.detail)}</details>` : ""}</div>`;
}

function showTarget(id) {
  const t = currentCase?.targets.find((row) => row.id === id);
  if (!t) return;
  const own = currentCase.evidence.filter((e) => e.target_id === id);
  openDrawer(t.label, html`<div class="row-actions">${chip(...(TARGET_STATUS[t.status] || ["", t.status]))}${gradeChip(t.grade)}</div>`, [
    { key: "info", label: "대상", body: kv([["종류", TARGET_KIND[t.kind] || t.kind], ["보유 주체", HOLDER[t.holder] || t.holder],
      ["발견 경로", DISCOVERED[t.discovered_by] || t.discovered_by], ["식별자", t.subject_ref ? html`<code>${t.subject_ref}</code>` : ""],
      ["확인 방법", VERIFICATION[t.verification] || t.verification], ["만료", t.expires_at ? when(t.expires_at, { seconds: true }) : ""],
      ["회수 시각", t.revoked_at ? when(t.revoked_at, { seconds: true }) : ""], ["메모", t.note]]) },
    { key: "criteria", label: "기준", body: t.criteria ? html`<div class="crit">${["C1", "C2", "C3", "C4"].map((k) => html`<div class="c"><h4>${k} ${CRITERIA[k]}
      ${chip(t.criteria[k].met ? "allow" : "block", t.criteria[k].met ? "충족" : "미충족")}</h4>
      ${t.criteria[k].gaps.length ? html`<ul>${t.criteria[k].gaps.map((g) => html`<li>${g}</li>`)}</ul>` : ""}</div>`)}</div>` : empty("미판정") },
    { key: "evidence", label: "증거", n: own.length, body: html`<div class="evidence">${own.map(evidenceItem)}</div>${own.length ? "" : empty("증거 없음")}` },
  ]);
}

// ── policy ───────────────────────────────────────────────────────────────────
let policyLedger = [];
ROUTES.audit = async (_, tab, query) => {
  const q = new URLSearchParams(query);
  const filters = ["decision", "server", "principal", "policy", "event_kind", "execution", "trace_id", "since", "until"];
  const params = new URLSearchParams([...q].filter(([k, v]) => [...filters, "before"].includes(k) && v));
  const data = await gw(`audit/events?${params}&limit=100`);
  const options = (values, selected) => values.map(([value, label]) => html`<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`);
  const local = (iso) => { const d = new Date(iso || NaN); return Number.isNaN(d.getTime()) ? "" : `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; };
  const executed = (e) => e.upstream_executed ? (e.response_disposition === "withheld" || e.policy_id === "MCP-OUTPUT-001" ? "응답 보류" : "실행됨") : e.upstream_attempted ? "실행 미확인" : "실행 안 함";
  return {html: page({head: head("감사 기록", {actions: html`<button class="btn" data-act="audit-verify">무결성 검증</button><button class="btn primary" data-act="audit-export">내보내기</button>`}),
    active: "events", tabs: [{key: "events", label: "감사 이벤트", n: data.events.length, body: html`<div class="stack">
      ${panel("조회 조건", html`<form class="form stack" data-form="audit"><div class="grid c3">
        <label>판정<select name="decision">${options([["", "전체"], ...Object.entries(DECISION).map(([k,v]) => [k,v[1]])], q.get("decision") || "")}</select></label>
        <label>실행 결과<select name="execution">${options([["", "전체"], ["executed", "실행됨"], ["not-sent", "실행 안 함"], ["unknown", "실행 미확인"], ["withheld", "응답 보류"]], q.get("execution") || "")}</select></label>
        <label>이벤트<select name="event_kind">${options([["", "전체"], ["tools/call", "도구 호출"], ["mcp-connection", "연결 거부"]], q.get("event_kind") || "")}</select></label>
        ${["server", "principal", "policy", "trace_id"].map((k) => field.text(k, {server:"서버", principal:"사용자", policy:"정책", trace_id:"Trace ID"}[k], 'maxlength="150"', q.get(k) || ""))}
        ${["since", "until"].map((k) => field.text(k, k === "since" ? "시작" : "종료", 'type="datetime-local"', local(q.get(k))))}
      </div><div class="row-actions"><button class="btn primary" type="submit">조회</button><a class="btn" href="#/audit">초기화</a></div></form>`)}
      ${panel("감사 원장", html`${data.events.length ? html`<table class="data"><thead><tr><th>번호·시각</th><th>사용자·도구</th><th>판정·정책</th><th>실행 결과</th></tr></thead><tbody>${data.events.map((e) => html`<tr class="clickable" tabindex="0" data-act="audit-event" data-id="${e.id}">
          <td>#${e.id}<span class="sub">${when(e.created_at)} · ${EVENT_KIND[e.event_kind] || e.event_kind}</span></td><td>${e.user_token}<span class="sub mono">${e.server_id}.${e.tool_name}</span></td><td>${decisionChip(e.decision)}<span class="sub mono">${e.policy_id}</span></td>
          <td>${executed(e)}<span class="sub mono">${e.entry_sha256 ? e.entry_sha256.slice(0,16) : "—"}</span></td></tr>`)}</tbody></table>` : empty("감사 이벤트 없음")}
          ${data.has_more ? html`<div class="row-actions center"><a class="btn" href="#/audit?${new URLSearchParams({...Object.fromEntries(params), before: data.next_before})}">더 보기</a></div>` : ""}`, {flush:true})}</div>`}]})};
};
const EVENT_KIND = { "tools/call": "도구 호출", "mcp-connection": "연결 거부" };

ROUTES.policy = async (_, tab) => {
  const [{ enforcement }, matrix, ledger] = await Promise.all([gw("enforcement"), gw("policy/matrix"), gw("policy/ledger")]);
  policyLedger = ledger.policies;
  const byOutcome = splitBy(ledger.policies, "outcome");
  const actions = (list) => (list || []).map((a) => ACTION[a] || a).join(", ");
  return {
    html: page({
      head: head("정책", { status: modeChip(enforcement), actions: html`<button class="btn ${enforcement === "enforce" ? "danger" : "primary"}" data-act="enforcement"
        data-mode="${enforcement === "enforce" ? "monitor" : "enforce"}">${enforcement === "enforce" ? "관찰 모드로 전환" : "집행 모드로 전환"}</button>` }),
      active: tab || "capabilities",
      tabs: [
        { key: "capabilities", label: "실행 권한", n: matrix.capabilities.length + matrix.runtime_envelopes.length, body: panel("실행 권한",
          matrix.capabilities.length + matrix.runtime_envelopes.length ? html`<table class="data"><thead><tr><th>권한</th><th>사용자</th><th>서버</th><th>행위·자원</th><th>만료</th></tr></thead><tbody>
          ${matrix.capabilities.map((g) => html`<tr><td><code>${g.id}</code></td><td>${(g.principals || []).join(", ")}</td><td>${(g.servers || []).join(", ")}</td>
            <td>${actions(g.actions)}<span class="sub">${(g.path_roots || []).join(", ")}</span></td><td>${when(g.valid_until)}</td></tr>`)}
          ${matrix.runtime_envelopes.map((g) => html`<tr><td><code>${g.server_id}</code></td><td>${(g.principals || []).join(", ")}</td><td><code>${g.server_id}</code></td><td>${Object.keys(g.tools || {}).join(", ")}<span class="sub">도입 승인</span></td><td>${when(g.valid_until)}</td></tr>`)}
          </tbody></table>` : empty("실행 권한 없음"), { flush: true }) },
        { key: "ledger", label: "정책 목록", n: ledger.policies.length, body: html`<div class="stack">
          ${panel("정책 목록", html`<table class="data"><thead><tr><th class="n">번호</th><th>정책</th><th>결과</th></tr></thead><tbody>
            ${ledger.policies.map((p, i) => html`<tr class="clickable" tabindex="0" data-act="policy" data-id="${p.policy_id}"><td class="n">${i + 1}</td>
              <td><b>${p.name}</b><span class="sub mono">${p.policy_id}</span></td><td>${outcomeDecision(p.outcome) ? decisionChip(outcomeDecision(p.outcome)) : chip("outline", p.outcome)}</td></tr>`)}
            </tbody></table>`, { flush: true })}<details class="analysis"><summary>결과별 정책 수</summary>${chartBox("c-outcomes", "결과별 정책 수", "sm")}</details></div>` },
      ],
    }),
    charts: {
      "c-outcomes": () => charts.bars(byOutcome.map((g) => ({ name: g.key, value: g.total, color: charts.color(outcomeDecision(g.key)) }))),
    },
  };
};

// ── actions ──────────────────────────────────────────────────────────────────
const field = {
  text: (name, label, attrs = "", value = null) => html`<label>${label}<input name="${name}" ${raw(attrs)} ${value === null ? "" : html`value="${value}"`} /></label>`,
  area: (name, label, attrs = "") => html`<label>${label}<textarea name="${name}" ${raw(attrs)}></textarea></label>`,
  select: (name, label, options, cur = "") => html`<label>${label}<select name="${name}">${Object.entries(options).map(([v, l]) =>
    html`<option value="${v}" ${v === cur ? raw("selected") : ""}>${Array.isArray(l) ? l[1] : l}</option>`)}</select></label>`,
};

const ACTIONS = {
  async "audit-event"(el) {
    const event = await gw(`audit/events/${el.dataset.id}`);
    openDrawer(`감사 이벤트 #${event.id}`, html`<div class="row-actions">${decisionChip(event.decision)}<code>${event.policy_id}</code></div>`, [{key:"record", label:"기록", body:json(event)}]);
  },
  async "audit-export"() {
    const q = new URLSearchParams(current.query);
    q.delete("t"); q.set("limit", "500");
    lastDocument = await gw(`audit/export?${q}`);
    ACTIONS["save-json"]({dataset:{name:"mcp-audit-evidence.json"}});
    toast(`${lastDocument.manifest.count}건 내보냄${lastDocument.payload.has_more ? " · 다음 페이지 있음" : ""} · ${lastDocument.payload.verification.intact ? "무결성 정상" : "무결성 손상"}`, !lastDocument.payload.verification.intact);
  },
  async "identity-bind"() {
    const fd = await ask({title:"SSO 계정 연결", fields:html`${field.text("principal", "사용자 ID", "required maxlength=150")}${field.text("subject", "SSO 사용자 ID (sub)", "required maxlength=255")}`, confirm:"연결"});
    if (!fd) return;
    const r = await api("/api/identity/bindings", {method:"POST", body:{principal:fd.get("principal").trim(), subject:fd.get("subject").trim()}});
    toast(r.message); reload();
  },
  async "identity-unbind"(el) {
    if (!await ask({title:"SSO 연결 해제", body:"로그인 세션도 함께 종료됩니다.", confirm:"해제", danger:true})) return;
    const r = await api(`/api/identity/bindings/${el.dataset.id}`, {method:"DELETE"});
    toast(r.message); reload();
  },
  async "account-invite"() {
    const result = await ask({ title: "사용자 초대", confirm: "초대 링크 만들기", fields: html`
      ${field.area("usernames", "아이디 (쉼표·줄바꿈 구분)", "required maxlength=1700")}
      ${field.text("department", "부서", "required minlength=2 maxlength=80")}` });
    if (!result) return;
    const usernames = String(result.get("usernames")).split(/[,\s]+/).filter(Boolean);
    const issued = await api("/api/account-invitations", { method: "POST", body: { usernames, department: result.get("department") } });
    openDrawer("초대 링크", html`${issued.invitations.map((item) => html`<section class="panel"><div class="body"><b>${item.username}</b><p><a href="${item.url}" target="_blank" rel="noopener noreferrer">${item.url}</a></p><span class="small muted">${when(item.expires_at)}까지 · 1회용</span></div></section>`)}`);
  },
  sidebar() {
    const closed = !document.documentElement.classList.contains("nav-collapsed");
    setNavCollapsed(closed);
    if (!matchMedia("(max-width: 900px)").matches) localStorage.setItem(NAV_KEY, String(closed));
    charts.redrawAll();
  },
  async reload() { await reload(); },
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
  async tab(el) {
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
    if (key === "new" && current.page === "intake") {
      const input = scope.querySelector("[data-catalog-search]");
      const query = input.value.trim();
      const data = await api(`/api/mcp-catalog/search?q=${encodeURIComponent(query)}`);
      if (input.isConnected && input.value.trim() === data.query)
        $("#catalog-results").innerHTML = String(catalogResults(data));
    }
  },
  decision: (el) => showDecision(el.dataset.id),
  relationship: (el) => showRelationship(el.dataset.id),
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
    feed.filters = Object.fromEntries(FEED_FILTERS.map((key) => [key, ""]));
    feed.query = "";
    location.hash = "#/activity";
    reload();
  },
  goto(el) { location.hash = el.dataset.href; },
  "coverage-filter"(el) {
    const q = new URLSearchParams(current.query);
    if (el.dataset.value) q.set(el.dataset.key, el.dataset.value); else q.delete(el.dataset.key);
    q.set("t", "items");
    location.hash = `#/coverage?${q}`;
  },
  async integration(el) {
    const i = integrationItems.find((x) => x.key === el.dataset.key);
    if (!i) return;
    const v = i.vendor_control;
    const gatewayId = i.key.startsWith("gateway:") ? i.key.slice(8) : "";
    // The termination view of a registered server: what would remain if it ended now.
    const rel = gatewayId ? (await gw("termination/relationships").catch(() => ({ relationships: [] })))
      .relationships?.find((r) => r.server_id === gatewayId) : null;
    const plane = (name, applies, body) => html`<tr><th>${name}</th><td>${applies ? body : NONE}</td></tr>`;
    openDrawer(i.name, html`<div class="row-actions">${statusPair(i)}${chip("outline", INTEGRATION_CLASS[i.class] || i.class)}
      ${i.class === "vendor_native_connector" ? html`<button class="btn sm" type="button" data-act="vendor-control" data-key="${i.item_key}" data-name="${i.name}">벤더 콘솔 확인 기록</button>` : ""}</div>`, [
      { key: "planes", label: "통제", body: html`<table class="data"><tbody>
        ${plane("게이트웨이", i.managed_by === "gateway", html`${chip(i.state === "bypass_possible" ? "block" : "allow", i.state === "bypass_possible" ? "게이트웨이 경로만 통제" : "게이트웨이 통제")}<span class="sub">${i.evidence}</span>`)}
        ${plane("엔드포인트", i.managed_by === "endpoint" || i.evidence_kind === "kernel", html`${controlChip(i.state)}<span class="sub">${i.evidence}</span>`)}
        ${plane("벤더", i.class === "vendor_native_connector" || (i.residual || []).length > 0, v
          ? html`${chip("restrict", VENDOR_CONSOLE[v.console_state] || v.console_state)}<span class="sub">수동 확인 · ${v.verified_by} · ${when(v.verified_at)}${(v.oauth_scopes || []).length ? ` · scope ${v.oauth_scopes.join(", ")}` : ""}${v.role_access ? ` · 역할 ${v.role_access}` : ""}</span>`
          : html`${chip("outline", "확인 기록 없음")}${(i.residual || []).map((r) => html`<span class="sub">${r}</span>`)}`)}
        </tbody></table>${kv([["우회 경로", (i.bypass || []).length ? html`<div class="pill-list">${i.bypass.map((b) => chip("block", b))}</div>` : "없음"],
          ["사용자·엔드포인트", `${(i.owners || [i.owner]).filter(Boolean).join(", ") || "—"}${i.pcs > 1 ? ` · PC ${i.pcs}대` : i.device ? ` · ${i.device}` : ""}`],
          ["발견", `${i.discovered_from}${i.discovered_at ? ` · ${when(i.discovered_at)}` : ""}`],
          ["대상", i.target ? html`<span class="mono">${i.target}</span>` : ""], ["마지막 확인", i.last_verified_at ? when(i.last_verified_at) : ""]])}` },
      { key: "approval", label: "승인", body: kv([["상태", approvalLabel(i.approval?.state)], ["만료", i.approval?.expires_at ? when(i.approval.expires_at) : ""],
        ["결정자", i.approval?.decided_by], ["검토 기한", i.approval?.review_days ? `${i.approval.review_days}일` : ""]]) },
      ...(gatewayId ? [{ key: "exit", label: "종료 시", body: rel ? kv([
        ["예상 등급", gradeChip(rel.readiness?.best_attainable_grade, "예상 ")],
        ...Object.entries(REVOKE_KEY).map(([k, label]) => [label, rel.readiness?.would_revoke?.[k] ?? 0]),
        ["제약", (rel.readiness?.blockers || []).join(" · ")]]) : empty("이용 관계 없음") }] : []),
    ]);
  },
  async "vendor-control"(el) {
    const fd = await ask({ title: `벤더 콘솔 확인 · ${el.dataset.name}`, confirm: "기록",
      fields: html`${field.select("console_state", "콘솔 상태", VENDOR_CONSOLE, "unknown")}
        ${field.text("allowed_actions", "허용 동작 (쉼표 구분)", 'maxlength="600"')}
        ${field.text("oauth_scopes", "OAuth scope (쉼표 구분)", 'maxlength="600"')}
        ${field.text("role_access", "역할 접근", 'maxlength="200"')}
        ${field.text("evidence_url", "근거 주소", 'maxlength="500"')}
        ${field.area("note", "메모", 'maxlength="500"')}` });
    if (!fd) return;
    const list = (k) => fd.get(k).split(",").map((s) => s.trim()).filter(Boolean);
    await api("/api/integrations/vendor-control", { method: "PUT", body: { key: el.dataset.key, console_state: fd.get("console_state"),
      allowed_actions: list("allowed_actions"), oauth_scopes: list("oauth_scopes"), role_access: fd.get("role_access").trim(),
      evidence_url: fd.get("evidence_url").trim(), note: fd.get("note").trim() } });
    toast("기록했습니다."); closeDrawer(); reload();
  },
  async "audit-verify"() {
    const r = await gw("audit/verify");
    if (r.intact) toast(`무결성 정상 · ${r.checked}건`);
    else toast(`무결성 손상 · #${r.broken_at ?? "마지막"}: ${r.reason}`, true);
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
    toast(drift ? `계약 변경 서버 ${drift}개` : "모든 서버 계약 일치", Boolean(drift));
    reload();
  },
  async "server-check"(el) {
    // A session handshake only; contract state is the catalog refresh's job.
    const r = await gw(`registry/${encodeURIComponent(el.dataset.id)}/check`, { method: "POST" });
    if (r.state === "healthy") toast(`연결 정상 · ${r.advertised_name || r.server_id} ${r.version} · ${Math.round(r.latency_ms)}ms`);
    else if (r.state === "retired") toast("폐기된 서버는 확인하지 않습니다.");
    else toast(`연결 실패 · ${r.error}`, true);
  },
  async "approve-contract"(el) {
    const fd = await ask({ title: "계약 변경 승인", fields: field.area("note", "검토 내용", 'required minlength="5" maxlength="500"'), confirm: "승인본 갱신" });
    if (!fd) return;
    await gw(`registry/${el.dataset.id}/approve-contract`, { method: "POST", body: { note: fd.get("note") } });
    toast("승인본을 갱신했습니다."); reload();
  },
  async "account-status"(el) {
    const fd = await ask({ title: `${el.dataset.name} 계정 상태`,
      fields: html`<fieldset><legend>상태</legend>${Object.entries({ active: "사용", disabled: "중지", locked: "잠김" }).map(([value, label]) =>
        html`<label class="check"><input type="radio" name="status" value="${value}" ${value === el.dataset.status ? raw("checked") : ""} required />${label}</label>`)}</fieldset>
        ${field.text("note", "메모", 'maxlength="300"')}` });
    if (!fd) return;
    const r = await api(`/api/accounts/${el.dataset.id}/status`, { method: "PUT", body: { status: fd.get("status"), note: fd.get("note") || "" } });
    await reload();
    toast(r.message);
  },
  async "account-delete"(el) {
    const fd = await ask({ title: `${el.dataset.name} 계정 삭제`,
      body: "로그인과 사내 저장소 접근이 즉시 차단됩니다.", confirm: "계정 삭제", danger: true });
    if (!fd) return;
    const r = await api(`/api/accounts/${encodeURIComponent(el.dataset.id)}`, { method: "DELETE" });
    await reload();
    toast(r.message);
  },
  async "signup-approve"(el) {
    const r = await api(`/api/signup-requests/${el.dataset.id}/approve`, { method: "POST" });
    toast(r.message); reload();
  },
  async "signup-reject"(el) {
    await api(`/api/signup-requests/${el.dataset.id}/reject`, { method: "POST" });
    toast("가입 신청을 거부했습니다."); reload();
  },
  "pc-kit"() {
    // The kit points the harnesses at the gateway; no password is stored on the PC.
    const kit = viewer.kit;
    openDrawer("내 PC 연결", html`<div class="row-actions">${chip(kit.servers ? "allow" : "outline", kit.servers ? `MCP 서버 ${kit.servers.split(",").length}개` : "사용 가능한 서버 없음")}
        <button class="btn sm primary" type="button" data-act="pc-kit-download">설치 키트 받기</button></div>
      ${[["windows", "Windows"], ["linux", "Linux"]].filter(([os]) => kit.commands?.[os]).map(([os, label]) => html`
        <h4>${label} <button class="btn sm" type="button" data-act="copy-kit" data-os="${os}">명령 복사</button></h4>
        <pre class="json">${kit.commands[os]}</pre>`)}`);
  },
  async "copy-kit"(el) {
    await navigator.clipboard.writeText(viewer.kit.commands[el.dataset.os]);
    toast("복사했습니다.");
  },
  async "pc-kit-download"() {
    const response = await fetch("/api/pc-kit", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    if (!response.ok) {
      const r = await response.json();
      throw new Error(detailText(r.detail) || "설치 키트를 받지 못했습니다.");
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a"); link.href = url; link.download = "mcp-managed-kit.zip";
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 30000);
    toast("설치 키트를 받았습니다.");
  },
  async "device-activate"(el) {
    const fd = await ask({ title: `엔드포인트 활성화 · ${el.dataset.id}`,
      fields: field.area("note", "확인 내용", 'required minlength="20" maxlength="1000"'), confirm: "활성화" });
    if (!fd) return;
    await gw(`endpoint/devices/${encodeURIComponent(el.dataset.id)}/activate`, { method: "POST", body: { policy_hash: el.dataset.hash, note: fd.get("note") } });
    toast("엔드포인트를 활성화했습니다."); reload();
  },
  async "device-issue"() {
    const owners = Object.fromEntries([["", "지정 안 함"], ...peopleAccounts.filter((a) => a.status === "active")
      .map((a) => [a.token, `${a.display_name} · ${a.department || ROLE[a.role] || a.role}`])]);
    const fd = await ask({ title: "엔드포인트 등록",
      fields: html`${field.text("endpoint_id", "엔드포인트 ID", 'required minlength="3" maxlength="120" pattern="[A-Za-z0-9._\\-]+" placeholder="laptop-001"')}
        ${field.text("hostname", "호스트명", 'required maxlength="200"')}
        ${field.select("platform", "플랫폼", { windows: "Windows", linux: "Linux", macos: "macOS", unknown: "기타" }, "linux")}
        ${field.select("owner_token", "사용자", owners)}
        <fieldset><legend>수집 항목</legend>
          <label class="check"><input type="checkbox" name="scopes" value="inventory" checked /> MCP 설정</label>
          <label class="check"><input type="checkbox" name="scopes" value="enforcement" /> 엔드포인트 차단 기록</label>
          <label class="check"><input type="checkbox" name="scopes" value="netscan" /> 내부망 MCP 탐색</label></fieldset>`,
      confirm: "등록" });
    if (!fd) return;
    const scopes = fd.getAll("scopes");
    if (!scopes.length) { toast("수집 항목을 하나 이상 고르세요.", true); return; }
    const r = await gw("endpoint/devices", { method: "POST", body: {
      endpoint_id: fd.get("endpoint_id").trim(), hostname: fd.get("hostname").trim(), platform: fd.get("platform"),
      owner_token: fd.get("owner_token") || null, scopes } });
    await reload();  // a reload closes the drawer, so the one-time key opens after it
    lastDocument = r.enrollment_key;
    openDrawer("엔드포인트 등록 키", html`<p class="note warn">이 키는 다시 표시되지 않습니다.</p>
      ${kv([["엔드포인트", html`<code>${r.endpoint_id}</code>`], ["수집 항목", r.scopes.map((s) => ({ inventory: "MCP 설정", enforcement: "엔드포인트 차단 기록", netscan: "내부망 MCP 탐색" })[s] || s).join(", ")], ["등록 키", html`<code>${r.enrollment_key}</code>`]])}
      <div class="row-actions"><button class="btn sm primary" type="button" data-act="copy-doc">키 복사</button></div>`);
  },
  async "device-revoke"(el) {
    const fd = await ask({ title: `엔드포인트 등록 해제 · ${el.dataset.id}`, confirm: "해제", danger: true });
    if (!fd) return;
    await gw(`endpoint/devices/${encodeURIComponent(el.dataset.id)}`, { method: "DELETE" });
    toast("등록을 해제했습니다."); reload();
  },
  async "intake-queue"(el) {
    const r = await api(`/api/mcp-requests/${el.dataset.id}/queue-validation`, { method: "POST" });
    toast(r.message); reload();
  },
  async "intake-report"(el) { await showIntakeReport(el.dataset.id); },
  async "intake-download"(el) {
    const response = await fetch(`/api/mcp-requests/${el.dataset.id}/artifacts/${encodeURIComponent(el.dataset.kind)}`,
      { headers: { authorization: `Bearer ${token}` } });
    if (!response.ok) {
      if (response.status === 401) { localStorage.removeItem(TOKEN_KEY); location.replace("/login"); }
      const body = await response.json().catch(() => ({}));
      throw new Error(detailText(body.detail) || `다운로드 실패 (${response.status})`);
    }
    const url = URL.createObjectURL(await response.blob());
    Object.assign(document.createElement("a"), { href: url, download: el.dataset.name }).click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
  async "intake-terms"(el) {
    const fd = await ask({ title: `종료 조건 확인 · ${el.dataset.name}`,
      fields: html`<fieldset><legend>제공자가 약속한 항목</legend>
          ${Object.entries(EXIT_TERMS).map(([k, label]) => html`<label class="check"><input type="checkbox" name="${k}" /> ${label}</label>`)}</fieldset>
        ${field.text("evidence_url", "근거 문서 (HTTPS)", 'type="url" required pattern="https://.+" maxlength="500"')}
        ${field.area("note", "확인 내용", 'required minlength="10" maxlength="1000"')}`,
      confirm: "기록" });
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
  async "intake-approve-risk"(el) {
    // Below T1 the conclusion is stated and the admin accepts the risk in writing,
    // the same rule that closes a T3 termination case.
    const fd = await ask({ title: `위험 수용 후 승인 · ${el.dataset.name}`, body: el.dataset.summary,
      fields: field.area("risk_acceptance", "수용 사유", 'required minlength="10" maxlength="1000"'), confirm: "승인" });
    if (!fd) return;
    const r = await api(`/api/mcp-requests/${el.dataset.id}/approve`, { method: "POST", body: { risk_acceptance: fd.get("risk_acceptance").trim() } });
    toast(r.message); reload();
  },
  async "intake-register"(el) {
    if (el.dataset.kind === "remote-endpoint" && !el.dataset.review) {
      const report = await api(`/api/mcp-requests/${el.dataset.id}/report`);
      const approved = report.request.evidence.remote_contract;
      const confirm = await ask({ title: `게이트웨이 등록 · ${el.dataset.name}`,
        body: html`<p class="mono">${approved.registration.endpoint}</p><p>도구 ${Object.keys(approved.registration.tools).length}개 · ${when(approved.valid_until)}까지</p>`, confirm: "등록" });
      if (!confirm) return;
      const result = await api(`/api/mcp-requests/${el.dataset.id}/register`, {method: "POST", body: approved.registration});
      toast(result.message); reload(); return;
    }
    // Approval says the service may be used; registration fixes which tools, at what grade, until when.
    const first = await ask({ title: `${el.dataset.review ? "계약 검토" : "게이트웨이 등록"} · ${el.dataset.name}`,
      fields: field.text("endpoint", "MCP 주소", `type="url" required pattern="https?://.+" maxlength="500" placeholder="https://…/mcp" ${el.dataset.review ? "readonly" : ""}`, el.dataset.review ? el.dataset.repo : null),
      confirm: "도구 불러오기" });
    if (!first) return;
    const found = await gw("registry/discover", { method: "POST", body: { endpoint: first.get("endpoint").trim() } });
    const suggested = el.dataset.repo.split("/").slice(-2).join("-").toLowerCase()
      .replace(/[^a-z0-9]+/g, "-").replace(/^[^a-z]+|-+$/g, "").slice(0, 31) || "mcp";
    const fd = await ask({ title: `도구 승인 · ${found.server_name || el.dataset.name} ${found.version}`,
      fields: html`${field.text("server_id", "서버 ID", `required pattern="[a-z][a-z0-9\\-]{1,30}" maxlength="31" value="${suggested}"`)}
        <p class="mono small">${found.endpoint}<br />계약 해시 ${found.catalog_hash}</p>
        <div class="grid c2">${field.select("data_class", "데이터 등급", DATA_CLASS, "nonimportant")}${field.select("valid_days", "사용 기한", VALIDITY, "90")}</div>
        ${el.dataset.review ? html`${field.text("allowed_principals", "허용 사용자 ID (쉼표 구분)", "required", el.dataset.principal)}${field.area("review_note", "검토 내용", 'required minlength="10" maxlength="1000"')}
          ${field.area("parameter_constraints", "도구별 인자 제한 (JSON Schema)", 'required maxlength="30000"', "{}")}` : ""}
        ${found.tools.some((t) => t.warnings?.length) ? html`<p class="note warn">도구 설명에 지시문으로 의심되는 문구가 있습니다.</p>` : ""}
        <fieldset class="tool-pick"><legend>도구 ${found.tools.length}</legend>${found.tools.map((t) => html`<label>
          <span><code>${t.name}</code>${(t.warnings || []).map((w) => chip("block", w))}
            <span class="sub">${t.description}</span><details><summary>입력 계약</summary><pre>${JSON.stringify(t.input_schema, null, 2)}</pre></details></span>
          <select name="tool:${t.name}" aria-label="${t.name}"><option value="">미승인</option>${Object.entries(ACTION).map(([k, l]) =>
            html`<option value="${k}">${l}</option>`)}</select></label>`)}</fieldset>
        ${found.tools.some((t) => t.warnings?.length) ? html`<label class="check"><input type="checkbox" name="poisoning_ack" /> 표시된 도구의 설명을 확인했습니다</label>` : ""}`,
      confirm: el.dataset.review ? "검토 기록" : "등록" });
    if (!fd) return;
    const tools = Object.fromEntries(found.tools.map((t) => [t.name, fd.get(`tool:${t.name}`)]).filter(([, v]) => v));
    if (!Object.keys(tools).length) { toast("도구를 하나 이상 고르세요.", true); return; }
    let parameterConstraints;
    if (el.dataset.review) {
      try { parameterConstraints = JSON.parse(fd.get("parameter_constraints")); }
      catch { toast("인자 제한은 올바른 JSON이어야 합니다.", true); return; }
    }
    const r = await api(`/api/mcp-requests/${el.dataset.id}/${el.dataset.review ? "review-contract" : "register"}`, { method: "POST", body: {
      server_id: fd.get("server_id").trim(), endpoint: found.endpoint, catalog_hash: found.catalog_hash, tools,
      data_class: fd.get("data_class"), valid_days: Number(fd.get("valid_days")), poisoning_ack: fd.get("poisoning_ack") === "on",
      ...(el.dataset.review ? {allowed_principals: fd.get("allowed_principals").split(",").map((p) => p.trim()).filter(Boolean), review_note: fd.get("review_note").trim(), parameter_constraints: parameterConstraints} : {}) } });
    toast(r.message); reload();
  },
  async "server-deregister"(el) {
    const fd = await ask({ title: `등록 해제 · ${el.dataset.id}`, body: "이후 호출은 차단됩니다.", confirm: "해제", danger: true });
    if (!fd) return;
    await gw(`registry/servers/${encodeURIComponent(el.dataset.id)}`, { method: "DELETE" });
    closeDrawer(); toast("등록을 해제했습니다."); reload();
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
    openDrawer(p.name, html`<div class="row-actions">${outcomeDecision(p.outcome) ? decisionChip(outcomeDecision(p.outcome)) : chip("outline", p.outcome)}
      <code>${p.policy_id}</code></div>${kv([["조건", p.condition], ["결과", p.outcome], ["처리", p.enforcement]])}`);
  },
  async enforcement(el) {
    const mode = el.dataset.mode;
    const fd = await ask({ title: mode === "monitor" ? "관찰 모드로 전환" : "집행 모드로 전환", body: mode === "monitor" ? "차단 대상 호출도 기록만 하고 실행됩니다." : "", confirm: "전환", danger: mode === "monitor" });
    if (!fd) return;
    await gw("enforcement", { method: "PUT", body: { mode } });
    toast("전환했습니다."); reload();
  },
  "open-case": (el) => { location.hash = `#/termination/${el.dataset.id}`; },
  async "open-termination"(el) {
    const grade = el.dataset.grade;
    const fd = await ask({
      title: `종료 시작 · ${el.dataset.name}`, body: `이 이용 관계의 호출이 즉시 차단됩니다.${grade ? ` 예상 등급 ${grade} ${GRADE[grade] || ""}` : ""}`,
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
    const kinds = { gateway: "게이트웨이 차단 확인", endpoint: "엔드포인트 설정 대조", credentials: "하위 시스템 자격 확인",
      liveness: "서버 도달 확인", session: "세션 종료 요청" };
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
    toast(`판정 ${d.case.grade} ${GRADE[d.case.grade]}`, d.case.grade === "T3"); reload(); refreshBadges();
  },
  async "revoke-credential"(el) {
    const fd = await ask({ title: "하위 시스템 자격 폐기", confirm: "폐기", danger: true });
    if (!fd) return;
    await gw(`termination/targets/${el.dataset.id}/revoke-credential`, { method: "POST" });
    toast("폐기를 확인했습니다."); reload();
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
    const kinds = Object.fromEntries(Object.entries(currentCase.evidence_kinds).map(([k, m]) => [k, m.label]));
    const targets = Object.fromEntries([["", "케이스 전체"], ...currentCase.targets.map((t) => [t.id, t.label])]);
    const fd = await ask({ title: "증거 등록",
      fields: html`${field.select("kind", "종류", kinds, "provider-attestation")}${field.select("target_id", "대상", targets)}
        ${field.text("subject", "식별자", 'required maxlength="300"')}${field.text("source", "출처", 'required maxlength="300"')}
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
  connector(el) {
    const g = connectorGroups.find((x) => x.key === el.dataset.key);
    if (!g) return;
    openDrawer(connectorName(g), html`<div class="row-actions">${connectorState(g)}
      ${g.violation ? chip("block", "미승인 사용") : ""}${connectorButtons(g)}</div>
      ${kv([["하네스", g.harness === "claude" ? "Claude Code" : "Codex"], ["종류", g.kinds.map((k) => CONNECTOR_KIND[k] || k).join(" · ")],
        ["대상", html`<span class="mono">${connectorTarget(g)}</span>`], ["처음 보고", when(g.first_seen)],
        ["결정", g.decision ? html`${g.note || "—"}<span class="sub">${g.decided_by} · ${when(g.decided_at)}</span>` : ""]])}
      <h3>사용 PC</h3>
      <table class="data"><thead><tr><th>사용자</th><th>PC</th><th>상태</th><th>마지막 보고</th></tr></thead><tbody>
        ${g.holders.map((h) => html`<tr><td>${h.display_name || "—"}</td><td class="mono">${h.workstation}</td>
          <td>${h.active ? chip(["pending", "denied", "expired"].includes(g.state) ? "block" : "plain", harnessStatus(h.status)) : chip("outline", "보고 없음")}</td><td class="small">${ago(h.last_seen)}</td></tr>`)}
      </tbody></table>`);
  },
  async "connector-decide"(el) {
    const r = await api("/api/connectors/decision", { method: "PUT", body: { key: el.dataset.key, decision: el.dataset.decision } });
    toast(r.message); reload(); refreshBadges();
  },
  async "connector-deny"(el) {
    const fd = await ask({ title: `거부 · ${el.dataset.name}`, fields: field.area("note", "사유", 'required minlength="2" maxlength="500"'),
      confirm: "거부", danger: true });
    if (!fd) return;
    const r = await api("/api/connectors/decision", { method: "PUT", body: { key: el.dataset.key, decision: "denied", note: fd.get("note").trim() } });
    toast(r.message); reload(); refreshBadges();
  },
  async "connector-policy"() {
    lastDocument = await api("/api/connectors/policy");
    ACTIONS["save-json"]({ dataset: { name: "connector-policy.json" } });
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
  audit(form) {
    // datetime-local carries no zone; the server needs one, so send UTC.
    const q = new URLSearchParams([...new FormData(form)].filter(([,v]) => String(v).trim())
      .map(([k, v]) => [k, ["since", "until"].includes(k) ? new Date(v).toISOString() : v]));
    location.hash = `#/audit?${q}`;
    reload();
  },
  "command-search"(form) {
    const query = String(new FormData(form).get("query") || "").trim();
    location.hash = `#/activity?q=${encodeURIComponent(query)}`;
  },
  async intake(form) {
    const fd = new FormData(form);
    const body = Object.fromEntries(["display_name", "repository_url", "endpoint_url", "intake_kind", "requested_transport", "purpose"].map((k) => [k, String(fd.get(k) || "").trim()]));
    const r = await api("/api/mcp-requests", { method: "POST", body });
    toast(r.message);
    location.hash = "#/intake?t=list";
    reload();
  },
};

// ── wiring ───────────────────────────────────────────────────────────────────
$("#drawer").addEventListener("cancel", (event) => { event.preventDefault(); closeDrawer(); });
$("#drawer").addEventListener("click", (event) => {
  if (event.target !== event.currentTarget) return;
  const bounds = event.currentTarget.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) closeDrawer();
});
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
document.addEventListener("toggle", (event) => {
  if (event.target.matches("details[open]")) charts.mountVisible(event.target);
}, true);
document.addEventListener("change", (event) => {
  if (event.target.matches("[data-intake-kind]")) {
    for (const label of event.target.form.querySelectorAll("[data-intake-field]")) {
      label.hidden = label.dataset.intakeField !== event.target.value;
      if (label.hidden) label.querySelector("input").value = "";
    }
    return;
  }
  const coverageFilter = event.target.closest("[data-coverage-filter]");
  if (coverageFilter) {
    ACTIONS["coverage-filter"]({ dataset: { key: coverageFilter.dataset.coverageFilter, value: coverageFilter.value } });
    return;
  }
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
  const input = event.target.closest("[data-list-search]");
  if (input) {
    const rows = [...(document.getElementById(input.dataset.listSearch)?.children || [])];
    const term = input.value.trim().toLocaleLowerCase();
    let shown = 0;
    for (const row of rows) {
      row.hidden = !row.textContent.toLocaleLowerCase().includes(term);
      if (!row.hidden) shown += 1;
    }
    const count = document.querySelector(`[data-list-count="${input.dataset.listSearch}"]`);
    if (count) count.textContent = `${shown}/${rows.length}건`;
    const note = document.querySelector(`[data-list-empty="${input.dataset.listSearch}"]`);
    if (note) note.hidden = shown > 0;
    return;
  }
  if (event.target.matches("[data-catalog-search]")) {
    const input = event.target;
    clearTimeout(input.searchTimer);
    input.searchTimer = setTimeout(async () => {
      try {
        const data = await api(`/api/mcp-catalog/search?q=${encodeURIComponent(input.value.trim())}`);
        if (input.isConnected && input.value.trim() === data.query) $("#catalog-results").innerHTML = String(catalogResults(data));
      } catch (error) { toast(error.message, true); }
    }, 250);
    return;
  }
  if (event.target.matches("[data-coverage-search]")) {
    const input = event.target;
    clearTimeout(input.searchTimer);
    input.searchTimer = setTimeout(() => {
      const q = new URLSearchParams(current.query);
      if (input.value.trim()) q.set("q", input.value.trim()); else q.delete("q");
      q.set("t", "items");
      history.replaceState(null, "", `#/coverage?${q}`);
      route().then(() => { const again = $("[data-coverage-search]"); again?.focus(); again?.setSelectionRange(again.value.length, again.value.length); });
    }, 400);
    return;
  }
  if (!event.target.matches("[data-feed-search]")) return;
  feed.query = event.target.value;
  renderFeed();
});
document.addEventListener("keydown", (event) => {
  if ($("#dialog").open) return; // Native dialog owns Escape and focus while it is open.
  if ($("#drawer").open && event.key === "Escape") { event.preventDefault(); closeDrawer(); }
  // Cancel the key default before opening: focus moves to the modal close button.
  if (["Enter", " "].includes(event.key) && !event.isComposing && event.target.matches("tr[data-act]")) { event.preventDefault(); event.target.click(); }
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
  const mobile = matchMedia("(max-width: 900px)");
  setNavCollapsed(mobile.matches || localStorage.getItem(NAV_KEY) === "true");
  mobile.addEventListener("change", () => setNavCollapsed(mobile.matches || localStorage.getItem(NAV_KEY) === "true"));
  $("#app-identity").textContent = `${viewer.name} · ${viewer.role_label}`;
  window.addEventListener("hashchange", route);
  await route();
  if (viewer.kit && viewer.managed_required && !(viewer.managed_devices || []).some((d) => d.status === "active" && d.managed_state === "active")) {
    ACTIONS["pc-kit"]();
  }
  if (viewer.admin) { refreshBadges(); setInterval(refreshBadges, 30000); }
}
boot().catch((error) => { $("#view").innerHTML = String(html`<div class="note bad">${error.message}</div>`); });
