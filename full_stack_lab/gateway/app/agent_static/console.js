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
import { mergeRows, searchRows, liveLabel, hourBuckets, splitBy, sankeyData, harnessLabel, DECISIONS,
  statusView, dedupeItems, pipelineOf, EVIDENCE } from "./console-state.mjs";
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
// D-62: who enforces what. Observed is never shown as blocked.
const CONTROL_STATE = {
  gateway_enforced: ["allow", "Gateway 강제"], endpoint_enforced: ["allow", "Endpoint 강제"],
  vendor_enforced: ["restrict", "Vendor 강제·수기 확인"], observed_only: ["alert", "관찰만"],
  unknown_not_enrolled: ["outline", "미등록·알 수 없음"], bypass_possible: ["block", "우회 가능"],
};
const INTEGRATION_CLASS = {
  gateway_mcp: "Gateway MCP", gateway_backend_connector: "Gateway 경유 SaaS", vendor_native_connector: "벤더 native",
  local_plugin_or_stdio: "로컬 플러그인·stdio", shadow_or_unknown: "섀도·미상",
};
const MANAGED_BY = { gateway: "Gateway", endpoint: "Endpoint", vendor: "벤더 콘솔", none: "없음" };
const RESPONSE = {
  returned: ["allow", "응답 반환"], masked: ["restrict", "마스킹 반환"], withheld: ["block", "실행 후 보류"],
  unknown: ["alert", "결과 미확인"], not_executed: ["outline", "전송 안 함"],
};
const controlChip = (s) => chip(...(CONTROL_STATE[s] || ["", s]));
const TONE_DECISION = { allow: "Allow", restrict: "Restrict", alert: "Alert", approval: "Approval", block: "Block", outline: "" };
const responseChip = (s) => chip(...(RESPONSE[s] || ["", s]));
const stateLabel = (s) => (CONTROL_STATE[s] || [, s])[1];

