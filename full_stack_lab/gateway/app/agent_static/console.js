/* MINT console.
 *
 * The console never calls an MCP tool. Harnesses call tools through the gateway; this
 * screen reads what happened and runs the procedures around it. Every request carries
 * the signed-in user's token and the server decides what that user may see, so hiding
 * a menu here is convenience only.
 */
import { lang, locale, t, clockText, dateTimeText } from "./i18n.mjs";
import { mergeRows, hourBuckets, sankeyData, harnessLabel, DECISIONS,
  statusView, dedupeItems, connectorControl, pipelineOf, resourceValues, observationRows, listenerCoverage,
  msText, pctText, LATENCY_STAGE, timingRows, privacyText,
  originLabel, denialClass, provenanceView, countView, pager, denialCount } from "./console-state.mjs";
import * as charts from "./charts.mjs";

const { DECISION_LABEL } = charts;
const TOKEN_KEY = "mcp-console-token";
const THEME_KEY = "mcp-console-theme";
const NAV_KEY = "mcp-console-nav-v4";
const ADMIN_IDLE_MS = 30 * 60 * 1000;
const ADMIN_MAX_MS = 8 * 60 * 60 * 1000;
const SESSION_WARNING_MS = 2 * 60 * 1000;
const token = localStorage.getItem(TOKEN_KEY);
if (!token) location.replace("/login");

function tokenTimes(value) {
  try {
    const encoded = value.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(encoded.padEnd(Math.ceil(encoded.length / 4) * 4, "=")));
    return { issuedAt: Number(payload.iat) * 1000, expiresAt: Number(payload.exp) * 1000,
      identityBinding: payload.identity_binding || "" };
  } catch { return { issuedAt: 0, expiresAt: 0 }; }
}

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

