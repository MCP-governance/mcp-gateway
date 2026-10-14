/* Console presentation kit: safe HTML, vocabulary, chips, icons and page layout.
 *
 * Everything here turns data into markup and has no access to the API or the session, so the
 * look of the console can change without touching how it loads data or routes.
 */
import { statusView, pipelineOf, harnessLabel } from "./console-state.mjs";
// ── safe HTML ────────────────────────────────────────────────────────────────
// Everything interpolated into html`` is escaped unless it is itself html`` or raw().
// Audit rows carry tool arguments an attacker controls (a prompt-injected agent
// writes them), so there is no other way to put data on this page.
export class Raw { constructor(s) { this.s = s; } toString() { return this.s; } }
export const raw = (s) => new Raw(String(s));
export const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ESC[c]);
export const part = (v) => (v instanceof Raw ? v.s : Array.isArray(v) ? v.map(part).join("")
  : v === null || v === undefined || v === false ? "" : esc(v));
export function html(strings, ...values) {
  let out = strings[0];
  values.forEach((value, i) => { out += part(value) + strings[i + 1]; });
  return new Raw(out);
}
export const short = (text, n = 120) => { const s = String(text ?? ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; };

export const entityRef = (value, n = 24) => html`<span class="entity-ref mono" title="${value || ""}">${short(value || "—", n)}</span>`;
export const listToolbar = (id, placeholder) => html`<label class="list-search"><input type="search" data-list-search="${id}" placeholder="${placeholder}" aria-label="${placeholder}" maxlength="120" /><span class="result-count" data-list-count="${id}" role="status"></span></label>`;
// ── vocabulary ───────────────────────────────────────────────────────────────
export const DECISION = {
  Allow: ["allow", "허용"], Alert: ["alert", "경보"], Restrict: ["restrict", "제한 실행"],
  Approval: ["approval", "승인 대기"], Block: ["block", "차단"],
};
export const NONE = html`<span class="muted">—</span>`;
export const SERVER_STATUS = { READY: "정상", DRIFT: "계약 변경", PENDING: "확인 대기", DISABLED: "사용 중지", ERROR: "연결 오류" };
export const LIFECYCLE = { OPERATING: "운영", TERMINATING: "종료 중", RETIRED: "폐기" };
export const GRADE = { T1: "종료", T2: "부분 종료", T3: "판단 불가" };
export const CASE_STATUS = { OPEN: "진행", REVOKING: "회수 중", ASSESSED: "판정됨", CLOSED: "종결", REOPENED: "재개" };
export const TARGET_KIND = {
  "gateway-route": "게이트웨이 경로", "gateway-access": "사용자 접근", "client-token": "클라이언트 토큰",
  "refresh-token": "갱신 토큰", "dynamic-registration": "동적 클라이언트 등록", session: "MCP 세션",
  "server-held-credential": "서버 보유 자격", "endpoint-config": "엔드포인트 MCP 설정", "api-key": "API 키",
  webhook: "웹훅", "cached-artifact": "캐시 산출물",
};
export const HOLDER = { org: "조직", provider: "제공자", endpoint: "엔드포인트" };
export const DISCOVERED = {
  "gateway-ledger": "게이트웨이 기록", "endpoint-agent": "엔드포인트 보고", "provider-disclosure": "제공자 고지",
  "operator-manual": "수동 등록", "liveness-probe": "도달 확인",
};
export const VERIFICATION = {
  "gateway-probe": "게이트웨이 차단 확인", "endpoint-report": "엔드포인트 보고", "gitea-token": "조직 직접 확인",
  "provider-attestation": "제공자 증명", stateless: "만료 시각",
};
export const TARGET_STATUS = { OUTSTANDING: ["alert", "미회수"], REVOKED: ["allow", "회수됨"], EXPIRED: ["allow", "만료"], UNVERIFIABLE: ["block", "확인 불가"] };
export const ENDPOINT_CLASS = { registered: ["allow", "등록 서버"], shadow: ["block", "미등록 MCP"], "retired-residue": ["alert", "폐기 잔존"] };
// Observed is never shown as blocked.
export const CONTROL_STATE = {
  gateway_enforced: ["allow", "게이트웨이 통제"], endpoint_enforced: ["allow", "엔드포인트 통제"],
  vendor_enforced: ["restrict", "벤더 통제"], observed_only: ["alert", "관찰만"],
  unknown_not_enrolled: ["outline", "미등록"], bypass_possible: ["block", "우회 가능"],
};
export const INTEGRATION_CLASS = {
  gateway_mcp: "게이트웨이 MCP", gateway_backend_connector: "게이트웨이 경유 SaaS", vendor_native_connector: "벤더 커넥터",
  local_plugin_or_stdio: "로컬 플러그인", shadow_or_unknown: "미등록 MCP",
};
export const MANAGED_BY = { gateway: "게이트웨이", endpoint: "엔드포인트", vendor: "벤더", none: "—" };
export const APPROVAL_STATE = {
  approved: "승인", pending: "미승인", unapproved: "미승인", expired: "기한 만료", denied: "거부", default: "재검토",
  drift: "계약 변경", disabled: "사용 중지", error: "연결 오류", blocked_supply_chain: "공급망 차단",
};
export const PLATFORM = { linux: "Linux", windows: "Windows", wsl: "WSL", macos: "macOS", other: "기타", unknown: "기타" };
export const RESPONSE = {
  returned: ["allow", "응답 반환"], masked: ["restrict", "마스킹 반환"], withheld: ["block", "응답 보류"],
  unknown: ["alert", "결과 미확인"], not_executed: ["outline", "실행 안 함"],
};
export const controlChip = (s) => chip(...(CONTROL_STATE[s] || ["", s]));
export const TONE_DECISION = { allow: "Allow", restrict: "Restrict", alert: "Alert", approval: "Approval", block: "Block", outline: "" };
export const responseChip = (s) => chip(...(RESPONSE[s] || ["", s]));
export const stateLabel = (s) => (CONTROL_STATE[s] || [, s])[1];
export const approvalLabel = (s) => (s ? APPROVAL_STATE[String(s).toLowerCase()] || s : "—");

export function statusPair(item) {
  const v = statusView(item);
  return html`<span class="pair">${chip(v.tone, stateLabel(v.state))}<span class="ev ${v.stale ? "stale" : ""}">${v.evLabel}</span></span>`;
}
export function flow3(r) {
  if (r.decision === "Approval" && !r.attempted) return chip("approval", "승인 대기");
  const label = r.executed ? "실행됨" : r.attempted ? "실행 미확인" : "실행 안 함";
  return html`<span class="flow3">${label}</span>${r.executed || r.attempted ? responseChip(r.response) : ""}`;
}
export const UPSTREAM = { executed: ["allow", "실행됨"], unknown: ["alert", "실행 미확인"], not_sent: ["outline", "실행 안 함"] };
/** The five stops of one call. */
export function pipeline(r, device) {
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
export const ACTION = { r: "읽기", w: "쓰기", x: "외부 전송·실행" };
export const DATA_CLASS = { public: "공개", nonimportant: "내부", important: "중요" };
export const ROLE = { admin: "관리자", employee: "직원", partner: "협력사" };
export const PLATFORM_KIT = { linux: "Linux 설치 파일", windows: "Windows 설치 파일" };
export const EXIT_TERMS = {
  provider_credential_disclosure: "보유 자격 고지",
  revocation_evidence: "폐기 기록 제출",
  audit_access_retained: "종료 후 감사 접근",
};
export const CRITERIA = { C1: "모집단", C2: "수행 권한", C3: "연속성", C4: "증거 접근" };
export const APPROVAL_STATUS = {
  APPROVED: ["allow", "승인"], EXECUTED: ["allow", "실행됨"], REJECTED: ["block", "거부"], EXPIRED: ["outline", "만료"],
  NOT_EXECUTED: ["alert", "실행 안 됨"], UNCONFIRMED: ["alert", "실행 미확인"],
};
export const INTAKE_STATUS = {
  HOLD: ["outline", "검토 대기"], REMOTE_REVIEWED: ["approval", "계약 검토 완료"], VALIDATION_QUEUED: ["approval", "검증 대기"], VALIDATING: ["approval", "검증 중"],
  VALIDATED: ["restrict", "검증 완료"], APPROVED: ["allow", "승인"], REJECTED: ["block", "거부"], FAILED: ["alert", "검증 실패"],
};

export const chip = (tone, label) => html`<span class="chip ${tone}">${label}</span>`;
export const decisionChip = (d) => chip(...(DECISION[d] || ["", d]));
export const gradeChip = (g, prefix = "") => (g ? chip(g, `${prefix}${g} ${GRADE[g]}`) : chip("outline", "미판정"));
export const REL_STATUS = { ACTIVE: ["outline", "이용 중"], TERMINATED: ["block", "종료"], TERMINATING: ["alert", "종료 중"], SUSPENDED: ["alert", "중지"] };
export const bool = (v, label) => (v ? chip("allow", label) : chip("block", label));
export const pad = (n) => String(n).padStart(2, "0");
export function when(value, { seconds = false } = {}) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}${seconds ? `:${pad(d.getSeconds())}` : ""}`;
  return d.toDateString() === new Date().toDateString() ? hm : `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`;
}
export function ago(value) {
  if (!value) return "—";
  const s = Math.round((Date.now() - new Date(value).getTime()) / 1000);
  if (s < 60) return "방금";
  if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
  return `${Math.floor(s / 86400)}일 전`;
}
export const json = (v) => html`<pre class="json">${JSON.stringify(v, null, 2)}</pre>`;
export const kv = (pairs) => html`<dl class="kv">${pairs.filter(([, v]) => v !== undefined && v !== null && v !== "")
  .map(([k, v]) => html`<dt>${k}</dt><dd>${v}</dd>`)}</dl>`;
export const empty = (text) => html`<p class="empty">${text}</p>`;
export const OUTCOME_TONE = [["차단", "Block"], ["승인", "Approval"], ["경보", "Alert"], ["제한", "Restrict"], ["허용", "Allow"]];
export const outcomeDecision = (text) => (OUTCOME_TONE.find(([word]) => String(text || "").includes(word)) || [])[1];

// ── icons (Lucide, ISC licence) ──────────────────────────────────────────────
export const ICON = {
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
export const icon = (name) => raw(`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[name] || ""}</svg>`);
// ── tabs ─────────────────────────────────────────────────────────────────────
// WAI-ARIA tabs: one tab stop, arrows move between tabs. Panels stay in the DOM;
// charts in a hidden panel are drawn when it is first shown (they need a size).
export function tabBar(tabs, active, scope = "p") {
  return html`<div class="tabs" role="tablist">${tabs.map((t) => html`<button class="tab" role="tab" type="button"
    id="${scope}-tab-${t.key}" aria-controls="${scope}-panel-${t.key}" aria-selected="${String(t.key === active)}"
    tabindex="${t.key === active ? 0 : -1}" data-act="tab" data-tab="${t.key}">${t.label}${t.n !== undefined && t.n !== null
      ? html`<span class="n ${t.hot ? "hot" : ""}">${t.n}</span>` : ""}</button>`)}</div>`;
}
export function tabPanel(key, active, body, scope = "p") {
  return html`<section class="tabpanel" role="tabpanel" id="${scope}-panel-${key}" aria-labelledby="${scope}-tab-${key}"
    data-panel="${key}" ${key === active ? "" : raw("hidden")}>${body}</section>`;
}
/** A page: head, optional KPI strip, tab bar and panels. `tabs`: [{key, label, n, hot, body}] */
export function page({ head, kpis = "", tabs, active }) {
  const current = tabs.some((t) => t.key === active) ? active : tabs[0].key;
  return html`${head}${kpis}${tabBar(tabs, current)}${tabs.map((t) => tabPanel(t.key, current, t.body))}`;
}
export const head = (title, { status = "", actions = "", back = "" } = {}) => html`<div class="page-head">
  ${back}<div class="heading"><h1>${title}</h1>${status ? html`<div class="status">${status}</div>` : ""}</div>
  ${actions ? html`<div class="actions">${actions}</div>` : ""}</div>`;
// A zero is not news: it stays in ink colour, and only a count that needs attention takes the decision colour.
export const kpiStrip = (items) => html`<div class="kpis kpis-${items.length}">${items.map(([label, value, tone = "", href = ""]) => [label, value,
  value === 0 || value === "0" ? "" : tone, href]).map(([label, value, tone, href]) => href
  ? html`<a class="kpi ${tone}" href="${href}"><div class="label">${label}</div><div class="value">${value ?? 0}</div></a>`
  : html`<div class="kpi ${tone}"><div class="label">${label}</div><div class="value">${value ?? 0}</div></div>`)}</div>`;
export const panel = (title, body, { sub = "", tools = "", flush = false, end = "" } = {}) => html`<section class="panel">
  <header><h2>${title}</h2>${sub ? html`<span class="sub">${sub}</span>` : ""}${end ? html`<div class="tools-end">${end}</div>` : ""}</header>
  ${tools ? html`<div class="tools">${tools}</div>` : ""}
  <div class="body ${flush ? "flush" : ""}">${body}</div></section>`;
export const chartBox = (id, label, size = "") => html`<div class="chart ${size}" id="${id}" role="img" aria-label="${label}"></div>`;