// Status × evidence (D-63). The meter's cells are drawn with SVG attributes, not style.
function evMeter(level, stale, label) {
  const cells = [0, 1, 2, 3].map((i) => `<rect x="${i * 7}" y="0" width="5" height="10" rx="1"${i < level ? ' class="on"' : ""}></rect>`).join("");
  return html`<span class="ev ${stale ? "stale" : ""}" role="img" aria-label="증거 ${level}/4 · ${label}">${raw(`<svg viewBox="0 0 26 10" aria-hidden="true">${cells}</svg>`)}<span aria-hidden="true">${label}</span></span>`;
}
function statusPair(item) {
  const v = statusView(item);
  return html`<span class="pair" role="group" aria-label="상태 ${stateLabel(v.state)}, 증거 ${v.evLabel}">${chip(v.tone, stateLabel(v.state))}${evMeter(v.level, v.stale, v.evLabel)}</span>`;
}
/** GW · EP · VD for one call: Gateway decided it, an enrolled device was bound, a vendor holds the rest. */
function planeGlyphs(r, providers) {
  const ep = (r.planes || []).includes("endpoint");
  const vd = providers?.has(r.server);
  const label = `게이트웨이 경유, ${ep ? "단말 결합" : "단말 결합 없음"}, ${vd ? "공급자 SaaS 잔여 범위" : "벤더 해당 없음"}`;
  return html`<span class="pg" role="img" aria-label="${label}"><b class="on" aria-hidden="true">GW</b><b class="${ep ? "on" : ""}" aria-hidden="true">EP</b><b class="${vd ? "res" : "na"}" aria-hidden="true">VD</b></span>`;
}
/** Sent · executed · response: ○ not sent, ◐ sent but unknown, ● executed. */
function flow3(r) {
  if (r.decision === "Approval" && !r.attempted) return chip("approval", "승인 대기");
  const mark = r.executed ? "●" : r.attempted ? "◐" : "○";
  const label = r.executed ? "실행됨" : r.attempted ? "전송·미확인" : "전송 안 함";
  return html`<span class="flow3" aria-label="${label}"><i aria-hidden="true">${mark}</i>${label}</span>${r.executed || r.attempted ? responseChip(r.response) : ""}`;
}
const UPSTREAM = { executed: ["allow", "실행됨"], unknown: ["alert", "전송·미확인"], not_sent: ["outline", "전송 안 함"] };
/** The five stops of one call. Self-reported fields are named as such. */
function pipeline(r, device) {
  const [source, gate, endpoint, upstream, response] = pipelineOf(r);
  const hash = (h) => (h ? html`<code>${String(h).slice(0, 8)}</code>` : "");
  return html`<ol class="pipe" aria-label="호출 경로">
    <li><b>출처</b><span class="v">${r.harness ? harnessLabel(r.harness) : r.agent || "—"} <span class="muted">자기 신고</span></span>
      <span class="v">${r.workstation || "단말 미상"}</span>${source.state === "signed" ? chip("brand", "서명 토큰") : chip("outline", "단말 결합 없음")}</li>
    <li class="${r.decision === "Block" ? "stop" : ""}"><b>Gateway</b>${decisionChip(r.decision)}<span class="v mono">${r.policy_id}</span>
      <span class="v">${gate.state === "refused-connection" ? "연결 단계 거부" : html`원장 #${r.id} ${hash(r.evidence_sha256)}`}</span></li>
    <li class="${endpoint.state === "bound" ? "" : "off"}"><b>Endpoint</b>${endpoint.state === "bound"
      ? html`${chip("brand", "단말 토큰 결합")}${device ? html`<span class="v">현재</span>${statusPair(device)}` : ""}`
      : chip("outline", "Endpoint 강제 아님")}</li>
    <li class="${upstream.state === "not_sent" ? "off" : ""}"><b>Upstream</b>${chip(...UPSTREAM[upstream.state])}</li>
    <li class="${response.state === "withheld" ? "stop" : ""}"><b>응답</b>${responseChip(response.state)}
      ${r.response_bytes != null ? html`<span class="v">${r.response_bytes} byte · ${(r.response_types || []).join(", ") || "—"} ${hash(r.response_sha256)}</span>` : ""}
      ${(r.masked_types || []).length ? html`<span class="v">${r.masked_types.join(", ")}</span>` : ""}
      ${response.state === "withheld" ? chip("block", "효과 유지") : ""}</li></ol>`;
}

// /api/integrations is admin-only and several pages read it; one fetch serves a 15 s window.
let planesCache = { at: 0, data: null };
async function planes() {
  if (!viewer.admin) return null;
  if (!planesCache.data || Date.now() - planesCache.at > 15000) planesCache = { at: Date.now(), data: await api("/api/integrations") };
  return planesCache.data;
}
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
  HOLD: ["outline", "검토 대기"], REMOTE_REVIEWED: ["approval", "계약 검토 완료"], VALIDATION_QUEUED: ["approval", "검증 대기"], VALIDATING: ["approval", "검증 중"],
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
  // The confirm button comes first in the DOM so Enter in a field confirms: implicit submission
  // uses the form's first submit button, and with 취소 first Enter silently cancelled (a status
  // change with a memo never applied). CSS shows 취소 on the left.
  form.innerHTML = String(html`<h3>${title}</h3>${body ? html`<p>${body}</p>` : ""}${fields}
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
  ${back}<h1>${title}</h1>${status ? html`<div class="status">${status}</div>` : ""}${actions ? html`<div class="actions">${actions}</div>` : ""}</div>`;
// A zero is not news: it stays in ink colour, and only a count that needs attention takes the decision colour.
const kpiStrip = (items) => html`<div class="kpis">${items.map(([label, value, tone = "", href = ""]) => [label, value,
  value === 0 || value === "0" ? "" : tone, href]).map(([label, value, tone, href]) => href
  ? html`<a class="kpi ${tone}" href="${href}"><div class="label">${label}</div><div class="value">${value ?? 0}</div></a>`
  : html`<div class="kpi ${tone}"><div class="label">${label}</div><div class="value">${value ?? 0}</div></div>`)}</div>`;
const panel = (title, body, { sub = "", tools = "", flush = false } = {}) => html`<section class="panel">
  <header><h2>${title}</h2>${sub ? html`<span class="sub">${sub}</span>` : ""}${tools ? html`<div class="tools">${tools}</div>` : ""}</header>
  <div class="body ${flush ? "flush" : ""}">${body}</div></section>`;
const chartBox = (id, label, size = "") => html`<div class="chart ${size}" id="${id}" role="img" aria-label="${label}"></div>`;

// ── routing ──────────────────────────────────────────────────────────────────
// Grouped the way an operator asks: what is happening, who controls what, how it starts and ends.
const PAGES = [
  { id: "overview", label: "개요", group: "관제" },
  { id: "activity", label: "호출", group: "관제" },
  { id: "approvals", label: "승인 대기", group: "관제", badge: "approvals" },
  { id: "coverage", label: "통제 범위", group: "통제", badge: "coverage" },
  { id: "servers", label: "MCP 서버", group: "통제" },
  { id: "people", label: "직원·단말", group: "통제" },
  { id: "intake", label: "도입 신청", group: "도입·종료" },
  { id: "termination", label: "종료·폐기", group: "도입·종료", badge: "termination" },
  { id: "policy", label: "정책", group: "도입·종료" },
];
// Addresses from before D-63 land on the tab that now holds their content.
const ALIASES = { "people?t=planes": "coverage?t=items", "people?t=configs": "coverage?t=shadow",
  "people?t=os": "coverage?t=shadow", "people?t=connectors": "coverage?t=vendor" };
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
    viewer.git_url && html`<a href="${viewer.git_url}" target="_blank" rel="noopener">${icon("git")}<span>내부 저장소</span><span class="ext" aria-hidden="true">↗</span></a>`,
    viewer.kit && html`<a href="#" data-act="pc-kit">${icon("plug")}<span>내 PC 연결</span></a>`,
  ].filter(Boolean);
  $("#nav").innerHTML = String(html`${[...groups].map(([group, pages]) => html`<div class="group">${group}</div>${pages.map((p) => html`
    <a href="#/${p.id}" title="${p.label}" ${active === p.id ? raw('aria-current="page"') : ""}>${icon(p.id)}<span>${p.label}</span>
      ${p.badge && badges[p.badge] ? html`<span class="count">${badges[p.badge]}</span>` : ""}</a>`)}`)}
    ${shortcuts.length ? html`<div class="group">바로가기</div>${shortcuts}` : ""}`);
}

function parseHash() {
  const [path, query = ""] = location.hash.replace(/^#\/?/, "").split("?");
  const [page = "", arg = ""] = path.split("/").map(decodeURIComponent);
  return { page, arg, query: new URLSearchParams(query) };
}

async function route() {
  stopLive();
  stopIntake();
  // Only hide the drawer: closeDrawer() also rewrites #/servers/<id> to #/servers, which here
  // would drop the id this route is about to open (a server tile never opened its drawer).
  setDrawer(false);
  charts.disposeAll();
  const alias = ALIASES[`${parseHash().page}?t=${parseHash().query.get("t")}`];
  if (alias) { history.replaceState(null, "", `#/${alias}`); return route(); }
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

// Provider-hosted servers (registry deployment "provider"): the vendor holds the SaaS side.
let providerServers = new Set();
function decisionRow(r) {
  return html`<tr class="clickable" tabindex="0" data-act="decision" data-id="${r.id}">
    <td class="t">${when(r.at, { seconds: true })}</td>
    <td>${decisionChip(r.decision)}<span class="sub mono">${r.policy_id}</span></td>
    <td class="who-cell"><b>${r.who}</b><span class="sub">${r.workstation ? html`<span class="mono">${r.workstation}</span> · ` : ""}${r.agent === "termination-probe" ? "종료 점검" : r.harness ? harnessLabel(r.harness) : "—"}</span></td>
    <td class="clip">${r.event_kind === "mcp-connection" ? chip("block", "연결 거부") : ""}<code>${r.server}.${r.tool}</code>${r.target ? html`<span class="sub muted">${short(r.target, 60)}</span>` : ""}</td>
    <td data-pri="2">${planeGlyphs(r, providerServers)}</td>
    <td>${flow3(r)}</td></tr>`;
}
const decisionTable = (rows, id = "") => html`<table class="data"><thead><tr><th>시각</th><th>판정·정책</th><th>사람·단말·하네스</th>
  <th>도구·대상</th><th data-pri="2">경로</th><th>전송→실행→응답</th></tr></thead><tbody ${id ? raw(`id="${id}"`) : ""}>${rows.map(decisionRow)}</tbody></table>`;

// D-49: a Console registration is approved until a date; past it P-APPROVAL-EXPIRY-001 blocks the calls.
const VALIDITY = { 1: "1일", 30: "30일", 90: "90일", 180: "180일", 365: "1년" };
function validityChip(registration) {
  if (!registration?.valid_until) return "";
  const days = Math.ceil((new Date(registration.valid_until).getTime() - Date.now()) / 86400000);
  return days <= 0 ? chip("block", "사용 기한 만료") : chip(days <= 14 ? "alert" : "outline", `D-${days}`);
}

function serverTile(s) {
  const tone = { READY: "ok", DRIFT: "warn", PENDING: "warn" }[s.status] || "bad";
  const retired = s.lifecycle && s.lifecycle !== "OPERATING";
  return html`<a class="tile" href="#/servers/${s.id}">
    <div class="top"><span class="dot ${tone}"></span><b>${s.display_name}</b></div>
    <div class="row-actions"><span class="chip outline mono">${s.id}</span>
      ${s.status !== "READY" ? chip("alert", SERVER_STATUS[s.status] || s.status) : ""}
      ${s.deployment === "provider" ? chip("brand", "제공자 운영") : ""}
      ${validityChip(s.registration)}
      ${retired ? chip(s.lifecycle === "RETIRED" ? "block" : "alert", LIFECYCLE[s.lifecycle] || s.lifecycle) : ""}</div>
    ${s.plane ? html`<div class="row-actions">${statusPair(s.plane)}${(s.plane.bypass || []).length ? chip("block", `우회 ${s.plane.bypass.length}`) : ""}</div>` : ""}
    <div class="stats"><span><b>${s.calls ?? 0}</b>호출</span><span><b>${s.blocked ?? 0}</b>차단</span><span><b>${s.tools ?? 0}</b>도구</span></div>
  </a>`;
}

// ── pages ────────────────────────────────────────────────────────────────────
const ROUTES = {};

ROUTES.overview = async (_, tab) => {
  const [o, blocked, pl] = await Promise.all([gw("overview"), gw("activity?limit=10&decision=Block"), planes()]);
  feed.rows = mergeRows([], blocked.rows);
  providerServers = new Set(o.servers.filter((s) => s.deployment === "provider").map((s) => s.id));
  const t = o.today, x = o.execution, term = o.termination || {};
  const buckets = hourBuckets(o.series);
  const byServer = splitBy(o.flows, "server", (r) => Number(r.n));
  const flowTotal = o.flows.reduce((s, f) => s + Number(f.n || 0), 0);
  const stations = o.workstations;
  const items = dedupeItems(pl.items);
  const count = (s) => items.filter((i) => i.state === s).length;
  const devices = pl.devices.filter((d) => d.endpoint_id);
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
    const sent = node(r.attempted ? "전송" : "전송 안 함");
    link(d, sent, n);
    if (!r.attempted) continue;
    const ran = node(r.executed ? "실행됨" : "실행 미확인");
    link(sent, ran, n);
    if (r.executed) link(ran, node(RESP[r.response] || r.response), n);
  }
  return {
    html: page({
      head: head("운영 현황", { status: modeChip(o.enforcement), actions: html`<a class="btn" href="#/coverage">통제 범위</a><a class="btn primary" href="#/activity">호출</a>` }),
      // One cell per operator question: traversal, enforcing plane, execution, response, bypass, termination.
      kpis: kpiStrip([["Gateway 경유 호출", x.tool_calls, "", "#/activity?event_kind=tools/call"],
        ["강제된 관리 계정", devices.filter((d) => d.account_state === "endpoint_enforced").length, "", "#/coverage?t=devices"],
        ["upstream 실행", x.executed, "allow", "#/activity?execution=executed"],
        ["실행 후 응답 보류", x.withheld, "block", "#/activity?execution=withheld"],
        ["우회 가능 항목", count("bypass_possible"), "block", "#/coverage?t=items&state=bypass_possible"],
        ["종료 T2·T3", term.unresolved_grades, "alert", "#/termination"]]),
      active: tab || "planes",
      tabs: [
        { key: "planes", label: "평면", n: count("bypass_possible"), hot: count("bypass_possible") > 0, body: html`<div class="stack"><div class="grid c21">
          ${panel("분류 × 통제 상태", items.length ? chartBox("c-ov-matrix", "분류별 통제 상태 항목 수", "lg") : empty("항목 없음"), { sub: `Gateway 밖 ${outside}건` })}
          ${panel("증거 수준", items.length ? chartBox("c-ov-evidence", "통제 상태를 받치는 증거 종류", "sm") : empty("항목 없음"))}</div>
          ${panel("우회 가능 상위", bypass.length ? html`<table class="data"><thead><tr><th>항목</th><th>분류</th><th>상태·증거</th><th>우회</th></tr></thead><tbody>
            ${bypass.map((i) => html`<tr class="clickable" tabindex="0" data-act="goto" data-href="#/coverage?t=items&state=bypass_possible&q=${encodeURIComponent(i.name)}">
              <td><b>${i.name}</b><span class="sub mono">${short(i.target || "", 50)}</span></td><td class="small">${INTEGRATION_CLASS[i.class] || i.class}</td>
              <td>${statusPair(i)}</td><td>${chip("block", `${(i.bypass || []).length}`)}</td></tr>`)}</tbody></table>` : empty("우회 가능 항목 없음"),
            { flush: true, tools: html`<a class="btn sm" href="#/coverage?t=items&state=bypass_possible">전체</a>` })}</div>` },
        { key: "exec", label: "실행·응답", n: x.withheld, hot: x.withheld > 0, body: html`<div class="stack">
          ${panel("판정 → 전송 → 실행 → 응답", (o.pipeline || []).length ? chartBox("c-ov-pipeline", "오늘 도구 호출의 판정에서 응답 처리까지의 흐름", "xl") : empty("오늘 도구 호출 없음"), { sub: "오늘" })}
          <div class="grid c2">
            ${panel("응답 처리", chartBox("c-ov-response", "오늘 실행된 호출의 응답 처리 비율", "sm"), { sub: `마스킹 ${x.masked} · 보류 ${x.withheld}` })}
            ${panel("전송 여부", chartBox("c-ov-sent", "오늘 호출의 전송·실행 여부", "sm"), { sub: `미확인 ${x.unknown}` })}</div></div>` },
        { key: "traffic", label: "출처·트래픽", body: html`<div class="stack">
          ${panel("시간대별 판정", chartBox("c-traffic", "최근 24시간 시간대별 판정 건수", "lg"), { sub: "최근 24시간" })}
          <div class="grid c12">
            ${panel("판정 비율", chartBox("c-share", "오늘 판정 비율", "sm"), { sub: "오늘" })}
            ${panel("서버별 호출", chartBox("c-servers", "최근 24시간 서버별 호출과 판정", "sm"), { sub: `${byServer.length}개 서버 · 24시간` })}
          </div>
          ${panel("하네스 → MCP 서버 → 판정", flowTotal ? chartBox("c-flow", "하네스에서 서버를 거쳐 판정까지의 호출 흐름", "xl") : empty("최근 24시간 호출 없음"), { sub: `${flowTotal}건 · 24시간` })}
          ${panel("직원 PC", html`<table class="data"><thead><tr><th>단말</th><th>사용자</th><th data-pri="2">하네스</th><th class="num">24시간 호출</th><th>통제 상태·증거</th><th data-pri="2">마지막 호출</th></tr></thead><tbody>
            ${stations.map((w) => html`<tr><td class="mono">${w.endpoint_id}</td><td><b>${w.display_name || w.owner_token}</b><span class="sub">${w.department || ""}</span></td>
              <td data-pri="2">${w.harness ? chip("plain", harnessLabel(w.harness)) : html`<span class="muted">—</span>`}</td><td class="num">${w.calls}</td>
              <td>${deviceOf[w.endpoint_id] ? statusPair(deviceOf[w.endpoint_id]) : chip("outline", "관측 전용")}</td><td class="small" data-pri="2">${ago(w.last_call)}</td></tr>`)}
            </tbody></table>${stations.length ? "" : empty("등록된 단말 없음")}`, { flush: true })}</div>` },
        { key: "risk", label: "위험·종료", n: t.Block, hot: t.Block > 0, body: html`<div class="stack">
          <div class="grid c2">
            ${panel("많이 걸린 정책", o.top_policies.length ? chartBox("c-policies", "최근 24시간 차단·경보가 많은 정책") : empty("최근 24시간 차단·경보 없음"), { sub: "차단·경보 · 24시간", tools: viewer.admin ? html`<a class="btn sm" href="#/intake?t=audit">A.I.G 검사</a>` : "" })}
            ${panel("종료·폐기", chartBox("c-term", "종료·폐기 현황"), { tools: html`<a class="btn sm" href="#/termination">열기</a>` })}
          </div>
          ${panel("최근 차단", feed.rows.length ? decisionTable(feed.rows) : empty("차단 기록 없음"), { flush: true, tools: html`<a class="btn sm" href="#/activity?decision=Block">전체</a>` })}
        </div>` },
      ],
    }),
    charts: {
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
        { name: "실행 후 보류", value: Number(x.withheld), color: charts.color("Block") }].filter((g) => g.value)),
      "c-ov-sent": () => charts.donut([
        { name: "실행됨", value: Number(x.executed), color: charts.color("Allow") },
        { name: "전송·미확인", value: Number(x.unknown), color: charts.color("Alert") },
        { name: "전송 안 함", value: Number(x.not_sent), color: charts.color("") }].filter((g) => g.value)),
      "c-traffic": () => charts.decisionColumns(buckets.map((b) => b.label), buckets),
      "c-share": () => charts.donut(DECISIONS.map((d) => ({ name: DECISION_LABEL[d], value: t[d], color: charts.color(d) }))),
      "c-servers": () => charts.decisionColumns(byServer.map((g) => g.key), byServer, {
        horizontal: true, grouped: true, onClick: (e) => { location.hash = `#/activity?server=${encodeURIComponent(e.name)}`; } }),
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
    "c-by-plane": () => charts.donut([
      { name: "Gateway + 단말 결합", value: shown.filter((r) => (r.planes || []).includes("endpoint")).length, color: charts.color("Allow") },
      { name: "Gateway 단독", value: shown.filter((r) => !(r.planes || []).includes("endpoint")).length, color: charts.color("Alert") }].filter((g) => g.value)),
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
  // others would AND a stale "미등록 연결" with "실제 실행" into an empty list.
  if (FEED_FILTERS.some((key) => query.has(key))) for (const key of FEED_FILTERS) feed.filters[key] = query.get(key) || "";
  if (query.has("q")) feed.query = query.get("q");
  const data = await gw(`activity?${feedQuery({ limit: 200 })}`);
  feed.rows = mergeRows([], data.rows);
  feed.pending = [];
  feed.cursor = data.cursor;
  feed.lastOk = Date.now();
  feed.failing = false;
  if (viewer.admin && !feed.servers.length) {
    const registry = (await gw("registry")).servers;
    feed.servers = registry.map((s) => s.id);
    providerServers = new Set(registry.filter((s) => s.deployment === "provider").map((s) => s.id));
  }
  const servers = viewer.admin ? feed.servers : [...new Set(feed.rows.map((r) => r.server))].sort();
  const option = (value, label, cur) => html`<option value="${value}" ${value === cur ? raw("selected") : ""}>${label}</option>`;
  const f = feed.filters;
  return {
    html: page({
      head: head("호출", {
        status: html`<span class="live"><span class="dot" id="feed-dot"></span><span id="feed-status"></span></span>`,
        actions: html`<button class="btn" type="button" data-act="live" aria-pressed="${String(!feed.live)}">${feed.live ? "일시정지" : "실시간 재개"}</button>
          ${viewer.admin ? html`<button class="btn" data-act="audit-verify">감사 체인 검증</button>` : ""}`,
      }),
      active: tab || "live",
      tabs: [
        { key: "live", label: "이벤트", body: html`<section class="panel">
          <div class="filters">
            <input class="grow" data-feed-search type="search" maxlength="120" value="${feed.query}" placeholder="사람·단말·하네스·도구·대상·정책·trace" aria-label="불러온 기록에서 찾기" />
            <select data-filter="decision" aria-label="판정">${option("", "모든 판정", f.decision)}
              ${Object.entries(DECISION).map(([k, [, label]]) => option(k, label, f.decision))}</select>
            <select data-filter="server" aria-label="서버">${option("", "모든 서버", f.server)}${servers.map((s) => option(s, s, f.server))}</select>
            <select data-filter="event_kind" aria-label="이벤트 종류">${option("", "모든 이벤트", f.event_kind)}${option("tools/call", "도구 호출", f.event_kind)}${option("mcp-connection", "연결 거부", f.event_kind)}</select>
            <select data-filter="execution" aria-label="실행 여부">${option("", "모든 실행 결과", f.execution)}${option("executed", "실제 실행", f.execution)}${option("not-sent", "미전송", f.execution)}${option("unknown", "실행 여부 미확인", f.execution)}${option("withheld", "실행 후 응답 보류", f.execution)}</select>
            ${viewer.admin ? html`<input data-filter="person" type="search" placeholder="사람" value="${f.person}" aria-label="사람" />` : ""}
          </div>
          <div class="body">${chartBox("c-minutes", "불러온 호출의 시간 분포", "sm")}</div>
          <div class="body flush">${decisionTable([], "feed")}<p class="empty" id="feed-empty" hidden></p></div></section>` },
        { key: "stats", label: "분석", body: html`<div class="stack"><div class="grid c2">
          ${panel("응답 처리", chartBox("c-by-response", "불러온 호출의 응답 처리 비율", "sm"))}
          ${panel("강제 평면", chartBox("c-by-plane", "불러온 호출의 Gateway 단독·단말 결합 비율", "sm"))}</div>
          <div class="grid c2">
          ${panel("서버별", chartBox("c-by-server", "불러온 호출의 서버별 판정"))}
          ${panel("하네스별", chartBox("c-by-harness", "불러온 호출의 하네스별 비율"))}</div>
          ${panel("사람별", chartBox("c-by-person", "불러온 호출의 사람별 판정", "lg"))}</div>` },
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
  const device = r.device_id ? (await planes().catch(() => null))?.devices.find((d) => d.endpoint_id === r.device_id) : null;
  const conflictChip = (c) => chip((DECISION[c.decision] || [""])[0], `${(DECISION[c.decision] || [, c.decision])[1]} ${c.policy_id}`);
  openDrawer(`호출 #${r.id}`, html`${pipeline(r, device)}`, [
    { key: "summary", label: "요약", body: html`<blockquote class="quote">${r.reason}</blockquote>
      ${r.policy_id === "P-ANOMALY-001" && viewer.admin ? html`<div class="row-actions">${chip("alert", "A.I.G 자동 검사 대상")}
        <a class="btn sm" href="#/intake?t=audit">A.I.G 검사 보기</a></div>` : ""}${kv([
      ["시각", new Date(r.at).toLocaleString("ko-KR")], ["사람", `${r.who}${r.department ? ` · ${r.department}` : ""}`],
      ["역할", ROLE[r.role] || r.role], ["단말", r.workstation], ["하네스", r.harness ? harnessLabel(r.harness) : r.agent],
      ["이벤트", r.event_kind === "mcp-connection" ? "연결 거부" : "도구 호출"],
      ["도구", html`<code>${r.server}.${r.tool}</code>`], ["대상", r.target ? html`<code>${r.target}</code>` : ""],
      ["종료 판정", r.server && r.server !== "?" && viewer.admin ? html`<a href="#/termination">이용 관계 T1~T3</a>` : ""]])}` },
    { key: "policy", label: "정책", n: (r.pac_failures || []).length, body: kv([
      ["최종 정책", html`<code>${r.policy_id}</code>`],
      ["PAC 실패", (r.pac_failures || []).length ? html`${r.pac_failures.map((x) => chip("block", x))}` : "없음"],
      ["다른 해당 정책", (r.conflicts || []).length ? html`${r.conflicts.map(conflictChip)}` : "없음"],
      ["행위", `${r.action_ko || "—"} (${r.action || "?"})`], ["데이터 등급", r.data_class_ko], ["분류 근거", r.summary],
      ["개인정보", (r.privacy_types || []).join(", ")], ["연쇄 표지", (r.sequence_flags || []).join(", ")],
      ["예외", r.exception_id], ["승인 요청", r.approval_id], ["집행 모드", r.enforcement], ["집행 시 판정", r.would_decision]]) },
    { key: "trace", label: "추적", body: html`${kv([["감사 해시", r.evidence_sha256 ? html`<code>${r.evidence_sha256}</code>` : ""],
      ["trace", r.trace_id ? html`<code>${r.trace_id}</code>` : ""], ["오류", r.error], ["작업", r.task_id]])}${json(r)}` },
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
        { key: "servers", label: "서버", n: servers.length, body: html`<div class="stack">
          ${panel("서버별 호출", byServer.length ? chartBox("c-srv-calls", "최근 24시간 서버별 호출과 판정") : empty("최근 24시간 호출 없음"), { sub: "24시간" })}
          ${servers.length ? html`<div class="tiles">${servers.map(serverTile)}</div>`
            : panel("서버", html`${empty("등록된 서버가 없어요")}<div class="row-actions center"><a class="btn primary" href="#/intake">도입 신청 보기</a></div>`)}</div>` },
        { key: "tools", label: "도구", n: reg.tools.length, body: html`<div class="stack">
          ${panel("서버별 도구 (행위)", chartBox("c-srv-actions", "서버별 승인 도구 수를 읽기·쓰기·실행으로 나눈 막대"))}
          ${panel("도구", html`<table class="data"><thead><tr><th>서버</th><th>도구</th><th>행위</th><th>상태</th></tr></thead><tbody>
            ${tools.map((t) => html`<tr><td class="mono">${t.server_id}</td><td><code>${t.name}</code></td>
              <td>${chip({ r: "allow", w: "alert", x: "block" }[t.action] || "", ACTION[t.action] || t.action)}</td>
              <td>${!t.enabled ? chip("outline", "미승인") : t.contract_ok ? chip("allow", "계약 일치") : chip("alert", "계약 불일치")}</td></tr>`)}
            </tbody></table>`, { flush: true, sub: `${tools.length}개`,
            tools: html`<select data-act-change="tool-filter" aria-label="서버">${option("", "모든 서버")}${reg.servers.map((s) => option(s.id, s.id))}</select>` })}</div>` },
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
  const registration = registry.registrations?.[id];
  openDrawer(s.display_name, html`<div class="row-actions">${chip({ READY: "allow", DRIFT: "alert" }[s.status] || "block", SERVER_STATUS[s.status] || s.status)}
      ${chip(s.lifecycle === "OPERATING" ? "outline" : "block", LIFECYCLE[s.lifecycle] || s.lifecycle)}
      ${chip("outline", s.deployment === "provider" ? "제공자 운영" : "사내 운영")}
      ${validityChip(registration)}
      ${s.status === "DRIFT" && !registration ? html`<button class="btn sm primary" data-act="approve-contract" data-id="${s.id}">승인본 갱신</button>` : ""}
      ${s.lifecycle !== "RETIRED" ? html`<button class="btn sm" type="button" data-act="server-check" data-id="${s.id}">연결 확인</button>` : ""}
      ${registration && !registration.intake_id ? chip("block", "신청 기록 없는 직접 등록 · 실행 차단") : ""}
      ${registration ? html`<button class="btn sm danger" type="button" data-act="server-deregister" data-id="${s.id}">등록 해제</button>` : ""}</div>
    ${s.status_reason && s.status !== "READY" ? html`<p class="note warn">${s.status_reason}</p>` : ""}`, [
    { key: "info", label: "개요", body: kv([["id", html`<code>${s.id}</code>`], ["Gateway 경로", html`<code>/mcp/${s.id}/</code>`],
      ["패키지", html`<code>${s.source_ref || `${s.package}@${s.version}`}</code>`], ["upstream", html`<code>${s.endpoint}</code>`],
      ["공급자", s.supplier], ["라이선스", s.license], ["하위 시스템", s.downstream ? JSON.stringify(s.downstream) : ""],
      ["사용 기한", registration ? `${when(registration.valid_until)} · ${DATA_CLASS[registration.data_class] || ""}` : ""],
      ["등록", registration ? `${registration.registered_by} · ${when(registration.registered_at)}` : ""],
      ["마지막 확인", s.last_seen_at ? `${when(s.last_seen_at)} · ${ago(s.last_seen_at)}` : ""]]) },
    { key: "tools", label: "도구", n: tools.length, body: html`<table class="data"><thead><tr><th>도구</th><th>행위</th><th>상태</th></tr></thead><tbody>
      ${tools.map((t) => html`<tr><td><code>${t.name}</code></td><td>${chip({ r: "allow", w: "alert", x: "block" }[t.action] || "", ACTION[t.action] || t.action)}</td>
        <td>${!t.enabled ? chip("outline", "미승인") : t.contract_ok ? chip("allow", "일치") : chip("alert", "불일치")}</td></tr>`)}</tbody></table>` },
    { key: "exit", label: "종료 조건", body: html`<div class="pill-list">${Object.entries(EXIT_TERMS).map(([k, label]) => bool(terms[k], label))}</div>
      ${creds.length ? kv([["보유 자격", html`${creds.map((c) => html`<code>${c.id}</code> `)}`]]) : ""}
      ${rels.length ? html`<h3>이용 관계</h3>${kv(rels.map((u) => [u.id, html`${u.purpose} · ${u.organization} · ${u.status}
        <span class="sub">허용 자원 ${(u.allowed_resources || []).join(", ") || "없음"} — 밖이면 P-SCOPE-001 경보</span>`]))}
        <div class="row-actions"><a class="btn sm" href="#/termination">종료·폐기</a></div>` : ""}` },
  ]);
}

// ── harness inventory (D-53): reported state is not enforcement evidence ──
const CONNECTOR_KIND = { connector: "claude.ai 커넥터", plugin: "플러그인", server: "직접 추가", app: "ChatGPT 앱", feature: "기본 기능" };
const CONNECTOR_STATE = { pending: ["approval", "미승인"], expired: ["block", "검토 기한 만료"], denied: ["block", "거부 정책"],
  approved: ["allow", "예외 승인"], default: ["outline", "재검토 필요"] };
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
  : html`${g.state === "default" ? "" : html`<button class="btn sm primary" data-act="connector-decide" data-key="${g.key}" data-decision="approved">예외 승인</button>`}
    <button class="btn sm danger" data-act="connector-deny" data-key="${g.key}" data-name="${connectorName(g)}">거부</button>`;
let connectorGroups = [];

// 통제 범위 (D-63): which plane governs each integration and device, with the evidence.
// Borrowed shapes: Microsoft mcp-gateway AdaptersPage (searchable list + status badge +
// detail drawer), LiteLLM MCPSubmissionsTab (state counts as the KPI row, review history),
// IBM ContextForge plugin modes (an inactive or unenrolled thing is a visible state).
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
  const seg = (key, value, label, cur) => html`<button type="button" data-act="coverage-filter" data-key="${key}" data-value="${value}" aria-pressed="${String(cur === value)}">${label}</button>`;
  const shadowRows = inv.entries.filter((e) => e.classification !== "registered");
  const oldest = p.devices.filter((d) => d.evidence_kind === "kernel").map((d) => statusView(d)).sort((a, b) => b.level - a.level)[0];
  return {
    html: page({
      head: head("통제 범위", { status: oldest ? evMeter(oldest.level, oldest.stale, oldest.evLabel) : chip("outline", "커널 증거 없음"),
        actions: html`<button class="btn" type="button" data-act="connector-policy">커넥터 정책 파일</button>` }),
      kpis: kpiStrip([["항목", items.length, "", "#/coverage?t=items"],
        ["Gateway 강제", count("gateway_enforced"), "allow", "#/coverage?t=items&state=gateway_enforced"],
        ["Endpoint 강제", count("endpoint_enforced"), "allow", "#/coverage?t=items&state=endpoint_enforced"],
        ["Vendor·수기", count("vendor_enforced"), "restrict", "#/coverage?t=items&state=vendor_enforced"],
        ["관찰만·미등록", count("observed_only") + count("unknown_not_enrolled"), "alert", "#/coverage?t=items&state=observed_only"],
        ["우회 가능", count("bypass_possible"), "block", "#/coverage?t=items&state=bypass_possible"]]),
      active: tab || "items",
      tabs: [
        { key: "items", label: "항목", n: items.length, body: html`<div class="stack"><div class="grid c21">
          ${panel("분류 × 상태", items.length ? chartBox("c-cov-matrix", "분류별 통제 상태 항목 수", "lg") : empty("항목 없음"))}
          ${panel("증거 수준", items.length ? chartBox("c-cov-evidence", "항목 상태를 받치는 증거 종류 비율", "sm") : empty("항목 없음"))}</div>
          ${panel("MCP·커넥터·플러그인", html`<table class="data"><thead><tr><th>항목</th><th>분류</th><th data-pri="2">관리 주체</th><th>상태·증거</th><th data-pri="2">승인</th><th>우회</th><th data-pri="2">발견</th></tr></thead><tbody>
            ${rows.map((i) => html`<tr class="clickable" tabindex="0" data-act="integration" data-key="${i.key}">
              <td><b>${i.name}</b><span class="sub mono">${short(i.target || "", 56)}</span>${i.pcs > 1 ? html`<span class="sub">×${i.pcs} PC</span>` : ""}</td>
              <td class="small">${INTEGRATION_CLASS[i.class] || i.class}${i.harness ? html`<span class="sub">${i.harness === "claude" ? "Claude Code" : "Codex"}</span>` : ""}</td>
              <td data-pri="2">${MANAGED_BY[i.managed_by] || i.managed_by}</td><td>${statusPair(i)}</td>
              <td class="small" data-pri="2">${i.approval?.state || "—"}${i.approval?.expires_at ? html`<span class="sub">~${when(i.approval.expires_at)}</span>` : ""}</td>
              <td>${(i.bypass || []).length ? chip("block", `${i.bypass.length}`) : html`<span class="muted">—</span>`}</td>
              <td class="small" data-pri="2">${i.discovered_from}${i.discovered_at ? html`<span class="sub">${when(i.discovered_at)}</span>` : ""}</td></tr>`)}
            </tbody></table>${rows.length ? "" : empty("조건에 맞는 항목 없음")}`, { flush: true,
            tools: html`<input type="search" data-coverage-search maxlength="80" value="${query.get("q") || ""}" placeholder="이름·대상·소유자" aria-label="항목 찾기" />
              <div class="seg" role="group" aria-label="상태">${seg("state", "", "전체", state)}${Object.entries(CONTROL_STATE).map(([k, [, label]]) => seg("state", k, label, state))}</div>
              <div class="seg" role="group" aria-label="분류">${seg("class", "", "모든 분류", cls)}${Object.entries(INTEGRATION_CLASS).map(([k, label]) => seg("class", k, label, cls))}</div>` })}</div>` },
        { key: "devices", label: "단말·계정", n: p.devices.length, hot: p.summary.devices.bypass_possible > 0, body: panel("단말·계정",
          html`<table class="data"><thead><tr><th>단말·계정</th><th>소유자</th><th data-pri="2">플랫폼</th><th>단말 상태·증거</th><th>관리 계정</th><th data-pri="2">검사</th><th>우회 경로</th></tr></thead><tbody>
            ${p.devices.map((d) => html`<tr><td class="mono">${d.endpoint_id || "—"}<span class="sub">${d.hostname || ""}${d.account ? ` · ${d.account}(${d.uid})` : ""}</span></td>
              <td>${d.owner || "—"}</td><td data-pri="2">${d.platform || "—"}</td><td>${statusPair(d)}</td>
              <td>${d.account_state ? controlChip(d.account_state) : "—"}</td>
              <td data-pri="2">${Object.keys(d.checks || {}).length ? html`<span class="pg" role="img" aria-label="${Object.entries(d.checks).map(([k, v]) => `${k} ${v ? "통과" : "실패"}`).join(", ")}">${Object.entries(d.checks).map(([k, v]) => html`<b class="${v ? "on" : ""}" aria-hidden="true">${{ apparmor_enforcing: "AA", nftables_active: "NF", protected_configs: "CF", ordinary_account: "UA" }[k] || k}</b>`)}</span>` : html`<span class="muted">—</span>`}</td>
              <td class="small">${(d.bypass || []).length ? d.bypass.map((b) => chip("block", b)) : html`<span class="muted">—</span>`}
                ${d.kernel_denials_24h ? html`<span class="sub">커널 차단 24시간 ${d.kernel_denials_24h}건</span>` : ""}</td></tr>`)}
            </tbody></table>${p.devices.length ? "" : empty("단말 없음")}`, { flush: true }) },
        { key: "shadow", label: "섀도·잔존", n: shadowRows.length + (inv.os_events || []).length, hot: shadowRows.length > 0, body: html`<div class="stack">
          ${panel("발견 대비 커널 차단", (shadowRows.length || (inv.os_events || []).length) ? chartBox("c-cov-shadow", "단말별 발견한 섀도·잔존 설정과 커널 차단 수", "sm") : empty("발견·차단 없음"))}
          ${panel("단말 MCP 설정", html`<table class="data"><thead><tr><th>단말</th><th data-pri="2">설정 파일</th><th>서버</th><th>연결</th><th>분류</th></tr></thead><tbody>
            ${inv.entries.map((e) => html`<tr><td class="mono">${e.endpoint_id}</td><td class="small mono" data-pri="2">${e.config_path}</td>
              <td><b>${e.server_label}</b>${e.registry_name ? html`<span class="sub">${e.registry_name}</span>` : ""}</td>
              <td class="small mono clip">${e.transport} ${short(e.endpoint_ref, 60)}</td><td>${chip(...(ENDPOINT_CLASS[e.classification] || ["", e.classification]))}</td></tr>`)}
            </tbody></table>${inv.entries.length ? "" : empty("보고된 설정 없음")}`, { flush: true })}
          ${panel("커널 차단 관측", html`<table class="data"><thead><tr><th>시각</th><th>단말</th><th>종류</th><th>관측</th></tr></thead><tbody>
            ${(inv.os_events || []).map((e) => html`<tr><td>${when(e.observed_at)}</td><td class="mono small">${e.endpoint_id}</td>
              <td>${chip("block", e.kind === "network-denied" ? "네트워크 차단" : "실행 차단")}</td>
              <td class="mono small">${Object.entries(e.details).map(([k, v]) => `${k}=${v}`).join(" · ")}</td></tr>`)}
            </tbody></table>${(inv.os_events || []).length ? "" : empty("커널 차단 관측 없음")}`, { flush: true })}</div>` },
        { key: "vendor", label: "벤더·커넥터", n: review, hot: review > 0, body: panel("하네스 커넥터·앱·기능",
          conn.items.length ? html`<table class="data"><thead><tr><th>이름</th><th>하네스</th><th data-pri="2">종류</th><th class="num">활성 PC</th><th>승인</th><th>벤더 콘솔</th><th></th></tr></thead><tbody>
            ${conn.items.map((g) => { const vendor = items.find((i) => i.item_key === g.key)?.vendor_control; return html`<tr class="clickable" tabindex="0" data-act="connector" data-key="${g.key}">
              <td><b>${connectorName(g)}</b><span class="sub mono">${connectorTarget(g)}</span></td>
              <td>${chip("plain", g.harness === "claude" ? "Claude Code" : "Codex")}</td>
              <td class="small" data-pri="2">${g.kinds.map((k) => CONNECTOR_KIND[k] || k).join(" · ")}</td>
              <td class="num">${g.active_pcs}<span class="sub">${g.people}명</span></td>
              <td>${connectorState(g)}${g.violation ? chip("block", "미승인 보고") : ""}</td>
              <td class="small">${vendor ? html`${chip("restrict", vendor.console_state)}<span class="sub">수기 · ${vendor.verified_by} · ${when(vendor.verified_at)}</span>` : html`<span class="muted">기록 없음</span>`}</td>
              <td class="num nowrap">${connectorButtons(g)}</td></tr>`; })}</tbody></table>`
            : empty("직원 PC 키트의 보고 없음"), { flush: true, sub: conn.review_days ? `검토 기한 ${conn.review_days}일` : "" }) },
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
          { name: "커널 차단", color: charts.color("Block"), data: ids.map((id) => (inv.os_events || []).filter((e) => e.endpoint_id === id).length) }],
          { horizontal: true }); },
    },
  };
};

// 직원·단말: people and the devices they enrolled; what controls them is on 통제 범위.
let peopleAccounts = [];
let integrationItems = [];
ROUTES.people = async (_, tab) => {
  const [{ accounts }, { requests: signups }, inv, o, p] = await Promise.all([
    api("/api/accounts"), api("/api/signup-requests"), gw("endpoint/inventory"), gw("overview"), planes()]);
  peopleAccounts = accounts;
  const deviceState = Object.fromEntries(p.devices.filter((d) => d.endpoint_id).map((d) => [d.endpoint_id, d]));
  const harnessOf = Object.fromEntries(o.workstations.map((w) => [w.endpoint_id, w]));
  const byHarness = splitBy(o.flows, (f) => harnessLabel(f.harness), (f) => Number(f.n));
  const managed = inv.agents.filter((a) => a.managed_state && a.managed_state !== "unmanaged");
  return {
    html: page({
      head: head("직원·단말", { actions: html`<button class="btn primary" type="button" data-act="account-invite">조직 초대</button><button class="btn" type="button" data-act="device-issue">장치 자격 발급</button>` }),
      kpis: kpiStrip([["단말", inv.coverage.known_endpoints], ["최근 15분 보고", inv.coverage.reporting_recently],
        ["관리형 활성", managed.filter((a) => a.managed_state === "active").length, "allow"],
        ["격리", managed.filter((a) => a.managed_state === "quarantined").length, "block"],
        ["설치 검토 대기", managed.filter((a) => a.managed_state === "pending").length, "approval"]]),
      active: tab || "devices",
      tabs: [
        { key: "devices", label: "단말", n: inv.agents.length, body: html`<div class="stack"><div class="grid c21">
          ${panel("단말별 호출", o.workstations.length ? chartBox("c-ws-calls", "최근 24시간 단말별 호출 수", "sm") : empty("단말 없음"), { sub: "24시간" })}
          ${panel("하네스", byHarness.length ? chartBox("c-harness", "최근 24시간 하네스별 호출 비율", "sm") : empty("호출 없음"), { sub: "24시간" })}</div>
          ${panel("단말", html`<table class="data"><thead><tr><th>단말</th><th>소유자</th><th data-pri="2">하네스</th><th>통제 상태·증거</th><th data-pri="2">마지막 보고</th><th></th></tr></thead><tbody>
            ${inv.agents.map((a) => html`<tr><td class="mono">${a.endpoint_id}<span class="sub">${a.platform || ""}</span></td><td>${harnessOf[a.endpoint_id]?.display_name || a.owner_token || "—"}</td>
              <td data-pri="2">${harnessOf[a.endpoint_id]?.harness ? chip("plain", harnessLabel(harnessOf[a.endpoint_id].harness)) : "—"}</td>
              <td>${deviceState[a.endpoint_id] ? statusPair(deviceState[a.endpoint_id]) : chip("outline", "관측 전용")}
                ${a.managed_state && a.managed_state !== "unmanaged" ? html`<span class="sub">${({ active: "활성", pending: "설치 검토 대기", quarantined: "격리" })[a.managed_state] || a.managed_state}</span>` : ""}</td>
              <td class="small" data-pri="2">${ago(a.last_seen_at)}</td>
              <td class="num">${["pending", "quarantined"].includes(a.managed_state) && a.policy_hash ? html`<button class="btn sm primary" type="button" data-act="device-activate" data-id="${a.endpoint_id}" data-hash="${a.policy_hash}">설치 확인·활성화</button>` : ""}
                ${a.status === "revoked" ? chip("outline", "폐기됨") : html`<button class="btn sm danger" type="button" data-act="device-revoke" data-id="${a.endpoint_id}">자격 폐기</button>`}</td></tr>`)}
            </tbody></table>${inv.agents.length ? "" : empty("보고한 단말 없음")}`, { flush: true })}</div>` },
        { key: "accounts", label: "계정", n: accounts.length, body: panel("계정", html`<table class="data"><thead><tr><th>이름</th><th data-pri="2">이메일</th><th>역할</th><th data-pri="2">부서</th><th>상태</th><th></th></tr></thead><tbody>
          ${accounts.map((a) => html`<tr><td><b>${a.display_name}</b><span class="sub">${a.job_title || ""}</span></td><td class="small" data-pri="2">${a.email}</td>
            <td>${ROLE[a.role] || a.role}</td><td data-pri="2">${a.department}</td>
            <td>${chip({ active: "allow", disabled: "block", locked: "alert" }[a.status] || "", { active: "사용", disabled: "중지", locked: "잠김" }[a.status] || a.status)}</td>
            <td class="num">${a.user_id === viewer.user_id ? html`<span class="small muted">본인</span>`
              : html`<button class="btn sm" data-act="account-status" data-id="${a.user_id}" data-name="${a.display_name}" data-status="${a.status}">상태 변경</button>
                ${a.user_id !== "root" ? html`<button class="btn sm danger" data-act="account-delete" data-id="${a.user_id}" data-name="${a.display_name}">삭제</button>` : ""}`}</td></tr>`)}
          </tbody></table>`, { flush: true }) },
        { key: "signups", label: "가입 승인", n: signups.filter((s) => s.status === "pending").length,
          body: panel("회원가입 신청", html`<table class="data"><thead><tr><th>아이디</th><th>이름</th><th>신청</th><th>상태</th><th></th></tr></thead><tbody>
          ${signups.map((s) => html`<tr><td class="mono">${s.username}</td><td>${s.display_name}</td><td>${when(s.requested_at)}</td>
            <td>${chip(s.status === "approved" ? "allow" : s.status === "rejected" ? "block" : "approval", s.status)}</td>
            <td>${s.status === "pending" ? html`<button class="btn sm primary" data-act="signup-approve" data-id="${s.id}">승인</button>
              <button class="btn sm danger" data-act="signup-reject" data-id="${s.id}">거부</button>` : ""}</td></tr>`)}
          </tbody></table>${signups.length ? "" : empty("가입 신청 없음")}`, { flush: true }) },
        { key: "managed", label: "설치·연결 이력", n: (inv.managed_events || []).length,
          body: panel("관리형 단말 연결 이력", html`<table class="data"><thead><tr><th>시각</th><th>사용자·단말</th><th>결과</th><th data-pri="2">근거</th></tr></thead><tbody>
            ${(inv.managed_events || []).map((e) => html`<tr><td>${when(e.observed_at)}</td><td>${e.owner_token}<span class="sub mono">${e.endpoint_id || "—"}</span></td>
              <td>${e.kind}</td><td class="small" data-pri="2">${short(JSON.stringify(e.detail), 220)}</td></tr>`)}</tbody></table>`, { flush: true }) },
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
let scanJobs = [];
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
    for (const key of ["list", "audit"]) {
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
  return html`${requests.length ? html`<table class="data"><thead><tr><th>MCP</th><th>신청자</th><th>상태</th><th>내부 저장소</th></tr></thead><tbody>
    ${requests.map((r) => html`<tr><td><b>${r.display_name}</b><span class="sub mono">${r.repository_url}</span></td>
      <td>${r.submitted_by_name}</td><td>${chip(...(INTAKE_STATUS[r.status] || ["", r.status]))}</td>
      <td>${r.internal_repo_url ? html`<a href="${r.internal_repo_url}" target="_blank" rel="noopener noreferrer">열기·클론 ↗</a>` : "승인 전"}</td></tr>`)}</tbody></table>` : empty(data.query ? "일치하는 신청 없음" : "아직 신청된 MCP가 없습니다.")}
    ${registry.length ? html`<p class="small muted">등록된 MCP: ${registry.map((r) => r.display_name).join(", ")}</p>` : ""}`;
}
ROUTES.intake = async (_, tab) => {
  const [{ requests }, audit, catalog] = await Promise.all([api("/api/mcp-requests"), viewer.admin ? api("/api/mcp-scan") : Promise.resolve(null),
    tab === "new" ? api("/api/mcp-catalog/search") : Promise.resolve(null)]);
  scanJobs = audit?.jobs || [];
  // Colours are read when the chart is drawn, so a theme switch redraws them in the new palette.
  const byStatus = () => Object.entries(INTAKE_STATUS).map(([k, [tone, label]]) => ({ name: label, value: requests.filter((r) => r.status === k).length,
    color: charts.color({ allow: "Allow", block: "Block", alert: "Alert", approval: "Approval", restrict: "Restrict" }[tone]) }));
  return {
    html: page({
      head: head("도입 신청", { actions: html`<button class="btn" data-act="reload">새로고침</button>` }),
      active: tab || "list",
      tabs: [
        { key: "list", label: viewer.admin ? "전체 신청" : "내 신청", n: requests.length, body: html`<div class="stack">
          ${panel("상태", requests.length ? chartBox("c-intake", "도입 신청의 상태별 건수", "sm") : empty("신청 없음"))}
          ${panel("신청", html`<table class="data"><thead><tr><th>서버</th><th>상태</th><th>종료 조건</th><th>신청</th>${viewer.admin ? html`<th></th>` : ""}</tr></thead><tbody>
          ${requests.map((r) => {
            const remote = r.requested_transport !== "stdio";
            const grade = r.evidence?.exit_terms_conclusion?.grade;
            const clear = !remote || termsVerified(r.exit_terms) || grade === "T1";
            return html`<tr><td><b>${r.display_name}</b><span class="sub mono">${r.endpoint_url || r.repository_url}</span>
              <span class="sub">${r.intake_kind === "remote-endpoint" ? "공급자 호스팅 · 계약 검토" : "구현 소스 · 격리 검사"}</span>
              ${r.internal_repo_url ? html`<a class="sub" href="${r.internal_repo_url}" target="_blank" rel="noopener noreferrer">사내 저장소 열기 ↗</a>` : ""}
              ${r.registered_server_id ? html`<span class="sub">${chip("allow", "Gateway 등록")} <code>/mcp/${r.registered_server_id}/</code></span>` : ""}
              <span class="sub">${r.requested_transport}${r.risk_level ? ` · 위험 ${r.risk_level}` : ""}${r.commit_sha ? ` · ${r.commit_sha.slice(0, 12)}` : ""}</span></td>
            <td>${chip(...(INTAKE_STATUS[r.status] || ["", r.status]))}</td>
            <td class="small">${exitConclusionChip(r)}</td>
            <td class="small">${when(r.created_at)}</td>
            ${viewer.admin ? html`<td class="num nowrap">
              ${r.intake_kind === "remote-endpoint" && ["HOLD", "REMOTE_REVIEWED"].includes(r.status) ? html`<button class="btn sm primary" data-act="intake-register" data-review="true" data-id="${r.id}"
                data-name="${r.display_name}" data-repo="${r.endpoint_url}" data-principal="${r.submitted_by}">계약·사용 범위 검토</button>` : ""}
              ${r.intake_kind !== "remote-endpoint" && ["HOLD", "FAILED"].includes(r.status) ? html`<button class="btn sm primary" data-act="intake-queue" data-id="${r.id}">${r.status === "FAILED" ? "재검증" : "검증 시작"}</button>` : ""}
              ${["VALIDATED", "REMOTE_REVIEWED"].includes(r.status) ? (clear ? html`<button class="btn sm primary" data-act="intake-approve" data-id="${r.id}">승인</button>`
                : html`<button class="btn sm primary" data-act="intake-approve-risk" data-id="${r.id}" data-name="${r.display_name}"
                  data-summary="${r.evidence?.exit_terms_conclusion?.summary || "종료 조건 결론이 아직 없어요"}">위험 수용 후 승인</button>`) : ""}
              ${r.status === "APPROVED" && !r.registered_server_id ? html`<button class="btn sm primary" data-act="intake-register" data-id="${r.id}"
                data-name="${r.display_name}" data-repo="${r.endpoint_url || r.repository_url}" data-kind="${r.intake_kind}">Gateway 활성화</button>` : ""}
              <button class="btn sm" data-act="intake-report" data-id="${r.id}">보고서</button>
              ${["HOLD", "VALIDATION_QUEUED", "VALIDATED", "REMOTE_REVIEWED", "FAILED"].includes(r.status) ? html`<button class="btn sm danger" data-act="intake-reject" data-id="${r.id}">거부</button>` : ""}</td>` : ""}</tr>`;
          })}</tbody></table>${requests.length ? "" : empty("신청 없음")}`, { flush: true })}</div>` },
        { key: "new", label: "새 신청", body: html`<div class="stack">
          ${panel("기존 신청 검색", html`<div class="filters"><input class="grow" type="search" data-catalog-search
            aria-label="MCP 이름 또는 GitHub 저장소 검색" placeholder="MCP 이름 또는 GitHub 저장소" /></div>
            <div id="catalog-results" aria-live="polite">${catalogResults(catalog || { requests: [], registry: [] })}</div>`, { flush: true })}
          ${panel("새 신청", html`<form class="stack form" data-form="intake">
          <label>이름<input name="display_name" required minlength="2" maxlength="80" placeholder="Slack MCP" /></label>
          <label>도입 대상<select name="intake_kind"><option value="remote-endpoint">공급자 호스팅 MCP · 엔드포인트 계약 검토</option><option value="repository">구현 소스 · 격리 공급망 검사</option></select></label>
          <label>MCP 엔드포인트<input name="endpoint_url" type="url" maxlength="500" placeholder="https://…/mcp" /></label>
          <label>구현 GitHub 저장소<input name="repository_url" type="url" maxlength="300" placeholder="소스 도입 시 필수 · https://github.com/org/repo" /></label>
          <label>연결 방식<select name="requested_transport"><option value="streamable-http">Streamable HTTP</option>
            <option value="stdio">stdio</option><option value="sse">SSE</option></select></label>
          <label>도입 목적<textarea name="purpose" required minlength="10" maxlength="1000"></textarea></label>
          <div class="row-actions"><button class="btn primary" type="submit">신청</button></div></form>`)}</div>` },
        ...(audit ? [{ key: "audit", label: "A.I.G 검사", n: audit.jobs.length, hot: audit.jobs.some((j) => j.trigger === "anomaly" && j.status !== "DONE"), body: html`<div class="stack">
          ${panel("검사 연결", html`<div class="row-actions">
            ${chip(audit.config.configured ? "allow" : "alert", audit.config.configured ? `모델 ${audit.config.model}${audit.config.local ? " · 로컬" : " · 외부"}` : "모델 미설정")}
            ${chip(audit.worker.alive ? "allow" : "block", audit.worker.alive ? "워커 동작" : "워커 중지")}
            ${chip(audit.config.auto_on_anomaly ? "allow" : "outline", `이상행위 → 자동 ${audit.config.auto_on_anomaly ? "켜짐" : "꺼짐"}`)}
            ${chip(audit.config.auto_on_validated ? "allow" : "outline", `검증 완료 → 자동 ${audit.config.auto_on_validated ? "켜짐" : "꺼짐"}`)}
            ${chip(audit.worker.queued ? "approval" : "outline", `대기 ${audit.worker.queued}`)}${chip(audit.worker.running ? "restrict" : "outline", `실행 ${audit.worker.running}`)}
            ${audit.config.configured ? html`<button class="btn sm" type="button" data-act="scan-connection">연결 확인</button>` : ""}</div>
            ${audit.config.missing.length ? html`<p class="note warn">필요한 설정: ${audit.config.missing.join(", ")}</p>` : ""}`)}
          ${audit.jobs.length ? panel("시작 원인별 작업", chartBox("c-scan-triggers", "시작 원인별 A.I.G 검사 작업 수", "sm")) : ""}
          ${panel("검사 대상", html`<table class="data"><thead><tr><th>대상</th><th>상태</th><th>최근 검사</th><th></th></tr></thead><tbody>
            ${audit.targets.map((r) => html`<tr><td>${r.display_name}<span class="sub mono">${r.commit_sha?.slice(0, 12)}</span></td><td>${r.status}</td><td>${r.last_status || "없음"}</td>
              <td><button class="btn sm" data-act="scan-run" data-kind="intake" data-id="${r.id}" ${audit.config.configured ? "" : raw("disabled")}>코드 검사</button></td></tr>`)}
            ${audit.servers.filter((s) => s.status !== "DISABLED").map((s) => html`<tr><td>${s.display_name}<span class="sub mono">${s.id}</span></td><td>${s.status}</td><td>${s.last_status || "없음"}</td>
              <td>${s.scannable ? html`<button class="btn sm" data-act="scan-run" data-kind="server" data-id="${s.id}" ${audit.config.configured ? "" : raw("disabled")}>코드 검사</button>` : chip("outline", "원격 제공")}</td></tr>`)}
            </tbody></table>${audit.targets.length || audit.servers.length ? "" : empty("검사 대상 없음")}`, { flush: true })}
          ${panel("검사 작업", html`<table class="data"><thead><tr><th>시각</th><th>대상</th><th>시작 원인</th><th>상태</th><th>결과</th><th></th></tr></thead><tbody>
            ${audit.jobs.map((j) => html`<tr><td>${when(j.created_at)}</td><td>${j.target_label}</td>
              <td>${j.trigger === "anomaly" ? html`<a href="#/activity?server=${encodeURIComponent(j.target_id)}&decision=Alert">${chip("alert", SCAN_TRIGGER.anomaly)}</a>`
                : chip("outline", SCAN_TRIGGER[j.trigger] || j.trigger)}</td>
              <td>${scanStatus(j)}</td><td>${scanResult(j)}</td>
              <td><button class="btn sm" data-act="scan-detail" data-id="${j.id}">상세</button></td></tr>`)}
            </tbody></table>${audit.jobs.length ? "" : empty("검사 이력 없음")}`, { flush: true })}
        </div>` }] : []),
      ],
    }),
    charts: { "c-intake": () => charts.columns(byStatus()),
      "c-scan-triggers": () => charts.bars(splitBy(scanJobs, (j) => SCAN_TRIGGER[j.trigger] || j.trigger).map((g) => ({
        name: g.key, value: g.total, color: g.key === SCAN_TRIGGER.anomaly ? charts.color("Alert") : undefined }))) },
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
const SCAN_TRIGGER = { manual: "수동", validated: "검증 완료", rescan: "정기 재감사", drift: "계약 변경", termination: "종료", anomaly: "이상행위" };
const SEVERITY = { CRITICAL: ["block", "치명"], HIGH: ["block", "높음"], MEDIUM: ["alert", "중간"], LOW: ["outline", "낮음"] };
function scanStatus(j) {
  if (j.status === "RUNNING") return chip("restrict", `실행 중 · ${ago(j.started_at || j.created_at).replace(" 전", "")}`);
  return chip(...({ QUEUED: ["approval", "대기"], DONE: ["allow", "완료"], FAILED: ["block", "실패"], CANCELLED: ["outline", "취소"] }[j.status] || ["", j.status]));
}
function scanResult(j) {
  if (j.status === "FAILED" || j.status === "CANCELLED") return html`<span class="small clip">${short(j.error || "—", 80)}</span>`;
  if (j.status !== "DONE") return "—";
  const levels = Object.entries(j.summary?.levels || {}).filter(([, n]) => Number(n) > 0);
  // A small local model misses findings; its zero is not evidence of safety (D-47).
  return levels.length ? html`${levels.map(([level, n]) => chip(SEVERITY[level]?.[0] || "outline", `${SEVERITY[level]?.[1] || level} ${n}`))}`
    : j.summary?.endpoint_kind === "local-model" ? chip("outline", "발견 0 · 로컬 소형 모델") : chip("allow", "발견 0");
}

// The same rule agent_service.approve_mcp_request enforces; the button only mirrors it.
const termsVerified = (t) => Boolean(t?.verified_by && t?.evidence_url && Object.keys(EXIT_TERMS).every((k) => t[k] === true));

// Evidence lines are raw README text; markdown and HTML markup only get in the way of reading them.
const plainLine = (s) => String(s || "").replace(/<[^>]*>/g, " ").replace(/[*_`#|>]+/g, " ").replace(/\s+/g, " ").trim();
const evidenceLink = (url, label) => /^https:\/\/github\.com\//.test(String(url || ""))
  ? html`<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>` : html`${label}`;

// ── exit terms: the platform's conclusion first (D-50) ─────────────────────────
const VERDICT = { met: ["allow", "충족"], unmet: ["block", "미충족"], unclear: ["alert", "불명확"] };
const EXIT_TERM_CRITERION = { provider_credential_disclosure: "C1", revocation_evidence: "C2", audit_access_retained: "C4" };
function exitConclusionChip(r) {
  const c = r.evidence?.exit_terms_conclusion;
  if (r.requested_transport === "stdio") return chip("outline", "해당 없음");
  if (r.exit_terms?.verified_by) return chip(termsVerified(r.exit_terms) ? "allow" : "block", termsVerified(r.exit_terms) ? "증거 확인" : "증거 미충족");
  if (r.exit_terms?.risk_accepted_by) return chip("alert", `위험 수용 · ${r.exit_terms.conclusion_grade || "결론 없음"}`);
  if (!c) return chip("outline", ["VALIDATION_QUEUED", "VALIDATING"].includes(r.status) ? "조사 중" : "결론 없음");
  return chip({ T1: "allow", T2: "alert", T3: "block" }[c.grade] || "outline", c.grade === "T1" ? "T1 가능" : `${c.grade} 예상`);
}
function exitTermsView(id, r, investigation, c) {
  const open = ["HOLD", "VALIDATION_QUEUED", "VALIDATING", "VALIDATED"].includes(r.status);
  return html`<div class="stack">
    ${c ? html`<div class="verdict ${c.grade || "na"}"><b>${c.grade || "해당 없음"}</b><span>${c.summary}</span></div>
      <table class="data"><thead><tr><th>조건</th><th>판정</th><th>근거</th></tr></thead><tbody>
      ${Object.keys(EXIT_TERM_CRITERION).filter((key) => c.terms[key]).map((key) => [key, c.terms[key]]).map(([key, t]) => html`<tr>
        <td class="nowrap"><b>${EXIT_TERM_CRITERION[key]}</b> ${EXIT_TERMS[key]}</td>
        <td>${chip(...(VERDICT[t.verdict] || ["", t.verdict]))}${t.probability !== null && t.probability !== undefined ? html`<span class="sub">${Math.round(t.probability * 100)}%</span>` : ""}</td>
        <td class="small">${t.evidence.length ? t.evidence.map((e) => html`<div>${evidenceLink(e.url, `${e.path}:${e.line}`)}<span class="sub">${short(plainLine(e.excerpt), 140)}</span></div>`) : html`<span class="muted">문서에 해당 문장 없음</span>`}</td></tr>`)}
      </tbody></table>
      <p class="small muted">${c.method === "jev" ? `Jev(${c.model}) 판정 · 근거 문장이 있어야 충족` : "규칙 판정 · 대상과 행위가 한 문장에 있어야 충족"}${c.error ? ` · Jev 오류로 규칙 판정: ${c.error}` : ""} · 문서 ${investigation.scanned_files}개</p>`
      : html`<p class="note warn">결론이 없는 예전 조사입니다. 다시 검증하면 결론을 냅니다.</p>
        ${open ? html`<div class="row-actions"><button class="btn primary" data-act="intake-queue" data-id="${id}">다시 검증</button></div>` : ""}`}
    ${r.exit_terms?.verified_by ? panel("관리자 증거 기록", html`${chip(termsVerified(r.exit_terms) ? "allow" : "block", termsVerified(r.exit_terms) ? "충족" : "미충족")}
      <p>${r.exit_terms.note}</p><p class="small">${evidenceLink(r.exit_terms.evidence_url, r.exit_terms.evidence_url)}</p>`) : ""}
    ${r.exit_terms?.risk_accepted_by ? panel("위험 수용", html`<p>${r.exit_terms.risk_acceptance}</p>
      <p class="small muted">${r.exit_terms.risk_accepted_by} · ${when(r.exit_terms.risk_accepted_at)} · 결론 ${r.exit_terms.conclusion_grade || "없음"}</p>`) : ""}
    ${open && r.requested_transport !== "stdio" ? html`<details class="more"><summary>제공자 문서로 직접 확인해 기록</summary>
      <button class="btn sm" data-act="intake-terms" data-id="${id}" data-name="${r.display_name}">증거 기록</button></details>` : ""}
  </div>`;
}

async function showIntakeReport(id) {
  const report = await api(`/api/mcp-requests/${id}/report`);
  const r = report.request, evidence = r.evidence || {}, investigation = report.exit_terms_discovery;
  lastDocument = report;
  if (r.intake_kind === "remote-endpoint") {
    const review = evidence.remote_contract, approval = evidence.remote_approval;
    openDrawer(`원격 서비스 검토 · ${r.display_name}`, chip(...(INTAKE_STATUS[r.status] || ["", r.status])), [
      {key: "contract", label: "계약·범위", body: html`<div class="stack">
        ${panel("공급자 엔드포인트", html`<p class="mono">${r.endpoint_url}</p><p>${r.purpose}</p>
          <p class="note">공급자가 운영하는 서비스입니다. 구현 소스 검사와 SBOM 생성은 수행하지 않았습니다.</p>`)}
        ${panel("검토 기록", review ? html`<p>${review.review_note}</p><p>${review.reviewed_by} · ${when(review.reviewed_at)}</p>
          <p>사용 주체 ${review.allowed_principals.join(", ")} · ${when(review.valid_until)}까지</p>
          <p class="mono small">${review.advertised_name} ${review.version}<br />계약 ${review.registration.catalog_hash}</p>
          <pre>${JSON.stringify(review.registration.tools, null, 2)}</pre>` : empty("계약 검토 전 · 활성화되지 않음"))}
        ${panel("승인한 인자 범위", review ? html`<pre>${JSON.stringify(review.parameter_constraints || {}, null, 2)}</pre>` : empty("검토 전"))}
        ${panel("도입 승인", approval ? html`<p>${approval.actor} · ${when(approval.at)}</p><p>${approval.risk_acceptance || "제공자 종료 조건 증거 확인"}</p>
          <p class="mono small">검토 다이제스트 ${approval.review_digest}</p>` : empty("승인 전 · 활성화되지 않음"))}
      </div>`},
      {key: "definitions", label: "승인 도구 계약", body: review ? html`<pre>${JSON.stringify(review.tools, null, 2)}</pre>` : empty("검토 전")},
    ]);
    return;
  }
  const scanners = Object.entries(evidence.scanners || {});
  const findings = report.reports.flatMap((scan) => (scan.summary?.findings || []).map((f) => ({ ...f, scanner: scan.scanner })));
  const inventory = report.reports.find((scan) => scan.scanner === "Syft")?.summary || {};
  openDrawer(`검증 보고서 · ${r.display_name}`, html`<div class="row-actions">
    ${chip(...(INTAKE_STATUS[r.status] || ["", r.status]))}
    <button class="btn sm" data-act="intake-report" data-id="${id}">새로고침</button>
    <button class="btn sm" data-act="save-json" data-name="intake-${id}-report.json">보고서 JSON 저장</button>
  </div>`, [
    { key: "summary", label: "요약", body: html`<div class="stack">
      ${panel("검증 결과", html`<p>${r.review_note || "자동 검증 대기 중"}</p>
        <p class="mono small">${r.repository_url}<br />${r.commit_sha || "커밋 확인 대기"}</p>
        ${kpiStrip([["SBOM 구성요소", evidence.sbom_components ?? "—"], ["Critical", evidence.critical ?? "—", "block"],
          ["High", evidence.high ?? "—", "alert"], ["Medium", evidence.medium ?? "—"]])}
        <p class="small muted">워커 최근 신호: ${when(report.worker.seen_at)}</p>`)}
      ${panel("검사 단계", scanners.length ? html`<table class="data"><thead><tr><th>검사기</th><th>결과</th><th>오류</th></tr></thead>
        <tbody>${scanners.map(([name, s]) => html`<tr><td>${name}</td><td>${chip(s.status === "DONE" ? "allow" : "block", s.status === "DONE" ? "완료" : "실패")}</td><td>${s.error || "—"}</td></tr>`)}</tbody></table>` : empty("검사 대기"))}
      ${panel("원본 보고서", report.artifacts.length ? html`<div class="row-actions">${report.artifacts.map((a) => html`
        <button class="btn sm" data-act="intake-download" data-id="${id}" data-kind="${a.kind}" data-name="${a.filename}">${a.kind} JSON</button>`)}</div>` : empty("생성된 보고서 없음"))}
    </div>` },
    { key: "findings", label: "취약점·코드 검사", n: findings.length, body: html`
      ${report.reports.some((s) => s.summary?.truncated && s.scanner !== "Syft") ? html`<p class="note warn">검사기별 최대 200건 표시 · 전체 결과는 원본 JSON에서 확인</p>` : ""}
      ${findings.length ? html`<table class="data"><thead><tr><th>검사기·등급</th><th>발견</th><th>대상</th><th>설치 → 수정 버전</th></tr></thead>
      <tbody>${findings.map((f) => html`<tr><td>${f.scanner}<span class="sub">${f.severity}</span></td>
        <td><b>${f.id}</b><span class="sub">${f.title}</span></td><td>${f.target}<span class="sub">${f.package || ""}</span></td>
        <td>${f.installed_version || "—"} → ${f.fixed_version || "—"}</td></tr>`)}</tbody></table>`
        : empty(scanners.some(([, s]) => s.status === "FAILED") || r.status === "FAILED" ? "검사 미완료 · 실패 사유를 확인하세요" : ["VALIDATED", "APPROVED", "REJECTED"].includes(r.status) ? "검사에서 발견된 항목 없음" : "검사 대기 중")}` },
    { key: "sbom", label: "SBOM", n: inventory.components, body: html`
      ${inventory.truncated ? html`<p class="note warn">구성요소 200개 표시 · 전체 목록은 SBOM JSON에서 확인</p>` : ""}
      ${(inventory.inventory || []).length ? html`<table class="data"><thead><tr><th>이름</th><th>버전</th><th>유형</th><th>식별자·라이선스</th></tr></thead>
        <tbody>${inventory.inventory.map((c) => html`<tr><td>${c.name}</td><td>${c.version || "—"}</td><td>${c.type}</td>
          <td class="small">${c.purl || "—"}<span class="sub">${(c.licenses || []).map((l) => l.expression || l.license?.id || l.license?.name || "미상").join(", ")}</span></td></tr>`)}</tbody></table>`
        : empty(inventory.components === 0 ? "탐지된 구성요소 없음" : "SBOM 생성 대기 또는 실패")}` },
    { key: "exit", label: "종료 조건", body: investigation ? exitTermsView(id, r, investigation, evidence.exit_terms_conclusion) : empty("자동 조사 대기 또는 저장소 복제 실패") },
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
    charts: { "c-grades": () => charts.columns(grades()), "c-readiness": () => charts.columns(readiness()) },
  };
};

function relationshipCard(r) {
  const ready = r.readiness || {};
  const terms = r.exit_terms || {};
  const revoke = ready.would_revoke || {};
  return html`<article class="rel">
    <div class="line1"><b>${r.purpose}</b><span class="spacer"></span>${gradeChip(ready.best_attainable_grade, "예상 ")}</div>
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
  const [{ enforcement }, matrix, ledger, runtime] = await Promise.all([gw("enforcement"), gw("policy/matrix"), gw("policy/ledger"), api("/api/readiness")]);
  policyLedger = ledger.policies;
  const byOutcome = splitBy(ledger.policies, "outcome");
  return {
    html: page({
      head: head("정책", { status: modeChip(enforcement), actions: html`<button class="btn ${enforcement === "enforce" ? "danger" : "primary"}" data-act="enforcement"
        data-mode="${enforcement === "enforce" ? "monitor" : "enforce"}">${enforcement === "enforce" ? "관찰 모드로 전환" : "집행 모드로 전환"}</button>` }),
      active: tab || "capabilities",
      tabs: [
        { key: "runtime", label: "배포 확인", body: panel("실행 중인 빌드와 정책", kv([
          ["Console 빌드", runtime.build?.console?.revision || "미확인"],
          ["Gateway 빌드", runtime.build?.gateway?.revision || "미확인"],
          ["서비스 코드 일치", runtime.build?.consistent ? "일치" : "불일치 · 서비스 재배포 필요"],
          ["OPA 규칙 일치", runtime.policy?.rules_match ? "일치" : "불일치 · OPA 갱신 필요"],
          ["OPA 데이터 일치", runtime.policy?.data_match ? "일치" : "불일치 · 권한 번들·관리대장·예외 갱신 필요"],
          ["공통 앱 SHA-256", runtime.build?.gateway?.code_sha256 || "미확인"],
          ["PC 설치 키트 SHA-256", runtime.build?.console?.pc_kit_sha256 || "미설치"],
          ["적재된 정책 SHA-256", runtime.policy?.loaded_sha256 || "미확인"],
          ["적재된 데이터 SHA-256", runtime.policy?.loaded_data_sha256 || "미확인"],
        ])) },
        { key: "capabilities", label: "승인 실행 범위", n: matrix.capabilities.length + matrix.runtime_envelopes.length, body: html`<div class="stack">
          ${panel("PAC-15 · 사용자·서버·기능·자원", html`<table class="data"><thead><tr><th>승인</th><th>사용자</th><th>서버</th><th>행위·자원</th><th>만료</th></tr></thead><tbody>
          ${matrix.capabilities.map((g) => html`<tr><td><code>${g.id}</code></td><td>${g.principals.join(", ")}</td><td>${g.servers.join(", ")}</td>
            <td>${g.actions.join(", ")}<span class="sub">${g.path_roots.join(", ")}</span></td><td>${when(g.valid_until)}</td></tr>`)}
          ${matrix.runtime_envelopes.map((g) => html`<tr><td><code>${g.server_id}</code></td><td>${g.principals.join(", ")}</td><td>${Object.keys(g.tools).join(", ")}</td><td>독립 도입 승인</td><td>${when(g.valid_until)}</td></tr>`)}
          </tbody></table>`, { flush: true, sub: `${matrix.bundle_id || "—"} · ${matrix.pack_version}` })}</div>` },
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
  async "account-invite"() {
    const result = await ask({ title: "일반 사용자 초대", confirm: "초대 만들기", fields: html`
      ${field.area("usernames", "아이디 · 쉼표 또는 줄바꿈으로 구분", "required maxlength=1700")}
      ${field.text("department", "부서", "required minlength=2 maxlength=80")}` });
    if (!result) return;
    const usernames = String(result.get("usernames")).split(/[,\s]+/).filter(Boolean);
    const issued = await api("/api/account-invitations", { method: "POST", body: { usernames, department: result.get("department") } });
    openDrawer("조직 초대 · 48시간 · 1회용", html`<p class="note">지정한 일반 사용자만 가입합니다. 링크는 다시 조회할 수 없습니다.</p>
      ${issued.invitations.map((item) => html`<section class="panel"><div class="body"><b>${item.username}</b><p><a href="${item.url}" target="_blank" rel="noopener noreferrer">${item.url}</a></p><span class="sub">${when(item.expires_at)}까지</span></div></section>`)}`);
  },
  sidebar(el) {
    const closed = document.documentElement.classList.toggle("nav-collapsed");
    el.setAttribute("aria-expanded", String(!closed));
    el.setAttribute("aria-label", closed ? "메뉴 펼치기" : "메뉴 접기");
    localStorage.setItem("mcp-console-nav-collapsed", String(closed));
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
    const plane = (name, applies, body) => html`<tr><th>${name}</th><td>${applies ? body : chip("outline", "해당 없음")}</td></tr>`;
    openDrawer(i.name, html`<div class="row-actions">${statusPair(i)}${chip("outline", INTEGRATION_CLASS[i.class] || i.class)}
      ${i.class === "vendor_native_connector" ? html`<button class="btn sm" type="button" data-act="vendor-control" data-key="${i.item_key}" data-name="${i.name}">벤더 콘솔 확인 기록</button>` : ""}</div>`, [
      { key: "planes", label: "평면", body: html`<table class="data"><tbody>
        ${plane("Gateway", i.managed_by === "gateway", html`${chip(i.state === "bypass_possible" ? "block" : "allow", i.state === "bypass_possible" ? "Gateway 경로만 강제" : "Gateway 강제")}<span class="sub">${i.evidence}</span>`)}
        ${plane("Endpoint", i.managed_by === "endpoint" || i.evidence_kind === "kernel", html`${controlChip(i.state)}<span class="sub">${i.evidence}</span>`)}
        ${plane("Vendor", i.class === "vendor_native_connector" || (i.residual || []).length > 0, v
          ? html`${chip("restrict", v.console_state)}<span class="sub">수기 · ${v.verified_by} · ${when(v.verified_at)} · scope ${(v.oauth_scopes || []).join(", ") || "—"} · 역할 ${v.role_access || "—"}</span>`
          : html`${chip("outline", "콘솔 기록 없음")}${(i.residual || []).map((r) => html`<span class="sub">${r}</span>`)}`)}
        </tbody></table>${kv([["우회 경로", (i.bypass || []).length ? html`${i.bypass.map((b) => chip("block", b))}` : "없음"],
          ["소유자·단말", `${(i.owners || [i.owner]).filter(Boolean).join(", ") || "—"}${i.pcs > 1 ? ` · ${i.pcs} PC` : i.device ? ` · ${i.device}` : ""}`],
          ["발견", `${i.discovered_from}${i.discovered_at ? ` · ${when(i.discovered_at)}` : ""}`], ["출처", i.source],
          ["대상", i.target ? html`<span class="mono">${i.target}</span>` : ""], ["마지막 확인", i.last_verified_at ? when(i.last_verified_at) : ""]])}` },
      { key: "approval", label: "승인", body: kv([["상태", i.approval?.state || "—"], ["만료", i.approval?.expires_at ? when(i.approval.expires_at) : ""],
        ["결정자", i.approval?.decided_by], ["검토 기한", i.approval?.review_days ? `${i.approval.review_days}일` : ""]]) },
      ...(gatewayId ? [{ key: "exit", label: "종료 잔존", body: rel ? kv([
        ["예상 등급", rel.readiness?.best_attainable_grade ? gradeChip(rel.readiness.best_attainable_grade, "예상 ") : chip("outline", "미판정")],
        ["회수 대상", Object.entries(rel.readiness?.would_revoke || {}).map(([k, n]) => `${k} ${n}`).join(" · ")],
        ["막는 요인", (rel.readiness?.blockers || []).join(" · ")]]) : empty("이용 관계 없음") }] : []),
      { key: "raw", label: "원본", body: json(i) },
    ]);
  },
  async "vendor-control"(el) {
    const fd = await ask({ title: `벤더 콘솔 확인 · ${el.dataset.name}`, confirm: "기록",
      fields: html`${field.select("console_state", "콘솔 상태", { blocked: "차단", limited: "제한 허용", allowed: "허용", unknown: "확인 불가" }, "unknown")}
        ${field.text("allowed_actions", "허용 action · 쉼표 구분", 'maxlength="600"')}
        ${field.text("oauth_scopes", "OAuth scope · 쉼표 구분", 'maxlength="600"')}
        ${field.text("role_access", "역할 접근", 'maxlength="200"')}
        ${field.text("evidence_url", "근거 주소", 'maxlength="500"')}
        ${field.area("note", "메모", 'maxlength="500"')}` });
    if (!fd) return;
    const list = (k) => fd.get(k).split(",").map((s) => s.trim()).filter(Boolean);
    await api("/api/integrations/vendor-control", { method: "PUT", body: { key: el.dataset.key, console_state: fd.get("console_state"),
      allowed_actions: list("allowed_actions"), oauth_scopes: list("oauth_scopes"), role_access: fd.get("role_access").trim(),
      evidence_url: fd.get("evidence_url").trim(), note: fd.get("note").trim() } });
    toast("기록했습니다. 수기 확인으로 표시됩니다."); closeDrawer(); reload();
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
  async "server-check"(el) {
    // A session handshake only; contract state is the catalog refresh's job (D-40).
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
      body: "로그인과 내부 Git 접근이 즉시 차단됩니다. 감사 기록은 보존됩니다.", confirm: "계정 삭제", danger: true });
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
  async "scan-run"(el) {
    const r = await api("/api/mcp-scan/run", { method: "POST", body: { target_kind: el.dataset.kind, target_id: el.dataset.id, mode: "static" } });
    toast(r.message); reload();
  },
  "scan-detail"(el) {
    const job = scanJobs.find((j) => j.id === el.dataset.id);
    if (!job) return;
    const s = job.summary || {};
    const findings = s.findings || [];
    openDrawer(`A.I.G 검사 · ${job.target_label}`, html`<div class="row-actions">${scanStatus(job)}
      ${chip(job.trigger === "anomaly" ? "alert" : "outline", SCAN_TRIGGER[job.trigger] || job.trigger)}${scanResult(job)}
      ${s.blocks_calls ? chip("block", "치명 발견 시 호출 차단") : ""}</div>`, [
      { key: "summary", label: "요약", body: kv([["대상", job.target_label], ["방식", s.mode === "dynamic" ? "동적 점검" : "정적 코드 감사"],
        ["모델", `${job.model || ""}${s.endpoint_kind ? ` · ${s.endpoint_kind}` : ""}`], ["커밋", s.commit ? html`<code>${String(s.commit).slice(0, 12)}</code>` : ""],
        ["요청", job.requested_by], ["시작", when(job.started_at)], ["완료", when(job.finished_at)], ["오류", job.error], ["메모", s.scan_note]]) },
      { key: "findings", label: "발견", n: findings.length, body: findings.length ? html`<table class="data"><thead><tr><th>심각도</th><th>항목</th><th>위치</th></tr></thead><tbody>
        ${findings.map((f) => html`<tr><td>${chip(...(SEVERITY[f.severity] || ["", f.severity]))}</td><td>${short(f.title, 160)}<span class="sub mono">${f.id} · ${f.risk_category || ""}</span></td>
          <td class="small mono">${f.target || "—"}</td></tr>`)}</tbody></table>` : empty(job.status === "DONE" ? "발견 없음" : "결과 보고서가 아직 없습니다.") },
      { key: "raw", label: "원본", body: Object.keys(s).length ? json(s) : empty("없음") },
    ]);
  },
  "pc-kit"() {
    // Claude Code·Codex CLI가 Gateway의 MCP 서버를 쓰게 하는 키트(D-42). 비밀번호는 PC에 저장되지 않는다.
    const kit = viewer.kit;
    lastDocument = kit.command;
    openDrawer("내 PC 연결", html`<div class="row-actions">${chip(kit.servers ? "allow" : "outline", kit.servers ? `서버 ${kit.servers.split(",").length}` : "운영 중인 서버 없음")}
        <button class="btn sm primary" type="button" data-act="pc-kit-download">1회용 설치 키트 받기</button>
        ${kit.command ? html`<button class="btn sm primary" type="button" data-act="copy-doc">명령 복사</button>` : ""}</div>
      ${kit.command ? html`<pre class="json">${kit.command}</pre>` : ""}
      <p class="note">Linux 일반 사용자용입니다. 조직 관리자가 설치하고 실제 OS 통제를 확인한 뒤 단말을 활성화합니다. 설치 토큰은 30분·1회용입니다.</p>
      ${kv([["연결 조건", "단말 활성화 · 최근 정책 heartbeat · 보호된 하네스 설정"], ["해제", "조직 관리자가 단말 자격을 폐기합니다."]])}`);
  },
  async "pc-kit-download"() {
    const response = await fetch("/api/pc-kit", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    if (!response.ok) {
      const r = await response.json();
      throw new Error(detailText(r.detail) || "설치 키트를 받을 수 없습니다.");
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a"); link.href = url; link.download = "mcp-managed-kit.zip";
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 30000);
    toast("1회용 설치 키트를 받았습니다. 조직 관리자에게 설치를 요청하세요.");
  },
  async "device-activate"(el) {
    const fd = await ask({ title: `관리형 단말 활성화 · ${el.dataset.id}`,
      fields: field.area("note", "실제 호스트의 일반 계정·root 관리 설정·AppArmor·방화벽 확인 근거", 'required minlength="20" maxlength="1000"'), confirm: "확인 후 활성화" });
    if (!fd) return;
    await gw(`endpoint/devices/${encodeURIComponent(el.dataset.id)}/activate`, { method: "POST", body: { policy_hash: el.dataset.hash, note: fd.get("note") } });
    toast("관리형 단말을 활성화했습니다."); reload();
  },
  async "scan-connection"() {
    const r = await api("/api/mcp-scan/connection-test", { method: "POST" });
    toast(r.message, !r.ready_for_scan);
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
          <label class="check"><input type="checkbox" name="scopes" value="enforcement" /> root 관리 OS 차단 수집</label>
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
  async "intake-approve-risk"(el) {
    // Below T1 the admin does not re-read the provider's docs: the conclusion is stated, the
    // admin accepts the risk in writing (the same rule that closes a T3 termination case).
    const fd = await ask({ title: `위험 수용 후 승인 · ${el.dataset.name}`, body: el.dataset.summary,
      fields: field.area("risk_acceptance", "수용 사유",
        'required minlength="10" maxlength="1000" placeholder="예: 공개 문서 검색 전용이라 사내 데이터가 나가지 않아요"'), confirm: "승인" });
    if (!fd) return;
    const r = await api(`/api/mcp-requests/${el.dataset.id}/approve`, { method: "POST", body: { risk_acceptance: fd.get("risk_acceptance").trim() } });
    toast(r.message); reload();
  },
  async "intake-register"(el) {
    if (el.dataset.kind === "remote-endpoint" && !el.dataset.review) {
      const report = await api(`/api/mcp-requests/${el.dataset.id}/report`);
      const approved = report.request.evidence.remote_contract;
      const confirm = await ask({ title: `승인한 계약 활성화 · ${el.dataset.name}`,
        body: html`<p class="mono">${approved.registration.endpoint}</p><p>도구 ${Object.keys(approved.registration.tools).length}개 · ${when(approved.valid_until)}까지</p><p class="small">승인한 주소·도구·사용 범위 그대로 활성화합니다.</p>`, confirm: "활성화" });
      if (!confirm) return;
      const result = await api(`/api/mcp-requests/${el.dataset.id}/register`, {method: "POST", body: approved.registration});
      toast(result.message); reload(); return;
    }
    // D-49: 승인은 "들여도 된다", 등록은 "이 엔드포인트의 이 도구를 이 등급·기한으로 쓴다".
    const first = await ask({ title: `Gateway 등록 · ${el.dataset.name}`,
      fields: field.text("endpoint", "MCP 엔드포인트", `type="url" required pattern="https?://.+" maxlength="500" placeholder="https://…/mcp" ${el.dataset.review ? "readonly" : ""}`, el.dataset.review ? el.dataset.repo : null),
      confirm: "도구 불러오기" });
    if (!first) return;
    const found = await gw("registry/discover", { method: "POST", body: { endpoint: first.get("endpoint").trim() } });
    const suggested = el.dataset.repo.split("/").slice(-2).join("-").toLowerCase()
      .replace(/[^a-z0-9]+/g, "-").replace(/^[^a-z]+|-+$/g, "").slice(0, 31) || "mcp";
    const fd = await ask({ title: `도구 승인 · ${found.server_name || el.dataset.name} ${found.version}`,
      fields: html`${field.text("server_id", "서버 id", `required pattern="[a-z][a-z0-9\\-]{1,30}" maxlength="31" value="${suggested}"`)}
        <p class="mono small">${found.endpoint}<br />계약 SHA-256 ${found.catalog_hash}</p>
        <div class="grid c2">${field.select("data_class", "데이터 등급", DATA_CLASS, "nonimportant")}${field.select("valid_days", "사용 기한", VALIDITY, "90")}</div>
        ${el.dataset.review ? html`${field.text("allowed_principals", "허용할 사용자 id (쉼표 구분)", "required", el.dataset.principal)}${field.area("review_note", "계약·자격·데이터 범위 검토 내용", 'required minlength="10" maxlength="1000"')}` : ""}
        ${el.dataset.review ? html`<p class="note">선택할 도구마다 인자 범위를 검토하세요. 저장소·프로젝트·경로에는 const 또는 enum으로 실제 승인 대상을 지정하세요.</p>
          ${field.area("parameter_constraints", "도구별 승인 인자 범위 (JSON Schema)", 'required maxlength="30000"', "{}")}` : ""}
        ${found.tools.some((t) => t.warnings?.length) ? html`<p class="note warn">모델을 조종하는 문구로 보이는 도구가 있어요 · 설명을 읽고 고르세요</p>` : ""}
        <fieldset class="tool-pick"><legend>도구 ${found.tools.length}</legend>${found.tools.map((t) => html`<label>
          <span><code>${t.name}</code>${(t.warnings || []).map((w) => chip("block", w))}
            <span class="sub">${t.description}</span><details><summary>입력 계약</summary><pre>${JSON.stringify(t.input_schema, null, 2)}</pre></details></span>
          <select name="tool:${t.name}" aria-label="${t.name}"><option value="">미승인</option>${Object.entries(ACTION).map(([k, l]) =>
            html`<option value="${k}">${l}</option>`)}</select></label>`)}</fieldset>
        ${found.tools.some((t) => t.warnings?.length) ? html`<label class="check"><input type="checkbox" name="poisoning_ack" /> 표시된 도구를 고른다면, 설명을 읽고 확인했어요</label>` : ""}`,
      confirm: el.dataset.review ? "검토 기록" : "등록" });
    if (!fd) return;
    const tools = Object.fromEntries(found.tools.map((t) => [t.name, fd.get(`tool:${t.name}`)]).filter(([, v]) => v));
    if (!Object.keys(tools).length) { toast("승인할 도구를 하나 이상 고르세요.", true); return; }
    let parameterConstraints;
    if (el.dataset.review) {
      try { parameterConstraints = JSON.parse(fd.get("parameter_constraints")); }
      catch { toast("승인 인자 범위에 올바른 JSON을 입력하세요.", true); return; }
    }
    const r = await api(`/api/mcp-requests/${el.dataset.id}/${el.dataset.review ? "review-contract" : "register"}`, { method: "POST", body: {
      server_id: fd.get("server_id").trim(), endpoint: found.endpoint, catalog_hash: found.catalog_hash, tools,
      data_class: fd.get("data_class"), valid_days: Number(fd.get("valid_days")), poisoning_ack: fd.get("poisoning_ack") === "on",
      ...(el.dataset.review ? {allowed_principals: fd.get("allowed_principals").split(",").map((p) => p.trim()).filter(Boolean), review_note: fd.get("review_note").trim(), parameter_constraints: parameterConstraints} : {}) } });
    toast(r.message); reload();
  },
  async "server-deregister"(el) {
    const fd = await ask({ title: `등록 해제 · ${el.dataset.id}`, body: "즉시 호출 차단 · 기록 유지", confirm: "해제", danger: true });
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
  connector(el) {
    const g = connectorGroups.find((x) => x.key === el.dataset.key);
    if (!g) return;
    openDrawer(connectorName(g), html`<div class="row-actions">${connectorState(g)}
      ${chip("outline", "차단 미검증")} ${g.violation ? chip("block", "미승인 항목 보고됨") : ""}${connectorButtons(g)}</div>
      ${kv([["하네스", g.harness === "claude" ? "Claude Code" : "Codex"], ["종류", g.kinds.map((k) => CONNECTOR_KIND[k] || k).join(" · ")],
        ["대상", html`<span class="mono">${connectorTarget(g)}</span>`], ["처음 보고", when(g.first_seen)],
        ["결정", g.decision ? html`${g.note || "—"}<span class="sub">${g.decided_by} · ${when(g.decided_at)}</span>` : ""]])}
      <h3>보고한 PC</h3>
      <table class="data"><thead><tr><th>직원</th><th>PC</th><th>상태</th><th>마지막 보고</th></tr></thead><tbody>
        ${g.holders.map((h) => html`<tr><td>${h.display_name || "—"}</td><td class="mono">${h.workstation}</td>
          <td>${h.active ? chip(["pending", "denied", "expired"].includes(g.state) ? "block" : "plain", harnessStatus(h.status)) : chip("outline", "미관측")}</td><td class="small">${ago(h.last_seen)}</td></tr>`)}
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
  document.documentElement.classList.toggle("nav-collapsed", localStorage.getItem("mcp-console-nav-collapsed") === "true");
  document.querySelector('[data-act="sidebar"]').setAttribute("aria-expanded", String(!document.documentElement.classList.contains("nav-collapsed")));
  $("#app-identity").textContent = `${viewer.name} · ${viewer.role_label}`;
  $("#who").innerHTML = String(html`<b>${viewer.name}</b>${[viewer.department, viewer.role_label].filter((x) => x && x !== "미지정").join(" · ")}`);
  // 내부 저장소(Gitea)와 PC 키트는 field 배치에서만 주소가 온다 - renderNav()의 바로가기(D-48).
  window.addEventListener("hashchange", route);
  await route();
  if (viewer.kit && viewer.managed_required && !(viewer.managed_devices || []).some((d) => d.status === "active" && d.managed_state === "active")) {
    ACTIONS["pc-kit"]();
  }
  if (viewer.admin) { refreshBadges(); setInterval(refreshBadges, 30000); }
}
boot().catch((error) => { $("#view").innerHTML = String(html`<div class="note bad">${error.message}</div>`); });