async function api(path, { method = "GET", body, signal } = {}) {
  const response = await fetch(path, {
    method,
    headers: { authorization: `Bearer ${token}`, ...(body === undefined ? {} : { "content-type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
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
const ARTIFACT_KIND = { sbom: "SBOM", trivy: "Trivy", semgrep: "Semgrep", gitleaks: "Gitleaks", "exit-terms": "종료 조건" };
const NONE = html`<span class="muted">—</span>`;
const SERVER_STATUS = { READY: "정상", DRIFT: "계약 변경", PENDING: "확인 대기", DISABLED: "사용 중지", ERROR: "연결 오류" };
const LIFECYCLE = { OPERATING: "운영", TERMINATING: "종료 중", RETIRED: "폐기" };
const GRADE = { T1: "종료", T2: "부분 종료", T3: "판단 불가" };
const CASE_STATUS = { OPEN: "진행", REVOKING: "회수 중", ASSESSED: "판정됨", CLOSED: "종결", REOPENED: "재개됨" };
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
  "provider-attestation": "제공자 증명", stateless: "만료 시각", "credential-store": "조직 보관소 확인",
};
const PROVIDER_SIDE = { rejected: "거부 확인", accepted: "수락함", unverified: "미확인" };
const TARGET_STATUS = { OUTSTANDING: ["alert", "미회수"], REVOKED: ["allow", "회수됨"], EXPIRED: ["allow", "만료"], UNVERIFIABLE: ["block", "확인 불가"] };
const COLLECTOR = {
  "config-file": "설정 파일", "proc-socket": "로컬 소켓", "windows-netstat": "로컬 소켓", lsof: "로컬 소켓",
  "network-probe": "네트워크 탐색", "process-table": "프로세스 표", "journal-apparmor": "운영체제 로그 · 실행",
  "journal-nft": "운영체제 로그 · 네트워크", "windows-event-log": "Windows 이벤트 로그", gateway: "게이트웨이",
};
const TRANSFORM = {
  command_sha256: "명령 해시화", url_sha256: "주소 해시화", drop_env_headers: "환경변수·헤더 제외", truncate: "길이 제한",
  path_to_basename: "파일명만 유지", journal_field_allowlist: "허용 필드만 추출", drop_raw_message: "원문 제외",
  event_xml_allowlist: "허용 필드만 추출",
};
const transformLabel = (step) => (step.startsWith("server:") ? "서버 · " : "") + (TRANSFORM[step.replace(/^server:/, "")] || step);
const RECORD_KIND = { config: "MCP 설정", listener: "수신기", "os-event": "엔드포인트 차단", decision: "게이트웨이 판정", "dispatch-intent": "전송 의도", "server-egress": "서버 외부 통신" };
const ENDPOINT_CLASS = { registered: ["allow", "등록 서버"], shadow: ["block", "미등록 MCP"], "retired-residue": ["alert", "폐기 잔존"] };
// Observed is never shown as blocked.
const CONTROL_STATE = {
  gateway_enforced: ["allow", "게이트웨이 통제"], endpoint_enforced: ["allow", "엔드포인트 통제"],
  vendor_enforced: ["brand", "벤더 통제"], observed_only: ["alert", "관찰만"],
  unknown_not_enrolled: ["outline", "엔드포인트 미등록"], bypass_possible: ["block", "조직 통제 의존"],
};
const INTEGRATION_CLASS = {
  gateway_mcp: "게이트웨이 MCP", gateway_backend_connector: "게이트웨이 연동 SaaS", vendor_native_connector: "벤더 커넥터",
  local_plugin_or_stdio: "로컬 MCP", shadow_or_unknown: "미등록 MCP",
};
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
  const label = r.executed ? "실행됨" : r.attempted ? "실행 미확인" : "실행 안 함";
  const notSent = r.event_kind === "mcp-connection" ? chip("block", "연결 거부")
    : r.decision === "Block" ? chip("block", "차단")
      : r.decision === "Approval" ? chip("approval", "승인 대기")
        : chip("outline", "전송 안 함");
  return html`<span class="flow3">${label}</span>${r.executed || r.attempted ? responseChip(r.response) : notSent}`;
}
const UPSTREAM = { executed: ["allow", "실행됨"], unknown: ["alert", "실행 미확인"], not_sent: ["outline", "실행 안 함"] };
/** The five stops of one call. */
function pipeline(r, device) {
  const [, gate, endpoint, upstream, response] = pipelineOf(r);
  const stage = (n, title, body, cls = "") => html`<li class="${cls}"><span class="step-no" aria-hidden="true">${n}</span><b>${title}</b><div class="stage-body">${body}</div></li>`;
  return html`<ol class="pipe" aria-label="호출 경로">
    ${stage(1, "요청", html`<span>${r.harness ? harnessLabel(r.harness) : r.agent || "—"}</span>
      <span class="v">엔드포인트 <code>${r.workstation || "—"}</code></span>`)}
    ${stage(2, "게이트웨이", html`${decisionChip(r.decision)}
      ${gate.state === "refused-connection" ? html`<span class="v">연결 거부</span>` : ""}`, r.decision === "Block" ? "stop" : "")}
    ${stage(3, "엔드포인트", endpoint.state === "bound" ? html`${chip("brand", "인증된 엔드포인트")}${device ? statusPair(device) : ""}`
      : chip("outline", "인증 없음"), endpoint.state === "bound" ? "" : "off")}
    ${stage(4, "도구 실행", chip(...UPSTREAM[upstream.state]), upstream.state === "not_sent" ? "off" : "")}
    ${stage(5, "응답", responseChip(response.state), response.state === "withheld" ? "stop" : "")}
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
const countryNames = new Intl.DisplayNames([locale()], { type: "region" });
const locationRows = (value = {}) => [
  ["처리 국가", (value.processing_countries || []).map((c) => countryNames.of(c)).join(", ") || "—"],
  ["저장 국가", (value.storage_countries || []).map((c) => countryNames.of(c)).join(", ") || "—"],
  ["처리 주체", value.processor || "—"], ["위치 근거", value.evidence_ref || "—"], ["이전 근거", value.transfer_basis || "—"],
];
const ROLE = { admin: "관리자", employee: "직원", partner: "협력사" };
const PLATFORM_KIT = { linux: "Linux", macos: "macOS", windows: "Windows" };
const KIT_FILE = { linux: "mcp-managed-kit-linux.zip", macos: "mcp-connect-macos.command", windows: "mcp-managed-setup-windows.cmd" };
// Windows is the main target: selected first whatever browser opened the Console.
function preferredKitPlatform() {
  return "windows";
}
// 설치 절차: 운영체제마다 실행 방법만 다르다. 명령 문자열 외에는 라벨만 둔다.
function kitSteps(os, kit = {}) {
  const run = os === "linux" ? html`<li>터미널에서 실행<code>unzip ~/Downloads/${KIT_FILE.linux} -d ~/mcp-managed-kit && ~/mcp-managed-kit/install.sh</code><span class="sub">관리자 암호 1회</span></li>`
    : os === "macos" ? html`<li>터미널에서 실행<code>/bin/bash "$HOME/Downloads/${KIT_FILE.macos}"</code><span class="sub">관리자 암호 1회 · 연결 파일 유효 시간 5분</span></li>`
    : html`<li>받은 .cmd 파일 실행<span class="sub">관리자 권한 확인 1회 · 지금 계정 그대로</span></li>`;
  const ready = kit.auto_activate === false ? "관리자 활성화 뒤 사용" : "설치가 끝나면 바로 사용";
  return html`<ol class="kit-steps"><li>설치 파일 받기</li>${run}<li>${ready}</li></ol>
    ${os === "linux" ? kv([["제거", html`<code>sudo ~/mcp-managed-kit/install.sh --remove</code>`]]) : ""}`;
}
function kitView(kit, os) {
  const platforms = [...(kit.platforms || [])].sort((a, b) => Number(b === preferredKitPlatform()) - Number(a === preferredKitPlatform()));
  return html`<div class="row-actions">${chip(kit.servers ? "allow" : "outline", kit.servers ? `MCP 서버 ${kit.servers.split(",").length}개` : "사용 가능한 서버 없음")}</div>
    <div class="row-actions" role="group">${platforms.map((name) => html`<button class="btn sm ${name === os ? "primary" : ""}" type="button" aria-pressed="${String(name === os)}" data-act="pc-kit-os" data-os="${name}">${PLATFORM_KIT[name] || "—"}</button>`)}</div>
    ${platforms.includes(os) ? html`${kitSteps(os, kit)}${os === "macos" ? "" : html`<label class="check"><input type="checkbox" name="kit-isolated"> 고급: 격리 계정<span class="sub">관리자 활성화</span></label>`}
      <div class="row-actions"><button class="btn primary" type="button" data-act="pc-kit-download" data-os="${os}">설치 파일 받기</button></div>` : ""}`;
}
const EXIT_TERMS = {
  provider_credential_disclosure: "보유 자격 고지",
  revocation_evidence: "폐기 기록 제출",
  audit_access_retained: "종료 후 감사 접근",
};
const CRITERIA = { C1: "모집단", C2: "수행 권한", C3: "연속성", C4: "증거 접근" };
const APPROVAL_STATUS = {
  REVOKED: ["block", "승인 번복"],
  APPROVED: ["allow", "승인"], EXECUTED: ["allow", "실행됨"], REJECTED: ["block", "거부"], EXPIRED: ["outline", "만료"],
  NOT_EXECUTED: ["alert", "실행 안 됨"], UNCONFIRMED: ["alert", "실행 미확인"],
};
const REVIEW_KIND = {
  "user-consent": "사용자 동의", "intake-approve": "운영자 승인", "contract-review": "계약 검토", "risk-accept": "위험 수용",
  "risk-lapse": "위험 수용 만료", "intake-reject": "거부", "intake-hold": "보류", "provenance-mismatch": "보류",
  "server-register": "게이트웨이 등록", "tool-scope-review": "범위 심사", "residency-review": "위치 심사", "intake-cosign": "1차 승인", "risk-input": "영향평가 입력",
  "tool-sunset": "자동 비활성", "tool-sunset-extension": "이용 기간 연장", "tool-sunset-review": "도구 재심사",
  "tool-sunset-check": "이용 상태 확인", "tool-approval-extension": "승인 기간 연장",
  "auto-suspend-count-failed": "자동 중지 집계 실패",
  "intake-one-click": "도입 승인",
  "mcp-source-download": "소스 다운로드",
  "runtime-start": "실행 요청", "runtime-stop": "실행 중지 요청", "runtime-built": "이미지 빌드", "runtime-active": "실행 시작",
  "runtime-rollback": "실행 판본 되돌리기", "runtime-rollback-queued": "실행 판본 전환", "runtime-rollback-refused": "실행 판본 전환 거부", "runtime-rollback-request-refused": "실행 판본 되돌리기 요청 거부",
  "runtime-failed": "실행 실패", "runtime-stopped": "실행 중지", "runtime-egress": "외부 통신", "runtime-image-scan": "이미지 검사",
  "solo-mode": "단독 운영 모드", "ledger-retention": "보존 기간 변경", "audit-annotate": "감사 주석",
  "server-deregister": "게이트웨이 등록 해제", "contract-reapprove": "계약 재승인", "addon-result": "외부 게이트웨이 실행 결과",
  "litellm-sync": "외부 게이트웨이 동기화",
  "automatic-suspension": "자동 중지", "automatic-suspension-resume": "자동 중지 해제",
  "user-server-suspend": "이용 중지", "user-server-resume": "이용 재개", "account-restore": "계정 복구",
  "server-audience": "사용 대상 변경", "upstream-credential-connect": "계정 연결", "upstream-credential-disconnect": "계정 연결 해제",
  "call-request": "중대 영향 요청", "call-explanation-view": "중대 영향 설명 열람", "call-approve": "중대 영향 승인",
  "call-reject": "중대 영향 거부", "call-revoke": "중대 영향 번복",
  "incident-created": "사고 기록 생성", "incident-supplement": "사고 범위 보완", "incident-report": "사고 보고 제출",
  "disposal-reconciled": "폐기 상태 복원", "disposal-integrity-failure": "폐기 목록 확인 실패",
};
const RUNTIME_STATUS = {
  QUEUED: ["approval", "실행 대기"], BUILDING: ["approval", "빌드 중"], STARTING: ["approval", "시작 중"], VERIFYING: ["approval", "응답 확인 중"],
  ACTIVE: ["allow", "실행 중"], STOPPING: ["alert", "중지 중"], STOPPED: ["outline", "중지됨"], FAILED: ["block", "실행 실패"],
};
const REVIEW_OUTCOME = { approved: ["allow", "승인"], rejected: ["block", "거부"], refused: ["block", "본인 승인 차단"], held: ["alert", "보류"], recorded: ["outline", "기록됨"], failed: ["block", "확인 실패"], verified: ["outline", "동기화 완료"] };
const SCAN_STATE = { DONE: ["allow", "완료"], FAILED: ["block", "실패"] };
const UNSUPPORTED_POLICY = new Set(["PAC-05-DELEGATION-UNSUPPORTED"]);
const INTAKE_STATUS = {
  HOLD: ["outline", "검토 대기"], REMOTE_REVIEWED: ["approval", "계약 검토 완료"], VALIDATION_QUEUED: ["approval", "검증 대기"], VALIDATING: ["approval", "검증 중"],
  VALIDATED: ["restrict", "검증 완료"], APPROVED: ["allow", "승인"], REJECTED: ["block", "거부"], FAILED: ["alert", "검증 실패"],
};

const chip = (tone, label) => html`<span class="chip ${tone}">${label}</span>`;
// Links into this solution follow the page's own scheme: the console is served over HTTP and HTTPS.
const sameSite = (u) => { try { const x = new URL(u, location.href); return x.hostname === location.hostname ? x.pathname + x.search + x.hash : u; } catch { return u; } };
const decisionChip = (d) => chip(...(DECISION[d] || ["", d]));
const gradeChip = (g, prefix = "") => (g ? chip(g, `${prefix}${g} ${GRADE[g]}`) : chip("outline", "미판정"));
const REL_STATUS = { ACTIVE: ["outline", "이용 중"], TERMINATED: ["block", "종료"], TERMINATING: ["alert", "종료 중"], SUSPENDED: ["alert", "중지"] };
const bool = (v, label) => (v ? chip("allow", label) : chip("block", label));
const pad = (n) => String(n).padStart(2, "0");
const MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dayLabel = (d) => (lang() === "en" ? `${MONTH[d.getMonth()]} ${d.getDate()}` : `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`);
function when(value, { seconds = false } = {}) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}${seconds ? `:${pad(d.getSeconds())}` : ""}`;
  return d.toDateString() === new Date().toDateString() ? hm : `${dayLabel(d)} ${hm}`;
}
function dateTimeInput(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
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
  consent: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
  pause: '<rect width="4" height="16" x="6" y="4" rx="1" fill="currentColor" stroke="none"/><rect width="4" height="16" x="14" y="4" rx="1" fill="currentColor" stroke="none"/>',
  play: '<path d="m7 4 13 8-13 8Z" fill="currentColor" stroke="none"/>',
  refresh: '<path d="M20 11a8.1 8.1 0 0 0-15.5-2M4 4v5h5"/><path d="M4 13a8.1 8.1 0 0 0 15.5 2M20 20v-5h-5"/>',
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
  connections: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
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
function ask({ title, body = "", fields = "", confirm = "확인", danger = false, disabled = false, reject = false }) {
  const dialog = $("#dialog");
  const form = $("#dialog-form");
  // The confirm button comes first in the DOM so Enter in a field confirms: implicit submission
  // uses the form's first submit button, and with 취소 first Enter silently cancelled (a status
  // change with a memo never applied). CSS shows 취소 on the left.
  form.innerHTML = String(html`<h3 id="dialog-title">${title}</h3>${body ? html`<p>${body}</p>` : ""}${fields}
    <div class="row"><button class="btn ${danger ? "danger solid" : "primary"}" value="ok" ${disabled ? raw("disabled") : ""}>${confirm}</button>
    ${reject ? html`<button class="btn danger" value="reject" formnovalidate>거부</button>` : ""}
    <button class="btn" value="cancel" formnovalidate>취소</button></div>`);
  dialog.returnValue = "";
  dialog.showModal();
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => {
      if (!["ok", "reject", "load"].includes(dialog.returnValue)) { resolve(null); return; }
      const data = new FormData(form); data.set("dialog_action", dialog.returnValue); resolve(data);
    }, { once: true });
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
  return tabs.length < 2 ? html`${head}${kpis}${tabs[0].body}`
    : html`${head}${kpis}${tabBar(tabs, current)}${tabs.map((t) => tabPanel(t.key, current, t.body))}`;
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
  { id: "overview", label: "대시보드", group: "운영" },
  { id: "activity", label: "도구 호출 로그", group: "운영" },
  { id: "audit", label: "감사 기록", group: "운영" },
  { id: "approvals", label: "승인 대기", group: "운영", badge: "approvals" },
  { id: "coverage", label: "통제 범위", group: "접근 통제", badge: "coverage" },
  { id: "servers", label: "MCP 서버", group: "접근 통제" },
  { id: "people", label: "사용자·엔드포인트", group: "접근 통제" },
  { id: "policy", label: "정책", group: "접근 통제" },
  { id: "consent", label: "이용 동의", group: "접근 통제", badge: "consent" },
  { id: "intake", label: "도입 신청", group: "도입 및 종료" },
  { id: "sbom-impact", label: "공급망 영향", group: "도입 및 종료" },
  { id: "termination", label: "종료·폐기", group: "도입 및 종료", badge: "termination" },
  { id: "connections", label: "내 연결", group: "내 계정" },
];
let viewer = null;
let routeSeq = 0;
let current = { page: "", arg: "", query: new URLSearchParams() };
const badges = { approvals: 0, termination: 0, coverage: 0, consent: 0 };

function renderNav(active) {
  const groups = new Map();
  for (const p of PAGES.filter((x) => viewer.pages.includes(x.id))) {
    if (!groups.has(p.group)) groups.set(p.group, []);
    groups.get(p.group).push(p);
  }
  const shortcuts = [
    viewer.admin && viewer.git_url && html`<a href="${sameSite(viewer.git_url)}" data-i18n-ctx="nav" target="_blank" rel="noopener" aria-label="사내 저장소 (새 탭)" title="사내 저장소">${icon("git")}<span>사내 저장소</span><span class="ext" aria-hidden="true">↗</span></a>`,
    viewer.kit && html`<a href="#" data-i18n-ctx="nav" data-act="pc-kit" aria-label="PC 연결 설정" title="PC 연결 설정">${icon("plug")}<span>PC 연결 설정</span></a>`,
  ].filter(Boolean);
  $("#nav").innerHTML = String(html`${[...groups].map(([group, pages]) => html`<div class="group" data-i18n-ctx="group">${group}</div>${pages.map((p) => html`
    <a href="#/${p.id}" data-i18n-ctx="nav" title="${p.label}" aria-label="${p.label}" ${active === p.id ? raw('aria-current="page"') : ""}>${icon(p.id)}<span>${p.label}</span>
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
  stopSystemMetrics();
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
  if (moved && id === "coverage") resetCoveragePaging();
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
      document.title = `${t(h1.textContent.trim())} · MINT`;
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
    badges.consent = new Set((await api("/api/consents")).consents.filter((c) => c.status === "PENDING").map((c) => c.server_id)).size;
  } catch { /* same as below */ }
  if (!viewer.pages.includes("overview")) return renderNav($("#view").dataset.page);
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
const HEALTH_LABEL = { gateway: "게이트웨이", postgresql: "데이터베이스", opa: "정책 엔진",
  presidio_analyzer: "개인정보 분석기", presidio_anonymizer: "개인정보 익명화기" };
function componentHealth(health) {
  if (!health?.components) return chip("alert", "구성 요소 확인 불가");
  const issues = Object.entries(HEALTH_LABEL).filter(([key]) => health.components[key] !== true).map(([, label]) => label);
  if (health.policy?.matches === false) issues.push("정책 설정");
  if (health.status !== "ok" && !issues.length && health.components.jaeger !== false) issues.push("상태 상세 확인");
  const tracingIssue = health.components.jaeger === false;
  return html`${chip(issues.length ? "alert" : "allow", issues.length ? "구성 요소 확인 필요" : "구성 요소 정상")}
    ${issues.length || tracingIssue ? html`<span class="health-detail">${[...issues, ...(tracingIssue ? ["추적 수집(선택)"] : [])].join(", ")}</span>` : ""}`;
}

function decisionRow(r) {
  return html`<tr class="clickable" tabindex="0" data-act="decision" data-id="${r.id}">
    <td class="t">${when(r.at, { seconds: true })}</td>
    <td>${decisionChip(r.decision)}${r.invalid ? chip("outline", "무효 처리") : ""}</td>
    <td class="who-cell"><b>${r.who}</b></td>
    <td><code>${r.server}.${r.tool}</code></td>
    <td>${outcomeChips(r.outcome_axes)}</td></tr>`;
}
const OUTCOME_LABELS = { connection: "연결", decision: "정책 판정", task: "도구 업무", effect: "독립 효과" };
function outcomeChips(axes) {
  const tone = (value) => ["연결 성공", "허용", "업무 성공", "실행됨"].includes(value) ? "allow"
    : ["연결 실패", "정책 거부", "통제 장애 차단", "도구 오류", "제공자 인증 실패", "제공자 접근 거부", "제공자 한도 초과"].includes(value) ? "block" : "outline";
  return html`<div class="outcome-axes">${Object.entries(OUTCOME_LABELS).map(([key, label]) => html`<div class="row-actions"><span>${label}</span>${chip(tone(axes?.[key]), axes?.[key] || "—")}</div>`)}</div>`;
}
const decisionTable = (rows, id = "") => html`<table class="data call-table"><thead><tr><th>시각</th><th>판정</th><th>사용자</th>
  <th>도구</th><th>호출 결과</th></tr></thead><tbody ${id ? raw(`id="${id}"`) : ""}>${rows.map(decisionRow)}</tbody></table>`;

// A registration is approved until a date; past it the calls are blocked.
const VALIDITY = { 1: "1일", 30: "30일", 90: "90일", 180: "180일", 365: "1년" };
const AUDIENCE = { all: "전체 직원", requester: "신청자만", selected: "지정 직원" };
// 사용 대상 입력(승인 화면·서버 상세 공통): 지정 직원일 때만 아이디 입력칸이 보인다.
const audienceFields = (cur) => html`<label>사용 대상<select name="audience" data-audience>${Object.entries(AUDIENCE).map(([v, l]) =>
  html`<option value="${v}" ${v === cur ? raw("selected") : ""}>${l}</option>`)}</select></label>
  <label data-audience-users ${cur === "selected" ? "" : raw("hidden")}>지정 직원<input name="audience_users" maxlength="2000" placeholder="아이디, 아이디" /></label>`;
const audienceBody = (fd) => {
  const audience = String(fd.get("audience") || "all");
  return { audience, audience_users: audience === "selected" ? String(fd.get("audience_users") || "").split(",").map((v) => v.trim()).filter(Boolean) : [] };
};
const audienceText = (principals) => (principals || []).includes("*") ? AUDIENCE.all : (principals || []).join(", ") || NONE;
function validityChip(registration) {
  if (!registration?.valid_until) return "";
  const days = Math.ceil((new Date(registration.valid_until).getTime() - Date.now()) / 86400000);
  return days <= 0 ? chip("block", registration.supplier_assurance || registration.risk_review ? "재승인 대기" : "사용 기한 만료") : chip(days <= 14 ? "alert" : "outline", `D-${days}`);
}

// ── pages ────────────────────────────────────────────────────────────────────
const ROUTES = {};

let metricsTimer = null;
let metricsRequest = null;
function stopSystemMetrics() {
  clearInterval(metricsTimer);
  metricsTimer = null;
  metricsRequest?.abort();
  metricsRequest = null;
}
function metricsCards(sample, failure = false) {
  const values = resourceValues(sample);
  return html`<div class="system-values">${[
    ["CPU 부하", values.cpu], ["메모리 사용", values.memory], ["내부 연결 지연", values.latency],
  ].map(([label, value]) => html`<div class="system-stat"><span>${label}</span><b>${value}</b></div>`)}</div>
    <div class="system-time">${failure ? "확인 실패" : values.measuredAt
      ? `확인 ${clockText(new Date(values.measuredAt))}` : sample ? "갱신 필요" : "미측정"}</div>`;
}
function latencyCards(lat, net) {
  const fresh = (net?.devices || []).filter((d) => d.state === "fresh").length;
  return html`<div class="system-values latency-values">${[
    ["게이트웨이 처리", lat?.gateway?.p50, lat?.gateway?.p95],
    ["MCP 서버 응답", lat?.upstream?.p50, lat?.upstream?.p95],
    ["엔드포인트 왕복", fresh ? net.summary?.p50_ms : null, fresh ? net.summary?.p95_ms : null],
  ].map(([label, p50, p95]) => html`<div class="system-stat"><span>${label}</span><b>${msText(p50)}</b>
    <small>${p95 == null ? "" : `95% ${msText(p95)}`}</small></div>`)}</div>`;
}
function startSystemMetrics() {
  if (!$("#system-metrics")) return;
  const seq = routeSeq;
  let busy = false;
  let lastSample = null;
  let failing = false;
  const refresh = async () => {
    if (seq === routeSeq && $("#system-metrics")) $("#system-metrics").innerHTML = String(metricsCards(lastSample, failing));
    if (busy || seq !== routeSeq || document.hidden) return;
    busy = true;
    const controller = new AbortController();
    metricsRequest = controller;
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const sample = await api("/api/system/metrics", { signal: controller.signal });
      lastSample = sample;
      failing = false;
      if (seq === routeSeq && $("#system-metrics")) $("#system-metrics").innerHTML = String(metricsCards(sample));
    } catch {
      lastSample = null;
      failing = true;
      if (seq === routeSeq && $("#system-metrics")) $("#system-metrics").innerHTML = String(metricsCards(null, true));
    } finally {
      clearTimeout(timeout);
      if (metricsRequest === controller) metricsRequest = null;
      busy = false;
    }
  };
  refresh();
  metricsTimer = setInterval(refresh, 10000);
}

ROUTES.overview = async (_, tab) => {
  const [o, blocked, pl, lat, net, health] = await Promise.all([gw("overview"), gw("activity?limit=10&decision=Block"), planes(),
    gw("latency").catch(() => null), gw("endpoint/network-quality").catch(() => null), gw("health").catch(() => null)]);
  const serverName = Object.fromEntries((o.servers || []).map((s) => [s.id, s.display_name || s.id]));
  const stages = lat?.stages || [];
  feed.rows = mergeRows([], blocked.rows);
  const x = o.execution, term = o.termination || {};
  const todayFilter = `since=${encodeURIComponent(o.today_since)}&event_kind=tools%2Fcall`;
  const buckets = hourBuckets(o.series);
  const flowTotal = o.flows.reduce((s, f) => s + Number(f.n || 0), 0);
  const stations = (o.workstations || []).filter((station) => Number(station.calls) > 0);
  const abnormalServers = (o.servers || []).filter((s) => !["READY", "DISABLED"].includes(s.status)).length;
  const items = dedupeItems(pl?.items || []);
  const count = (s) => items.filter((i) => i.state === s).length;
  const devices = (pl?.devices || []).filter((d) => d.endpoint_id);
  const deviceOf = Object.fromEntries(devices.map((d) => [d.endpoint_id, d]));
  const bypass = items.filter((i) => i.state === "bypass_possible").sort((a, b) => (b.bypass || []).length - (a.bypass || []).length).slice(0, 8);
  const bypassImpact = (item) => {
    const users = new Set((item.owners || [item.owner]).filter(Boolean)).size;
    const endpoints = Number(item.pcs) || (item.device ? 1 : 0);
    return [users ? `사용자 ${users}명` : "", endpoints ? `엔드포인트 ${endpoints}대` : ""].filter(Boolean).join(", ") || "—";
  };
  const bypassPaths = (item) => {
    const paths = item.bypass || [];
    const details = [...paths.slice(0, 2), ...(paths.length > 2 ? [`외 ${paths.length - 2}개`] : [])];
    return html`<span class="pair">${controlChip("bypass_possible")}
      ${details.length ? html`<span class="ev">${details.join(", ")}</span>` : ""}</span>`;
  };
  return {
    html: page({
      head: head("대시보드", { status: html`${modeChip(o.enforcement)}${componentHealth(health)}` }),
      kpis: html`<div class="dashboard-kpi-groups">
        <section><h2>오늘 운영 현황</h2>${kpiStrip([
          ["전체 요청", x.tool_calls, "", `#/activity?${todayFilter}`],
          ["실행된 요청", x.executed, "allow", `#/activity?${todayFilter}&execution=executed`],
          ["차단된 요청", x.blocked, "block", `#/activity?${todayFilter}&decision=Block`],
          ["실행 미확인", x.unknown, "alert", `#/activity?${todayFilter}&execution=unknown`]])}</section>
        <section><h2>현재 상태</h2>${kpiStrip([
        ["통제 적용 엔드포인트", devices.filter((d) => d.account_state === "endpoint_enforced").length, "", "#/coverage?t=devices"],
        ["조직 통제 의존", count("bypass_possible"), "block", "#/coverage?t=items&state=bypass_possible"],
          ["종료 조치 필요", term.unresolved_grades, "alert", "#/termination"],
          ["운영 이상 MCP", abnormalServers, "alert", "#/servers"]])}</section>
      </div>`,
      active: tab || "summary",
      tabs: [
        { key: "summary", label: "요약", body: html`<div class="stack">
          ${panel("시스템 상태", html`<div id="system-metrics" aria-live="polite">${metricsCards(null)}</div>`)}
          ${panel("관리자 조치", html`<div class="action-list">
            <a class="action-link" href="#/approvals"><span>승인 요청</span><b class="n">${o.pending_approvals || 0}</b></a>
            <a class="action-link" href="#/intake"><span>도입 조치 필요</span><b class="n">${o.intake_actions || 0}</b></a>
            <a class="action-link" href="#/termination"><span>종료 기한 초과</span><b class="n">${term.overdue || 0}</b></a>
          </div>`)}
          ${panel("최근 차단 10건", feed.rows.length ? decisionTable(feed.rows) : empty("차단된 호출 없음"), { flush: true, end: html`<a class="btn sm" href="#/activity?decision=Block">차단 로그 <span aria-hidden="true">↗</span></a>` })}
        </div>` },
        { key: "planes", label: "통제 적용 현황", body: html`<div class="stack">
          ${panel("조직 통제 의존 경로 (최대 8건)", bypass.length ? html`<table class="data"><thead><tr><th>항목</th><th>연동 유형</th><th>영향 범위</th><th>우회 경로</th></tr></thead><tbody>
            ${bypass.map((i) => html`<tr class="clickable" tabindex="0" data-act="goto" data-href="#/coverage?t=items&state=bypass_possible&q=${encodeURIComponent(i.name)}">
              <td><b>${i.name}</b><span class="sub mono">${short(i.target || "", 50)}</span></td><td class="small">${INTEGRATION_CLASS[i.class] || i.class}</td>
              <td class="small">${bypassImpact(i)}</td><td>${bypassPaths(i)}</td></tr>`)}</tbody></table>` : empty("조직 통제 의존 경로 없음"),
            { flush: true, end: html`<a class="btn sm" href="#/coverage?t=items&state=bypass_possible">전체</a>` })}
          ${panel("연동 유형별 통제 상태", items.length ? chartBox("c-ov-matrix", "연동 유형별 통제 항목 수", "lg") : empty("항목 없음"), { sub: "항목 수" })}</div>` },
        { key: "traffic", label: "호출 분석", body: html`<div class="stack">
          ${panel("시간대별 판정", chartBox("c-traffic", "최근 24시간 시간대별 판정 건수", "lg"), { sub: "최근 24시간" })}
          ${panel("차단 및 경보 정책", o.top_policies.length ? chartBox("c-policies", "최근 24시간 차단 및 경보가 많은 정책") : empty("최근 24시간 차단 및 경보 없음"), { sub: "최근 24시간" })}
          ${panel("하네스별 호출 흐름", flowTotal ? chartBox("c-flow", "하네스에서 MCP 서버를 거쳐 판정까지의 호출 흐름", "xl") : empty("최근 24시간 호출 없음"), { sub: `${flowTotal}건 · 최근 24시간` })}
          ${panel("엔드포인트별 호출", html`<table class="data"><thead><tr><th>엔드포인트</th><th>사용자</th><th>최근 하네스</th><th class="num">24시간 호출</th><th>통제 상태</th><th>마지막 호출</th></tr></thead><tbody>
            ${stations.map((w) => html`<tr><td>${entityRef(w.endpoint_id)}</td><td><b>${w.display_name || w.owner_token}</b><span class="sub">${w.department || ""}</span></td>
              <td>${w.harness ? chip("plain", harnessLabel(w.harness)) : NONE}</td><td class="num">${w.calls}</td>
              <td>${deviceOf[w.endpoint_id] ? statusPair(deviceOf[w.endpoint_id]) : chip("outline", "확인 불가")}</td><td class="small">${ago(w.last_call)}</td></tr>`)}
            </tbody></table>${stations.length ? "" : empty("최근 24시간 호출 없음")}`, { flush: true })}
        </div>` },
        { key: "latency", label: "지연", body: html`<div class="stack">
          ${latencyCards(lat, net)}
          ${panel("구간별 처리 시간", stages.length ? chartBox("c-lat-stages", "최근 24시간 도구 호출의 구간별 처리 시간", "lg") : empty("측정된 호출 없음"),
            { sub: lat?.calls ? `${lat.calls}건 · 최근 24시간` : "" })}
          <div class="grid c2">
          ${panel("MCP 서버", (lat?.servers || []).length ? html`<table class="data"><thead><tr><th>MCP 서버</th><th class="num">호출</th><th class="num">중앙값</th><th class="num">95%</th><th class="num">실패</th></tr></thead><tbody>
            ${lat.servers.map((r) => html`<tr class="clickable" tabindex="0" data-act="goto" data-href="#/activity?server=${encodeURIComponent(r.server_id)}">
              <td><b>${serverName[r.server_id] || r.server_id}</b></td><td class="num">${r.n}</td><td class="num">${msText(r.p50)}</td>
              <td class="num">${msText(r.p95)}</td><td class="num ${r.failed ? "bad-text" : ""}">${r.failed}</td></tr>`)}</tbody></table>` : empty("측정된 호출 없음"), { flush: true })}
          ${panel("엔드포인트 왕복", (net?.devices || []).length ? html`<table class="data"><thead><tr><th>엔드포인트</th><th class="num">중앙값</th><th class="num">95%</th><th class="num">지터</th><th class="num">실패율</th><th>확인</th></tr></thead><tbody>
            ${net.devices.map((d) => html`<tr><td>${entityRef(d.endpoint_id)}<span class="sub">${d.hostname || ""}</span></td>
              <td class="num">${d.state === "fresh" ? msText(d.rtt_p50_ms) : "—"}</td><td class="num">${d.state === "fresh" ? msText(d.rtt_p95_ms) : "—"}</td>
              <td class="num">${d.state === "fresh" ? msText(d.jitter_ms) : "—"}</td><td class="num">${d.state === "fresh" ? pctText(d.failure_pct) : "—"}</td>
              <td class="small">${d.state === "fresh" ? ago(d.measured_at) : d.state === "stale" ? chip("alert", "오래됨") : chip("outline", "확인 불가")}</td></tr>`)}</tbody></table>`
            : empty("측정된 엔드포인트 없음"), { flush: true })}</div></div>` },
      ],
    }),
    charts: {
      "c-ov-matrix": () => charts.stacked(Object.values(INTEGRATION_CLASS),
        Object.entries(CONTROL_STATE).map(([k, [, label]]) => ({ name: label, color: charts.color(STATE_DECISION[k]),
          data: Object.keys(INTEGRATION_CLASS).map((c) => items.filter((i) => i.class === c && i.state === k).length) })),
        { horizontal: true, onClick: (e) => { const c = Object.keys(INTEGRATION_CLASS)[e.dataIndex]; const st = Object.keys(CONTROL_STATE)[e.seriesIndex];
          if (c && st) location.hash = `#/coverage?t=items&class=${c}&state=${st}`; } }),
      "c-traffic": () => charts.decisionColumns(buckets.map((b) => b.label), buckets),
      "c-lat-stages": () => charts.stacked(stages.map((r) => LATENCY_STAGE[r.stage] || r.stage), [
        { name: "중앙값", color: charts.color("Allow"), data: stages.map((r) => r.p50) },
        { name: "95%", color: charts.color("Alert"), data: stages.map((r) => r.p95) }], { horizontal: true, grouped: true, unit: "ms" }),
      "c-flow": () => charts.sankey(sankeyData(o.flows, (d) => DECISION_LABEL[d] || d)),
      "c-policies": () => charts.bars(o.top_policies.map((p) => ({ name: p.policy_id, value: Number(p.n), color: charts.color(p.decision) }))),
    },
    after: startSystemMetrics,
  };
};

// Activity keeps its rows between renders so live updates and the detail drawer
// read from the same list. Paused, it keeps polling but holds new rows back and
// counts them, so the list stops moving without going stale.
const FEED_FILTERS = ["decision", "server", "since", "until", "execution", "person", "endpoint", "policy", "event_kind"];
const FEED_PAGE_SIZE = 50;
const feed = { rows: [], pending: [], cursor: 0, filters: Object.fromEntries(FEED_FILTERS.map((key) => [key, ""])), query: "",
  live: true, servers: [], lastOk: 0, failing: false, gen: 0, page: 1, pageSize: FEED_PAGE_SIZE,
  total: 0, filteredTotal: 0, highlight: [], analysis: null, analysisKey: "", analysisAt: 0 };
let liveTimer = null;
function stopLive() { clearInterval(liveTimer); liveTimer = null; feed.gen += 1; }
const feedQuery = (extra) => new URLSearchParams({ ...Object.fromEntries(Object.entries(feed.filters).filter(([, v]) => v)
  .map(([key, value]) => [key,
    ["since", "until"].includes(key) ? new Date(value).toISOString() : value])),
  ...(feed.query ? { q: feed.query } : {}), ...extra });

function renderFeedStatus() {
  const status = $("#feed-status");
  if (!status) return;
  const start = feed.rows.length ? (feed.page - 1) * feed.pageSize + 1 : 0;
  const end = feed.rows.length ? start + feed.rows.length - 1 : 0;
  const range = feed.query ? `${start}–${end} / 검색 ${feed.filteredTotal}건 · 전체 ${feed.total}건`
    : Object.values(feed.filters).some(Boolean) ? `${start}–${end} / 필터 ${feed.filteredTotal}건 · 전체 ${feed.total}건`
      : `${start}–${end} / 전체 ${feed.total}건`;
  status.textContent = range;
  $("#feed-live-state").textContent = feed.failing ? "갱신 실패" : feed.live ? "실시간" : "일시정지";
  $("#feed-live-time").textContent = feed.lastOk
    ? clockText(new Date(feed.lastOk), { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "연결 중";
  $("#feed-dot").className = `dot ${feed.failing ? "bad" : feed.live ? "on" : "paused"}`;
}

function feedCharts() {
  const data = feed.analysis || { series: [], hours: [], responses: [], harnesses: [], servers: [], people: [] };
  const occupied = new Map();
  for (const row of data.series || []) {
    const at = new Date(row.at);
    const key = at.getTime();
    if (!occupied.has(key)) occupied.set(key, Object.fromEntries(DECISIONS.map((decision) => [decision, 0])));
    if (DECISIONS.includes(row.decision)) occupied.get(key)[row.decision] = Number(row.n) || 0;
  }
  const series = [];
  const times = [...occupied.keys()].sort((a, b) => a - b);
  if (times.length) {
    const cursor = new Date(times[0]), end = times[times.length - 1];
    while (cursor.getTime() <= end) {
      const at = cursor.getTime();
      const label = data.bucket === "hour" ? `${dayLabel(cursor)} ${pad(cursor.getHours())}${lang() === "en" ? ":00" : "시"}`
        : data.bucket === "day" ? `${cursor.getFullYear()}-${pad(cursor.getMonth() + 1)}-${pad(cursor.getDate())}`
          : `${cursor.getFullYear()}-${pad(cursor.getMonth() + 1)}`;
      series.push({ label, ...(occupied.get(at) || Object.fromEntries(DECISIONS.map((decision) => [decision, 0]))) });
      if (data.bucket === "month") cursor.setMonth(cursor.getMonth() + 1);
      else cursor.setTime(cursor.getTime() + (data.bucket === "day" ? 86400000 : 3600000));
    }
  }
  return {
    "c-minutes": () => charts.decisionColumns(series.map((b) => b.label), series),
    "c-by-server": () => charts.decisionColumns(data.servers.map((x) => x.key), data.servers, { horizontal: true, grouped: true }),
    ...(viewer.admin ? { "c-by-person": () => charts.decisionColumns(data.people.map((x) => x.key), data.people, { horizontal: true, grouped: true }) } : {}),
    "c-by-response": () => charts.donut(Object.entries(RESPONSE).map(([k, [tone, label]]) => ({ name: label,
      value: Number(data.responses.find((row) => row.response === k)?.n) || 0, color: charts.color(TONE_DECISION[tone]) })).filter((g) => g.value)),
  };
}

function renderFeed(newIds = []) {
  const body = $("#feed");
  if (!body) return;
  const focused = document.activeElement?.closest?.("#feed tr")?.dataset.id;
  body.innerHTML = String(html`${feed.rows.map(decisionRow)}`);
  const fresh = new Set(newIds.map(String));
  for (const row of body.querySelectorAll("tr[data-id]")) row.classList.toggle("new-call", fresh.has(row.dataset.id));
  if (focused) $(`#feed tr[data-id="${CSS.escape(focused)}"]`)?.focus();
  const note = $("#feed-empty");
  note.hidden = feed.rows.length > 0;
  note.innerHTML = String(feed.rows.length || feed.query || Object.values(feed.filters).some(Boolean)
    ? html`조건에 맞는 호출 없음 <button class="btn sm" type="button" data-act="feed-reset">조건 초기화</button>` : html`호출 없음`);
  const pages = Math.max(1, Math.ceil(feed.filteredTotal / feed.pageSize));
  const pager = $("#feed-pager");
  if (pager) pager.innerHTML = String(html`<button class="pager-button" type="button" data-act="feed-page" data-page="${feed.page - 1}" aria-label="이전 페이지" title="이전 페이지" ${feed.page <= 1 ? raw("disabled") : ""}>‹</button>
    <span>${feed.page} / ${pages}</span>
    <button class="pager-button" type="button" data-act="feed-page" data-page="${feed.page + 1}" aria-label="다음 페이지" title="다음 페이지" ${feed.page >= pages ? raw("disabled") : ""}>›</button>`);
  for (const [id, build] of Object.entries(feedCharts())) charts.redraw(id, build);
  renderFeedStatus();
}

function startLive() {
  stopLive();
  const gen = feed.gen;
  liveTimer = setInterval(async () => {
    if (document.hidden) return;
    try {
      const data = await gw(`activity?${feedQuery({ after: feed.cursor, limit: 100 })}`);
      if (gen !== feed.gen) return;  // the page was rebuilt while this poll was in flight
      feed.cursor = Math.max(feed.cursor, data.cursor || 0);
      feed.lastOk = Date.now();
      feed.failing = false;
      if (feed.live && feed.page === 1 && data.rows.length) {
        const existing = new Set(feed.rows.map((row) => String(row.id)));
        const fresh = data.rows.filter((row) => !existing.has(String(row.id)));
        if (fresh.length) {
          feed.rows = mergeRows(feed.rows, data.rows, feed.pageSize);
          feed.filteredTotal += fresh.length;
          if (!feed.query && !Object.values(feed.filters).some(Boolean)) feed.total += fresh.length;
          renderFeed(fresh.map((row) => row.id));
        } else renderFeedStatus();
      } else {
        feed.pending = mergeRows(feed.pending, data.rows);
        renderFeedStatus();
      }
    } catch {
      // A failed poll must not end the live view, and must not look like a quiet one.
      if (gen === feed.gen) { feed.failing = true; renderFeedStatus(); }
    }
  }, 5000);
}

ROUTES.activity = async (_, tab, query) => {
  // A link that names a filter (an overview KPI) replaces the whole set; keeping the
  // others would AND a stale filter with the new one into an empty list.
  if (FEED_FILTERS.some((key) => query.has(key))) for (const key of FEED_FILTERS) feed.filters[key] = query.get(key) || "";
  if (query.has("q")) feed.query = query.get("q");
  const analysisKey = feedQuery({}).toString();
  const [data, analysis] = await Promise.all([
    gw(`activity?${feedQuery({ limit: FEED_PAGE_SIZE, page: feed.page })}`),
    feed.analysis && feed.analysisKey === analysisKey && Date.now() - feed.analysisAt < 30000
      ? Promise.resolve(feed.analysis) : gw(`activity/analysis?${analysisKey}`),
  ]);
  feed.rows = mergeRows([], data.rows);
  feed.pending = [];
  feed.cursor = data.cursor;
  feed.page = data.page || feed.page;
  feed.pageSize = data.page_size || FEED_PAGE_SIZE;
  feed.total = data.total || 0;
  feed.filteredTotal = data.filtered_total || 0;
  feed.analysis = analysis;
  feed.analysisKey = analysisKey;
  feed.analysisAt = Date.now();
  feed.lastOk = Date.now();
  feed.failing = false;
  if (viewer.admin && !feed.servers.length) feed.servers = (await gw("registry")).servers.map((s) => s.id);
  const servers = viewer.admin ? feed.servers : [...new Set(feed.rows.map((r) => r.server))].sort();
  const option = (value, label, cur) => html`<option value="${value}" ${value === cur ? raw("selected") : ""}>${label}</option>`;
  const f = feed.filters;
  const advancedOpen = ["execution", "person", "endpoint", "policy"].some((key) => f[key]);
  return {
    html: page({
      head: head("도구 호출 로그"),
      active: tab || "live",
      tabs: [
        { key: "live", label: "목록", body: html`<div class="feed-toolbar">
          <span class="live"><span class="dot" id="feed-dot"></span><span id="feed-live-state"></span><span aria-hidden="true">|</span><span id="feed-live-time"></span>
            <button class="feed-live-toggle" type="button" data-act="live" aria-pressed="${String(!feed.live)}" aria-label="${feed.live ? "일시정지" : "실시간 재개"}" title="${feed.live ? "일시정지" : "실시간 재개"}">${icon(feed.live ? "pause" : "play")}</button></span>
          <span class="feed-count" id="feed-status"></span>
        </div><section class="panel feed-panels">
          <div class="filters">
            <label class="grow">검색<input data-feed-search type="search" maxlength="120" value="${feed.query}" placeholder="사용자, 엔드포인트, 도구, 정책" aria-label="호출 검색" /></label>
            <label>시작<input data-filter="since" type="datetime-local" value="${dateTimeInput(f.since)}" aria-label="조회 시작 시각" /></label>
            <label>종료<input data-filter="until" type="datetime-local" value="${dateTimeInput(f.until)}" aria-label="조회 종료 시각" /></label>
            <label>판정<select data-filter="decision" aria-label="판정">${option("", "모든 판정", f.decision)}
              ${Object.entries(DECISION).map(([k, [, label]]) => option(k, label, f.decision))}</select></label>
            <label>MCP 서버<select data-filter="server" aria-label="서버">${option("", "모든 서버", f.server)}${servers.map((s) => option(s, s, f.server))}</select></label>
            <details class="feed-advanced" ${advancedOpen ? raw("open") : ""}><summary>상세 필터</summary><div class="advanced-filters">
              <label>실행 결과<select data-filter="execution" aria-label="실행 결과">${option("", "모든 실행 결과", f.execution)}${option("executed", "실행됨", f.execution)}${option("not-sent", "실행 안 함", f.execution)}${option("unknown", "실행 미확인", f.execution)}${option("withheld", "응답 보류", f.execution)}${option("connection-denied", "연결 거부", f.execution)}</select></label>
              ${viewer.admin ? html`<label>사용자<input data-filter="person" type="search" placeholder="이름 또는 계정" value="${f.person}" aria-label="사용자" /></label>` : ""}
              <label>엔드포인트<input data-filter="endpoint" type="search" placeholder="엔드포인트 ID" value="${f.endpoint}" aria-label="엔드포인트" /></label>
              <label>정책<input data-filter="policy" type="search" placeholder="정책 ID" value="${f.policy}" aria-label="정책" /></label>
            </div></details>
          </div>
          <div class="body flush">${decisionTable([], "feed")}<p class="empty" id="feed-empty" hidden></p><div class="pager" id="feed-pager"></div></div></section>` },
        { key: "stats", label: "분석", body: html`<div class="feed-toolbar analysis-toolbar">
          <span class="analysis-total" id="analysis-total">전체 ${analysis.total ?? 0}건</span>
          <span class="analysis-updated">갱신 시각 <span id="analysis-updated-time">${clockText(new Date(), { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span></span>
          <button class="analysis-refresh" type="button" data-act="analysis-refresh" aria-label="분석 새로고침" title="분석 새로고침">${icon("refresh")}</button>
        </div><div class="stack">
          ${panel("호출 추이", chartBox("c-minutes", "전체 호출 추이", "sm"), { sub: `${analysis.total}건` })}
          ${panel("응답 처리", chartBox("c-by-response", "전체 호출의 응답 처리 비율", "sm"))}
          ${panel("서버별", chartBox("c-by-server", "전체 호출의 서버별 판정"))}
          ${viewer.admin ? panel("사용자별", chartBox("c-by-person", "전체 호출의 사용자별 판정", "lg")) : ""}</div>` },
      ],
    }),
    charts: feedCharts(),
    after: () => { const highlighted = feed.highlight; feed.highlight = []; renderFeed(highlighted); startLive(); },
  };
};

function timingView(timings) {
  const { rows, total } = timingRows(timings);
  if (!rows.length) return empty("측정 없음");
  return html`<table class="data"><thead><tr><th>구간</th><th class="num">시간</th><th class="num">비율</th></tr></thead><tbody>
    ${rows.map((r) => html`<tr><td>${r.label}</td><td class="num">${msText(r.ms)}</td><td class="num">${r.share == null ? "—" : `${r.share}%`}</td></tr>`)}
    <tr><td><b>전체</b></td><td class="num"><b>${msText(total)}</b></td><td class="num"></td></tr></tbody></table>`;
}

const MCP_EVIDENCE_LABEL = { confirmed: "MCP 응답 확인", suspected: "MCP로 추정", unknown: "MCP 여부 미확인" };
function relatedBody(related) {
  if (!related) return empty("확인 불가");
  if (!related.records.length) return empty("연관 기록 없음");
  const evidence = (x) => (x.link_basis || []).map((key) => ({ request_id: "요청 ID", trace_id: "추적 ID",
    decision_id: "판정 ID", same_endpoint: "같은 엔드포인트", same_principal: "같은 주체", time_window: "시간 창",
    same_server: "같은 서버", dispatch_interval: "호출 실행 구간" })[key] || key).join(" · ");
  const state = { pending: "대기", resolved: "확정", uncertain: "미확인", confirmed_executed: "실행 확인", confirmed_not_executed: "미실행 확인" };
  const egressState = { connected: "연결 확인", blocked: "프록시에서 차단", connect_failed: "연결 실패" };
  const identifier = (x) => x.kind === "decision" ? `판정 ${x.id} · 추적 ID ${x.trace_id || "—"}`
    : x.kind === "dispatch-intent" ? `요청 ID ${x.request_id}` : `${x.kind === "os-event" ? "이벤트" : "기록"} ${x.id}`;
  return html`<table class="data"><thead><tr><th>시각</th><th>종류</th><th>ID</th><th>내용</th><th>상태</th><th>연관 근거</th></tr></thead><tbody>
    ${related.records.map((x) => html`<tr><td class="small">${when(x.at, { seconds: true })}</td><td>${chip("outline", RECORD_KIND[x.kind] || x.kind)}</td>
      <td class="small"><code>${identifier(x)}</code></td>
      <td class="small">${x.kind === "decision" ? html`${decisionChip(x.decision)} <code>${x.title}</code>` : html`${x.denial_class ? chip(...denialClass(x.denial_class)) : ""} ${x.title || "—"}`}</td>
      <td class="small">${x.kind === "server-egress" ? egressState[x.state] || "—" : x.kind === "dispatch-intent" ? state[x.state] || "—" : x.policy_id || "—"}</td>
      <td class="small">${evidence(x)} · ${x.link_strength === "exact" ? "정확 연결" : "보조 근거"}</td></tr>`)}
    </tbody></table><span class="small muted">±${Math.round(related.window_seconds / 60)}분</span>`;
}

async function showDecision(id) {
  const r = feed.rows.find((row) => String(row.id) === String(id));
  if (!r) return;
  // The device's current state, beside (never instead of) what the call itself carried.
  const [related, device] = viewer.admin ? await Promise.all([
    gw(`endpoint/correlation?decision_id=${encodeURIComponent(r.id)}`).catch(() => null),
    r.device_id ? planes().then((p) => p?.devices.find((d) => d.endpoint_id === r.device_id)).catch(() => null) : null]) : [null, null];
  const conflictChip = (c) => chip((DECISION[c.decision] || [""])[0], `${(DECISION[c.decision] || [, c.decision])[1]} ${c.policy_id}`);
  openDrawer(`호출 #${r.id}`, html`<div class="drawer-summary"><span class="tool">${r.server}.${r.tool}</span>
    ${decisionChip(r.decision)}${r.invalid ? chip("outline", "무효 처리") : ""}<span class="muted small">${dateTimeText(new Date(r.at))}</span></div>`, [
    { key: "flow", label: "요약", body: pipeline(r, device) },
    { key: "call", label: "요청 정보", body: kv([
      ["사용자", r.who], ["부서", r.department],
      ["역할", ROLE[r.role] || r.role], ["엔드포인트", r.workstation], ["하네스", r.harness ? harnessLabel(r.harness) : r.agent],
      ["이벤트", r.event_kind === "mcp-connection" ? "연결 거부" : ""],
      ["MCP 서버", r.server], ["도구", html`<code>${r.tool}</code>`], ["대상", r.target ? html`<code>${r.target}</code>` : ""]]) },
    { key: "policy", label: "판정", body: html`
      <div class="decision-reason"><span>판정 사유</span><p>${r.reason || "—"}</p></div>${kv([
        ["적용 정책", html`<code>${r.policy_id}</code>`],
        ["실행 권한 위반", (r.pac_failures || []).length ? html`${r.pac_failures.map((x) => chip("block", x))}` : "없음"],
        ["함께 적용된 정책", (r.conflicts || []).length ? html`${r.conflicts.map(conflictChip)}` : "없음"],
        ["행위", r.action_ko || ACTION[r.action] || "—"], ["데이터 등급", r.data_class_ko], ["분류 근거", r.summary],
        ["개인정보", privacyText(r.privacy_types)], ["연쇄 탐지", (r.sequence_flags || []).join(", ")],
        ["무효 처리", r.invalid ? `${r.invalid.reason} · ${r.invalid.by} · ${when(r.invalid.at)}` : ""],
        ["승인 요청", r.approval_id], ["집행 모드", r.enforcement === "monitor" ? "관찰" : r.enforcement === "enforce" ? "집행" : r.enforcement],
        ["관찰 판정", r.would_decision ? (DECISION[r.would_decision]?.[1] || r.would_decision) : ""]])}` },
    { key: "execution", label: "실행 결과", body: html`${outcomeChips(r.outcome_axes)}${kv([
      ["MCP 서버 전송", r.attempted ? "시도" : "전송 안 함"],
      ["도구 실행", r.executed ? "실행됨" : r.attempted ? "실행 미확인" : "실행 안 함"],
      ["응답 처리", RESPONSE[r.response]?.[1] || r.response || "—"],
      ["응답 크기", r.response_bytes != null ? `${r.response_bytes} 바이트` : ""],
      ["응답 형식", (r.response_types || []).join(", ")],
      ["마스킹 항목", (r.masked_types || []).join(", ")],
      ["오류", r.error]])}<details><summary>추적 정보</summary>${kv([
      ["응답 해시", r.response_sha256 ? html`<code>${r.response_sha256}</code>` : ""],
      ["감사 해시", r.evidence_sha256 ? html`<code>${r.evidence_sha256}</code>` : ""],
      ["추적 ID", r.trace_id ? html`<code>${r.trace_id}</code>` : ""], ["추적 문맥", r.traceparent ? html`<code>${r.traceparent}</code>` : ""],
      ["작업 ID", r.task_id]])}</details>` },
    { key: "timing", label: "처리 시간", body: timingView(r.timings) },
    ...(viewer.admin ? [{ key: "related", label: "연관 이벤트", n: related ? related.records.length : undefined, body: relatedBody(related) }] : []),
  ]);
}

let approvalRows = [];
ROUTES.approvals = async (_, tab) => {
  const [{ approvals, history }, { rows: unsent }] = await Promise.all([api("/approvals"), gw("dispatch-intents")]);
  approvalRows = [...approvals, ...history];
  const oldest = approvals.reduce((m, a) => Math.min(m, new Date(a.created_at).getTime()), Date.now());
  return {
    html: page({
      head: head("승인 대기"),
      active: tab || "queue",
      tabs: [
        { key: "queue", label: "대기", n: approvals.length, hot: approvals.length > 0, body: panel("승인 요청", approvals.length ? html`<table class="data">
          <thead><tr><th>요청자</th><th>도구</th><th>행위 · 데이터 등급</th><th>하네스</th><th>요청 시각</th><th>만료 시각</th><th></th></tr></thead><tbody>
          ${approvals.map((a) => html`<tr class="clickable" tabindex="0" data-act="approval" data-id="${a.id}">
            <td class="who-cell"><b>${a.display_name || a.requested_by}</b><span class="sub">${a.department || ""}</span></td>
            <td><code>${a.server_id}.${a.tool}</code>${a.explanation ? chip("approval", "중대 영향") : ""}</td>
            <td>${ACTION[a.action] || a.action || "—"} · ${DATA_CLASS[a.data_class] || a.data_class || "—"}</td>
            <td>${a.client?.harness?.name ? chip("plain", harnessLabel(a.client.harness.name)) : "—"}</td>
            <td class="small">${ago(a.created_at)}</td><td class="small">${when(a.expires_at)}</td>
            <td class="num nowrap"><button class="btn sm danger" data-act="reject" data-id="${a.id}">거부</button>
              ${a.own ? chip("outline", "본인 요청") : html`<button class="btn sm primary" data-act="approve" data-id="${a.id}">승인·실행</button>`}</td></tr>`)}
          </tbody></table>` : empty("대기 중인 요청 없음"), { flush: true, sub: approvals.length ? `가장 오래된 요청 ${ago(oldest)}` : "" }) },
        { key: "unsent", label: "실행 확인", n: unsent.length, hot: unsent.length > 0, body: panel("실행 확인 필요", unsent.length ? html`<table class="data">
          <thead><tr><th>사용자</th><th>도구</th><th>행위</th><th>전송</th><th></th></tr></thead><tbody>
          ${unsent.map((u) => html`<tr><td class="who-cell"><b>${u.display_name || u.user_token}</b></td>
            <td><code>${u.server_id}.${u.tool_name}</code></td><td>${ACTION[u.action] || u.action}</td>
            <td class="small">${when(u.attempted_at, { seconds: true })}</td>
            <td class="num nowrap"><button class="btn sm" data-act="intent-resolve" data-id="${u.request_id}" data-outcome="not_executed">실행 안 됨</button>
              <button class="btn sm primary" data-act="intent-resolve" data-id="${u.request_id}" data-outcome="executed">실행됨</button></td></tr>`)}
          </tbody></table>` : empty("확인할 호출 없음"), { flush: true }) },
        { key: "history", label: "처리 이력", n: history.length, body: html`${panel("이력", history.length ? html`<table class="data"><thead><tr><th>요청자</th><th>도구</th><th>결과</th><th>처리 시각</th><th>검토자</th></tr></thead><tbody>
            ${history.map((h) => html`<tr class="clickable" tabindex="0" data-act="${h.explanation ? "approval" : ""}" data-id="${h.id}"><td class="who-cell"><b>${h.display_name || h.requested_by}</b><span class="sub">${h.department || ""}</span></td>
              <td><code>${h.server_id}.${h.tool}</code></td><td>${chip(...(APPROVAL_STATUS[h.status] || ["", h.status]))}</td>
              <td class="small">${when(h.reviewed_at || h.created_at)}</td><td class="small">${h.reviewed_by || "—"}
                ${h.explanation && h.can_revoke && ["APPROVED", "UNCONFIRMED", "EXECUTED", "NOT_EXECUTED"].includes(h.status) ? html`<button class="btn sm danger" data-act="approval-revoke" data-id="${h.id}">승인 번복</button>` : ""}</td></tr>`)}</tbody></table>` : "", { flush: true })}` },
      ],
    }),
  };
};

const IMPACT_DOMAIN = { employment: "고용·급여", credit: "신용", legal: "법적 효력", benefits: "급부", contract: "계약", service_access: "서비스 접근" };
function impactExplanation(e) {
  const types = { object: "객체", array: "목록", string: "문자", number: "숫자", boolean: "참거짓", null: "빈 값" };
  return kv([["요청 요약", e.summary], ["중대 영향", "해당"], ["영향 영역", e.impact_domains.map((d) => IMPACT_DOMAIN[d] || "—").join(" · ")],
    ["서버", e.server_id], ["도구", e.tool],
    ["인자 유형·건수", Object.entries(e.arguments).map(([k, v]) => `${types[k] || "—"} ${v}`).join(" · ")],
    ["데이터 등급", DATA_CLASS[e.data_class] || "—"], ["행위", ACTION[e.action] || "—"],
    ["정책", e.policy_id], ["선행 정책", e.basis_policy_id], ["선행 판정", DECISION[e.basis_decision]?.[1] || "—"],
    ["기존 실행 효과 복구", "미지원"]]);
}
async function showApproval(id) {
  const a = approvalRows.find((row) => row.id === id);
  if (!a) return;
  if (a.explanation) {
    const bundle = await gw(`approvals/${id}/evidence`);
    const kinds = { "call-request": "요청", "call-explanation-view": "설명 열람", "call-approve": "승인", "call-reject": "거부", "call-revoke": "번복" };
    openDrawer("중대 영향 결정 증빙", html`<button class="btn" data-act="approval-export" data-id="${id}">결정 증빙 내보내기</button>`, [
      { key: "explanation", label: "설명 증빙", body: impactExplanation(bundle.explanation) },
      { key: "history", label: "개입 이력", body: html`<table class="data"><thead><tr><th>결정</th><th>처리자</th><th>시각</th><th>근거</th></tr></thead><tbody>
        ${bundle.events.map((e) => html`<tr><td>${kinds[e.kind] || "검토"}</td><td>${e.actor_display_name || "—"}</td><td>${when(e.created_at)}</td><td>${e.reason || "—"}</td></tr>`)}</tbody></table>` },
    ]);
    return;
  }
  openDrawer(`${a.server_id}.${a.tool}`, html`<div class="row-actions">
    <button class="btn danger" data-act="reject" data-id="${a.id}">거부</button>
    ${a.own ? chip("outline", "본인 요청") : html`<button class="btn primary" data-act="approve" data-id="${a.id}">승인·실행</button>`}</div>`, [
    { key: "request", label: "요청", body: kv([["요청자", `${a.display_name || a.requested_by}${a.department ? ` · ${a.department}` : ""}`],
      ["엔드포인트", a.client?.workstation], ["하네스", a.client?.harness?.name ? harnessLabel(a.client.harness.name) : a.client?.agent],
      ["요청 시각", when(a.created_at, { seconds: true })], ["만료 시각", when(a.expires_at)]]) },
    { key: "args", label: "인자", body: json(a.arguments) },
    ...((a.residency_targets || []).length ? [{ key: "locations", label: "처리·저장 위치", body: html`${a.residency_targets.map((target) => html`<h3>${target.id}</h3>${kv(locationRows(target))}`)}` }] : []),
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
  const toolFilter = query.get("server") || "";
  const tools = reg.tools.filter((t) => !toolFilter || t.server_id === toolFilter);
  const drifted = servers.filter((s) => s.status !== "READY");
  const option = (value, label) => html`<option value="${value}" ${value === toolFilter ? raw("selected") : ""}>${label}</option>`;
  return {
    html: page({
      head: head("MCP 서버", { actions: html`<button class="btn" data-act="registry-export" data-format="csv">등록부 CSV</button>
        <button class="btn" data-act="registry-export" data-format="json">등록부 JSON</button>
        <button class="btn" data-act="catalog-refresh">계약 다시 확인</button>` }),
      active: tab || "servers",
      tabs: [
        { key: "servers", label: "서버 목록", n: servers.length, body: html`<div class="stack">
          ${panel("등록된 MCP 서버", servers.length ? html`<table class="data"><thead><tr><th>서버</th><th>상태</th><th>통제</th><th>사용 기한</th><th class="num">도구</th><th class="num">24시간 호출</th></tr></thead><tbody id="server-list">
            ${servers.map((s) => html`<tr class="clickable" tabindex="0" data-act="goto" data-href="#/servers/${encodeURIComponent(s.id)}">
              <td><b>${s.display_name}</b><span class="sub mono">${s.id}</span></td>
              <td>${chip(s.status === "READY" ? "allow" : s.status === "DISABLED" ? "outline" : "alert", SERVER_STATUS[s.status] || s.status)}
                ${s.litellm_sync ? chip(s.litellm_sync.label === "동기화 완료" ? "outline" : "alert", s.litellm_sync.label) : ""}
                ${s.lifecycle && s.lifecycle !== "OPERATING" ? chip(s.lifecycle === "RETIRED" ? "block" : "alert", LIFECYCLE[s.lifecycle] || s.lifecycle) : ""}
                ${s.registration?.risk_review?.state === "grace" ? chip("alert", "재평가 필요") : ""}
                ${s.registration?.supplier_assurance?.support_end ? chip(supportStatus(s.registration.supplier_assurance.support_end) === "지원 종료 경과" ? "block" :
                  supportStatus(s.registration.supplier_assurance.support_end) === "지원 종료 임박" ? "alert" : "outline", supportStatus(s.registration.supplier_assurance.support_end)) : ""}
                <span class="sub">${s.deployment === "provider" ? "제공자 운영" : "사내 운영"}</span></td>
              <td>${s.plane ? statusPair(s.plane) : NONE}</td>
              <td>${validityChip(s.registration) || NONE}</td>
              <td class="num">${s.tools ?? reg.tools.filter((t) => t.server_id === s.id && t.enabled).length}</td><td class="num">${s.calls || 0}</td></tr>`)}</tbody></table><p class="empty" data-list-empty="server-list" hidden>검색 결과 없음</p>`
            : html`${empty("등록된 MCP 서버 없음")}<div class="row-actions center"><a class="btn primary" href="#/intake">도입 신청</a></div>`,
            { flush: true, tools: listToolbar("server-list", "서버 검색") })}
        </div>` },
        { key: "tools", label: "도구", n: reg.tools.length, body: html`<div class="stack">
          ${panel("도구", html`<table class="data"><thead><tr><th>서버</th><th>도구</th><th>행위</th><th>상태</th></tr></thead><tbody>
            ${tools.map((t) => html`<tr><td class="mono">${t.server_id}</td><td><code>${t.name}</code></td>
              <td>${chip({ r: "allow", w: "alert", x: "block" }[t.action] || "", ACTION[t.action] || t.action)}</td>
              <td>${!t.enabled ? chip("outline", "미승인") : t.contract_ok ? chip("allow", "계약 일치") : chip("alert", "계약 불일치")}</td></tr>`)}
            </tbody></table>`, { flush: true, sub: `${tools.length}개`,
            tools: html`<select data-act-change="tool-filter" aria-label="서버">${option("", "모든 서버")}${reg.servers.map((s) => option(s.id, s.id))}</select>` })}</div>` },
        { key: "contract", label: "계약", n: drifted.length, hot: drifted.length > 0, body: panel("서버 상태", html`<table class="data"><thead><tr><th>서버</th><th>상태</th><th>사유</th><th>마지막 확인</th><th></th></tr></thead><tbody>
            ${servers.map((s) => html`<tr><td><b>${s.display_name}</b><span class="sub mono">${s.id}</span></td>
              <td>${chip({ READY: "allow", DRIFT: "alert" }[s.status] || "block", SERVER_STATUS[s.status] || s.status)}</td>
              <td class="small clip">${s.status_reason || "—"}</td><td class="small">${ago(s.last_seen_at)}</td>
              <td class="num">${s.status === "DRIFT" && !s.registration ? html`<button class="btn sm primary" data-act="approve-contract" data-id="${s.id}">승인본 갱신</button>` : ""}</td></tr>`)}
            </tbody></table>`, { flush: true }) },
      ],
    }),
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
      ${s.litellm_sync ? chip(s.litellm_sync.label === "동기화 완료" ? "outline" : "alert", s.litellm_sync.label) : ""}
      ${chip(s.lifecycle === "OPERATING" ? "outline" : "block", LIFECYCLE[s.lifecycle] || s.lifecycle)}
      ${chip("outline", s.deployment === "provider" ? "제공자 운영" : "사내 운영")}
      ${validityChip(registration)}
      ${s.status === "DRIFT" && !registration ? html`<button class="btn sm primary" data-act="approve-contract" data-id="${s.id}">승인본 갱신</button>` : ""}
      ${s.lifecycle !== "RETIRED" ? html`<button class="btn sm" type="button" data-act="server-check" data-id="${s.id}">연결 확인</button>` : ""}
      ${registration && !registration.intake_id ? chip("block", "도입 신청 없음 · 차단") : ""}
      ${registration && tools.some((t) => registration.tools?.[t.name] && !registration.tool_reviews?.[t.name]) ? html`<button class="btn sm primary" type="button" data-act="tool-scope" data-id="${s.id}">범위 심사</button>` : ""}
      ${registration?.intake_id && s.deployment === "provider" ? html`<button class="btn sm primary" type="button" data-act="residency-review" data-id="${s.id}">위치 심사</button>` : ""}
      ${registration?.intake_id ? html`<button class="btn sm" type="button" data-act="server-audience" data-id="${s.id}">사용 대상</button>` : ""}
      ${registration ? html`<button class="btn sm danger" type="button" data-act="server-deregister" data-id="${s.id}">등록 해제</button>` : ""}</div>
    ${s.status_reason && s.status !== "READY" ? html`<p class="note warn">${s.status_reason}</p>` : ""}`, [
    { key: "info", label: "개요", body: kv([["ID", html`<code>${s.id}</code>`], ["게이트웨이 경로", html`<code>/mcp/${s.id}/</code>`],
      ["패키지", html`<code>${s.source_ref || `${s.package}@${s.version}`}</code>`], ["원격 주소", html`<code>${s.endpoint}</code>`],
      ["공급자", s.supplier], ["라이선스", s.license], ["하위 시스템", downstreamText(s.downstream)],
      ...(registration?.supplier_assurance ? assuranceRows(registration.supplier_assurance) : []),
      ...locationRows(s.residency),
       ...(registration?.residency_review ? [["위치 심사", `${registration.residency_review.reviewed_by} · ${when(registration.residency_review.reviewed_at)}`]] : []),
      ...(registration?.risk_assessment ? [["위험 등급", chip(...RISK_TIER[registration.risk_assessment.tier])],
        ["처리 개인정보", RISK_CHOICES.personal_data[registration.risk_assessment.input.personal_data]],
        ["외부 전송", registration.risk_assessment.input.external_transfer ? "있음" : "없음"],
        ["실행 권한", RISK_CHOICES.permission[registration.risk_assessment.input.permission]],
        ["예상 사용자 수", `${registration.risk_assessment.input.users}명`],
        ["자율성", RISK_CHOICES.autonomy[registration.risk_assessment.input.autonomy]],
        ["승인자", (registration.risk_assessment.approvers || []).join(", ")],
        ["승인 방식", registration.risk_assessment.solo_mode === true ? "단독 운영" : registration.risk_assessment.solo_mode === false ? "일반 운영" : "—"]]
        : registration?.risk_review ? [["위험 등급", html`${chip(...RISK_TIER[registration.risk_review.tier])}<span class="sub">영향평가 입력 없음</span>`],
          ["재평가 기한", registration.risk_review.until.slice(0, 10)]] : []),
      ["사용 기한", registration ? `${when(registration.valid_until)} · ${DATA_CLASS[registration.data_class] || ""}` : ""],
      ...(registration?.intake_id ? [["사용 대상", audienceText(registration.allowed_principals)]] : []),
      ["등록", registration ? `${registration.registered_by} · ${when(registration.registered_at)}` : ""],
      ["마지막 확인", s.last_seen_at ? `${when(s.last_seen_at)} · ${ago(s.last_seen_at)}` : ""]]) },
    { key: "tools", label: "도구", n: tools.length, body: html`<table class="data"><thead><tr><th>도구</th><th>행위</th><th>상태</th><th>마지막 사용</th><th>기한</th><th>이용 상태</th></tr></thead><tbody>
      ${tools.map((t) => { const [lastUse, deadline, sunsetStatus] = toolSunsetRow(id, t.name); return html`<tr><td><code>${t.name}</code></td><td>${chip({ r: "allow", w: "alert", x: "block" }[t.action] || "", ACTION[t.action] || t.action)}</td>
        <td>${!t.enabled ? (registration?.tools?.[t.name] ? chip("block", "범위 미심사") : chip("outline", "미승인")) : t.contract_ok ? chip("allow", "일치") : chip("alert", "불일치")}</td>
        <td>${lastUse}</td><td>${deadline}</td><td>${sunsetStatus}</td></tr>`; })}</tbody></table>` },
    ...(registration ? [{ key: "scope", label: "범위", body: scopeTable(registration.tools, registration.tool_reviews, registration.data_class, registration.intake_id ? s.id : null, registration.address_tools || []) }] : []),
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
  approved: ["outline", "승인 · 기록만"], default: ["outline", "재검토"] };
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
  : html`<button class="btn sm danger" data-act="connector-deny" data-key="${g.key}" data-name="${connectorName(g)}">거부</button>
    ${g.state === "default" ? "" : html`<button class="btn sm primary" data-act="connector-decide" data-key="${g.key}" data-decision="approved">승인</button>`}`;
const connectorControlChip = (all, key) => { const c = connectorControl(all, key); return c ? chip(c[0], c[1]) : NONE; };
let connectorGroups = [], connectorItems = [];

// Which control governs each integration and endpoint, with what evidence.
const STATE_DECISION = { gateway_enforced: "Allow", endpoint_enforced: "Allow", vendor_enforced: "",
  observed_only: "Alert", unknown_not_enrolled: "", bypass_possible: "Block" };
const COV_LISTS = { entries: "entries", listeners: "listeners", os_events: "os-events" };
const covPaging = Object.fromEntries(Object.keys(COV_LISTS).map((key) => [key, { cursors: [null], index: 0, next: null }]));
const resetCoveragePaging = () => Object.values(covPaging).forEach((state) => Object.assign(state, { cursors: [null], index: 0, next: null }));
async function covPage(inv, list) {
  const state = covPaging[list], first = { ...inv.pages[list], rows: inv[list] };
  const page = !state.index ? first : await gw(`endpoint/inventory/${COV_LISTS[list]}?${new URLSearchParams({
    limit: first.limit, cursor: state.cursors[state.index], ...(list === "os_events" ? {} : { classification: "shadow,retired-residue" }) })}`);
  state.next = page.next_cursor;
  return page;
}
const covPager = (list, page) => {
  const p = pager(covPaging[list], page);
  return p.count > 1 || p.hasPrev ? html`<div class="pager"><button class="pager-button" type="button" data-act="cov-page" data-list="${list}" data-dir="-1" aria-label="이전 페이지" title="이전 페이지" ${p.hasPrev ? "" : raw("disabled")}>‹</button>
    <span>${p.number} / ${p.count}</span>
    <button class="pager-button" type="button" data-act="cov-page" data-list="${list}" data-dir="1" aria-label="다음 페이지" title="다음 페이지" ${p.hasNext ? "" : raw("disabled")}>›</button></div>` : "";
};
const covCount = (page, shown) => { const c = countView(page, shown); return { sub: c.label, end: c.truncated ? chip("alert", `일부 표시 ${c.shown}건`) : "" }; };
const evidenceChip = (state) => { const v = provenanceView({ state }); return v.state === "unreported" ? NONE : chip(v.tone, v.label); };
const recordRow = (kind, id, cells) => html`<tr class="clickable" tabindex="0" data-act="endpoint-record" data-kind="${kind}" data-id="${id}">${cells}</tr>`;
ROUTES.coverage = async (_, tab, query) => {
  const [p, inv, conn] = await Promise.all([planes(), gw("endpoint/inventory?classification=shadow,retired-residue"), api("/api/connectors")]);
  const [entriesPage, listenersPage, eventsPage] = await Promise.all([covPage(inv, "entries"), covPage(inv, "listeners"), covPage(inv, "os_events")]);
  connectorGroups = conn.items;
  connectorItems = p.items;
  const items = dedupeItems(p.items);
  integrationItems = items;
  const state = query.get("state") || "", cls = query.get("class") || "", q = (query.get("q") || "").toLowerCase();
  const rows = items.filter((i) => (!state || i.state === state) && (!cls || i.class === cls)
    && (!q || `${i.name} ${i.target || ""} ${(i.owners || []).join(" ")}`.toLowerCase().includes(q)));
  const count = (s) => items.filter((i) => i.state === s).length;
  const review = conn.summary.pending + conn.summary.expired;
  const coverageSelect = (key, label, choices, cur) => html`<label class="list-search">${label}<select data-coverage-filter="${key}" aria-label="${label}">
    <option value="">전체</option>${Object.entries(choices).map(([k,v]) => html`<option value="${k}" ${k === cur ? raw("selected") : ""}>${Array.isArray(v) ? v[1] : v}</option>`)}</select></label>`;
  const shadowRows = entriesPage.rows.filter((e) => e.classification !== "registered");
  const listenerView = listenerCoverage(listenersPage.rows);
  const observations = observationRows(inv.agents);
  const osEvents = eventsPage.rows;
  const shadowTotal = entriesPage.total + listenersPage.total + eventsPage.total;
  return {
    html: page({
      head: head("통제 범위", { actions: html`<button class="btn" type="button" data-act="connector-policy">커넥터 정책 내보내기</button>` }),
      kpis: kpiStrip([["게이트웨이 통제", count("gateway_enforced"), "allow", "#/coverage?t=items&state=gateway_enforced"],
        ["엔드포인트 통제", count("endpoint_enforced"), "allow", "#/coverage?t=items&state=endpoint_enforced"],
        ["벤더 통제", count("vendor_enforced"), "restrict", "#/coverage?t=items&state=vendor_enforced"],
        ["관찰 및 미등록", count("observed_only") + count("unknown_not_enrolled"), "alert", "#/coverage?t=items&state=observed_only"],
        ["조직 통제 의존", count("bypass_possible"), "block", "#/coverage?t=items&state=bypass_possible"]]),
      active: tab || "items",
      tabs: [
        { key: "items", label: "MCP·커넥터", n: items.length, body: html`<div class="stack">
          ${panel("MCP·커넥터·플러그인", html`<table class="data"><thead><tr><th>항목</th><th>분류</th><th>상태</th><th>승인</th><th class="num">우회 경로</th><th>발견</th></tr></thead><tbody>
            ${rows.map((i) => html`<tr class="clickable" tabindex="0" data-act="integration" data-key="${i.key}">
              <td><b>${i.name}</b><span class="sub">${entityRef(i.target || "", 48)}</span>${i.pcs > 1 ? html`<span class="sub">엔드포인트 ${i.pcs}대</span>` : ""}</td>
              <td class="small">${INTEGRATION_CLASS[i.class] || i.class}${i.harness ? html`<span class="sub">${i.harness === "claude" ? "Claude Code" : "Codex"}</span>` : ""}</td>
              <td>${statusPair(i)}</td>
              <td class="small">${approvalLabel(i.approval?.state)}${i.approval?.expires_at ? html`<span class="sub">${when(i.approval.expires_at)}까지</span>` : ""}</td>
              <td class="num">${(i.bypass || []).length ? html`<span class="bad-text">${i.bypass.length}</span>` : NONE}</td>
              <td class="small">${i.discovered_from}${i.discovered_at ? html`<span class="sub">${when(i.discovered_at)}</span>` : ""}</td></tr>`)}
            </tbody></table>${rows.length ? "" : empty("조건에 맞는 항목 없음")}`, { flush: true,
            tools: html`<input type="search" data-coverage-search maxlength="80" value="${query.get("q") || ""}" placeholder="이름·대상·사용자" aria-label="항목 검색" />
              ${coverageSelect("state", "상태", CONTROL_STATE, state)}
              ${coverageSelect("class", "연동 유형", INTEGRATION_CLASS, cls)}<span class="small muted">${rows.length}/${items.length}건</span>` })}</div>` },
        { key: "devices", label: "엔드포인트", n: p.devices.length, hot: p.summary.devices.bypass_possible > 0, body: panel("엔드포인트",
          html`<table class="data"><thead><tr><th>엔드포인트</th><th>사용자</th><th>플랫폼</th><th>상태</th><th>관리 계정</th><th>점검</th><th>우회 경로</th></tr></thead><tbody>
            ${p.devices.map((d) => html`<tr><td>${d.endpoint_id ? entityRef(d.endpoint_id) : NONE}<span class="sub">${d.hostname || ""}${d.account ? ` · ${d.account}` : ""}</span></td>
              <td>${d.owner || "—"}</td><td>${PLATFORM[d.platform] || d.platform || "—"}</td><td>${statusPair(d)}</td>
              <td>${d.account_state ? controlChip(d.account_state) : NONE}</td>
              <td>${checksChip(d.checks)}</td>
              <td class="small">${(d.bypass || []).length ? html`<div class="pill-list">${d.bypass.map((b) => chip("block", b))}</div>` : NONE}
                ${denialCount(d) ? html`<span class="sub">엔드포인트 차단 24시간 ${denialCount(d)}</span>` : ""}</td></tr>`)}
            </tbody></table>${p.devices.length ? "" : empty("엔드포인트 없음")}`, { flush: true }) },
        { key: "shadow", label: "미등록·잔존", n: shadowTotal,
          hot: entriesPage.total + listenersPage.total > 0, body: html`<div class="stack">
          ${panel("엔드포인트 MCP 설정", html`<table class="data"><thead><tr><th>엔드포인트</th><th>설정 파일</th><th>서버</th><th>연결</th><th>분류</th><th>출처</th><th>증거</th></tr></thead><tbody>
            ${shadowRows.map((e) => recordRow("config", e.id, html`<td>${entityRef(e.endpoint_id)}</td><td class="small mono">${e.config_path}</td>
              <td><b>${e.server_label}</b>${e.registry_name ? html`<span class="sub">${e.registry_name}</span>` : ""}</td>
              <td class="small mono clip">${e.transport} ${short(e.endpoint_ref, 60)}</td><td>${chip(...(ENDPOINT_CLASS[e.classification] || ["outline", "확인 불가"]))}</td>
              <td class="small">${originLabel(e.origin)}</td><td>${evidenceChip(e.provenance_state)}</td>`))}
            </tbody></table>${shadowRows.length ? "" : empty("미등록·잔존 설정 없음")}${covPager("entries", entriesPage)}`, { flush: true, ...covCount(entriesPage, shadowRows.length) })}
          ${panel("엔드포인트 수신기", html`<table class="data"><thead><tr><th>시각</th><th>엔드포인트</th><th>출처</th><th>주소·프로세스</th><th>MCP 여부</th><th>분류</th><th>신선도</th><th>증거</th></tr></thead><tbody>
            ${listenerView.rows.map((l) => recordRow("listener", l.id, html`<td class="small">${when(l.observedAt)}</td><td>${entityRef(l.endpointId)}<span class="sub">${l.hostname}</span></td>
              <td>${l.source}<span class="sub">${l.origin}</span>${l.scanStatusLabel ? html`<span class="sub">수집 ${l.scanStatusLabel}</span>` : ""}</td>
              <td class="small mono">${l.address}${l.port ? `:${l.port}` : ""}${l.processName !== "—" ? html`<span class="sub">${l.processName}</span>` : ""}${l.serverName !== "—" ? html`<span class="sub">${l.serverName}</span>` : ""}</td>
              <td>${chip(l.evidence === "MCP 응답 확인" ? "plain" : l.evidence === "MCP로 추정" ? "alert" : "outline", l.evidence)}</td>
              <td>${chip(l.classification === "폐기 잔존" ? "alert" : l.classification === "미등록" ? "block" : "outline", l.classification)}</td>
              <td>${chip(l.freshness === "stale" ? "alert" : l.freshness === "fresh" ? "plain" : "outline", l.freshnessLabel)}</td><td>${evidenceChip(l.provenance)}</td>`))}
            </tbody></table>${listenerView.total ? "" : empty("수신기 관측 없음")}${covPager("listeners", listenersPage)}`, { flush: true, ...covCount(listenersPage, listenerView.total) })}
          ${panel("관측 수집 상태", html`<table class="data"><thead><tr><th>엔드포인트</th><th>관측 범위</th><th>상태</th><th>신선도</th><th>보고 시각</th><th>마지막 성공</th><th class="num">수신 건수</th><th>오류</th></tr></thead><tbody>
            ${observations.map((o) => html`<tr><td>${entityRef(o.endpointId)}</td><td>${o.channelLabel}<span class="sub">엔드포인트 보고</span></td>
              <td>${chip(o.tone, o.stateLabel)}</td><td>${chip(o.freshness === "stale" ? "alert" : o.freshness === "fresh" ? "plain" : "outline", o.freshnessLabel)}</td>
              <td class="small">${when(o.reportedAt, { seconds: true })}</td><td class="small">${when(o.lastSuccessAt, { seconds: true })}</td>
              <td class="num">${o.acceptedCount ?? "—"}</td><td>${o.hasError ? chip("alert", "오류 있음") : NONE}</td></tr>`)}
            </tbody></table>${observations.length ? "" : empty("수집 상태 없음")}`, { flush: true,
            sub: `전체 ${observations.length}건` })}
          ${panel("엔드포인트 차단", html`<table class="data"><thead><tr><th>시각</th><th>엔드포인트</th><th>종류</th><th>분류</th><th>대상</th><th>증거</th></tr></thead><tbody>
            ${osEvents.map((e) => recordRow("os-event", e.id, html`<td>${when(e.observed_at)}</td><td>${entityRef(e.endpoint_id)}</td>
              <td>${chip("block", e.kind === "network-denied" ? "네트워크 차단" : e.kind === "execution-denied" ? "실행 차단" : "차단 기록")}</td>
              <td>${chip(...denialClass(e.denial_class))}</td>
              <td class="mono small">${osEventTarget(e)}${e.details?.parent_executable ? html`<span class="sub">${e.details.parent_executable}</span>` : ""}</td>
              <td>${evidenceChip(e.provenance_state)}</td>`))}
            </tbody></table>${osEvents.length ? "" : empty("수신된 차단 기록 없음")}${covPager("os_events", eventsPage)}`, { flush: true, ...covCount(eventsPage, osEvents.length) })}</div>` },
        { key: "vendor", label: "벤더 커넥터", n: review, hot: review > 0, body: panel("하네스 커넥터·앱·기능",
          conn.items.length ? html`<table class="data"><thead><tr><th>이름</th><th>하네스</th><th>종류</th><th class="num">사용 엔드포인트</th><th>승인</th><th>통제</th><th>벤더 콘솔</th><th></th></tr></thead><tbody>
            ${conn.items.map((g) => { const vendor = items.find((i) => i.item_key === g.key)?.vendor_control; return html`<tr class="clickable" tabindex="0" data-act="connector" data-key="${g.key}">
              <td><b>${connectorName(g)}</b><span class="sub mono">${connectorTarget(g)}</span></td>
              <td>${chip("plain", g.harness === "claude" ? "Claude Code" : "Codex")}</td>
              <td class="small">${g.kinds.map((k) => CONNECTOR_KIND[k] || k).join(" · ")}</td>
              <td class="num">${g.active_pcs}<span class="sub">${g.people}명</span></td>
              <td>${connectorState(g)}${g.violation ? chip("block", "미승인 사용") : ""}</td>
              <td>${connectorControlChip(connectorItems, g.key)}</td>
              <td class="small">${vendor ? html`${chip("restrict", VENDOR_CONSOLE[vendor.console_state] || vendor.console_state)}<span class="sub">${vendor.verified_by} · ${when(vendor.verified_at)}</span>` : NONE}</td>
              <td class="num nowrap">${connectorButtons(g)}</td></tr>`; })}</tbody></table>`
            : empty("보고된 커넥터 없음"), { flush: true, sub: conn.review_days ? `검토 기한 ${conn.review_days}일` : "" }) },
      ],
    }),
  };
};

const VENDOR_CONSOLE = { blocked: "차단", limited: "제한 허용", allowed: "허용", unknown: "확인 불가" };
const CHECK_LABEL = { apparmor_enforcing: "실행 통제", nftables_active: "네트워크 통제", firewall_enforcing: "네트워크 통제", pf_enforcing: "네트워크 통제", protected_configs: "설정 보호", ordinary_account: "일반 계정", user_command_helpers: "사용자 명령 헬퍼 없음" };
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
const MANAGED_MODE = { simple: "간편 모드", isolated: "격리 계정" };
const SIGNUP_STATUS = { pending: ["approval", "대기"], approved: ["allow", "승인"], rejected: ["block", "거부"] };
const MANAGED_EVENT = {
  "kit-issued": ["outline", "설치 파일 발급"], enrolled: ["approval", "설치 보고"], activated: ["allow", "활성화"],
  quarantined: ["block", "격리"], revoked: ["outline", "등록 해제"], "unmanaged-login-denied": ["block", "미관리 로그인 거부"],
  "token-denied": ["block", "토큰 거부"], "mcp-auth-denied": ["block", "MCP 인증 거부"],
};
const managedEventDetail = (d) => (d && (d.reason || d.note || (d.actor ? `처리 ${d.actor}` : "") || (d.expires_at ? `${when(d.expires_at)}까지` : ""))) || "—";

// Users and the endpoints they enrolled; what controls them is on the coverage page.
let peopleAccounts = [];
let integrationItems = [];
ROUTES.people = async (_, tab) => {
  const [{ accounts }, { accounts: deletedAccounts }, { requests: signups }, inv, o, p, identity, { suspensions }] = await Promise.all([
    api("/api/accounts"), api("/api/accounts/deleted").catch(() => ({ accounts: [] })), api("/api/signup-requests"), gw("endpoint/inventory"), gw("overview"), planes(), api("/api/identity").catch(() => ({ provider: "local", bindings: [] })),
    gw("suspensions")]);
  peopleAccounts = accounts;
  const option = (value, label, cur) => html`<option value="${value}" ${value === cur ? raw("selected") : ""}>${label}</option>`;
  const deviceState = Object.fromEntries(p.devices.filter((d) => d.endpoint_id).map((d) => [d.endpoint_id, d]));
  const harnessOf = Object.fromEntries(o.workstations.map((w) => [w.endpoint_id, w]));
  const managed = inv.agents.filter((a) => a.managed_state && a.managed_state !== "unmanaged");
  return {
    html: page({
      head: head("사용자·엔드포인트", { actions: html`<button class="btn" type="button" data-act="device-issue">엔드포인트 등록</button><button class="btn primary" type="button" data-act="account-invite">사용자 초대</button>` }),
      kpis: kpiStrip([["최근 15분 보고", inv.coverage.reporting_recently],
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
                <button class="btn sm" data-act="suspend-open" data-token="${a.token}" data-name="${a.display_name}">MCP 이용 중지</button>
                <button class="btn sm" data-act="suspend-all" data-token="${a.token}" data-name="${a.display_name}">전체 중지</button>
                <button class="btn sm" data-act="resume-all" data-token="${a.token}" data-name="${a.display_name}">전체 재개</button>
                ${a.user_id !== "root" ? html`<button class="btn sm danger" data-act="account-delete" data-id="${a.user_id}" data-name="${a.display_name}">삭제</button>` : ""}`}</td></tr>`)}
          </tbody></table><p class="empty" data-list-empty="account-list" hidden>검색 결과 없음</p>`, { flush: true, tools: listToolbar("account-list", "이름·이메일·부서 검색") }) },
        { key: "deleted", label: "삭제된 사용자", n: deletedAccounts.length,
          body: panel("삭제된 사용자", html`<table class="data"><thead><tr><th>이름</th><th>이메일</th><th>역할</th><th>부서</th><th>삭제 시각</th><th></th></tr></thead><tbody>
            ${deletedAccounts.map((a) => html`<tr><td><b>${a.display_name}</b></td><td class="small">${a.email}</td>
              <td>${ROLE[a.role] || a.role}</td><td>${a.department || "—"}</td>
              <td class="small">${when(a.status_changed_at)}<span class="sub">${a.status_changed_by || "—"}</span></td>
              <td class="num"><button class="btn sm primary" type="button" data-act="account-restore" data-id="${a.user_id}" data-name="${a.display_name}">복구</button></td></tr>`)}
            </tbody></table>${deletedAccounts.length ? "" : empty("삭제된 사용자 없음")}`, { flush: true }) },
        { key: "devices", label: "엔드포인트", n: inv.agents.length, body: html`<div class="stack">
          ${panel("엔드포인트", html`<table class="data"><thead><tr><th>엔드포인트</th><th>사용자</th><th>하네스</th><th>상태</th><th>마지막 보고</th><th></th></tr></thead><tbody>
            ${inv.agents.map((a) => html`<tr><td>${entityRef(a.endpoint_id)}<span class="sub">${PLATFORM[String(a.platform || "").toLowerCase()] || a.platform || ""}</span></td><td>${a.owner_name || harnessOf[a.endpoint_id]?.display_name || "—"}</td>
              <td>${harnessOf[a.endpoint_id]?.harness ? chip("plain", harnessLabel(harnessOf[a.endpoint_id].harness)) : NONE}</td>
              <td>${deviceState[a.endpoint_id] ? statusPair(deviceState[a.endpoint_id]) : chip("outline", "관찰만")}
                ${a.managed_state && a.managed_state !== "unmanaged" ? html`<span class="sub">${MANAGED_STATE[a.managed_state] || a.managed_state} · ${MANAGED_MODE[deviceState[a.endpoint_id]?.mode] || "—"}</span>` : ""}</td>
              <td class="small">${ago(a.last_seen_at)}</td>
              <td class="num nowrap">${a.status === "revoked" ? chip("outline", "등록 해제됨") : html`<button class="btn sm danger" type="button" data-act="device-revoke" data-id="${a.endpoint_id}">등록 해제</button>`}
                ${["pending", "quarantined"].includes(a.managed_state) && a.policy_hash ? html`<button class="btn sm primary" type="button" data-act="device-activate" data-id="${a.endpoint_id}" data-hash="${a.policy_hash}">활성화</button>` : ""}</td></tr>`)}
            </tbody></table>${inv.agents.length ? "" : empty("엔드포인트 없음")}`, { flush: true,
            tools: html`<label>새 PC 활성화<select data-act-change="endpoint-auto" aria-label="새 PC 활성화">${option("on", "자동", inv.settings?.auto_activate === false ? "off" : "on")}${option("off", "관리자 확인", inv.settings?.auto_activate === false ? "off" : "on")}</select></label>` })}</div>` },
        { key: "suspensions", label: "이용 중지", n: suspensions.filter((x) => !x.resumed_at).length,
          body: panel("이용 중지", html`<table class="data"><thead><tr><th>사용자</th><th>서버</th><th>사유</th><th>중지</th><th>해제 예정</th><th>상태</th><th>재개</th><th></th></tr></thead><tbody>
            ${suspensions.map((x) => html`<tr><td>${x.display_name || "—"}</td><td>${x.server_name || x.server_id}</td><td class="small">${x.reason}</td>
              <td class="small">${when(x.suspended_at)}<span class="sub">${x.suspended_by || "—"}</span></td>
              <td class="small">${x.expires_at ? when(x.expires_at) : "—"}</td>
              <td>${x.resumed_at ? chip("allow", "재개") : chip("block", "중지")}</td>
              <td class="small">${x.resumed_at ? html`${when(x.resumed_at)}<span class="sub">${x.resumed_by || "—"} · ${x.resume_note || "—"}</span>` : "—"}</td>
              <td class="num">${x.resumed_at ? "" : html`<button class="btn sm primary" data-act="suspend-resume" data-id="${x.id}" data-name="${x.display_name || ""}" data-server="${x.server_name || x.server_id}">재개</button>`}</td></tr>`)}
            </tbody></table>${suspensions.length ? "" : empty("중지한 이용 없음")}`, { flush: true }) },
        { key: "signups", label: "가입 요청", n: signups.filter((s) => s.status === "pending").length,
          body: panel("가입 요청", html`<table class="data"><thead><tr><th>아이디</th><th>이름</th><th>요청</th><th>상태</th><th></th></tr></thead><tbody>
          ${signups.map((s) => html`<tr><td class="mono">${s.username}</td><td>${s.display_name}</td><td>${when(s.requested_at)}</td>
            <td>${chip(...(SIGNUP_STATUS[s.status] || ["", s.status]))}</td>
            <td class="num nowrap">${s.status === "pending" ? html`<button class="btn sm danger" data-act="signup-reject" data-id="${s.id}">거부</button>
              <button class="btn sm primary" data-act="signup-approve" data-id="${s.id}">승인</button>` : ""}</td></tr>`)}
          </tbody></table>${signups.length ? "" : empty("가입 요청 없음")}`, { flush: true }) },
        { key: "managed", label: "연결 이력", n: (inv.managed_events || []).length,
          body: panel("연결 이력", html`<table class="data"><thead><tr><th>시각</th><th>사용자·엔드포인트</th><th>내용</th><th>사유</th></tr></thead><tbody>
            ${(inv.managed_events || []).map((e) => html`<tr><td>${when(e.observed_at)}</td><td>${e.owner_name || "사용자 확인 불가"}<span class="sub mono">${e.endpoint_id || "—"}</span></td>
              <td>${chip(...(MANAGED_EVENT[e.kind] || ["", e.kind]))}</td><td class="small">${managedEventDetail(e.detail)}</td></tr>`)}</tbody></table>
            ${(inv.managed_events || []).length ? "" : empty("연결 이력 없음")}`, { flush: true }) },
        ...(identity.provider === "oidc" ? [{ key: "sso", label: "SSO", n: identity.bindings.length, body: html`<div class="stack">
          ${panel("SSO", kv([["로그인 방식", identity.label || "SSO"], ["상태", identity.configured ? "사용" : "설정 필요"], ["발급자", identity.issuer || "—"]]),
            { end: identity.configured ? html`<button class="btn sm primary" data-act="identity-bind">SSO 계정 연결</button>` : "" })}
          ${panel("연결된 SSO 계정", identity.bindings.length ? html`<table class="data"><thead><tr><th>사용자</th><th>SSO 계정</th><th>연결</th><th></th></tr></thead><tbody>${identity.bindings.map((b) => html`<tr><td>${b.principal}</td><td class="mono">${b.subject}</td><td>${b.linked_by}<span class="sub">${when(b.linked_at)}</span></td><td class="num"><button class="btn sm danger" data-act="identity-unbind" data-id="${b.id}">연결 해제</button></td></tr>`)}</tbody></table>` : empty("연결된 계정 없음"), { flush: true })}</div>` }] : []),
      ],
    }),
  };
};

function requestedToolList(tools) {
  return html`<div class="tool-list">${tools.map((t) => html`<label class="check">
    <input type="checkbox" name="requested_tool" value="${t.name}" checked />
    <span><b class="mono">${t.name}</b>${t.description ? html`<span class="sub">${t.description}</span>` : ""}</span></label>`)}</div>`;
}

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
  const title = (section) => t(section.querySelector(":scope > header > h2")?.textContent ?? "");
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
    for (const key of ["list", "approved"]) {
      patchIntakePanel(view, next, key);
      const oldCount = view.querySelector(`#p-tab-${key} .n`);
      const newCount = next.querySelector(`#p-tab-${key} .n`);
      if (oldCount && newCount) oldCount.replaceWith(newCount);
    }
    intakeRendered = markup;
  } finally { intakeRefreshing = false; }
}
function catalogResults(data) {
  const requests = data.requests || [], registry = data.registry || [];
  return html`${requests.length ? html`<table class="data"><thead><tr><th>MCP</th><th>신청자</th><th>상태</th>${viewer.admin ? html`<th>사내 저장소</th>` : ""}</tr></thead><tbody>
    ${requests.map((r) => html`<tr><td><b>${r.display_name}</b><span class="sub mono">${r.endpoint_url || [r.repository_url, r.repository_path].filter(Boolean).join("/") || ""}</span></td>
      <td>${r.submitted_by_name}</td><td>${chip(...(INTAKE_STATUS[r.status] || ["", r.status]))}</td>
      ${viewer.admin ? html`<td>${r.internal_repo_url ? html`<a href="${sameSite(r.internal_repo_url)}" target="_blank" rel="noopener noreferrer">열기 ↗</a>` : NONE}</td>` : ""}</tr>`)}</tbody></table>` : empty(data.query ? "조건에 맞는 신청 없음" : "신청 없음")}
    ${registry.length ? html`<p class="small muted">등록된 MCP: ${registry.map((r) => r.display_name).join(", ")}</p>` : ""}`;
}
const CONSENT_STATUS = { PENDING: ["alert", "확인 필요"], GRANTED: ["allow", "동의"], DENIED: ["block", "거부"],
  REVOKED: ["outline", "철회"], EXPIRED: ["outline", "만료"] };
ROUTES.consent = async (_, tab) => {
  const { consents } = await api("/api/consents");
  const pending = consents.filter((c) => c.status === "PENDING");
  const decided = consents.filter((c) => c.status !== "PENDING");
  const servers = new Map();
  for (const c of pending) {
    if (!servers.has(c.server_id)) servers.set(c.server_id, []);
    servers.get(c.server_id).push(c);
  }
  badges.consent = servers.size;
  const button = (c, decision, label, tone = "") => html`<button class="btn sm ${tone}" data-act="consent" data-id="${c.id}" data-decision="${decision}">${label}</button>`;
  const serverButton = (id, rows, decision, label, tone) => html`<button class="btn sm ${tone}" data-act="consent-server" data-id="${id}" data-consents="${rows.map((c) => c.id).join(",")}" data-decision="${decision}">${label}</button>`;
  const table = (rows) => html`<table class="data"><thead><tr><th>도구</th><th>데이터 등급</th><th>목적</th><th>상태</th><th>시각</th><th></th></tr></thead><tbody>
    ${rows.map((c) => html`<tr><td><code>${c.server_id}.${c.tool_name}</code></td><td>${DATA_CLASS[c.grade] || NONE}</td>
      <td>${c.purpose || NONE}<span class="sub">외부 목적지 ${destinationText(c.terms?.destinations)}${c.terms?.inputs ? ` · 입력 ${c.terms.inputs.join(", ") || "없음"}` : ""}</span></td>
      <td>${chip(...(CONSENT_STATUS[c.status] || ["", "—"]))}</td>
      <td class="small">${when(c.decided_at || c.requested_at)}${c.status === "GRANTED" && c.expires_at ? html`<span class="sub">${when(c.expires_at)}까지</span>` : ""}</td>
      <td class="num nowrap">${c.status === "PENDING" ? ""
        : c.status === "GRANTED" ? button(c, "revoke", "철회") : ["DENIED", "REVOKED"].includes(c.status) ? button(c, "grant", "동의") : ""}</td></tr>`)}
    </tbody></table>`;
  return page({
    head: head("이용 동의"),
    active: tab || "pending",
    tabs: [
      { key: "pending", label: "확인 필요", n: servers.size, hot: servers.size > 0,
        body: servers.size ? html`<div class="stack">${[...servers].map(([id, rows]) => panel(id, html`
          <div class="row-actions">${chip("alert", `요청 ${rows.length}건`)}${serverButton(id, rows, "deny", "모두 거부", "danger")}${serverButton(id, rows, "grant", "모두 허용", "primary")}</div>
          ${table(rows)}`))}</div>` : empty("확인할 요청 없음") },
      { key: "history", label: "이력", n: decided.length, body: panel("동의 기록", decided.length ? table(decided) : empty("기록 없음"), { flush: true }) },
    ],
  });
};

const CONNECTION_KIND = { token: "개인 액세스 토큰", device: "인증 코드" };
ROUTES.connections = async () => {
  const { connections, available } = await api("/api/my-connections");
  const card = (c) => panel(c.name, c.connected && !c.expired ? html`<table class="data"><tbody>
      <tr><th>계정</th><td><b>${c.account}</b></td></tr>
      <tr><th>방식</th><td>${CONNECTION_KIND[c.kind] || NONE}</td></tr>
      <tr><th>연결 시각</th><td>${when(c.connected_at)}</td></tr>
      <tr><th>만료</th><td>${c.expires_at ? when(c.expires_at) : NONE}</td></tr>
      <tr><th>마지막 사용</th><td>${c.last_used_at ? when(c.last_used_at) : NONE}</td></tr></tbody></table>
    <div class="row-actions"><button class="btn danger" data-act="disconnect" data-id="${c.server_id}">연결 해제</button></div>`
    : available ? html`<form class="stack form" data-form="connect-token" data-id="${c.server_id}">
        <label>개인 액세스 토큰<input name="token" type="password" autocomplete="off" required minlength="8" maxlength="2000" /></label>
        <div class="row-actions"><button class="btn primary" type="submit">연결</button>
          ${c.device ? html`<button class="btn" type="button" data-act="connect-device" data-id="${c.server_id}">인증 코드로 연결</button>` : ""}
          <a class="btn" href="${c.token_url}" target="_blank" rel="noopener noreferrer">토큰 만들기 ↗</a></div></form>`
      : chip("block", "연결 불가"),
    { sub: c.service, end: c.expired ? chip("alert", "만료") : c.connected ? chip("allow", "연결됨") : chip("outline", "연결 안 됨") });
  return page({ head: head("내 연결"), active: "list", tabs: [{ key: "list", label: "연결",
    body: connections.length ? html`<div class="stack">${connections.map(card)}</div>` : empty("연결할 계정 없음") }] });
};

function approvedMcpTable(servers) {
  const execution = { remote: "원격", pc: "PC 격리", runtime: "솔루션 런타임" };
  return servers.length ? html`<table class="data"><thead><tr><th>서버</th><th>출처</th><th>고정 커밋</th><th>승인 기한</th><th>실행 방식</th><th></th></tr></thead>
    <tbody>${servers.map((s) => html`<tr><td><b>${s.display_name || s.server_id}</b></td><td class="mono small">${s.source_url || "—"}</td>
      <td><code>${s.commit_sha || "—"}</code></td><td class="nowrap">${when(s.valid_until)}</td><td>${execution[s.execution] || "—"}</td>
      <td>${s.source_available ? html`<button class="btn sm" data-act="mcp-source-download" data-id="${s.server_id}" data-commit="${s.commit_sha}">소스 받기</button>`
        : html`<dl><dt>MCP 주소</dt><dd><code>${s.connection_url || "—"}</code></dd></dl>`}</td></tr>`)}</tbody></table>` : empty("승인된 MCP 없음");
}

ROUTES.intake = async (_, tab) => {
  const [{ requests }, { servers }, catalog] = await Promise.all([api("/api/mcp-requests"), api("/api/approved-mcp"),
    tab === "new" ? api("/api/mcp-catalog/search") : Promise.resolve(null)]);
  return {
    html: page({
      head: head("도입 신청"),
      active: tab || "list",
      tabs: [
        { key: "list", label: viewer.admin ? "전체 신청" : "내 신청", n: requests.length, body: html`<div class="stack">
          ${panel("신청", html`<table class="data"><thead><tr><th>서버</th><th>상태</th><th>종료 조건</th><th>위험 등급</th><th>신청</th>${viewer.admin ? html`<th></th>` : ""}</tr></thead><tbody>
          ${requests.map((r) => {
            return html`<tr><td><b>${r.display_name}</b><span class="sub">${entityRef(r.endpoint_url || [r.repository_url, r.repository_path].filter(Boolean).join("/"), 52)}</span>
              <span class="sub">${r.intake_kind === "remote-endpoint" ? "원격 MCP" : "소스 코드"} · ${TRANSPORT[r.requested_transport] || r.requested_transport}${r.commit_sha ? ` · ${r.commit_sha.slice(0, 12)}` : ""}</span>
              ${viewer.admin && r.internal_repo_url ? html`<a class="sub" href="${sameSite(r.internal_repo_url)}" target="_blank" rel="noopener noreferrer">사내 저장소 ↗</a>` : ""}
              ${r.registered_server_id ? html`<span class="sub">${chip("allow", "게이트웨이 등록")} <code>/mcp/${r.registered_server_id}/</code></span>` : ""}
              ${r.runtime ? html`<span class="sub">${chip(...(RUNTIME_STATUS[r.runtime.status] || ["", r.runtime.status]))}
                ${r.runtime.status === "ACTIVE" ? html`<code>${r.runtime.endpoint}</code>` : r.runtime.status === "FAILED" && r.runtime.error ? short(r.runtime.error, 80) : ""}</span>` : ""}</td>
            <td>${chip(...(INTAKE_STATUS[r.status] || ["", r.status]))}
              ${r.status === "HOLD" && r.review_note ? html`<span class="sub">${short(r.review_note, 90)}</span>` : ""}</td>
            <td class="small">${exitConclusionChip(r)}</td>
            <td class="small">${riskCell(r)}</td>
            <td class="small">${when(r.created_at)}</td>
            ${viewer.admin ? html`<td><div class="row-actions">
              ${r.own ? chip("outline", "본인 신청") : ""}
              ${r.intake_kind !== "remote-endpoint" && ["HOLD", "FAILED"].includes(r.status) ? html`<button class="btn sm" data-act="intake-queue" data-id="${r.id}">재검증</button>` : ""}
              <button class="btn sm" data-act="intake-report" data-id="${r.id}">보고서</button>
              ${["HOLD", "VALIDATION_QUEUED", "VALIDATED", "REMOTE_REVIEWED", "FAILED"].includes(r.status) ? html`<button class="btn sm danger" data-act="intake-reject" data-id="${r.id}">거부</button>` : ""}
              ${!r.own && ["HOLD", "VALIDATED", "REMOTE_REVIEWED", "APPROVED"].includes(r.status) && !r.registered_server_id
                ? html`<button class="btn sm primary" data-act="intake-one-click" data-id="${r.id}">검토</button>` : ""}</div></td>` : ""}</tr>`;
          })}</tbody></table>${requests.length ? "" : empty("신청 없음")}`, { flush: true })}</div>` },
        { key: "approved", label: "승인된 MCP", body: panel("승인된 MCP", approvedMcpTable(servers), { flush: true }) },
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
          ${field.select("data_class", "데이터 등급", DATA_CLASS, "nonimportant")}
          <fieldset data-intake-field="remote-endpoint"><legend>필요한 도구</legend>
            <button class="btn" type="button" data-act="intake-discover">도구 불러오기</button>
            <div data-requested-tools></div>
          </fieldset>
          <div class="row-actions"><button class="btn primary" type="submit">신청</button></div></form>`)}</div>` },
      ],
    }),
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

ROUTES["sbom-impact"] = async (_, _tab, query) => {
  const packageName = query.get("package") || "", versionRange = query.get("range") || "";
  const result = packageName && versionRange
    ? await api("/api/supply-chain/impact", { method: "POST", body: { package: packageName, version_range: versionRange } })
    : null;
  return html`<div class="stack">${head("공급망 영향")}
    ${panel("영향 조회", html`<form class="filters" data-form="sbom-impact">
      <label>패키지<input name="package" required maxlength="200" value="${packageName}" /></label>
      <label>판본 범위<input name="range" required maxlength="120" value="${versionRange}" placeholder=">=1.2.0 <2.0.0" /></label>
      <button class="btn primary" type="submit">조회</button></form>`)}
    ${result ? html`<section>${kpiStrip([["영향 있음", result.counts.affected], ["영향 없음", result.counts.unaffected],
      ["판단 불가", result.counts.unknown], ["자료 없음", result.counts.no_data]])}
      <div class="row-actions"><button class="btn danger" data-act="sbom-impact-stop" data-package="${packageName}"
        data-range="${versionRange}" ${result.counts.affected ? "" : raw("disabled")}>영향 서버 중지</button></div></section>` : ""}
  </div>`;
};

// The same rule agent_service.approve_mcp_request enforces; the button only mirrors it.
const termsVerified = (t) => Boolean(t?.verified_by && t?.evidence_url && Object.keys(EXIT_TERMS).every((k) => t[k] === true));
const RISK_TIER = { low: ["allow", "낮음"], medium: ["outline", "보통"], high: ["alert", "높음"], very_high: ["block", "매우 높음"] };
const RISK_CHOICES = {
  data_class: DATA_CLASS,
  personal_data: { none: "없음", general: "일반 개인정보", unique_id: "고유식별정보", sensitive: "민감정보" },
  external_transfer: { no: "없음", yes: "있음" },
  permission: { r: "읽기", w: "쓰기", x: "실행" },
  autonomy: { approve_each: "건별 확인", supervised: "감독 하 실행", autonomous: "자율 실행" },
};
function riskCell(r) {
  const k = r.risk;
  if (!k) return NONE;
  let waiting = ["HOLD", "VALIDATED", "REMOTE_REVIEWED"].includes(r.status) && viewer.admin;
  if (k.status !== "ok") return html`${chip("alert", "보류")}${waiting ? html`<span class="sub">승인 —</span>` : ""}`;
  waiting &&= k.required > 1;
  return html`${chip(...RISK_TIER[k.tier])}${waiting ? html`<span class="sub">승인 ${k.approvals}/${k.required}</span>` : ""}`;
}
function riskView(risk) {
  if (!risk) return empty("기록 없음");
  return html`<div class="stack">
    ${kv([["위험 등급", risk.status === "ok" ? chip(...RISK_TIER[risk.tier]) : chip("alert", "보류")],
      ["산정 점수", risk.status === "ok" ? String(risk.score) : "—"], ["적용 규칙", (risk.floors || []).join(", ") || "—"],
      ["입력 상태", (risk.messages || []).join(" / ")]])}
    ${panel("영향평가 입력 자료", html`<table class="data"><thead><tr><th>항목</th><th>값</th><th>서식 항목</th></tr></thead><tbody>
      ${(risk.package || []).map((p) => html`<tr><td>${p.item}</td><td>${p.value}</td><td class="small">${p.form}</td></tr>`)}</tbody></table>`, { flush: true })}</div>`;
}
const supportStatus = (date) => !date ? "" : date < new Date().toISOString().slice(0, 10) ? "지원 종료 경과" :
  date <= new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10) ? "지원 종료 임박" : "지원 중";

const ASSURANCE_LABELS = { legal_entity: "법인명", supplier_contact: "연락처", security_contact: "보안 연락처",
  vulnerability_policy_url: "취약점 정책 주소", subprocessors: "하위 처리자", contract_basis_ref: "계약 근거",
  exit_strategy: "종료 전략", support_end: "지원 종료" };
const LOCATION_LABELS = { processing_countries: "처리 국가 코드", storage_countries: "저장 국가 코드",
  processor: "처리 주체", evidence_ref: "위치 근거", transfer_basis: "이전 근거" };

const UNCONFIRMED = "확인 안 됨";
const given = (a, key) => { const v = a?.[key]; return typeof v === "boolean" || (typeof v === "string" && v.trim() && v !== "미확인") ? v : null; };
function assuranceRows(a) {
  const text = (key) => given(a, key) ?? UNCONFIRMED, yes = (key) => given(a, key) === null ? UNCONFIRMED : a[key] ? "제출" : "미제출";
  const end = given(a, "support_end"), tone = supportStatus(end) === "지원 종료 경과" ? "block" : supportStatus(end) === "지원 종료 임박" ? "alert" : "allow";
  return [["공급자 법인명", text("legal_entity")], ["공급자 연락처", text("supplier_contact")], ["보안 연락처", text("security_contact")],
    ["지원 종료일", end ? html`${end} ${chip(tone, supportStatus(end))}` : UNCONFIRMED],
    ["취약점 공개 정책", given(a, "vulnerability_policy_url") ? html`<a href="${a.vulnerability_policy_url}" target="_blank" rel="noopener noreferrer">${a.vulnerability_policy_url}</a>` : UNCONFIRMED],
    ["하위 처리자", text("subprocessors")], ["SBOM 제출", yes("sbom_submitted")], ["VEX 제출", yes("vex_submitted")],
    ["계약 근거", text("contract_basis_ref")], ["종료 전략", text("exit_strategy")]];
}

function intakeApprovalFields(out) {
  const p = out.proposal, r = out.request, pending = out.pending;
  const scope = pending?.scope;
  const selected = scope?.tools || Object.keys(p.tools);
  const scans = out.gate.scanners || [];
  const count = out.gate.critical?.count || 0;
  const unknown = "확인 안 됨";
  const assurance = scope?.supplier_assurance || p.supplier_assurance;
  const location = scope?.residency || {};
  const localRun = out.local_execution || p.local_execution || r.local_execution || r.evidence?.local_execution;
  return html`<fieldset><legend>제안값</legend>
    ${kv([["주소", p.endpoint || r.repository_url], ["판본", r.commit_sha || p.catalog?.version || unknown],
      ["용도", p.purpose], ["신청자", r.submitter_name || r.submitted_by], ["서버 ID", p.server_id],
      ["데이터 등급", DATA_CLASS[p.data_class]], ["위험 등급", chip(...(RISK_TIER[p.risk.tier] || ["alert", unknown]))],
      ["원격 도메인", r.endpoint_url ? new URL(r.endpoint_url).hostname : "—"],
      ["계약 지문", p.catalog?.catalog_hash || unknown], ["허용 사용자", r.submitter_name || r.submitted_by],
      ["공급자 홈페이지", p.supplier_metadata?.homepage || unknown], ["라이선스", p.provenance?.license?.spdx || unknown],
      ["관할 규칙", p.jurisdiction_pack_enabled ? "사용" : "사용 안 함"]])}
    ${localRun ? html`<fieldset><legend>PC 격리 실행</legend>${kv([
      ["관찰 엔드포인트", localRun.observer_device || unknown],
      ["실행 계정 번호", localRun.observer_uid == null ? unknown : String(localRun.observer_uid)],
      ["격리 구성", localRun.isolation_scope || unknown], ["사용자 매핑", localRun.user_mapping || unknown],
    ])}</fieldset>` : ""}
    ${scans.length ? html`<table class="data"><thead><tr><th>검사기</th><th>상태</th><th>치명</th><th>높음</th></tr></thead><tbody>
      ${scans.map((s) => html`<tr><td>${s.scanner}</td><td>${s.status === "DONE" ? "완료" : s.status === "FAILED" ? "실패" : "미완료"}</td>
        <td>${s.critical_count ?? "—"}</td><td>${s.high_count ?? "—"}</td></tr>`)}</tbody></table>` : kv([["소스 검사", "검사 대상 아님"]])}
    ${kv([...Object.entries(ASSURANCE_LABELS).map(([key, label]) => [label, given(assurance, key) ?? unknown]),
      ["SBOM 제출", given(assurance, "sbom_submitted") === null ? unknown : assurance.sbom_submitted ? "제출" : "미제출"],
      ["VEX 제출", given(assurance, "vex_submitted") === null ? unknown : assurance.vex_submitted ? "제출" : "미제출"]])}
  </fieldset>
  ${p.blockers.map((b) => html`<div class="note warn">${b.message}</div>`)}
  <fieldset class="tool-pick"><legend>승인 도구</legend>${(p.catalog?.tools || []).filter((t) => t.name in p.tools).map((t) => html`<label>
    <input type="checkbox" name="approved_tool" value="${t.name}" ${selected.includes(t.name) ? raw("checked") : ""} ${pending ? raw("disabled") : ""} />
    <span><b>${t.name}</b>${pending ? html`<span>${ACTION[scope.actions?.[t.name] || p.tools[t.name]]}</span>`
      : html`<select name="action_${t.name}">${Object.entries(ACTION).slice(0, "rwx".indexOf(p.tools[t.name]) + 1).map(([k, v]) =>
        html`<option value="${k}" ${k === p.tools[t.name] ? raw("selected") : ""}>${v}</option>`)}</select>`}<span class="sub">${t.description || "—"}</span>
      ${(p.address_tools || []).includes(t.name) ? (pending ? kv([["허용 주소", destinationText(scope.destinations?.[t.name] || p.tool_reviews[t.name].destinations)]])
        : field.text(`destinations_${t.name}`, "허용 주소", 'maxlength="300"', p.tool_reviews[t.name].destinations.join(", "))) : ""}
      ${(t.warnings || []).length ? chip("alert", "도구 설명 경고") : ""}
      <details><summary>계약·인자 제한</summary><pre>${JSON.stringify({ input: t.input_schema, output: t.output_schema,
        constraints: p.parameter_constraints[t.name], scope: p.tool_reviews[t.name] }, null, 2)}</pre></details></span></label>`)}</fieldset>
  ${pending ? kv([["승인", `${pending.approvers.length} / ${p.risk.tier === "high" || p.risk.tier === "very_high" ? 2 : 1}`],
    ["사용 기한", `${scope.valid_days}일`], ["사용 대상", AUDIENCE[scope.audience || "all"] + (scope.audience_users?.length ? ` · ${scope.audience_users.join(", ")}` : "")]])
    : html`${field.select("valid_days", "사용 기한", VALIDITY, "90")}${audienceFields("all")}`}
  ${count && !pending ? field.text("critical_reason", "치명적 발견 수용 사유", 'required minlength="10" maxlength="1000"') : ""}
  ${p.risk.tier === "very_high" ? field.text("risk_reason", "위험 수용 사유", 'required minlength="10" maxlength="1000"') : ""}
  <details ${p.jurisdiction_pack_enabled ? raw("open") : ""}><summary>${p.jurisdiction_pack_enabled ? "추가 정보" : "추가 정보(선택)"}</summary>
    ${pending ? kv([...Object.entries(LOCATION_LABELS).map(([key, label]) => [label, Array.isArray(location[key]) ? location[key].join(", ") : location[key] || "—"]),
      ["수용 사유", pending.critical_reason || "—"]]) : html`<div class="grid c2">
      ${Object.entries(ASSURANCE_LABELS).map(([key, label]) => field.text(`assurance_${key}`, label,
        key === "support_end" ? 'type="date"' : 'maxlength="500"', assurance[key] || ""))}
      ${Object.entries(LOCATION_LABELS).map(([key, label]) => field.text(`location_${key}`, label,
        `maxlength="500" ${p.jurisdiction_pack_enabled && p.data_class !== "public" && key !== "transfer_basis" ? "required" : ""}`, ""))}
    </div><details><summary>영향평가 제안값</summary>${kv(Object.entries(RISK_CHOICES).map(([key, values]) =>
      [{ data_class: "데이터 등급", personal_data: "처리 개인정보", external_transfer: "외부 전송", permission: "실행 권한", autonomy: "자율성" }[key],
        key === "external_transfer" ? (p.risk_input[key] ? "있음" : "없음") : values[p.risk_input[key]]]))}</details>
`}
  </details>`;
}

const LOCAL_REASON = { local_file: "로컬 파일", local_tool: "로컬 도구", device: "장치" };

async function askLocalRun(id, request, preset = {}, status = "") {
  const cur = request.evidence?.local_run || preset;
  const fd = await ask({ title: `PC 격리 실행 · ${request.display_name}`, confirm: "확인", fields: html`
    ${status ? chip("alert", status) : ""}
    ${field.text("image", "이미지", 'required minlength="3" maxlength="300"',
      cur.image || (request.repository_path && !status ? `mcp/${request.repository_path.split("/").pop()}` : ""))}
    ${field.text("command", "실행 인자", 'maxlength="2000" placeholder="/workspace/폴더이름"', (cur.command || []).join(" "))}
    ${field.text("mounts", "폴더 (홈 기준 → /workspace/경로, 쉼표 구분, 경로:ro|rw)", 'maxlength="1000" placeholder="폴더이름:ro"',
      (cur.mounts || []).map((m) => `${m.path}:${m.mode}`).join(", "))}
    ${field.text("env", "환경 변수 (이름=값, 쉼표 구분)", 'maxlength="2000" placeholder="이름=값"',
      Object.entries(cur.env || {}).map(([k, v]) => `${k}=${v}`).join(", "))}
    ${field.select("reason_kind", "실행 위치 근거", LOCAL_REASON, cur.reason_kind || "local_file")}
    ${field.text("reason_text", "근거 설명", 'required minlength="10" maxlength="500"', cur.reason_text || "")}` });
  if (!fd) return false;
  const mounts = String(fd.get("mounts") || "").split(",").map((v) => v.trim()).filter(Boolean).map((v) => {
    const [path, mode = "ro"] = v.split(":");
    return { path: path.trim().replace(/^~\//, ""), mode: mode.trim() || "ro" };
  });
  const env = Object.fromEntries(String(fd.get("env") || "").split(",").map((v) => v.trim()).filter(Boolean).map((v) => {
    const at = v.indexOf("=");
    return at < 0 ? [v, ""] : [v.slice(0, at).trim(), v.slice(at + 1).trim()];
  }));
  const result = await api(`/api/mcp-requests/${id}/local-run`, { method: "POST", body: {
    image: String(fd.get("image")).trim(), command: String(fd.get("command") || "").trim().split(/\s+/).filter(Boolean),
    mounts, env, reason_kind: fd.get("reason_kind"), reason_text: String(fd.get("reason_text")).trim() } });
  toast(result.message);
  return true;
}

async function showIntakeApproval(id) {
  let out = await api(`/api/mcp-requests/${id}/approval-preview`, { method: "POST", body: {} });
  if (out.request.requested_transport === "stdio" && out.proposal.blockers.some((b) => b.code === "execution-missing")) {
    if (!(await askLocalRun(id, out.request, out.local_run_preset, out.local_run_status))) return;
    out = await api(`/api/mcp-requests/${id}/approval-preview`, { method: "POST", body: {} });
  }
  const fd = await ask({ title: `도입 승인 · ${out.request.display_name}`, fields: intakeApprovalFields(out),
    confirm: "승인", disabled: out.proposal.blockers.length > 0, reject: true });
  if (!fd) return;
  if (fd.get("dialog_action") === "reject") {
    await ACTIONS["intake-reject"]({ dataset: { id } }); return;
  }
  const scope = out.pending?.scope;
  const selected = scope?.tools || fd.getAll("approved_tool");
  if (!selected.length) { toast("도구를 하나 이상 선택하세요.", true); return; }
  const actions = scope ? scope.actions || {} : Object.fromEntries(selected.map((name) => [name, fd.get(`action_${name}`)])
    .filter(([name, action]) => action && action !== out.proposal.tools[name]));
  const destinations = scope ? scope.destinations || {} : Object.fromEntries(selected
    .filter((name) => (out.proposal.address_tools || []).includes(name)).map((name) => [name, hostList(fd.get(`destinations_${name}`))]));
  const assurance = scope?.supplier_assurance || Object.fromEntries(Object.keys(ASSURANCE_LABELS)
    .map((key) => [key, String(fd.get(`assurance_${key}`) || "").trim()]).filter(([, value]) => value));
  const location = scope?.residency || Object.fromEntries(Object.keys(LOCATION_LABELS).map((key) => {
    const value = String(fd.get(`location_${key}`) || "").trim();
    return [key, key.endsWith("countries") ? value.split(",").map((v) => v.trim().toUpperCase()).filter(Boolean) : value];
  }));
  const result = await api(`/api/mcp-requests/${id}/approve-and-register`, { method: "POST", body: {
    proposal_sha256: out.proposal_sha256, tools: selected, valid_days: scope?.valid_days || Number(fd.get("valid_days")),
    critical_reason: String(fd.get("critical_reason") || "").trim(), risk_reason: String(fd.get("risk_reason") || "").trim(), supplier_assurance: assurance, residency: location, actions, destinations,
    ...(scope ? { audience: scope.audience || "all", audience_users: scope.audience_users || [] } : audienceBody(fd)) } });
  toast(result.message); reload();
}

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

const verdictChip = (ok, yes = "일치", no = "미확인") => (ok ? chip("allow", yes) : chip("alert", no));
function intakeProvenanceView(p) {
  if (!p?.kind) return empty("기록 없음");
  const hosted = p.kind === "provider-hosted", a = p.artifact || {}, v = p.verification;
  return kv([
    ["공급 주소", html`<span class="mono">${p.source_url}</span>`],
    ["버전", p.version ? html`<code>${p.version}</code>` : NONE],
    ["라이선스", hosted ? "해당 없음" : p.license?.spdx ? `${p.license.spdx} · ${p.license.source === "operator" ? "승인자 기재" : "검사기"}` : NONE],
    ["배포 파일 해시", hosted ? "해당 없음" : a.sha256 ? html`<code>${a.sha256}</code>` : NONE],
    ["파일", !hosted && a.files != null ? `${a.files}개 · ${a.bytes}바이트` : ""],
    ["사본 대조", hosted ? "해당 없음" : v ? html`${verdictChip(v.match === true, "일치", "불일치")}<span class="sub">${when(v.at)} · ${v.by}</span>` : verdictChip(false)],
    ["서명·빌드 증명", hosted ? "해당 없음" : v?.provenance_status || "확인 안 됨"],
  ]);
}
const outcomeChip = (o) => chip(...(REVIEW_OUTCOME[o] || ["", o]));
function reviewRecords(events, r) {
  const consent = events.filter((e) => e.kind === "user-consent");
  const operator = events.filter((e) => !["user-consent", "runtime-egress"].includes(e.kind));
  return html`<div class="stack">
    ${panel("사용자 동의", html`<table class="data"><thead><tr><th>신청자</th><th>시각</th><th>목적</th></tr></thead><tbody>
      ${(consent.length ? consent : [{ actor: r.submitted_by, created_at: r.created_at, reason: r.purpose }]).map((e) => html`<tr><td>${e.actor}</td>
        <td class="small">${when(e.created_at)}</td><td>${e.reason || NONE}</td></tr>`)}</tbody></table>`, { flush: true })}
    ${panel("운영자 승인", operator.length ? html`<table class="data"><thead><tr><th>시각</th><th>구분</th><th>처리자</th><th>결과</th><th>사유</th></tr></thead><tbody>
      ${operator.map((e) => html`<tr><td class="small">${when(e.created_at)}</td><td>${REVIEW_KIND[e.kind] || e.kind}</td><td>${e.actor}</td>
        <td>${outcomeChip(e.outcome)}</td><td>${e.reason ? short(e.reason, 120) : NONE}</td></tr>`)}</tbody></table>` : empty("기록 없음"), { flush: true })}
  </div>`;
}
const destinationText = (list) => ((list || []).length ? list.join(", ") : "없음");
function scopeTerms(item) {
  const terms = [item.inputs && `입력 ${item.inputs.join(", ") || "없음"}`, item.mask && "입력 민감정보 가림",
    item.grade === "nonimportant" && `외부 전송 ${DATA_CLASS.nonimportant} 등급까지`,
    item.accepts_from?.length && `중요정보 수신 ${item.accepts_from.join(", ")}`, item.consent && "사용자 동의",
    item.high_impact && `중대 영향 · ${(item.impact_domains || []).map((d) => IMPACT_DOMAIN[d] || "—").join(" · ")}`].filter(Boolean);
  return terms.length ? html`<div class="pill-list">${terms.map((t) => chip("plain", t))}</div>` : NONE;
}
function scopeTable(tools, reviews, dataClass, serverId = null, addressTools = []) {
  const names = Object.keys(tools || {});
  if (!names.length) return empty("범위 없음");
  return html`${dataClass ? kv([["데이터 등급", DATA_CLASS[dataClass] || dataClass]]) : ""}
    <table class="data"><thead><tr><th>도구</th><th>행위</th><th>목적</th><th>자산</th><th>외부 목적지</th><th>조건</th></tr></thead><tbody>
    ${names.map((name) => { const item = reviews?.[name]; return html`<tr><td><code>${name}</code></td>
      <td>${chip({ r: "allow", w: "alert", x: "block" }[tools[name]] || "", ACTION[tools[name]] || tools[name])}</td>
      ${item ? html`<td>${item.purpose}</td><td>${item.asset}</td><td>${destinationText(item.destinations)}</td><td>${scopeTerms(item)}
        ${serverId ? html`<button class="btn sm" data-act="impact-scope" data-id="${serverId}" data-tool="${name}">중대 영향 심사</button>` : ""}
        ${serverId && addressTools.includes(name) ? html`<button class="btn sm" data-act="destination-scope" data-id="${serverId}" data-tool="${name}">허용 주소</button>` : ""}</td>`
        : html`<td colspan="4">${chip("block", "범위 미심사")}</td>`}</tr>`; })}</tbody></table>`;
}
function toolSunsetRow(serverId, name) {
  const state = registry?.tool_sunset?.tools?.[`${serverId}/${name}`];
  return state ? [state.last_use ? when(state.last_use, { seconds: true }) : NONE,
    state.deadline ? when(state.deadline, { seconds: true }) : NONE, state.status || NONE] : [NONE, NONE, NONE];
}
function gateView(gate) {
  if (!gate) return NONE;
  const db = gate.vuln_db;
  return html`<div class="stack">
    ${gate.scanners.length ? html`<table class="data"><thead><tr><th>검사기</th><th>버전</th><th>결과</th><th>시각</th></tr></thead><tbody>
      ${gate.scanners.map((x) => html`<tr><td>${x.scanner}</td><td>${x.version || NONE}</td>
        <td>${x.status ? chip(...(SCAN_STATE[x.status] || ["", x.status])) : NONE}</td><td class="small">${x.scanned_at ? when(x.scanned_at) : "—"}</td></tr>`)}</tbody></table>` : ""}
    ${db ? kv([["취약점 DB 갱신", db.updated_at ? html`${when(db.updated_at)}<span class="sub">${db.age_days}일 전 · 기준 ${db.max_days}일</span>` : NONE]]) : ""}
    ${gate.critical?.count ? kv([["치명적 발견", html`${gate.critical.count}건 ${gate.critical.covered ? chip("restrict", "수용 중") : chip("block", "수용 필요")}`]]) : ""}
    ${gate.blockers.length ? html`<div class="pill-list">${gate.blockers.map((b) => chip("block", b.message))}</div>` : ""}</div>`;
}

async function showIntakeReport(id) {
  const report = await api(`/api/mcp-requests/${id}/report`);
  const r = report.request, evidence = r.evidence || {}, investigation = report.exit_terms_discovery;
  const registered = r.registered_server_id ? (await gw("registry").catch(() => null))?.registrations?.[r.registered_server_id] : null;
  const accepted = report.risk_acceptances || [];
  lastDocument = report;
  if (r.intake_kind === "remote-endpoint") {
    const review = evidence.remote_contract, approval = evidence.remote_approval;
    openDrawer(`원격 MCP 검토 · ${r.display_name}`, chip(...(INTAKE_STATUS[r.status] || ["", r.status])), [
      {key: "contract", label: "계약·범위", body: html`<div class="stack">
        ${panel("서비스", kv([["MCP 주소", html`<span class="mono">${r.endpoint_url}</span>`], ["사용 목적", r.purpose]]))}
        ${panel("계약 검토", review ? kv([["검토 내용", review.review_note], ["검토자", `${review.reviewed_by} · ${when(review.reviewed_at)}`],
          ["허용 사용자", audienceText(review.allowed_principals)], ["사용 기한", when(review.valid_until)],
          ["서버", `${review.advertised_name} ${review.version}`], ["계약 해시", html`<code>${review.registration.catalog_hash}</code>`],
          ["승인 도구", Object.keys(review.registration.tools || {}).join(", ")], ...locationRows(review.registration.residency)]) : empty("검토 전"))}
        ${panel("허용 인자 범위", review ? html`<pre>${JSON.stringify(review.parameter_constraints || {}, null, 2)}</pre>` : empty("검토 전"))}
        ${panel("도입 승인", approval ? kv([["승인", `${approval.actor} · ${when(approval.at)}`], ["위험 수용", approval.risk_acceptance],
          ["검토 해시", html`<code>${approval.review_digest}</code>`]]) : empty("승인 전"))}
      </div>`},
      {key: "scope", label: "범위", body: review ? scopeTable(review.registration.tools, review.registration.tool_reviews, review.registration.data_class) : empty("검토 전")},
      {key: "risk", label: "영향평가", body: riskView(report.risk)},
      {key: "provenance", label: "출처", body: intakeProvenanceView(r.provenance)},
      {key: "records", label: "승인 기록", body: reviewRecords(report.events || [], r)},
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
        ${kpiStrip([["SBOM 구성요소", evidence.sbom_components ?? "—"], ["치명", evidence.critical ?? "—", "block"],
          ["높음", evidence.high ?? "—", "alert"], ["보통", evidence.medium ?? "—"]])}`)}
      ${panel("검사 단계", scanners.length ? html`<table class="data"><thead><tr><th>검사기</th><th>결과</th><th>오류</th></tr></thead>
        <tbody>${scanners.map(([name, s]) => html`<tr><td>${name}</td><td>${chip(s.status === "DONE" ? "allow" : "block", s.status === "DONE" ? "완료" : "실패")}</td><td>${s.error || "—"}</td></tr>`)}</tbody></table>` : empty("검사 대기"))}
      ${panel("검사 기준", gateView(report.gate))}
      ${panel("원본 보고서", report.artifacts.length ? html`<div class="row-actions">${report.artifacts.map((a) => html`
        <button class="btn sm" data-act="intake-download" data-id="${id}" data-kind="${a.kind}" data-name="${a.filename}">${ARTIFACT_KIND[a.kind] || a.kind} JSON</button>`)}</div>` : empty("생성된 보고서 없음"))}
    </div>` },
    { key: "runtime", label: "실행", n: (report.runtimes || []).length, body: html`${(report.runtimes || []).length ? html`<table class="data">
      <thead><tr><th>세대</th><th>상태</th><th>이미지</th><th>주소</th><th>시각</th></tr></thead><tbody>
      ${report.runtimes.map((rt) => html`<tr><td>${rt.generation}</td>
        <td>${chip(...(RUNTIME_STATUS[rt.status] || ["", rt.status]))}${rt.error ? html`<span class="sub">${short(rt.error, 120)}</span>` : ""}</td>
        <td class="mono small">${rt.image_id ? rt.image_id.slice(7, 19) : "—"}<span class="sub">${rt.source_commit.slice(0, 12)} · ${rt.recipe_id}</span></td>
        <td class="mono small">${rt.endpoint || "—"}</td><td class="small">${when(rt.updated_at)}</td></tr>`)}</tbody></table>` : empty("실행 기록 없음")}
      ${(report.rollback_options || []).length ? panel("되돌릴 수 있는 판본", html`<table class="data"><thead><tr><th>세대</th><th>승인 시각</th><th>승인자</th><th>계약 해시</th><th></th></tr></thead><tbody>
        ${report.rollback_options.map((item) => html`<tr><td>${item.generation}</td><td>${when(item.approved_at)}</td><td>${item.approved_by || "—"}</td>
          <td class="mono small">${item.contract_sha256}</td><td><button class="btn sm" data-act="runtime-rollback" data-id="${id}" data-generation="${item.generation}">되돌리기</button></td></tr>`)}</tbody></table>`) : ""}` },
    { key: "findings", label: "취약점·코드 검사", n: findings.length, body: html`
      ${report.reports.some((s) => s.summary?.truncated && s.scanner !== "Syft") ? html`<p class="small muted">검사기별 최대 200건</p>` : ""}
      ${findings.length ? html`<table class="data"><thead><tr><th>검사기·등급</th><th>발견</th><th>대상</th><th>설치 → 수정 버전</th></tr></thead>
      <tbody>${findings.map((f) => html`<tr><td>${f.scanner}<span class="sub">${f.severity}</span></td>
        <td><b>${f.id}</b><span class="sub">${f.title}</span></td><td>${f.target}<span class="sub">${f.package || ""}</span></td>
        <td>${f.installed_version || "—"} → ${f.fixed_version || "—"}</td></tr>`)}</tbody></table>`
        : empty(scanners.some(([, s]) => s.status === "FAILED") || r.status === "FAILED" ? "검사 실패" : ["VALIDATED", "APPROVED", "REJECTED"].includes(r.status) ? "발견 없음" : "검사 대기")}` },
    {key: "secrets", label: "비밀 정보 검사", n: secretFindings.length, body: html`
      ${secretFindings.length ? html`<table class="data"><thead><tr><th>규칙·등급</th><th>파일</th><th>행</th></tr></thead><tbody>${secretFindings.map((f) => html`<tr><td>${f.id}<span class="sub">${f.severity}</span></td><td>${f.target}</td><td>${f.line || "—"}</td></tr>`)}</tbody></table>` : empty(evidence.scanners?.gitleaks?.status === "DONE" ? "발견 없음" : "검사 대기")}`},
    { key: "sbom", label: "SBOM", n: inventory.components, body: html`
      ${inventory.truncated ? html`<p class="small muted">최대 200개</p>` : ""}
      ${(inventory.inventory || []).length ? html`<table class="data"><thead><tr><th>이름</th><th>버전</th><th>유형</th><th>식별자·라이선스</th></tr></thead>
        <tbody>${inventory.inventory.map((c) => html`<tr><td>${c.name}</td><td>${c.version || "—"}</td><td>${c.type}</td>
          <td class="small">${c.purl || "—"}<span class="sub">${(c.licenses || []).map((l) => l.expression || l.license?.id || l.license?.name || "미상").join(", ")}</span></td></tr>`)}</tbody></table>`
        : empty(inventory.components === 0 ? "구성요소 없음" : r.status === "FAILED" ? "생성 실패" : "생성 대기")}` },
    { key: "exit", label: "종료 조건", body: exitTermsView(id, r, investigation, evidence.exit_terms_conclusion) },
    { key: "scope", label: "범위", body: registered ? scopeTable(registered.tools, registered.tool_reviews, registered.data_class) : empty("등록 전") },
    { key: "risk", label: "영향평가", body: riskView(report.risk) },
    { key: "provenance", label: "출처", body: intakeProvenanceView(r.provenance) },
    { key: "records", label: "승인 기록", n: accepted.length || undefined, body: html`<div class="stack">${reviewRecords(report.events || [], r)}
      ${accepted.length ? panel("위험 수용", html`<table class="data"><thead><tr><th>수용자</th><th>기한</th><th>건수</th><th>사유</th></tr></thead><tbody>
        ${accepted.map((a) => html`<tr><td>${a.accepted_by}</td><td class="small">${when(a.expires_at)}</td><td class="num">${a.critical_count}</td><td>${short(a.reason, 120)}</td></tr>`)}</tbody></table>`, { flush: true }) : ""}</div>` },
  ]);
}

// ── termination ──────────────────────────────────────────────────────────────
ROUTES.termination = async (caseId, tab) => {
  if (caseId) return caseView(caseId, tab);
  const [{ relationships }, { cases, summary }] = await Promise.all([gw("termination/relationships"), gw("termination/cases")]);
  termRelationships = relationships;
  return {
    html: page({
      head: head("종료·폐기"),
      kpis: kpiStrip([["진행 중", summary.open_cases], ["종결 대기", summary.awaiting_close, "approval"],
        ["미해결 T2·T3", summary.unresolved_grades, summary.unresolved_grades ? "alert" : ""],
        [`기한 ${summary.sla_days}일 초과`, summary.overdue, summary.overdue ? "block" : ""],
        ["폐기 잔존", summary.retired_residue, summary.retired_residue ? "alert" : ""]]),
      active: tab || "relationships",
      tabs: [
        { key: "relationships", label: "이용 관계", n: relationships.length, body: html`${panel("이용 관계", relationships.length ? html`<table class="data"><thead><tr><th>이용 관계</th><th>운영</th><th class="num">이용자</th><th class="num">호출</th><th class="num">회수 대상</th><th>예상 등급</th><th></th></tr></thead><tbody>
            ${relationships.map(relationshipRow)}</tbody></table>` : empty("이용 관계 없음"), { flush: true })}` },
        { key: "cases", label: "케이스", n: cases.length, body: html`${panel("케이스", html`<table class="data"><thead><tr><th>이용 관계</th><th>상태</th><th>등급</th><th class="num">회수 대상</th><th class="num">미회수</th><th class="num">증거</th><th>시작</th></tr></thead><tbody>
            ${cases.map((c) => html`<tr class="clickable" tabindex="0" data-act="open-case" data-id="${c.id}">
              <td><b>${c.display_name}</b><span class="sub mono">${c.relationship_id || c.server_id}</span></td>
              <td>${chip(c.status === "CLOSED" ? "outline" : "approval", CASE_STATUS[c.status] || c.status)}${c.overdue ? chip("block", "기한 초과") : ""}</td>
              <td>${gradeChip(c.grade)}</td><td class="num">${c.targets}</td><td class="num">${c.outstanding}</td><td class="num">${c.evidence}</td>
              <td class="small">${when(c.opened_at)}</td></tr>`)}
            </tbody></table>${cases.length ? "" : empty("케이스 없음")}`, { flush: true })}` },
      ],
    }),
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
  return {
    html: page({
      head: html`${head(c.engagement_label, {
        back: html`<a class="back" href="#/termination?t=cases">← 종료·폐기</a>`,
        status: html`${chip(closed ? "outline" : "approval", CASE_STATUS[c.status] || c.status)}${gradeChip(c.grade)}`,
        actions: html`${c.grade ? html`<button class="btn" data-act="report">판정서</button>` : ""}
          ${c.deployment === "provider" ? html`<button class="btn" data-act="disclosure">고지 요청서</button>` : ""}
          ${closed ? html`<button class="btn" data-act="reopen-case">케이스 재개</button>` : ""}
          ${!closed ? html`<button class="btn" data-act="collect">증거 수집</button><button class="btn primary" data-act="assess">판정</button>` : ""}
          ${c.status === "ASSESSED" ? html`<button class="btn danger solid" data-act="close-case">종결</button>` : ""}` })}
        <ol class="stepper" aria-label="종료 판정 절차">${procedureState(d).map((s, i) => html`
          <li class="step ${s.done ? "done" : ""} ${s.now ? "now" : ""} ${s.gap ? "gap" : ""}"><span class="n">${s.done ? "✓" : i + 1}</span><b>${s.title}</b></li>`)}</ol>`,
      kpis: kpiStrip([["미회수", outstanding, "alert"], ["차단 후 실행", act.executed || 0, "block"], ["차단 후 거부", act.blocked || 0],
        ["엔드포인트 잔존", d.endpoint_residue || 0, "alert"]]),
      active: tab || "verdict",
      tabs: [
        { key: "verdict", label: "판정", body: html`<div class="grid c12">
          ${panel("등급", html`${c.grade ? html`<div class="grade-big ${c.grade}">${c.grade} · ${GRADE[c.grade]}</div>` : html`<div class="grade-big">—</div>`}
            ${criteria.assessed_at ? html`<p class="muted small">${when(criteria.assessed_at)}</p>` : ""}
            ${c.grade && c.grade !== "T1" && (criteria.determined_by || []).length ? kv([["결정 대상", criteria.determined_by.join(", ")]]) : ""}
            ${(criteria.notes || []).map((n) => html`<p class="note bad">${n}</p>`)}
            ${kv([["위험 수용", c.risk_acceptance_note ? `${c.risk_acceptance_note} (${c.risk_accepted_by})` : ""], ["종결 사유", c.close_note],
              ["재개 사유", criteria.reopened_note]])}`)}
          ${panel("기준별 충족 대상", html`<div class="crit">${["C1", "C2", "C3", "C4"].map((k) => { const cr = criteria[k]; return html`<div class="c">
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
  };
}

/** What this one piece of evidence observed - the kind says what it *can* prove. */
function evidenceResult(e) {
  const d = e.detail || {};
  switch (e.kind) {
    case "gateway-denial": return d.blocked ? chip("allow", `실행 전 차단 · ${d.policy_id}`) : chip("block", `차단 안 됨 · ${DECISION[d.decision]?.[1] || d.decision || "—"} ${d.policy_id || ""}`);
    case "credential-check": return d.present === false ? chip("allow", "자격 없음") : d.present ? chip("block", "자격 남음") : chip("alert", `확인 실패 · HTTP ${d.http_status}`);
    case "resource-rejection": return d.rejected ? chip("allow", `자원 서버 거부 · ${d.http_status}`) : chip("block", `자원 서버 수락 · ${d.http_status}`);
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
      ["확인 방법", VERIFICATION[t.verification] || t.verification], ["만료 시각", t.expires_at ? when(t.expires_at, { seconds: true }) : ""],
      ["회수 시각", t.revoked_at ? when(t.revoked_at, { seconds: true }) : ""],
      ["자원 서버", t.criteria?.provider_side ? PROVIDER_SIDE[t.criteria.provider_side.state] : ""], ["메모", t.note]]) },
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
  const [data, delivery, incidentData] = await Promise.all([gw(`audit/events?${params}&limit=100`), gw("audit/siem"), gw("audit/incidents")]);
  const options = (values, selected) => values.map(([value, label]) => html`<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`);
  const local = (iso) => { const d = new Date(iso || NaN); return Number.isNaN(d.getTime()) ? "" : `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; };
  return {html: page({head: head("감사 기록", {actions: html`<button class="btn" data-act="audit-verify">무결성 검증</button><button class="btn primary" data-act="audit-export">내보내기</button>`}),
    active: "events", tabs: [{key: "events", label: "감사 이벤트", n: data.events.length, body: html`<div class="stack">
      ${panel("사고 보고 기한", html`${incidentData.incidents.length ? html`<table class="data"><thead><tr><th>사고</th><th>관할·단계</th><th>기한</th><th>남은 시간</th><th>상태</th></tr></thead><tbody>${incidentData.incidents.flatMap((incident) => incident.deadlines.map((deadline) => html`<tr class="clickable" tabindex="0" data-act="incident-evidence" data-id="${incident.id}">
        <td>${incident.title}<span class="sub">${when(incident.detected_at)}</span></td><td>${deadline.jurisdiction_name}<span class="sub">${deadline.stage_name}</span></td><td>${deadline.due_at ? when(deadline.due_at) : "—"}</td><td>${deadline.remaining_seconds == null ? "—" : `${deadline.remaining_seconds < 0 ? "초과 " : ""}${Math.floor(Math.abs(deadline.remaining_seconds) / 86400)}일 ${Math.floor(Math.abs(deadline.remaining_seconds) % 86400 / 3600)}시간`}</td><td>${deadline.status}</td></tr>`))}</tbody></table>` : empty("사고 기록 없음")}`, {flush:true, sub:`타이머 ${incidentData.timer_status}`})}
      ${panel("보안 관제 전달", kv([["대기", delivery.pending], ["재시도", delivery.retrying], ["최초 대기", delivery.oldest_pending ? when(delivery.oldest_pending) : "—"], ["최근 수신 확인", delivery.last_delivered ? when(delivery.last_delivered) : "—"]]))}
      ${panel("조회 조건", html`<form class="form stack" data-form="audit"><div class="grid c3">
        <label>판정<select name="decision">${options([["", "전체"], ...Object.entries(DECISION).map(([k,v]) => [k,v[1]])], q.get("decision") || "")}</select></label>
        <label>실행 결과<select name="execution">${options([["", "전체"], ["executed", "실행됨"], ["not-sent", "실행 안 함"], ["unknown", "실행 미확인"], ["withheld", "응답 보류"]], q.get("execution") || "")}</select></label>
        <label>이벤트<select name="event_kind">${options([["", "전체"], ["tools/call", "도구 호출"], ["mcp-connection", "연결 거부"]], q.get("event_kind") || "")}</select></label>
        ${["server", "principal", "policy", "trace_id"].map((k) => field.text(k, {server:"서버", principal:"사용자", policy:"정책", trace_id:"추적 ID"}[k], 'maxlength="150"', q.get(k) || ""))}
        ${["since", "until"].map((k) => field.text(k, k === "since" ? "시작" : "종료", 'type="datetime-local"', local(q.get(k))))}
      </div><div class="row-actions"><button class="btn primary" type="submit">조회</button><a class="btn" href="#/audit">초기화</a></div></form>`)}
      ${panel("감사 원장", html`${data.events.length ? html`<table class="data"><thead><tr><th>번호·시각</th><th>판정·정책</th><th>사용자·도구</th><th>실행 결과</th></tr></thead><tbody>${data.events.map((e) => html`<tr class="clickable" tabindex="0" data-act="audit-event" data-id="${e.id}">
          <td>#${e.id}<span class="sub">${when(e.created_at)} · ${EVENT_KIND[e.event_kind] || e.event_kind}</span></td><td>${decisionChip(e.decision)}${e.invalid ? chip("outline", "무효 처리") : ""}<span class="sub mono">${e.policy_id}</span></td><td>${e.user_token}<span class="sub mono">${e.server_id}.${e.tool_name}</span></td>
          <td>${outcomeChips(e.outcome_axes)}</td></tr>`)}</tbody></table>` : empty("감사 이벤트 없음")}
          ${data.has_more ? html`<div class="row-actions center"><a class="btn" href="#/audit?${new URLSearchParams({...Object.fromEntries(params), before: data.next_before})}">더 보기</a></div>` : ""}`, {flush:true})}</div>`}]})};
};
const EVENT_KIND = { "tools/call": "도구 호출", "mcp-connection": "연결 거부" };

ROUTES.policy = async (_, tab) => {
  const [{ enforcement }, matrix, ledger] = await Promise.all([gw("enforcement"), gw("policy/matrix"), gw("policy/ledger")]);
  policyLedger = ledger.policies;
  const actions = (list) => (list || []).map((a) => ACTION[a] || a).join(", ");
  return {
    html: page({
      head: head("정책", { status: modeChip(enforcement), actions: html`<button class="btn ${enforcement === "enforce" ? "danger" : "primary"}" data-act="enforcement"
        data-mode="${enforcement === "enforce" ? "monitor" : "enforce"}">${enforcement === "enforce" ? "관찰 모드로 전환" : "집행 모드로 전환"}</button>` }),
      active: tab || "capabilities",
      tabs: [
        { key: "capabilities", label: "실행 권한", n: matrix.capabilities.length + matrix.runtime_envelopes.length, body: panel("실행 권한",
          matrix.capabilities.length + matrix.runtime_envelopes.length ? html`<table class="data"><thead><tr><th>권한</th><th>사용자</th><th>서버</th><th>행위·자원</th><th>만료 시각</th></tr></thead><tbody>
          ${matrix.capabilities.map((g) => html`<tr><td><code>${g.id}</code></td><td>${(g.principals || []).join(", ")}</td><td>${(g.servers || []).join(", ")}</td>
            <td>${actions(g.actions)}<span class="sub">${(g.path_roots || []).join(", ")}</span></td><td>${when(g.valid_until)}</td></tr>`)}
          ${matrix.runtime_envelopes.map((g) => html`<tr><td><code>${g.server_id}</code></td><td>${audienceText(g.principals)}</td><td><code>${g.server_id}</code></td><td>${Object.keys(g.tools || {}).join(", ")}<span class="sub">도입 승인</span></td><td>${when(g.valid_until)}</td></tr>`)}
          </tbody></table>` : empty("실행 권한 없음"), { flush: true }) },
        { key: "ledger", label: "정책 목록", n: ledger.policies.length, body: panel("정책 목록", html`<table class="data"><thead><tr><th class="n">번호</th><th>정책</th><th>결과</th></tr></thead><tbody>
            ${ledger.policies.map((p, i) => html`<tr class="clickable" tabindex="0" data-act="policy" data-id="${p.policy_id}"><td class="n">${i + 1}</td>
              <td><b>${p.name}</b></td><td>${UNSUPPORTED_POLICY.has(p.policy_id) ? chip("outline", "지원 안 함") : outcomeDecision(p.outcome) ? decisionChip(outcomeDecision(p.outcome)) : chip("outline", p.outcome)}</td></tr>`)}
            </tbody></table>`, { flush: true }) },
      ],
    }),
  };
};

// ── actions ──────────────────────────────────────────────────────────────────
const field = {
  text: (name, label, attrs = "", value = null) => html`<label>${label}<input name="${name}" ${raw(attrs)} ${value === null ? "" : html`value="${value}"`} /></label>`,
  area: (name, label, attrs = "") => html`<label>${label}<textarea name="${name}" ${raw(attrs)}></textarea></label>`,
  select: (name, label, options, cur = "") => html`<label>${label}<select name="${name}">${Object.entries(options).map(([v, l]) =>
    html`<option value="${v}" ${v === cur ? raw("selected") : ""}>${Array.isArray(l) ? l[1] : l}</option>`)}</select></label>`,
};

function scopeFields(names) {
  return html`<fieldset><legend>도구 범위</legend>
    ${field.text("scope_purpose", "목적", 'required minlength="4" maxlength="200"')}
    ${field.text("scope_asset", "자산", 'required minlength="2" maxlength="200"')}
    ${field.text("scope_destinations", "외부 목적지 (쉼표 구분)", 'maxlength="300"')}
    <div class="grid c2">${field.select("scope_grade", "외부 전송 등급", { public: DATA_CLASS.public, nonimportant: DATA_CLASS.nonimportant }, "public")}
      ${field.text("scope_accepts", "중요정보를 받을 서버 (쉼표 구분)", 'maxlength="300"')}</div>
    <label class="check"><input type="checkbox" name="scope_mask" /> 입력 민감정보 가림</label>
    <label class="check"><input type="checkbox" name="scope_consent" /> 사용자 동의</label>
    ${field.select("scope_impact", "중대 영향", { none: "해당 없음", ...IMPACT_DOMAIN }, "none")}
    <details><summary>도구별 조정</summary>${names.map((name) => html`<div class="grid c2">
      ${field.text(`purpose:${name}`, html`<code>${name}</code> 목적`, 'maxlength="200"')}
      ${field.text(`asset:${name}`, "자산", 'maxlength="200"')}
      ${field.text(`destinations:${name}`, "외부 목적지", 'maxlength="300"')}
      ${field.text(`inputs:${name}`, "허용 입력 항목 (쉼표 구분)", 'maxlength="500"')}
      ${field.select(`impact:${name}`, "중대 영향", { "": "공통 설정", none: "해당 없음", ...IMPACT_DOMAIN })}</div>`)}</details></fieldset>`;
}
const hostList = (text) => String(text || "").split(",").map((h) => h.trim().toLowerCase()).filter(Boolean);
function collectScopes(fd, names) {
  const own = (key, name) => String(fd.get(`${key}:${name}`) || "").trim();
  const impact = (name) => own("impact", name) || String(fd.get("scope_impact") || "none");
  return Object.fromEntries(names.map((name) => [name, {
    purpose: own("purpose", name) || String(fd.get("scope_purpose")).trim(),
    asset: own("asset", name) || String(fd.get("scope_asset")).trim(),
    destinations: hostList(own("destinations", name) || fd.get("scope_destinations")),
    inputs: own("inputs", name) ? own("inputs", name).split(",").map((v) => v.trim()).filter(Boolean) : null,
    mask: fd.get("scope_mask") === "on", consent: fd.get("scope_consent") === "on",
    grade: String(fd.get("scope_grade") || "public"),
    high_impact: impact(name) !== "none", impact_domains: impact(name) === "none" ? [] : [impact(name)],
    accepts_from: String(fd.get("scope_accepts") || "").split(",").map((v) => v.trim()).filter(Boolean) }]));
}

const ACTIONS = {
  async "sbom-impact-stop"(el) {
    const fd = await ask({ title: "영향 서버 중지", fields: field.text("reason", "사유", 'required minlength="4" maxlength="500"'),
      confirm: "중지", danger: true });
    if (!fd) return;
    const result = await api("/api/supply-chain/impact/stop", { method: "POST", body: {
      package: el.dataset.package, version_range: el.dataset.range, reason: fd.get("reason").trim(),
    } });
    toast(`중지 ${result.counts.succeeded}건 · 건너뜀 ${result.counts.skipped}건 · 실패 ${result.counts.failed}건`, result.counts.failed > 0);
    reload();
  },
  async disconnect(el) {
    await api(`/api/my-connections/${encodeURIComponent(el.dataset.id)}`, { method: "DELETE" });
    toast("연결을 해제했습니다.");
    reload();
  },
  async "connect-device"(el) {
    const base = `/api/my-connections/${encodeURIComponent(el.dataset.id)}/device`;
    const flow = await api(`${base}/start`, { method: "POST" });
    const dialog = $("#dialog");
    const outcome = { connected: ["연결했습니다.", false], expired: ["인증 코드가 만료되었습니다.", true],
      denied: ["연결이 거부되었습니다.", true], failed: ["연결하지 못했습니다.", true] };
    let timer = null;
    const poll = async () => {
      let result;
      try { result = await api(`${base}/poll`, { method: "POST", body: { flow_id: flow.flow_id } }); } catch { result = { state: "failed" }; }
      if (result.state === "pending") { timer = setTimeout(poll, (result.interval || flow.interval) * 1000); return; }
      timer = null;
      toast(...(outcome[result.state] || outcome.failed));
      if (dialog.open) dialog.close("cancel");
      reload();
    };
    timer = setTimeout(poll, flow.interval * 1000);
    const link = String(flow.verification_uri).startsWith("https://github.com/") ? flow.verification_uri : "https://github.com/login/device";
    await ask({ title: "인증 코드로 연결", confirm: "닫기",
      fields: html`<label>코드<input value="${flow.user_code}" readonly /></label>
        <a href="${link}" target="_blank" rel="noopener noreferrer">${link.replace("https://", "")} ↗</a>` });
    clearTimeout(timer);
  },
  async consent(el) {
    await api(`/api/consents/${el.dataset.id}`, { method: "POST", body: { decision: el.dataset.decision } });
    toast({ grant: "동의했습니다.", deny: "거부했습니다.", revoke: "철회했습니다." }[el.dataset.decision]);
    reload(); refreshBadges();
  },
  async "consent-server"(el) {
    await api(`/api/consents/server/${encodeURIComponent(el.dataset.id)}`, { method: "POST", body: {
      decision: el.dataset.decision, consent_ids: el.dataset.consents.split(",").map(Number),
    } });
    toast(el.dataset.decision === "grant" ? "허용했습니다." : "거부했습니다.");
    reload(); refreshBadges();
  },
  async "audit-event"(el) {
    const event = await gw(`audit/events/${el.dataset.id}`);
    openDrawer(`감사 이벤트 #${event.id}`, html`<div class="row-actions">${decisionChip(event.decision)}${event.invalid ? chip("outline", "무효 처리") : ""}<code>${event.policy_id}</code></div>`,
      [{key:"record", label:"기록", body:html`${outcomeChips(event.outcome_axes)}${kv([
        ["시각", when(event.created_at)], ["사용자", event.user_token], ["서버", event.server_id], ["도구", event.tool_name],
        ["행위", ACTION[event.action] || "—"], ["데이터 등급", DATA_CLASS[event.data_class] || "—"],
        ["승인 요청", event.approval_id], ["응답 해시", event.response_sha256], ["감사 해시", event.entry_sha256],
        ["무효 처리", event.invalid ? `${event.invalid.reason} · ${event.invalid.by} · ${when(event.invalid.at)}` : "—"]])}`}]);
  },
  async "incident-evidence"(el) {
    const result = await gw(`audit/incidents/${el.dataset.id}`);
    const pack = result.evidence_package;
    openDrawer("사고 증빙", html`<code>${result.incident.id}</code>`, [{key:"evidence", label:"증빙", body:kv([
      ["영향 호출", `${pack.included_count} / ${pack.query_count}`], ["건수 일치", pack.count_matches ? "정상" : "불일치"],
      ["전체 호출", pack.total_count], ["무효 호출", pack.invalid_count], ["유효 호출", pack.valid_count],
      ["해시 사슬", pack.chain_verification?.intact ? "정상" : "무결성 미확인"], ["패키지 해시", pack.package_sha256],
      ["패키지 검증", result.package_hash_valid ? "정상" : "실패"]])}]);
  },
  async "audit-export"() {
    const q = new URLSearchParams(current.query);
    q.delete("t"); q.set("limit", "500");
    lastDocument = await gw(`audit/export?${q}`);
    ACTIONS["save-json"]({dataset:{name:"mcp-audit-evidence.json"}});
    const intact = lastDocument.payload.verification.intact;
    toast([`${lastDocument.manifest.count}건 내보냄`, lastDocument.payload.has_more ? "다음 페이지 있음" : "", intact ? "무결성 정상" : "무결성 손상"]
      .filter(Boolean).join(" · "), !intact);
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
    el.innerHTML = String(icon(feed.live ? "pause" : "play"));
    el.setAttribute("aria-label", feed.live ? "일시정지" : "실시간 재개");
    el.title = feed.live ? "일시정지" : "실시간 재개";
    el.setAttribute("aria-pressed", String(!feed.live));
    if (feed.live && feed.pending.length) {
      feed.highlight = feed.pending.map((row) => row.id);
      feed.pending = [];
      feed.page = 1;
      feed.analysisAt = 0;
      reload();
    } else renderFeedStatus();
  },
  async "analysis-refresh"() {
    const extra = feed.query ? { q: feed.query } : {};
    const analysis = await gw(`activity/analysis?${feedQuery(extra)}`);
    feed.analysis = analysis;
    feed.analysisKey = feedQuery({}).toString();
    feed.analysisAt = Date.now();
    $("#analysis-total").textContent = `전체 ${analysis.total ?? 0}건`;
    $("#analysis-updated-time").textContent = clockText(new Date(), {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
    for (const [id, build] of Object.entries(feedCharts(analysis))) {
      if ($(`#${id}`)) charts.redraw(id, build);
    }
  },
  "feed-page"(el) {
    feed.page = Math.max(1, Number(el.dataset.page) || 1);
    if (feed.page === 1 && feed.pending.length) {
      feed.highlight = feed.pending.map((row) => row.id);
      feed.pending = [];
    }
    reload();
  },
  "feed-reset"() {
    feed.filters = Object.fromEntries(FEED_FILTERS.map((key) => [key, ""]));
    feed.query = "";
    location.hash = "#/activity";
    reload();
  },
  goto(el) { location.hash = el.dataset.href; },
  "cov-page"(el) {
    const state = covPaging[el.dataset.list];
    if (Number(el.dataset.dir) > 0) {
      if (!state.next) return;
      state.cursors[state.index + 1] = state.next;
      state.index += 1;
    } else if (state.index) state.index -= 1;
    reload();
  },
  async "endpoint-record"(el) {
    const [record, related] = await Promise.all([gw(`endpoint/records/${el.dataset.kind}/${el.dataset.id}`),
      gw(`endpoint/correlation?kind=${el.dataset.kind}&record_id=${el.dataset.id}`).catch(() => null)]);
    const view = provenanceView(record.provenance);
    const details = record.details || {};
    openDrawer(`${RECORD_KIND[record.record_kind]} #${record.id}`, html`<div class="drawer-summary">${record.record_kind === "os-event" ? chip(...denialClass(record.denial_class)) : ""}
      ${chip("outline", originLabel(record.origin))}<span class="muted small">${when(record.at, { seconds: true })}</span></div>`, [
      { key: "record", label: "기록", body: kv(record.record_kind === "os-event" ? [
        ["엔드포인트", record.endpoint_id], ["호스트", record.hostname], ["종류", record.kind === "network-denied" ? "네트워크 차단" : "실행 차단"],
        ["대상", osEventTarget(record)], ["실행 시도 프로세스", details.parent_executable], ["프로파일", details.profile],
        ["작업", details.operation], ["발생", when(record.observed_at, { seconds: true })], ["수신", when(record.received_at, { seconds: true })]]
        : record.record_kind === "listener" ? [
        ["엔드포인트", record.endpoint_id], ["호스트", record.hostname], ["주소", `${record.address}${record.port ? `:${record.port}` : ""}`],
        ["프로세스", record.process_name], ["서버", record.server_name], ["MCP 여부", MCP_EVIDENCE_LABEL[record.mcp_evidence]],
        ["분류", (ENDPOINT_CLASS[record.classification] || [, ""])[1]], ["관측", when(record.observed_at, { seconds: true })]]
        : [["엔드포인트", record.endpoint_id], ["호스트", record.hostname], ["설정 파일", record.config_path], ["서버", record.server_label],
        ["연결", `${record.transport} ${short(record.endpoint_ref, 80)}`], ["분류", (ENDPOINT_CLASS[record.classification] || [, ""])[1]],
        ["보고", when(record.reported_at, { seconds: true })]]) },
      { key: "source", label: "출처", body: kv([
        ["출처", originLabel(record.origin)], ["수집기", COLLECTOR[record.provenance?.collector] || record.provenance?.collector],
        ["수신", when(record.provenance?.received_at, { seconds: true })], ["원본 해시", view.raw === "—" ? "" : html`<code>${view.raw}</code>`],
        ["보고 해시", view.agent === "—" ? "" : html`<code>${view.agent}</code>`], ["저장 해시", view.server === "—" ? "" : html`<code>${view.server}</code>`],
        ["대조", view.state === "unreported" ? "" : chip(view.tone, view.label)],
        ["변환", view.steps.length ? html`<div class="pill-list">${view.steps.map((s) => chip("outline", transformLabel(s)))}</div>` : ""]]) },
      { key: "related", label: "연관 기록", n: related ? related.records.length : undefined, body: relatedBody(related) },
    ]);
  },
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
          ? html`${chip("restrict", VENDOR_CONSOLE[v.console_state] || v.console_state)}<span class="sub">수동 확인 · ${v.verified_by} · ${when(v.verified_at)}${(v.oauth_scopes || []).length ? ` · 범위 ${v.oauth_scopes.join(", ")}` : ""}${v.role_access ? ` · 역할 ${v.role_access}` : ""}</span>`
          : html`${chip("outline", "확인 기록 없음")}${(i.residual || []).map((r) => html`<span class="sub">${r}</span>`)}`)}
        </tbody></table>${kv([["우회 경로", (i.bypass || []).length ? html`<div class="pill-list">${i.bypass.map((b) => chip("block", b))}</div>` : "없음"],
          ["사용자·엔드포인트", `${(i.owners || [i.owner]).filter(Boolean).join(", ") || "—"}${i.pcs > 1 ? ` · 엔드포인트 ${i.pcs}대` : i.device ? ` · ${i.device}` : ""}`],
          ["발견", `${i.discovered_from}${i.discovered_at ? ` · ${when(i.discovered_at)}` : ""}`],
          ["대상", i.target ? html`<span class="mono">${i.target}</span>` : ""], ["마지막 확인", i.last_verified_at ? when(i.last_verified_at) : ""]])}` },
      { key: "approval", label: "승인", body: kv([["상태", approvalLabel(i.approval?.state)], ["만료 시각", i.approval?.expires_at ? when(i.approval.expires_at) : ""],
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
        ${field.text("oauth_scopes", "OAuth 범위 (쉼표 구분)", 'maxlength="600"')}
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
    const a = approvalRows.find((row) => row.id === el.dataset.id);
    let r;
    if (a?.explanation) {
      const b = await gw(`approvals/${a.id}/evidence`);
      const fd = await ask({ title: "중대 영향 호출 승인", fields: html`${impactExplanation(b.explanation)}
        <label class="check"><input type="checkbox" name="confirmed" required /> 요청 범위·정책 근거 확인</label>`, confirm: "승인·실행" });
      if (!fd) return;
      r = await gw(`approvals/${a.id}/approve`, { method: "POST", body: { evidence_sha256: b.evidence_sha256, reason: "scope_confirmed" } });
    } else r = await api(`/approvals/${el.dataset.id}/approve`, { method: "POST" });
    toast(`승인했습니다 · ${DECISION[r.decision]?.[1] || r.decision || "처리됨"}`);
    reload(); refreshBadges();
  },
  async "intent-resolve"(el) {
    const executed = el.dataset.outcome === "executed";
    const fd = await ask({ title: executed ? "실행됨으로 기록" : "실행 안 됨으로 기록", fields: field.area("note", "확인 내용", 'maxlength="500"'), confirm: "기록" });
    if (!fd) return;
    await gw(`dispatch-intents/${el.dataset.id}/resolve`, { method: "POST", body: { outcome: el.dataset.outcome, note: fd.get("note") } });
    toast("기록했습니다."); reload();
  },
  async reject(el) {
    const a = approvalRows.find((row) => row.id === el.dataset.id);
    if (a?.explanation) {
      const b = await gw(`approvals/${a.id}/evidence`);
      if (!await ask({ title: "중대 영향 호출 거부", fields: impactExplanation(b.explanation), confirm: "요청 부적합 · 거부", danger: true })) return;
      await gw(`approvals/${a.id}/reject`, { method: "POST", body: { note: "request_inappropriate", evidence_sha256: b.evidence_sha256 } });
      toast("거부했습니다."); reload(); refreshBadges(); return;
    }
    const fd = await ask({ title: "승인 요청 거부", fields: field.area("note", "사유", 'required maxlength="500"'), confirm: "거부", danger: true });
    if (!fd) return;
    await api(`/approvals/${el.dataset.id}/reject`, { method: "POST", body: { note: fd.get("note") } });
    toast("거부했습니다."); reload(); refreshBadges();
  },
  async "approval-revoke"(el) {
    const b = await gw(`approvals/${el.dataset.id}/evidence`);
    if (!await ask({ title: "승인 번복", fields: impactExplanation(b.explanation), confirm: "승인 판단 변경 · 번복", danger: true })) return;
    await gw(`approvals/${el.dataset.id}/revoke`, { method: "POST", body: { evidence_sha256: b.evidence_sha256 } });
    toast("번복을 기록했습니다."); reload();
  },
  async "approval-export"(el) {
    const b = await gw(`approvals/${el.dataset.id}/evidence`);
    const url = URL.createObjectURL(new Blob([JSON.stringify(b, null, 2)], { type: "application/json" }));
    Object.assign(document.createElement("a"), { href: url, download: `mint-decision-${el.dataset.id}.json` }).click();
    URL.revokeObjectURL(url);
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
  async "suspend-open"(el) {
    const { servers } = await gw("registry");
    const fd = await ask({ title: `${el.dataset.name} · MCP 이용 중지`,
      fields: html`${field.select("server_id", "서버", Object.fromEntries(servers.map((s) => [s.id, s.display_name || s.id])))}
        ${field.text("reason", "사유", 'required minlength="4" maxlength="500"', "관리자 수동 중지")}`,
      confirm: "이용 중지", danger: true });
    if (!fd) return;
    await gw("suspensions", { method: "POST", body: { user_token: el.dataset.token, server_id: fd.get("server_id"), reason: fd.get("reason").trim() } });
    toast("이용을 중지했습니다."); reload();
  },
  async "suspend-resume"(el) {
    const fd = await ask({ title: `${el.dataset.name} · ${el.dataset.server} 이용 재개`,
      fields: field.text("note", "메모", 'required minlength="4" maxlength="500"', "중지 해소"), confirm: "재개" });
    if (!fd) return;
    await gw(`suspensions/${encodeURIComponent(el.dataset.id)}/resume`, { method: "POST", body: { note: fd.get("note").trim() } });
    toast("이용을 재개했습니다."); reload();
  },
  async "suspend-all"(el) {
    const fd = await ask({ title: `${el.dataset.name} · 전체 MCP 이용 중지`,
      fields: field.text("reason", "사유", 'required minlength="4" maxlength="500"', "관리자 수동 중지"),
      confirm: "전체 중지", danger: true });
    if (!fd) return;
    const r = await gw("user-suspensions/stop-all", { method: "POST", body: { user_token: el.dataset.token, reason: fd.get("reason").trim() } });
    toast(`중지 ${r.suspended.length}건 · 건너뜀 ${r.skipped.length}건 · 실패 ${r.failed.length}건`, r.failed.length > 0);
    reload();
  },
  async "resume-all"(el) {
    const fd = await ask({ title: `${el.dataset.name} · 전체 MCP 이용 재개`,
      fields: field.text("note", "메모", 'required minlength="4" maxlength="500"', "중지 해소"), confirm: "전체 재개" });
    if (!fd) return;
    const r = await gw("user-suspensions/resume-all", { method: "POST", body: { user_token: el.dataset.token, note: fd.get("note").trim() } });
    toast(`재개 ${r.resumed.length}건 · 건너뜀 ${r.skipped.length}건 · 실패 ${r.failed.length}건`, r.failed.length > 0);
    reload();
  },
  async "account-delete"(el) {
    const fd = await ask({ title: `${el.dataset.name} 계정 삭제`,
      body: "로그인과 사내 저장소 접근이 즉시 차단됩니다.", confirm: "계정 삭제", danger: true });
    if (!fd) return;
    const r = await api(`/api/accounts/${encodeURIComponent(el.dataset.id)}`, { method: "DELETE" });
    await reload();
    toast(r.message);
  },
  async "account-restore"(el) {
    const fd = await ask({ title: `${el.dataset.name} 계정 복구`,
      body: "이전 엔드포인트와 동의는 복구되지 않습니다.", confirm: "계정 복구" });
    if (!fd) return;
    const r = await api(`/api/accounts/${encodeURIComponent(el.dataset.id)}/restore`, { method: "POST" });
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
    const kit = viewer.kit;
    const preferred = preferredKitPlatform();
    const os = (kit.platforms || []).includes(preferred) ? preferred : (kit.platforms || [])[0];
    openDrawer("내 PC 연결", html`<div data-kit>${kitView(kit, os)}</div>`);
  },
  "pc-kit-os"(el) {
    el.closest("[data-kit]").innerHTML = String(kitView(viewer.kit, el.dataset.os));
  },
  async "pc-kit-download"(el) {
    const os = el.dataset.os || "linux";
    const isolated = el.closest("[data-kit]")?.querySelector('[name="kit-isolated"]')?.checked ? "&isolated=true" : "";
    const query = (os === "macos" ? "&delivery=command" : os === "windows" ? "&packaging=oneclick" : "") + isolated;
    const response = await fetch(`/api/pc-kit?platform=${encodeURIComponent(os)}${query}`,
      { method: "POST", headers: { authorization: `Bearer ${token}` } });
    if (!response.ok) {
      const r = await response.json().catch(() => ({}));
      throw new Error(detailText(r.detail) || "설치 파일을 받지 못했습니다.");
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a"); link.href = url;
    link.download = /filename="?([^";]+)"?/.exec(response.headers.get("content-disposition") || "")?.[1] || KIT_FILE[os];
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 30000);
    toast("설치 파일을 받았습니다.");
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
    if (!scopes.length) { toast("수집 항목을 하나 이상 선택하세요.", true); return; }
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
  async "runtime-start"(el) {
    const r = await api(`/api/mcp-requests/${el.dataset.id}/runtime`, { method: "POST" });
    toast(r.message); reload();
  },
  async "runtime-stop"(el) {
    const fd = await ask({ title: "실행 중지", body: "게이트웨이 호출이 이 실행에 닿지 않게 됩니다.", confirm: "중지", danger: true });
    if (!fd) return;
    const r = await api(`/api/mcp-requests/${el.dataset.id}/runtime/stop`, { method: "POST" });
    toast(r.message); reload();
  },
  async "runtime-rollback"(el) {
    const fd = await ask({ title: `실행 판본 되돌리기 · ${el.dataset.generation}`,
      fields: field.text("note", "사유", 'required maxlength="300"'), confirm: "되돌리기", danger: true });
    if (!fd) return;
    const r = await api(`/api/mcp-requests/${el.dataset.id}/runtime/rollback`, {
      method: "POST", body: { generation: Number(el.dataset.generation), note: fd.get("note") },
    });
    toast(r.message); reload();
  },
  async "mcp-source-download"(el) {
    const response = await fetch(`/api/approved-mcp/${encodeURIComponent(el.dataset.id)}/source?commit=${encodeURIComponent(el.dataset.commit)}`,
      { headers: { authorization: `Bearer ${token}` } });
    if (!response.ok) {
      if (response.status === 401) { localStorage.removeItem(TOKEN_KEY); location.replace("/login"); }
      const body = await response.json().catch(() => ({}));
      throw new Error(detailText(body.detail) || `다운로드하지 못했습니다 (${response.status}).`);
    }
    const url = URL.createObjectURL(await response.blob());
    Object.assign(document.createElement("a"), { href: url, download: `${el.dataset.id}-${el.dataset.commit.slice(0, 12)}.zip` }).click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
  async "intake-download"(el) {
    const response = await fetch(`/api/mcp-requests/${el.dataset.id}/artifacts/${encodeURIComponent(el.dataset.kind)}`,
      { headers: { authorization: `Bearer ${token}` } });
    if (!response.ok) {
      if (response.status === 401) { localStorage.removeItem(TOKEN_KEY); location.replace("/login"); }
      const body = await response.json().catch(() => ({}));
      throw new Error(detailText(body.detail) || `다운로드하지 못했습니다 (${response.status}).`);
    }
    const url = URL.createObjectURL(await response.blob());
    Object.assign(document.createElement("a"), { href: url, download: el.dataset.name }).click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
  async "registry-export"(el) {
    const format = el.dataset.format;
    const response = await fetch(`/gw/registry/export?format=${encodeURIComponent(format)}`, { headers: { authorization: `Bearer ${token}` } });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(detailText(body.detail) || `등록부를 내보내지 못했습니다 (${response.status}).`);
    }
    const blob = await response.blob(), url = URL.createObjectURL(blob);
    Object.assign(document.createElement("a"), { href: url, download: `mint-registry.${format}` }).click();
    toast(`등록부 SHA-256 · ${response.headers.get("X-Registry-SHA256") || "—"}`);
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
  async "intake-one-click"(el) { await showIntakeApproval(el.dataset.id); },
  async "intake-discover"(el) {
    const form = el.closest("form");
    const found = await api("/api/mcp-requests/discover", { method: "POST", body: { endpoint: form.elements.endpoint_url.value.trim() } });
    form.querySelector("[data-requested-tools]").innerHTML = String(requestedToolList(found.tools));
  },
  async "server-deregister"(el) {
    const fd = await ask({ title: `등록 해제 · ${el.dataset.id}`, body: "이후 호출은 차단됩니다.", confirm: "해제", danger: true });
    if (!fd) return;
    await gw(`registry/servers/${encodeURIComponent(el.dataset.id)}`, { method: "DELETE" });
    closeDrawer(); toast("등록을 해제했습니다."); reload();
  },
  async "server-audience"(el) {
    const s = registry?.servers.find((row) => row.id === el.dataset.id);
    if (!s) return;
    const fd = await ask({ title: `사용 대상 · ${s.display_name}`, fields: audienceFields((registry.registrations?.[el.dataset.id]?.allowed_principals || []).includes("*") ? "all" : "requester"), confirm: "변경" });
    if (!fd) return;
    await gw(`registry/servers/${encodeURIComponent(el.dataset.id)}/audience`, { method: "POST",
      body: (({ audience, audience_users }) => ({ audience, users: audience_users }))(audienceBody(fd)) });
    closeDrawer(); toast("사용 대상을 변경했습니다."); reload();
  },
  async "intake-accept-risk"(el) {
    const fd = await ask({ title: `위험 수용 · ${el.dataset.name}`,
      fields: html`${field.select("days", "수용 기한", { 7: "7일", 14: "14일", 30: "30일" }, "7")}
        ${field.area("reason", "수용 사유", 'required minlength="10" maxlength="1000"')}`, confirm: "수용" });
    if (!fd) return;
    const r = await api(`/api/mcp-requests/${el.dataset.id}/accept-risk`, { method: "POST", body: { reason: fd.get("reason").trim(), days: Number(fd.get("days")) } });
    toast(r.message); reload();
  },
  async "tool-scope"(el) {
    const s = registry?.servers.find((row) => row.id === el.dataset.id);
    const registration = registry?.registrations?.[el.dataset.id];
    if (!s || !registration) return;
    const pending = Object.keys(registration.tools || {}).filter((name) => !registration.tool_reviews?.[name]);
    const fd = await ask({ title: `도구 범위 심사 · ${s.display_name}`, fields: scopeFields(pending), confirm: "기록" });
    if (!fd) return;
    const r = await gw(`registry/servers/${encodeURIComponent(el.dataset.id)}/tool-reviews`, { method: "POST", body: { reviews: collectScopes(fd, pending) } });
    closeDrawer(); toast(`도구 ${r.reviewed.length}개의 범위를 기록했습니다.`); reload();
  },
  async "impact-scope"(el) {
    const item = registry?.registrations?.[el.dataset.id]?.tool_reviews?.[el.dataset.tool];
    if (!item) return;
    const fd = await ask({ title: "중대 영향 심사", fields: html`<fieldset><legend>영향 영역</legend>
      ${Object.entries(IMPACT_DOMAIN).map(([key, label]) => html`<label class="check"><input type="checkbox" name="impact" value="${key}" ${(item.impact_domains || []).includes(key) ? raw("checked") : ""} /> ${label}</label>`)}</fieldset>`, confirm: "기록" });
    if (!fd) return;
    const { purpose, asset, destinations, inputs, mask, grade, accepts_from, consent } = item;
    const domains = fd.getAll("impact");
    await gw(`registry/servers/${encodeURIComponent(el.dataset.id)}/tool-reviews`, { method: "POST", body: {
      reviews: { [el.dataset.tool]: { purpose, asset, destinations, inputs, mask, grade, accepts_from, consent,
        high_impact: domains.length > 0, impact_domains: domains } } } });
    toast("기록했습니다."); closeDrawer(); reload();
  },
  async "destination-scope"(el) {
    const item = registry?.registrations?.[el.dataset.id]?.tool_reviews?.[el.dataset.tool];
    if (!item) return;
    const fd = await ask({ title: `허용 주소 · ${el.dataset.tool}`,
      fields: field.text("destinations", "허용 주소", 'maxlength="300"', (item.destinations || []).join(", ")), confirm: "기록" });
    if (!fd) return;
    const { purpose, asset, inputs, mask, grade, accepts_from, consent, high_impact, impact_domains } = item;
    await gw(`registry/servers/${encodeURIComponent(el.dataset.id)}/tool-reviews`, { method: "POST", body: {
      reviews: { [el.dataset.tool]: { purpose, asset, destinations: hostList(fd.get("destinations")), inputs, mask, grade, accepts_from, consent,
        high_impact: Boolean(high_impact), impact_domains: impact_domains || [] } } } });
    toast("기록했습니다."); closeDrawer(); reload();
  },
  async "residency-review"(el) {
    const s = registry?.servers.find((row) => row.id === el.dataset.id);
    if (!s) return;
    const current = s.residency || {};
    const fd = await ask({ title: `위치 심사 · ${s.display_name}`, fields: html`<div class="stack">
      ${field.text("processing_countries", "처리 국가", 'required maxlength="749"', (current.processing_countries || []).join(", "))}
      ${field.text("storage_countries", "저장 국가", 'required maxlength="749"', (current.storage_countries || []).join(", "))}
      ${field.text("processor", "처리 주체", 'required maxlength="500"', current.processor || "")}
      ${field.text("evidence_ref", "위치 근거", 'required maxlength="500"', current.evidence_ref || "")}
      ${field.text("transfer_basis", "이전 근거", 'maxlength="500"', current.transfer_basis || "")}</div>`, confirm: "기록" });
    if (!fd) return;
    const countries = (key) => String(fd.get(key)).split(",").map((code) => code.trim().toUpperCase()).filter(Boolean);
    await gw(`registry/servers/${encodeURIComponent(el.dataset.id)}/residency`, { method: "POST", body: {
      processing_countries: countries("processing_countries"), storage_countries: countries("storage_countries"),
      processor: String(fd.get("processor")).trim(), evidence_ref: String(fd.get("evidence_ref")).trim(),
      transfer_basis: String(fd.get("transfer_basis")).trim() } });
    closeDrawer(); toast("위치 심사를 기록했습니다."); reload();
  },
  async "intake-reject"(el) {
    const fd = await ask({ title: "도입 신청 거부", fields: field.text("note", "사유", 'required minlength="2" maxlength="500"'), confirm: "거부", danger: true });
    if (!fd) return;
    await api(`/api/mcp-requests/${el.dataset.id}/reject`, { method: "POST", body: { note: fd.get("note") } });
    toast("거부했습니다."); reload();
  },
  policy(el) {
    const p = policyLedger.find((row) => row.policy_id === el.dataset.id);
    if (!p) return;
    openDrawer(p.name, html`<div class="row-actions">${UNSUPPORTED_POLICY.has(p.policy_id) ? chip("outline", "지원 안 함") : outcomeDecision(p.outcome) ? decisionChip(outcomeDecision(p.outcome)) : chip("outline", p.outcome)}
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
    if (!chosen.length) { toast("항목을 하나 이상 선택하세요.", true); return; }
    const r = await gw(`termination/cases/${currentCase.case.id}/collect`, { method: "POST", body: { kinds: chosen } });
    toast(`증거 ${r.collected.length}건을 기록했습니다.`); reload();
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
      ${kv([["하네스", g.harness === "claude" ? "Claude Code" : "Codex"], ["통제", connectorControlChip(connectorItems, g.key)], ["종류", g.kinds.map((k) => CONNECTOR_KIND[k] || k).join(" · ")],
        ["대상", html`<span class="mono">${connectorTarget(g)}</span>`], ["처음 보고", when(g.first_seen)],
        ["결정", g.decision ? html`${g.note || "—"}<span class="sub">${g.decided_by} · ${when(g.decided_at)}</span>` : ""]])}
      <h3>사용 엔드포인트</h3>
      <table class="data"><thead><tr><th>사용자</th><th>엔드포인트</th><th>상태</th><th>마지막 보고</th></tr></thead><tbody>
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
  async "connect-token"(form) {
    const data = new FormData(form);
    const result = await api(`/api/my-connections/${encodeURIComponent(form.dataset.id)}/token`, {
      method: "POST", body: { token: String(data.get("token") || "").trim() } });
    form.reset();
    toast(`${result.account} 계정을 연결했습니다.`);
    reload();
  },
  "sbom-impact"(form) {
    const q = new URLSearchParams(new FormData(form));
    location.hash = `#/sbom-impact?${q}`;
    reload();
  },
  audit(form) {
    // datetime-local carries no zone; the server needs one, so send UTC.
    const q = new URLSearchParams([...new FormData(form)].filter(([,v]) => String(v).trim())
      .map(([k, v]) => [k, ["since", "until"].includes(k) ? new Date(v).toISOString() : v]));
    location.hash = `#/audit?${q}`;
    reload();
  },
  async intake(form) {
    const fd = new FormData(form);
    const body = Object.fromEntries(["display_name", "repository_url", "endpoint_url", "intake_kind", "requested_transport", "purpose"].map((k) => [k, String(fd.get(k) || "").trim()]));
    const r = await api("/api/mcp-requests", { method: "POST", body: { ...body, data_class: fd.get("data_class"),
      requested_tools: fd.getAll("requested_tool") } });
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
  if (event.target.matches("[data-audience]")) {
    const users = event.target.form.querySelector("[data-audience-users]");
    users.hidden = event.target.value !== "selected";
    if (users.hidden) users.querySelector("input").value = "";
    return;
  }
  if (event.target.matches("[data-intake-kind]")) {
    for (const label of event.target.form.querySelectorAll("[data-intake-field]")) {
      label.hidden = label.dataset.intakeField !== event.target.value;
      if (label.hidden) for (const input of label.querySelectorAll("input,textarea")) input.value = "";
    }
    event.target.form.elements.requested_transport.value = event.target.value === "repository" ? "stdio" : "streamable-http";
    event.target.form.querySelector("[data-requested-tools]").replaceChildren();
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
    feed.page = 1;
    reload();
    return;
  }
  if (event.target.matches('[data-act-change="endpoint-auto"]')) {
    gw("endpoint/settings", { method: "PUT", body: { auto_activate: event.target.value === "on" } })
      .then(() => toast(event.target.value === "on" ? "새 PC를 자동으로 활성화합니다." : "새 PC는 관리자가 활성화합니다."))
      .catch((error) => { toast(error.message); reload(); });
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
  if (event.target.matches("[data-feed-search]")) {
    const input = event.target;
    clearTimeout(input.searchTimer);
    input.searchTimer = setTimeout(() => {
      feed.query = input.value.trim();
      feed.page = 1;
      reload();
    }, 300);
    return;
  }
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

function startAdminSessionGuard() {
  const warning = $("#session-warning");
  const message = $("#session-warning-text");
  const keepUsing = $("#session-continue");
  const dismiss = $("#session-dismiss");
  const activityKey = `mcp-console-admin-activity-${viewer.user_id}`;
  const { issuedAt, expiresAt: tokenExpiresAt } = tokenTimes(token);
  const maximumAt = (issuedAt || Date.now()) + ADMIN_MAX_MS;
  let lastActivity = Date.now();
  let lastServerTouch = 0;
  let touching = false;
  let ending = false;
  let warningDismissed = false;
  let currentWarningReason = "";

  const touchServerSession = async () => {
    if (touching || Date.now() - lastServerTouch < 60000) return;
    touching = true;
    try {
      await api("/auth/session/activity", { method: "POST" });
      lastServerTouch = Date.now();
    } catch { /* A failed heartbeat never extends the server session. */ }
    finally { touching = false; }
  };

  const recordActivity = (event) => {
    if (!event.isTrusted) return;
    lastActivity = Date.now();
    if (currentWarningReason === "idle") warningDismissed = false;
    localStorage.setItem(activityKey, String(lastActivity));
    touchServerSession();
  };
  for (const name of ["pointerdown", "keydown", "wheel"]) {
    document.addEventListener(name, recordActivity, { passive: true });
  }
  window.addEventListener("storage", (event) => {
    if (event.key === activityKey) {
      lastActivity = Math.max(lastActivity, Number(event.newValue) || 0);
      touchServerSession();
    }
  });
  localStorage.setItem(activityKey, String(lastActivity));
  touchServerSession();

  keepUsing.addEventListener("click", () => {
    lastActivity = Date.now();
    warningDismissed = false;
    localStorage.setItem(activityKey, String(lastActivity));
    touchServerSession();
  });
  dismiss.addEventListener("click", () => {
    warningDismissed = true;
    warning.close();
  });

  const endSession = async (reason) => {
    if (ending) return;
    ending = true;
    await fetch("/auth/logout", { method: "POST", headers: { authorization: `Bearer ${token}` } }).catch(() => {});
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(activityKey);
    location.replace(`/login?session=${reason}`);
  };

  setInterval(() => {
    if (ending) return;
    const now = Date.now();
    if (!document.hidden && now - lastActivity < 60000) touchServerSession();
    const idleAt = lastActivity + ADMIN_IDLE_MS;
    const deadline = Math.min(idleAt, maximumAt, tokenExpiresAt);
    const reason = idleAt <= maximumAt && idleAt <= tokenExpiresAt ? "idle"
      : maximumAt <= tokenExpiresAt ? "maximum" : "authentication";
    const remaining = deadline - now;
    if (remaining <= 0) { endSession(reason); return; }
    if (remaining > SESSION_WARNING_MS) {
      if (warning.open) warning.close();
      warningDismissed = false;
      return;
    }
    if (warningDismissed) return;
    const seconds = Math.ceil(remaining / 1000);
    const minutes = Math.floor(seconds / 60);
    const rest = seconds % 60;
    const reasonText = reason === "idle" ? "유휴 시간이"
      : reason === "maximum" ? "최대 로그인 시간이" : "인증 세션이";
    message.textContent = `${reasonText} ${minutes}분 ${rest}초 후 만료됩니다.`;
    keepUsing.hidden = reason !== "idle";
    currentWarningReason = reason;
    if (!warning.open) warning.showModal();
  }, 1000);
}

(function applyTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  document.documentElement.dataset.theme = saved || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
})();

async function boot() {
  viewer = await api("/auth/me");
  viewer.admin = viewer.roles.includes("admin");
  if (viewer.admin) startAdminSessionGuard();
  const mobile = matchMedia("(max-width: 900px)");
  setNavCollapsed(mobile.matches || localStorage.getItem(NAV_KEY) === "true");
  mobile.addEventListener("change", () => setNavCollapsed(mobile.matches || localStorage.getItem(NAV_KEY) === "true"));
  $("#app-identity").textContent = `${viewer.name} · ${t(viewer.role_label)}`;
  window.addEventListener("hashchange", route);
  await route();
  if (viewer.kit && viewer.managed_required && !(viewer.managed_devices || []).some((d) => d.status === "active" && d.managed_state === "active")) {
    ACTIONS["pc-kit"]();
  }
  refreshBadges(); setInterval(refreshBadges, 30000);
}
boot().catch((error) => { $("#view").innerHTML = String(html`<div class="note bad">${error.message}</div>`); });
