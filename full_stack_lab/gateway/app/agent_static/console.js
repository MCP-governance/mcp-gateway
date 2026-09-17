const TOKEN_KEY = "bob_mock_sso_token";
const SESSION_KEY = "bob_agent_session";
const token = sessionStorage.getItem(TOKEN_KEY);

const NAV = [
  {page: "overview", group: "GOVERNANCE", label: "운영 현황"},
  {page: "intake", group: "GOVERNANCE", label: "MCP 도입"},
  {page: "verification", group: "GOVERNANCE", label: "검증 파이프라인"},
  {page: "risks", group: "GOVERNANCE", label: "위험 분석"},
  {page: "mcpscan", group: "GOVERNANCE", label: "AI 코드 감사"},
  {page: "policy", group: "GOVERNANCE", label: "정책 관리대장"},
  {page: "accounts", group: "GOVERNANCE", label: "신원 관리대장"},
  {page: "execution", group: "OPERATIONS", label: "MCP 실행"},
  {page: "audit", group: "OPERATIONS", label: "감사 기록"},
];
const PROMPTS = {
  partner: [["공개 문서를 읽어줘", "공개 문서 읽기"], ["감사 대응 사본을 읽어줘", "예외 적용 열람"], ["현재 시간을 알려줘", "시간 조회"]],
  employee: [["공개 문서를 읽어줘", "공개 문서 읽기"], ["중요 계약 초안을 읽어줘", "중요 문서 열람"], ["내부 업무 메모를 수정해줘", "내부 메모 수정"], ["현재 시간을 알려줘", "시간 조회"]],
  admin: [["공개 문서를 읽어줘", "공개 문서 읽기"], ["중요 계약 초안을 읽어줘", "중요 문서 열람"], ["공개 공지를 외부에 전송해줘", "외부 전송"], ["중요 계약을 외부에 전송해줘", "중요 외부 전송"], ["현재 시간을 알려줘", "시간 조회"]],
};
const INTAKE_STATUS = {
  HOLD: "보류", VALIDATION_QUEUED: "검증 대기", VALIDATING: "검증 중",
  VALIDATED: "검증 통과", APPROVED: "승인", REJECTED: "거부", FAILED: "검증 실패",
};
const INTAKE_TONE = {VALIDATED: "ok", APPROVED: "ok", REJECTED: "bad", FAILED: "bad", VALIDATING: "warn", VALIDATION_QUEUED: "warn"};
const SERVER_STATUS = {READY: "운영", DISABLED: "비활성", BLOCKED_SUPPLY_CHAIN: "공급망 차단", ERROR: "오류"};
const JOB_STATUS = {QUEUED: "대기", RUNNING: "실행 중", DONE: "완료", FAILED: "실패", CANCELLED: "취소"};
const ACCOUNT_STATUS = {active: "사용 중", disabled: "중지", locked: "잠김"};
const ACCOUNT_TONE = {active: "ok", disabled: "bad", locked: "warn"};
const JOB_TRIGGER = {manual: "수동 실행", validated: "검증 통과 자동", rescan: "재감사 주기", drift: "드리프트 감지"};
const DECISIONS = ["Allow", "Alert", "Approval", "Restrict", "Block"];
const SEVERITY_ALIAS = {ERROR: "HIGH", WARNING: "MEDIUM", INFO: "LOW", UNKNOWN: "LOW", NONE: "LOW", NOTE: "LOW"};

let state = null;
let scan = null;
let allowed = [];
let sessionId = sessionStorage.getItem(SESSION_KEY);
let pendingRequest = null;
let currentResult = null;
let busy = false;
let severityFilter = "ALL";
let findingTerm = "";
let auditTerm = "";
let liveRows = [];
let stream = null;
// 감사 기록은 한 번에 다 그리면 스크롤 끝까지 가야 오래된 행이 보이고, 정렬이
// 없으면 "누가 제일 많이 막혔나"를 표에서 답할 수 없다.
let accounts = null;
let auditSort = {key: "created_at", dir: "desc"};
let auditLimit = 25;
const AUDIT_PAGE = 25;
const THEME_KEY = "bob_console_theme";

/* ── theme ────────────────────────────────────────────────── */
// 판정을 오래 들여다보는 화면이라 야간 사용이 실제로 많다. 시스템 설정을 기본으로
// 두고, 사용자가 고른 값이 있으면 그것이 이긴다.
function applyTheme(value) {
  if (value === "light" || value === "dark") document.documentElement.dataset.theme = value;
  else delete document.documentElement.dataset.theme;
  const button = document.querySelector("#theme-toggle");
  if (button) button.textContent = value === "dark" ? "☾" : value === "light" ? "☀" : "◐";
}
function initTheme() {
  let stored = null;
  try { stored = localStorage.getItem(THEME_KEY); } catch { stored = null; }
  applyTheme(stored);
}
function cycleTheme() {
  let stored = null;
  try { stored = localStorage.getItem(THEME_KEY); } catch { stored = null; }
  const next = stored === "light" ? "dark" : stored === "dark" ? null : "light";
  try { next ? localStorage.setItem(THEME_KEY, next) : localStorage.removeItem(THEME_KEY); } catch { /* 저장 못 해도 화면은 바뀐다 */ }
  applyTheme(next);
}

/* ── helpers ──────────────────────────────────────────────── */

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}
function count(value) { return Number(value || 0); }
function isAdmin() { return (state?.viewer?.roles || []).includes("admin"); }
function currentPage() {
  const page = location.hash.replace("#/", "");
  return allowed.includes(page) ? page : allowed[0] || "execution";
}
function redirectToLogin() { sessionStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(SESSION_KEY); window.location.replace("/login"); }

function formatDate(value) {
  return value ? new Intl.DateTimeFormat("ko-KR", {dateStyle: "short", timeStyle: "short"}).format(new Date(value)) : "-";
}
// "26. 9. 16. 오후 6:52"보다 "3분 전"이 흐름을 읽는 데 훨씬 빠르다.
function ago(value) {
  if (!value) return "-";
  const seconds = Math.round((Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 10) return "방금";
  if (seconds < 60) return `${seconds}초 전`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}분 전`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}시간 전`;
  return `${Math.floor(seconds / 86400)}일 전`;
}

// 알림이 화면에 계속 붙어 있으면 다음 작업의 결과와 섞인다. 스스로 사라지게 둔다.
function toast(message, tone = "ok") {
  const box = document.createElement("div");
  box.className = `toast ${tone}`;
  box.textContent = message;
  document.querySelector("#toasts").prepend(box);
  setTimeout(() => { box.classList.add("leaving"); setTimeout(() => box.remove(), 300); }, tone === "bad" ? 8000 : 4500);
}

// FastAPI의 422 detail은 객체 배열이다. 그대로 문자열화하면 [object Object]가
// 되어 사용자가 고칠 수 있는 유일한 오류가 가장 안 읽히는 자리가 된다.
function errorMessage(data, status) {
  const detail = data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map(item => {
      const field = Array.isArray(item.loc) ? item.loc.filter(part => part !== "body").join(".") : "";
      return field ? `${field}: ${item.msg}` : item.msg;
    }).join(" / ");
  }
  return `요청을 처리하지 못했습니다. (HTTP ${status})`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || "GET",
    headers: {Authorization: `Bearer ${token}`, ...(options.body ? {"Content-Type": "application/json"} : {})},
    ...(options.body ? {body: JSON.stringify(options.body)} : {}),
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) { redirectToLogin(); throw new Error("다시 로그인하세요."); }
  if (!response.ok) throw new Error(errorMessage(data, response.status));
  return data;
}

// 버튼이 눌린 뒤 아무 반응이 없으면 사용자는 다시 누른다. 그 자리에서 상태를 바꾼다.
async function withButton(button, label, run) {
  if (!button || button.disabled) return;
  const original = button.textContent;
  button.disabled = true;
  button.textContent = label;
  try { return await run(); }
  finally { button.disabled = false; button.textContent = original; }
}

async function act(button, label, run, fallback) {
  if (busy) return;
  busy = true;
  try {
    const body = await withButton(button, label, run);
    toast(body?.message || fallback);
    await loadConsole();
  } catch (error) { toast(error.message, "bad"); }
  finally { busy = false; }
}

/* ── navigation ───────────────────────────────────────────── */

// 화면 8개를 평평하게 나열하면 어디부터 봐야 하는지 메뉴가 답하지 못한다.
// 처리 대기 수를 메뉴에 붙이면 이동 전에 알 수 있다.
function navBadges() {
  if (!state) return {};
  const badges = {};
  const pendingIntake = state.intake.filter(row => ["HOLD", "VALIDATION_QUEUED", "VALIDATING"].includes(row.status)).length;
  if (pendingIntake) badges.intake = [pendingIntake, "warn"];
  const approvals = (state.approvals || []).length;
  if (approvals) badges.execution = [approvals, "warn"];
  const criticals = count(state.severity?.critical);
  if (criticals) badges.risks = [criticals, "bad"];
  const unwired = (state.coverage?.unwired || []).length;
  if (unwired) badges.verification = [unwired, "warn"];
  if (scan && !scan.worker?.alive && (scan.worker?.queued || scan.worker?.running)) badges.mcpscan = ["!", "bad"];
  return badges;
}

function renderNav() {
  const visible = NAV.filter(item => allowed.includes(item.page));
  const badges = navBadges();
  let group = null;
  document.querySelector("#side-nav-list").innerHTML = visible.map(item => {
    const heading = item.group !== group ? `<p class="nav-group">${item.group}</p>` : "";
    group = item.group;
    const badge = badges[item.page];
    return `${heading}<button data-page="${item.page}" type="button"><span>${escapeHtml(item.label)}</span>` +
      `${badge ? `<span class="nav-badge ${badge[1]}">${escapeHtml(badge[0])}</span>` : ""}</button>`;
  }).join("");
  document.querySelectorAll(".side-nav [data-page]").forEach(button =>
    button.classList.toggle("active", button.dataset.page === currentPage()));
}

function navigate(page, replace = false) {
  if (!allowed.includes(page)) page = allowed[0] || "execution";
  document.querySelectorAll("[data-view]").forEach(view => view.classList.toggle("hidden", view.dataset.view !== page));
  document.querySelectorAll(".side-nav [data-page]").forEach(button => button.classList.toggle("active", button.dataset.page === page));
  if (location.hash !== `#/${page}`) {
    if (replace) history.replaceState(null, "", `#/${page}`); else location.hash = `/${page}`;
  }
  if (page === "mcpscan") loadScan().catch(error => toast(error.message, "bad"));
}

function cards(target, rows) {
  document.querySelector(target).innerHTML = rows.map(([label, value, note, tone]) =>
    `<article class="metric-card ${tone || ""}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>`).join("");
}

function emptyState(message, hint, action) {
  // "없습니다"로 끝나는 빈 상태는 다음에 뭘 해야 할지 알려주지 않는다.
  return `<p class="empty-state">${escapeHtml(message)}${hint ? `<small>${escapeHtml(hint)}</small>` : ""}` +
    `${action ? `<button class="ghost-button" data-page="${escapeHtml(action[1])}" type="button">${escapeHtml(action[0])}</button>` : ""}</p>`;
}

function skeleton(rows = 3) {
  return `<div class="skeleton" aria-hidden="true">${"<i></i>".repeat(rows)}</div>`;
}

// 첫 로딩에서 빈 화면과 "불러오는 중"이 같아 보이면 사용자는 고장으로 읽는다.
function showSkeletons() {
  [["#overview-cards", 4], ["#registry-summary", 3], ["#intake-list", 3],
   ["#validation-list", 3], ["#finding-list", 4], ["#ledger-list", 0],
   ["#coverage-list", 2], ["#approvals-list", 2]].forEach(([selector, rows]) => {
    const node = document.querySelector(selector);
    if (node && !node.children.length && rows) node.innerHTML = skeleton(rows);
  });
}

function showLoadError(message) {
  const main = document.querySelector(".console-main");
  document.querySelector("#load-error")?.remove();
  const box = document.createElement("div");
  box.id = "load-error";
  box.className = "load-error";
  box.innerHTML = `<span>${escapeHtml(message)}</span><button class="ghost-button" id="load-retry" type="button">다시 시도</button>`;
  main.prepend(box);
  document.querySelector("#load-retry").addEventListener("click", event =>
    withButton(event.currentTarget, "다시 읽는 중", async () => {
      await loadConsole();
      document.querySelector("#load-error")?.remove();
    }).catch(error => toast(error.message, "bad")));
}

/* ── live stream ──────────────────────────────────────────── */

function decisionRow(row) {
  return `<li class="live-row"><span class="decision ${escapeHtml(String(row.decision).toLowerCase())}">${escapeHtml(row.decision)}</span>
    <div><b>${escapeHtml(row.tool_name)}</b><small>${escapeHtml(row.user_token)} · ${escapeHtml(row.data_class)}/${escapeHtml(row.action)} · <code>${escapeHtml(row.policy_id)}</code>${row.exception_id ? " · 예외 " + escapeHtml(row.exception_id) : ""}</small></div>
    <span class="live-time">${escapeHtml(ago(row.created_at))}</span></li>`;
}

function renderLive() {
  const feed = document.querySelector("#live-feed");
  if (!feed) return;
  feed.innerHTML = liveRows.length
    ? liveRows.slice(0, 25).map(decisionRow).join("")
    : `<li class="empty-state">아직 들어온 판정이 없습니다.<small>MCP 실행에서 요청을 보내면 여기에 즉시 나타납니다.</small></li>`;
  const recent = liveRows.slice(0, 40);
  const bar = document.querySelector("#live-sparkline");
  bar.innerHTML = DECISIONS.map(label =>
    `<span class="spark ${label.toLowerCase()}" title="${label}"></span>`).join("");
  DECISIONS.forEach((label, index) => {
    const value = recent.filter(row => row.decision === label).length;
    const node = bar.children[index];
    node.title = `${label} ${value}`;
    // CSP style-src 'self'는 인라인 style 속성을 막는다. 스크립트에서 CSSOM으로
    // 쓰는 것은 막지 않으므로 크기는 여기서 준다.
    node.style.width = `${recent.length ? Math.round(value / recent.length * 100) : 0}%`;
  });
}

function markLive(on) {
  document.querySelectorAll(".live-state").forEach(node => {
    node.classList.toggle("on", on);
    node.lastChild.textContent = on ? "수신 중" : "끊김";
  });
}

function openStream() {
  if (stream || !(allowed.includes("overview") || allowed.includes("audit"))) return;
  // EventSource는 헤더를 못 붙이므로 토큰을 query로 넘기지 않고, 같은 출처에서
  // fetch 스트림을 읽는다. CSP connect-src 'self' 안에서 동작한다.
  const controller = new AbortController();
  stream = controller;
  (async () => {
    try {
      const response = await fetch("/api/stream/decisions", {
        headers: {Authorization: `Bearer ${token}`}, signal: controller.signal,
      });
      if (!response.ok || !response.body) throw new Error("stream unavailable");
      markLive(true);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const {value, done} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream: true});
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
          const line = part.split("\n").find(item => item.startsWith("data: "));
          if (!line) continue;
          let payload;
          try { payload = JSON.parse(line.slice(6)); } catch { continue; }
          const rows = (payload.rows || []).reverse();
          if (!rows.length) continue;
          liveRows = rows.concat(liveRows).slice(0, 60);
          renderLive();
          prependAudit(rows);
        }
      }
    } catch (error) {
      if (controller.signal.aborted) return;
    } finally {
      markLive(false);
      stream = null;
      setTimeout(openStream, 5000);
    }
  })();
}

/* ── overview ─────────────────────────────────────────────── */

// 대시보드의 첫 줄은 상태가 아니라 "지금 누가 무엇을 해야 하는가"여야 한다.
// 승인 대기와 죽은 워커는 숫자 카드 사이에 섞여 있으면 눈에 띄지 않는다.
function renderActionBanner() {
  const box = document.querySelector("#action-banner");
  if (!box) return;
  const items = [];
  const approvals = (state.approvals || []).length;
  if (approvals) items.push(["warn", `승인 대기 <b>${approvals}건</b>`,
    "10분 안에 승인하거나 사유와 함께 거부해야 합니다.", "확인", "execution"]);
  const holds = state.intake.filter(row => row.status === "HOLD").length;
  if (holds) items.push(["warn", `격리 검증 대기 <b>${holds}건</b>`,
    "제출만 되어 있고 아직 증적이 없습니다.", "도입 화면", "intake"]);
  const validated = state.intake.filter(row => row.status === "VALIDATED").length;
  if (validated) items.push(["", `검증 통과 <b>${validated}건</b>`,
    "Registry 등록 대상으로 올릴지 결정이 남았습니다.", "검토", "verification"]);
  const criticals = count(state.severity?.critical);
  if (criticals) items.push(["bad", `치명 공급망 발견 <b>${criticals}건</b>`,
    "서버에 귀속된 치명점은 호출을 차단합니다.", "위험 분석", "risks"]);
  const unwired = (state.coverage?.unwired || []).length;
  if (unwired) items.push(["warn", `차단에 연결되지 않은 스캔 대상 <b>${unwired}건</b>`,
    "scan_path는 있지만 결과가 없어 MCP-SUPPLY-001이 세지 못합니다.", "검증 파이프라인", "verification"]);
  if (scan && scan.worker && !scan.worker.alive && (scan.worker.queued || scan.worker.running))
    items.push(["bad", "AI 코드 감사 워커 응답 없음",
      `대기 ${count(scan.worker.queued)}건 · 실행 중 ${count(scan.worker.running)}건이 진행되지 않습니다.`,
      "감사 화면", "mcpscan"]);
  if ((state.enforcement?.enforcement || "") === "monitor")
    items.push(["warn", "관찰 모드",
      "권한 판정은 기록만 하고 실행됩니다. 무결성 통제는 그대로 집행됩니다.", "집행 전환", "overview"]);

  box.innerHTML = items.length
    ? items.map(([tone, title, note, label, page]) =>
        `<div class="action-item ${tone}"><span>${title}</span><small>${escapeHtml(note)}</small>` +
        `<span class="spacer"></span><button class="ghost-button" data-page="${escapeHtml(page)}" type="button">${escapeHtml(label)}</button></div>`).join("")
    : `<div class="action-item good"><span><b>지금 처리할 것이 없습니다.</b></span><small>승인 대기, 검증 대기, 치명 발견, 워커 이상이 모두 없습니다.</small></div>`;
}

function renderOverview() {
  if (!allowed.includes("overview")) return;
  renderActionBanner();
  const active = state.registry.filter(server => server.status === "READY").length;
  const waiting = state.intake.filter(request => ["HOLD", "VALIDATION_QUEUED", "VALIDATING"].includes(request.status)).length;
  const blocked = state.decisions.filter(item => item.decision === "Block").length;
  cards("#overview-cards", [
    ["운영 MCP", active, `Registry ${state.registry.length}건`, active ? "good" : "warn"],
    ["검증 대기", waiting, "보류·대기·검증 중", waiting ? "warn" : ""],
    ["차단 판정", blocked, `최근 판정 ${state.decisions.length}건 중`, blocked ? "bad" : "good"],
    ["실행 증적", state.upstream_effect_count, "독립 upstream 효과", ""],
  ]);
  document.querySelector("#registry-summary").innerHTML = state.registry.map(server => {
    const status = server.status || "ERROR";
    return `<div class="server-row"><div><b>${escapeHtml(server.display_name || server.id)}</b><small>${escapeHtml(server.transport || "")} · ${escapeHtml(server.supplier || "")}</small></div><span class="tag ${status === "READY" ? "ok" : "muted"}">${escapeHtml(SERVER_STATUS[status] || status)}</span></div>`;
  }).join("") || emptyState("등록된 MCP가 없습니다.");

  const buckets = DECISIONS.map(label => ({label, value: state.decisions.filter(item => item.decision === label).length}));
  const max = Math.max(1, ...buckets.map(item => item.value));
  document.querySelector("#decision-total").textContent = state.decisions.length;
  const chart = document.querySelector("#decision-chart");
  chart.innerHTML = buckets.map(item =>
    `<div class="bar-item"><strong>${item.value}</strong><i class="bar ${item.label.toLowerCase()}"></i><span>${item.label}</span></div>`).join("");
  // 인라인 style 속성은 CSP가 막는다. 막힌 채로도 막대가 "보이기는" 해서 이
  // 차트는 값과 무관하게 평평했다.
  buckets.forEach((item, index) => {
    chart.children[index].querySelector(".bar").style.height =
      `${Math.max(2, Math.round(item.value / max * 120))}px`;
  });

  const mode = state.enforcement?.enforcement || "확인 중";
  const badge = document.querySelector("#enforcement-badge");
  badge.textContent = mode === "monitor" ? "관찰" : "집행";
  badge.className = `tag ${mode === "monitor" ? "warn" : "ok"}`;
  const stopped = count(state.monitor?.would_have_stopped);
  document.querySelector("#enforcement-body").innerHTML = `
    <p>${mode === "monitor"
      ? `관찰 모드입니다. 권한 판정은 기록만 하고 실행합니다. 최근 7일 기준 집행 모드였다면 <b>${stopped}건</b>이 멈췄습니다.`
      : "집행 모드입니다. 정책 판정이 그대로 적용됩니다."}</p>
    ${isAdmin() ? `<div class="button-row"><button class="ghost-button" data-enforcement="enforce" type="button">집행 모드</button><button class="ghost-button" data-enforcement="monitor" type="button">관찰 모드</button></div>` : ""}`;
}

/* ── intake ───────────────────────────────────────────────── */

function intakeCard(request, withActions) {
  const evidence = request.evidence || {};
  const meta = [escapeHtml(request.requested_transport), `위험도 ${escapeHtml(request.risk_level)}`, ago(request.created_at)];
  if (request.commit_sha) meta.push(`commit ${escapeHtml(String(request.commit_sha).slice(0, 12))}`);
  if (evidence.sbom_components !== undefined) {
    meta.push(`구성요소 ${count(evidence.sbom_components)}`);
    meta.push(`C ${count(evidence.critical)} · H ${count(evidence.high)} · M ${count(evidence.medium)}`);
  }
  const actions = [];
  if (withActions && request.status === "HOLD") actions.push(`<button class="mini-button" data-queue="${escapeHtml(request.id)}" type="button">격리 검증 실행</button>`);
  if (withActions && request.status === "VALIDATED") actions.push(`<button class="mini-button" data-approve-intake="${escapeHtml(request.id)}" type="button">승인</button>`);
  if (withActions && ["HOLD", "VALIDATION_QUEUED", "VALIDATED"].includes(request.status)) actions.push(`<button class="mini-button danger" data-reject-intake="${escapeHtml(request.id)}" type="button">거부</button>`);
  const busyRow = ["VALIDATION_QUEUED", "VALIDATING"].includes(request.status);
  return `<article class="request-row${busyRow ? " working" : ""}">
    <div class="request-top"><div><h3>${escapeHtml(request.display_name)}</h3><a href="${escapeHtml(request.repository_url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(request.repository_url)}</a></div><span class="tag ${INTAKE_TONE[request.status] || "muted"}">${escapeHtml(INTAKE_STATUS[request.status] || request.status)}</span></div>
    <p>${escapeHtml(request.purpose)}</p>
    <div class="request-meta">${meta.map(item => `<span>${item}</span>`).join("")}</div>
    ${request.review_note ? `<p class="note-line">${escapeHtml(request.review_note)}</p>` : ""}
    ${actions.length ? `<div class="button-row">${actions.join("")}</div>` : ""}
    <div class="reason-slot" data-reason-for="${escapeHtml(request.id)}"></div>
  </article>`;
}

function renderIntake() {
  if (!allowed.includes("intake")) return;
  document.querySelector("#intake-total").textContent = state.intake.length;
  document.querySelector("#intake-list").innerHTML =
    state.intake.map(request => intakeCard(request, isAdmin())).join("")
    || emptyState("제출한 요청이 없습니다.", "위에서 먼저 검색해 이미 승인된 MCP인지 확인하세요.");
}

function renderCatalog(result) {
  const box = document.querySelector("#catalog-results");
  const rows = [];
  for (const server of result.registry) {
    rows.push(`<div class="catalog-row"><span class="tag ${server.status === "READY" ? "ok" : "muted"}">Registry · ${escapeHtml(SERVER_STATUS[server.status] || server.status)}</span>
      <div><b>${escapeHtml(server.display_name)}</b><small>${escapeHtml(server.source_url)} · ${escapeHtml(server.supplier)} · ${escapeHtml(server.status_reason || "")}</small></div></div>`);
  }
  for (const request of result.requests) {
    const when = request.reviewed_at || request.validated_at || request.created_at;
    rows.push(`<div class="catalog-row"><span class="tag ${INTAKE_TONE[request.status] || "muted"}">도입 요청 · ${escapeHtml(INTAKE_STATUS[request.status] || request.status)}</span>
      <div><b>${escapeHtml(request.display_name)}</b><small>${escapeHtml(request.repository_url)} · 위험도 ${escapeHtml(request.risk_level)}${request.commit_sha ? " · commit " + escapeHtml(String(request.commit_sha).slice(0, 12)) : ""} · ${escapeHtml(ago(when))}</small></div></div>`);
  }
  box.innerHTML = rows.join("")
    || emptyState(result.query ? `"${result.query}"로 등록되거나 신청된 MCP가 없습니다.` : "검색어를 입력하세요.",
                  result.query ? "새 요청을 제출해도 됩니다." : "");
}

async function searchCatalog(button) {
  const term = document.querySelector("#catalog-search").value.trim();
  await withButton(button, "검색 중", async () => {
    try { renderCatalog(await api("/api/mcp-catalog/search?q=" + encodeURIComponent(term))); }
    catch (error) { toast(error.message, "bad"); }
  });
}

/* ── verification · risks ─────────────────────────────────── */

function renderVerification() {
  if (!allowed.includes("verification")) return;
  const rows = state.intake.filter(request => request.status !== "HOLD");
  document.querySelector("#validation-total").textContent = rows.length;
  document.querySelector("#validation-list").innerHTML =
    rows.map(request => intakeCard(request, isAdmin())).join("")
    || emptyState("격리 검증을 실행한 요청이 없습니다.", "MCP 도입에서 보류 요청의 '격리 검증 실행'을 누르세요.");
  document.querySelector("#coverage-list").innerHTML = (state.coverage.servers || []).map(item =>
    `<div class="coverage-row"><b>${escapeHtml(item.server_id)}</b><span>${escapeHtml(item.scan_path || "스캔 경로 없음")}</span><small>증적 ${count(item.reports)} · Critical ${count(item.critical_count)}</small></div>`).join("")
    || emptyState("연결된 공급망 증적이 없습니다.");
}

function findingRows(reports) {
  return reports.flatMap(report => {
    const findings = Array.isArray(report.summary?.findings) ? report.summary.findings : [];
    return findings.map(item => {
      const raw = String(item.severity || "INFO").toUpperCase();
      return {
        scanner: report.scanner,
        severity: SEVERITY_ALIAS[raw] || raw,
        title: item.title || item.message || item.id || "세부 정보 없음",
        reference: item.id || item.rule || "-",
        path: item.target || item.path || "",
      };
    });
  });
}

function findingMarkup(items) {
  return items.slice(0, 200).map(item =>
    `<article class="finding-row"><span class="sev ${escapeHtml(item.severity.toLowerCase())}">${escapeHtml(item.severity)}</span><div><b>${escapeHtml(item.title)}</b><p>${escapeHtml(item.scanner)} · ${escapeHtml(item.reference)}</p><small>${escapeHtml(item.path)}</small></div></article>`).join("");
}

function renderRisks() {
  if (!allowed.includes("risks")) return;
  const severity = state.severity;
  const all = findingRows(state.supply_chain);
  cards("#risk-cards", [
    ["Critical", severity.critical, "즉시 조치", severity.critical ? "bad" : "good"],
    ["High", severity.high, "승인 전 검토", severity.high ? "warn" : "good"],
    ["Medium", severity.medium, "개선 계획", ""],
    ["스캔 보고서", state.supply_chain.length, "가져온 증적", ""],
  ]);
  document.querySelector("#finding-filter").innerHTML = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"].map(level => {
    const total = level === "ALL" ? all.length : all.filter(item => item.severity === level).length;
    return `<button class="chip ${severityFilter === level ? "active" : ""}" data-severity="${level}" type="button">${level} ${total}</button>`;
  }).join("");
  const term = findingTerm.toLowerCase();
  const shown = all
    .filter(item => severityFilter === "ALL" || item.severity === severityFilter)
    .filter(item => !term || `${item.title} ${item.path} ${item.reference} ${item.scanner}`.toLowerCase().includes(term));
  document.querySelector("#findings-total").textContent = shown.length;
  document.querySelector("#finding-list").innerHTML = findingMarkup(shown)
    || emptyState("해당 조건의 발견 항목이 없습니다.", "심각도 칩이나 검색어를 바꿔보세요.");
}

/* ── mcp-scan ─────────────────────────────────────────────── */

function scanJobCard(job) {
  const tone = {DONE: "ok", FAILED: "bad", CANCELLED: "muted", RUNNING: "warn", QUEUED: "warn"}[job.status] || "muted";
  const summary = job.summary || {};
  const meta = [ago(job.created_at), JOB_TRIGGER[job.trigger] || job.trigger || "수동 실행",
                `요청 ${escapeHtml(job.requested_by)}`];
  if (job.attempts > 1) meta.push(`시도 ${count(job.attempts)}회`);
  if (job.model) meta.push(`model ${escapeHtml(job.model)}`);
  if (job.base_url) meta.push(escapeHtml(job.base_url));
  if (summary.scan_note) meta.push(`scanNote ${escapeHtml(summary.scan_note)}`);
  if (summary.total !== undefined) meta.push(`발견 ${count(summary.total)}건`);
  if (summary.blocks_calls !== undefined)
    meta.push(summary.blocks_calls ? "차단에 연결됨" : "차단에 연결 안 됨");
  const actions = [];
  if (["QUEUED", "RUNNING"].includes(job.status))
    actions.push(`<button class="mini-button danger" data-scan-cancel="${escapeHtml(job.id)}" type="button">취소</button>`);
  if (["FAILED", "CANCELLED"].includes(job.status))
    actions.push(`<button class="mini-button" data-scan-retry="${escapeHtml(job.id)}" type="button">다시 실행</button>`);
  const stubRun = summary.endpoint_kind === "wire-stub";
  return `<article class="request-row${["QUEUED", "RUNNING"].includes(job.status) ? " working" : ""}">
    <div class="request-top"><div><h3>${escapeHtml(job.display_name || job.target_label || "대상 미상")}</h3>
      <small>${escapeHtml(job.repository_url || job.intake_repository_url || "")}</small></div>
      <span class="tag ${tone}">${escapeHtml(JOB_STATUS[job.status] || job.status)}</span></div>
    <div class="request-meta">${meta.map(item => `<span>${item}</span>`).join("")}</div>
    ${stubRun ? `<p class="note-line bad">배선 확인용 stub으로 실행한 결과입니다. 보안 판단이 아니며 발견 0건이 안전을 뜻하지 않습니다.</p>` : ""}
    ${job.error ? `<p class="note-line bad">${escapeHtml(job.error)}</p>` : ""}
    ${actions.length ? `<div class="button-row">${actions.join("")}</div>` : ""}</article>`;
}

function renderScanWorker() {
  const box = document.querySelector("#mcpscan-worker");
  if (!box) return;
  const worker = scan.worker || {};
  box.classList.toggle("alive", Boolean(worker.alive));
  const parts = [];
  if (worker.alive) {
    parts.push(`<b>격리 워커 정상</b>`, `${escapeHtml(worker.worker || "worker")} · 신호 ${escapeHtml(ago(worker.seen_at))}`);
  } else if (worker.seen_at) {
    parts.push(`<b>격리 워커 응답 없음</b>`,
      `마지막 신호 ${escapeHtml(ago(worker.seen_at))} · ${count(worker.stale_after_seconds)}초 넘게 소식이 없습니다.`);
  } else {
    parts.push(`<b>격리 워커 신호 없음</b>`, "워커가 한 번도 붙지 않았습니다. <code>docker compose up -d intake-worker</code>");
  }
  parts.push(`대기 ${count(worker.queued)} · 실행 중 ${count(worker.running)}${count(worker.stale) ? ` · lease 만료 ${count(worker.stale)}` : ""}`);
  if (!worker.alive && (count(worker.queued) || count(worker.running)))
    parts.push("큐에 들어간 감사는 워커가 뜨기 전까지 실행되지 않습니다.");
  box.innerHTML = `<i></i>${parts.map(item => `<span>${item}</span>`).join("")}`;
}

function renderScan() {
  if (!scan) return;
  const config = scan.config;
  const worker = scan.worker || {};
  const runnable = config.configured && worker.alive;
  const badge = document.querySelector("#mcpscan-state");
  badge.textContent = !config.configured ? "설정 필요" : worker.alive ? "실행 가능" : "워커 없음";
  badge.className = `tag ${runnable ? "ok" : config.configured ? "bad" : "warn"}`;
  renderScanWorker();

  document.querySelector("#mcpscan-config-body").innerHTML = config.configured
    ? `<dl class="result-facts"><div><dt>Endpoint</dt><dd>${escapeHtml(config.base_url)}</dd></div><div><dt>Model</dt><dd>${escapeHtml(config.model)}</dd></div><div><dt>mcp-scan 커밋</dt><dd>${escapeHtml(config.pinned_commit.slice(0, 12))}</dd></div><div><dt>승인 게이트</dt><dd>${config.required_for_approval ? "감사 결과 없이는 승인 불가" : "감사는 승인의 필수 조건이 아님"}</dd></div></dl>
       <p class="note-line">어떤 모델이 판단했는지는 결과와 함께 기록됩니다. 모델을 모르는 보안 결과는 증적이 아닙니다.</p>`
    : `<p>AI 코드 감사는 OpenAI 호환 endpoint를 요구합니다. <code>full_stack_lab/.env</code>에 다음 값을 넣고 <code>./console.sh up</code>을 다시 실행하세요.</p>
       <pre class="code-block">${config.missing.map(key => escapeHtml(key) + "=...").join("\n")}</pre>
       <p class="note-line">로컬 모델(Ollama, LM Studio)이라면 <code>MCP_SCAN_BASE_URL=http://host.docker.internal:11434/v1</code> 형태로 넣습니다. 배선만 확인하려면 <code>docker compose --profile llm-stub up -d llm-stub</code> 후 <code>http://llm-stub:4010/v1</code>을 쓰세요. stub은 취약점을 찾지 않습니다.</p>`;

  document.querySelector("#mcpscan-targets").innerHTML = scan.targets.map(target => {
    const stale = target.last_status === "DONE" && target.last_commit_sha !== target.commit_sha;
    const note = !target.last_status ? "감사한 적 없음"
      : stale ? "지금 commit과 다른 코드에 대한 결과입니다"
      : `마지막 감사 ${JOB_STATUS[target.last_status] || target.last_status} · ${ago(target.last_finished_at)}`;
    return `<article class="request-row"><div class="request-top"><div><h3>${escapeHtml(target.display_name)}</h3>
      <small>${escapeHtml(target.repository_url)} · commit ${escapeHtml(String(target.commit_sha).slice(0, 12))}</small></div>
      <span class="tag ${INTAKE_TONE[target.status] || "muted"}">${escapeHtml(INTAKE_STATUS[target.status] || target.status)}</span></div>
      <div class="request-meta"><span>${escapeHtml(note)}</span></div>
      <div class="button-row"><button class="mini-button" data-scan-run="${escapeHtml(target.id)}" data-scan-kind="intake" type="button" ${runnable ? "" : "disabled"}>AI 코드 감사 실행</button></div></article>`;
  }).join("") || emptyState("감사할 도입 요청이 없습니다.", "격리 검증을 통과해 commit이 고정된 요청만 감사할 수 있습니다.", ["도입 화면으로", "intake"]);

  // 등록된 서버도 대상이다. 이미 호출되고 있는 코드를 빼두면 "심사한 코드"와
  // "지금 도는 코드"가 갈라져도 확인할 방법이 없다.
  document.querySelector("#mcpscan-servers").innerHTML = (scan.servers || []).map(server => {
    const note = !server.scannable ? "원격 전용이라 국소 감사 대상이 아닙니다. 공급자 증적으로 대신합니다."
      : !server.last_status ? "감사한 적 없음"
      : `마지막 감사 ${JOB_STATUS[server.last_status] || server.last_status} · ${ago(server.last_finished_at)}`;
    return `<article class="request-row"><div class="request-top"><div><h3>${escapeHtml(server.display_name)}</h3>
      <small>${escapeHtml(server.source_url)} · ref ${escapeHtml(server.source_ref || "-")}</small></div>
      <span class="tag ${server.status === "READY" ? "ok" : "muted"}">${escapeHtml(SERVER_STATUS[server.status] || server.status)}</span></div>
      <div class="request-meta"><span>${escapeHtml(note)}</span></div>
      ${server.scannable ? `<div class="button-row"><button class="mini-button" data-scan-run="${escapeHtml(server.id)}" data-scan-kind="server" type="button" ${runnable ? "" : "disabled"}>재감사 실행</button></div>` : ""}</article>`;
  }).join("") || emptyState("등록된 서버가 없습니다.");

  document.querySelector("#mcpscan-job-total").textContent = scan.jobs.length;
  document.querySelector("#mcpscan-jobs").innerHTML = scan.jobs.map(scanJobCard).join("")
    || emptyState("실행한 감사가 없습니다.");

  const findings = findingRows(scan.reports);
  document.querySelector("#mcpscan-finding-total").textContent = findings.length;
  document.querySelector("#mcpscan-findings").innerHTML = findingMarkup(findings)
    || emptyState("저장된 감사 결과가 없습니다.", runnable ? "위에서 대상을 골라 실행하세요." : "먼저 endpoint 설정과 워커 상태를 확인하세요.");
}

async function loadScan() {
  if (!allowed.includes("mcpscan")) return;
  scan = await api("/api/mcp-scan");
  renderScan();
  // 워커 이상은 감사 화면에 들어가야만 보이면 늦는다. 메뉴와 첫 화면에도 알린다.
  renderNav();
  if (state && allowed.includes("overview")) renderActionBanner();
}

/* ── accounts ─────────────────────────────────────────────── */

function renderAccounts() {
  if (!allowed.includes("accounts") || !accounts) return;
  document.querySelector("#accounts-total").textContent = accounts.length;
  document.querySelector("#accounts-list").innerHTML = accounts.map(row => {
    const self = row.user_id === state?.viewer?.user_id;
    const actions = self
      ? `<span class="hint">본인 계정</span>`
      : ["active", "disabled", "locked"].filter(value => value !== row.status)
          .map(value => `<button class="mini-button${value === "active" ? "" : " danger"}" data-account="${escapeHtml(row.user_id)}" data-account-status="${value}" type="button">${escapeHtml(ACCOUNT_STATUS[value])}</button>`).join(" ");
    const changed = row.status_changed_at
      ? `${escapeHtml(ago(row.status_changed_at))}<small class="sub">${escapeHtml(row.status_changed_by || "")}</small>`
      : "-";
    return `<tr><td>${escapeHtml(row.email || "-")}</td><td>${escapeHtml(row.display_name)}</td>` +
      `<td>${escapeHtml(row.role)}</td><td>${escapeHtml(row.department || "-")}<small class="sub">${escapeHtml(row.job_title || "")}</small></td>` +
      `<td>${escapeHtml(row.employee_no || "-")}</td>` +
      `<td><span class="tag ${ACCOUNT_TONE[row.status] || "muted"}">${escapeHtml(ACCOUNT_STATUS[row.status] || row.status)}</span></td>` +
      `<td>${changed}</td><td>${actions}</td></tr>`;
  }).join("") || `<tr><td colspan="8">${emptyState("관리대장이 비어 있습니다.")}</td></tr>`;
}

async function loadAccounts() {
  if (!allowed.includes("accounts")) return;
  accounts = (await api("/api/accounts")).accounts;
  renderAccounts();
}

/* ── policy · execution · audit ───────────────────────────── */

function renderPolicyLedger() {
  if (!allowed.includes("policy")) return;
  const ledger = state.ledger || {};
  const policies = ledger.policies || [];
  const exceptions = ledger.exceptions || [];
  const set = ledger.policy_set || {};
  const enforcing = policies.filter(policy => ["운영", "제한"].includes(policy.status)).length;
  const active = exceptions.filter(item => item.status === "적용").length;
  document.querySelector("#ledger-total").textContent = policies.length;
  cards("#ledger-cards", [
    ["정책집", set.version || "-", `${set.id || ""} · ${set.status || "-"}`, ""],
    ["집행 중", enforcing, `중지·폐기 ${policies.length - enforcing}건`, enforcing ? "good" : "warn"],
    ["적용 중 예외", active, `등록 ${exceptions.length}건`, active ? "warn" : "good"],
    ["적용환경", ledger.environment || "-", ledger.deployed_rego?.id || "-", ""],
  ]);
  document.querySelector("#ledger-list").innerHTML = policies.map(policy => {
    const off = !["운영", "제한"].includes(policy.status);
    return `<tr class="${off ? "row-muted" : ""}"><td>${escapeHtml(policy.priority)}</td><td><code>${escapeHtml(policy.policy_id)}</code></td><td>${escapeHtml(policy.name)}</td><td>${escapeHtml(policy.version)}</td><td><span class="tag ${off ? "muted" : "ok"}">${escapeHtml(policy.status)}</span></td><td>${escapeHtml(policy.enforced_by || "-")}</td><td>${escapeHtml(policy.outcome || "-")}</td><td class="wrap">${escapeHtml((policy.risk_ids || []).join(", "))} / ${escapeHtml((policy.control_ids || []).join(", "))}</td><td>${policy.exceptionable ? "가능" : "불가"}</td></tr>`;
  }).join("") || `<tr><td colspan="9">${emptyState("정책 관리대장을 읽지 못했습니다.")}</td></tr>`;
  document.querySelector("#exception-total").textContent = exceptions.length;
  document.querySelector("#exception-list").innerHTML = exceptions.map(item =>
    `<article class="request-row"><div class="request-top"><div><h3>${escapeHtml(item.id)} · ${escapeHtml(item.title)}</h3><small>${escapeHtml(item.policy_id)} → ${escapeHtml(item.effect)}</small></div><span class="tag ${item.status === "적용" ? "warn" : "muted"}">${escapeHtml(item.status)}</span></div>
      <p>${escapeHtml(item.reason)}</p>
      <div class="request-meta"><span>범위 ${escapeHtml(JSON.stringify(item.scope))}</span><span>${formatDate(item.valid_from)} ~ ${formatDate(item.valid_until)}</span><span>승인 ${escapeHtml(item.approved_by)}</span><span>잔여위험 ${escapeHtml(item.residual_risk)}</span></div>
      <ul class="tick-list">${(item.compensating_controls || []).map(control => `<li>${escapeHtml(control)}</li>`).join("")}</ul>
      <p class="note-line">종료계획: ${escapeHtml(item.exit_plan)}</p></article>`).join("") || emptyState("등록된 예외가 없습니다.");
}

function renderExecution() {
  if (!allowed.includes("execution")) return;
  const role = (state.viewer.roles || [])[0] || "partner";
  document.querySelector("#execution-examples").innerHTML = (PROMPTS[role] || PROMPTS.partner)
    .map(([prompt, label]) => `<button class="chip" data-prompt="${escapeHtml(prompt)}" type="button">${escapeHtml(label)}</button>`).join("");
  const panel = document.querySelector("#approvals-panel");
  panel.classList.toggle("hidden", !isAdmin());
  if (!isAdmin()) return;
  const pending = state.approvals || [];
  document.querySelector("#approvals-total").textContent = pending.length;
  document.querySelector("#approvals-list").innerHTML = pending.map(item =>
    `<article class="request-row"><div class="request-top"><div><h3>${escapeHtml(item.request_payload?.tool_name || "tool")}</h3><small>요청자 ${escapeHtml(item.requested_by)} · 만료 ${escapeHtml(ago(item.expires_at))}</small></div><span class="tag warn">대기</span></div>
      <div class="button-row"><button class="mini-button" data-approve="${escapeHtml(item.id)}" type="button">승인</button><button class="mini-button danger" data-reject="${escapeHtml(item.id)}" type="button">거부</button></div>
      <div class="reason-slot" data-reason-for="${escapeHtml(item.id)}"></div></article>`).join("")
    || emptyState("승인 대기 중인 요청이 없습니다.");
}

function auditRow(item) {
  const conflicts = Array.isArray(item.conflicts) ? item.conflicts : [];
  const trail = [`v${item.policy_version || "?"}`];
  if (item.exception_id) trail.push(`예외 ${item.exception_id}`);
  if (item.would_policy_id) trail.push(`관찰: 집행 시 ${item.would_decision}/${item.would_policy_id}`);
  if (conflicts.length) trail.push(`경합 ${conflicts.map(entry => entry.policy_id).join(", ")}`);
  const haystack = `${item.tool_name} ${item.policy_id} ${item.decision} ${item.user_token} ${item.data_class}`.toLowerCase();
  const hidden = auditTerm && !haystack.includes(auditTerm.toLowerCase());
  return `<tr data-decision-id="${escapeHtml(item.id ?? "")}" class="${hidden ? "hidden" : ""}"><td title="${escapeHtml(formatDate(item.created_at))}">${escapeHtml(ago(item.created_at))}</td><td>${escapeHtml(item.user_token || "-")}</td><td>${escapeHtml(item.tool_name || "-")}</td><td>${escapeHtml(item.data_class || "-")} / ${escapeHtml(item.action || "-")}</td><td><span class="decision ${escapeHtml(String(item.decision || "").toLowerCase())}">${escapeHtml(item.decision || "-")}</span></td><td><code>${escapeHtml(item.policy_id || "-")}</code><small class="sub">${escapeHtml(trail.join(" · "))}</small></td><td>${item.upstream_executed ? "실행" : "미실행"}</td><td>${escapeHtml((item.trace_id || "-").slice(0, 12))}</td></tr>`;
}

function sortedDecisions() {
  const {key, dir} = auditSort;
  const sign = dir === "asc" ? 1 : -1;
  return state.decisions.slice().sort((a, b) => {
    const left = a[key] ?? "";
    const right = b[key] ?? "";
    if (key === "created_at") return sign * (new Date(left) - new Date(right));
    if (typeof left === "boolean" || typeof right === "boolean") return sign * ((left ? 1 : 0) - (right ? 1 : 0));
    return sign * String(left).localeCompare(String(right), "ko");
  });
}

function renderAudit() {
  if (!allowed.includes("audit")) return;
  const rows = sortedDecisions();
  document.querySelector("#audit-total").textContent = rows.length;
  const page = rows.slice(0, auditLimit);
  document.querySelector("#audit-list").innerHTML = page.map(auditRow).join("")
    || `<tr><td colspan="8">${emptyState("감사 기록이 없습니다.", "MCP 실행에서 요청을 보내면 여기에 남습니다.", ["MCP 실행으로", "execution"])}</td></tr>`;
  const more = document.querySelector("#audit-more");
  if (more) {
    more.classList.toggle("hidden", rows.length <= auditLimit);
    more.textContent = `더 보기 (${Math.max(0, rows.length - auditLimit)}건 남음)`;
  }
  document.querySelectorAll("#audit-list th.sortable, .view[data-view=audit] th.sortable").forEach(header => {
    header.classList.toggle("asc", header.dataset.sort === auditSort.key && auditSort.dir === "asc");
    header.classList.toggle("desc", header.dataset.sort === auditSort.key && auditSort.dir === "desc");
  });
  document.querySelector("#audit-chain-panel").classList.toggle("hidden", !isAdmin());
}

// 새 판정을 표 맨 위에 끼워 넣는다. 전체를 다시 그리면 스크롤과 검색 상태가 튄다.
function prependAudit(rows) {
  const body = document.querySelector("#audit-list");
  if (!body || !allowed.includes("audit")) return;
  const empty = body.querySelector(".empty-state");
  if (empty) body.innerHTML = "";
  for (const row of rows.slice().reverse()) {
    if (body.querySelector(`[data-decision-id="${row.id}"]`)) continue;
    body.insertAdjacentHTML("afterbegin", auditRow(row));
    body.firstElementChild?.classList.add("fresh");
  }
  while (body.children.length > 60) body.lastElementChild.remove();
  document.querySelector("#audit-total").textContent = body.children.length;
}

/* ── render · load ────────────────────────────────────────── */

function render() {
  document.querySelector("#viewer-name").textContent = state.viewer.name;
  document.querySelector("#viewer-role").textContent = `${state.viewer.department} · ${state.viewer.role_label}`;
  const connection = document.querySelector("#connection-state");
  connection.classList.toggle("ready", state.health.status === "ok");
  connection.querySelector("b").textContent = state.health.status === "ok" ? "연결 정상" : "연결 확인";
  renderOverview(); renderIntake(); renderVerification(); renderRisks();
  renderPolicyLedger(); renderAccounts(); renderExecution(); renderAudit(); renderLive();
}

async function loadConsole() {
  showSkeletons();
  state = await api("/api/console");
  allowed = state.viewer.pages || ["execution"];
  if (allowed.includes("overview")) state.enforcement = await api("/api/enforcement").catch(() => ({}));
  // 워커 상태는 감사 화면 전용이 아니다. 관리자는 첫 화면에서 알아야 한다.
  if (allowed.includes("mcpscan")) scan = await api("/api/mcp-scan").catch(() => scan);
  if (allowed.includes("accounts")) accounts = (await api("/api/accounts").catch(() => ({accounts})))?.accounts ?? accounts;
  document.querySelector("#load-error")?.remove();
  renderNav();
  navigate(currentPage(), true);
  render();
  if (scan) renderScan();
  openStream();
}

function renderResult(body) {
  currentResult = body;
  const outcome = body.gateway_result || {};
  const decision = outcome.decision || (body.status === "no_tool" ? "No Tool" : "Error");
  const titles = {Allow: "실행 완료", Alert: "실행 완료 · 경보", Restrict: "제한 적용 후 실행", Approval: "승인 대기", Block: "실행 차단", "No Tool": "실행 대상 없음", Error: "처리 확인 필요"};
  document.querySelector("#result-title").textContent = titles[decision] || "실행 결과";
  const badge = document.querySelector("#result-decision");
  badge.textContent = decision;
  badge.className = `tag decision ${String(decision).toLowerCase()}`;
  document.querySelector("#result-message").textContent = body.message || outcome.reason || "처리 결과를 확인하세요.";
  const facts = [
    ["정책", outcome.policy_id || body.error_code || "-"],
    ["정책 버전", outcome.policy_version || "-"],
    ["적용 예외", outcome.exception?.id ? `${outcome.exception.id} (~${String(outcome.exception.valid_until || "").slice(0, 10)})` : "없음"],
    ["증적·의무", (outcome.obligations || []).join(", ") || "-"],
    ["경합 정책", (outcome.conflicts || []).map(entry => entry.policy_id).join(", ") || "없음"],
    ["도구", body.tool_call?.tool_name || outcome.tool_name || "-"],
    ["실행", outcome.upstream_executed ? "upstream 실행 확인" : "실행되지 않음"],
    ["Trace", outcome.trace_id || "-"],
  ];
  document.querySelector("#result-facts").innerHTML = facts.map(([key, value]) =>
    `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
  document.querySelector("#approve-button").classList.toggle("hidden", !(decision === "Approval" && isAdmin()));
  // 결과가 화면 밖에 생기면 사용자는 아무 일도 안 일어났다고 생각한다.
  document.querySelector("#result-panel").scrollIntoView({behavior: "smooth", block: "nearest"});
}

async function sendPrompt() {
  const prompt = document.querySelector("#prompt");
  const message = prompt.value.trim();
  if (busy || !message) { if (!message) toast("업무 요청을 입력하세요.", "bad"); return; }
  busy = true;
  const button = document.querySelector("#send-button");
  if (!pendingRequest || pendingRequest.message !== message || pendingRequest.session_id !== sessionId) {
    pendingRequest = {message, request_id: crypto.randomUUID(), session_id: sessionId};
  }
  try {
    const body = await withButton(button, "정책 확인 중", () => api("/chat", {method: "POST", body: pendingRequest}));
    sessionId = body.session_id; sessionStorage.setItem(SESSION_KEY, sessionId); pendingRequest = null;
    renderResult(body); await loadConsole();
  } catch (error) { renderResult({status: "failed", message: error.message}); toast(error.message, "bad"); }
  finally { busy = false; }
}

/* ── inline reason (window.prompt 대신) ───────────────────── */

function askReason(id, label, submit) {
  const slot = document.querySelector(`.reason-slot[data-reason-for="${id}"]`);
  if (!slot) return;
  if (slot.dataset.open === "1") { slot.dataset.open = "0"; slot.innerHTML = ""; return; }
  slot.dataset.open = "1";
  slot.innerHTML = `<div class="reason-row"><input type="text" maxlength="500" placeholder="${escapeHtml(label)}" />
    <button class="mini-button danger" type="button">확인</button></div>`;
  const input = slot.querySelector("input");
  const button = slot.querySelector("button");
  input.focus();
  const send = async () => {
    const note = input.value.trim();
    if (note.length < 2) { input.classList.add("invalid"); input.focus(); return; }
    await act(button, "처리 중", () => submit(note), "처리했습니다.");
  };
  button.addEventListener("click", send);
  input.addEventListener("keydown", event => { if (event.key === "Enter") send(); });
}

/* ── events ───────────────────────────────────────────────── */

document.addEventListener("click", async event => {
  const target = event.target.closest("button");
  if (!target) return;
  const data = target.dataset;
  if (data.page) return navigate(data.page);
  if (data.prompt) { const box = document.querySelector("#prompt"); box.value = data.prompt; box.focus(); return; }
  if (data.severity) { severityFilter = data.severity; renderRisks(); return; }
  if (data.enforcement) return act(target, "전환 중", () => api("/api/enforcement", {method: "PUT", body: {mode: data.enforcement}}), "집행 모드를 바꿨습니다.");
  if (data.queue) return act(target, "시작 중", () => api(`/api/mcp-requests/${data.queue}/queue-validation`, {method: "POST", body: {}}), "격리 검증을 시작했습니다.");
  if (data.approveIntake) return act(target, "승인 중", () => api(`/api/mcp-requests/${data.approveIntake}/approve`, {method: "POST", body: {}}), "승인했습니다.");
  if (data.rejectIntake) return askReason(data.rejectIntake, "거부 사유 (2자 이상)",
    note => api(`/api/mcp-requests/${data.rejectIntake}/reject`, {method: "POST", body: {note}}));
  if (data.approve) return act(target, "승인 중", () => api(`/approvals/${data.approve}/approve`, {method: "POST", body: {}}), "승인 후 재검증했습니다.");
  if (data.reject) return askReason(data.reject, "거부 사유 (2자 이상)",
    note => api(`/approvals/${data.reject}/reject`, {method: "POST", body: {note}}));
  if (data.account) {
    const label = ACCOUNT_STATUS[data.accountStatus] || data.accountStatus;
    return act(target, "바꾸는 중",
      () => api(`/api/accounts/${data.account}/status`, {method: "PUT", body: {status: data.accountStatus}})
              .then(async body => { await loadAccounts(); return body; }),
      `계정을 ${label}으로 바꿨습니다.`);
  }
  if (data.scanCancel) return act(target, "취소 중",
    () => api(`/api/mcp-scan/jobs/${data.scanCancel}/cancel`, {method: "POST", body: {}}), "취소했습니다.");
  if (data.scanRetry) return act(target, "다시 넣는 중",
    () => api(`/api/mcp-scan/jobs/${data.scanRetry}/retry`, {method: "POST", body: {}}), "대기열에 다시 넣었습니다.");
  if (data.scanRun) {
    if (busy) return;
    busy = true;
    try {
      const body = await withButton(target, "큐에 넣는 중", () => api("/api/mcp-scan/run",
        {method: "POST", body: {target_kind: data.scanKind || "intake", target_id: data.scanRun}}));
      toast(body.message, body.worker_alive === false ? "bad" : "ok");
      await loadScan();
      // 작업이 끝나면 화면이 스스로 최신이 되게 몇 번 다시 읽는다.
      let polls = 0;
      const timer = setInterval(async () => {
        polls += 1;
        try { await loadScan(); } catch { /* 화면 새로고침 실패는 조용히 넘긴다 */ }
        const active = (scan?.jobs || []).some(job => ["QUEUED", "RUNNING"].includes(job.status));
        if (!active || polls > 120) clearInterval(timer);
      }, 5000);
    } catch (error) { toast(error.message, "bad"); }
    finally { busy = false; }
    return;
  }
});

document.querySelector("#refresh-console").addEventListener("click", event =>
  act(event.currentTarget, "읽는 중", async () => ({}), "최신 상태를 읽었습니다."));
document.querySelector("#refresh-registry").addEventListener("click", event =>
  act(event.currentTarget, "비교 중", () => api("/api/registry/refresh", {method: "POST", body: {}}), "현재 Catalog를 Registry 계약과 다시 비교했습니다."));
document.querySelector("#import-evidence").addEventListener("click", event =>
  act(event.currentTarget, "반영 중", () => api("/api/supply-chain/import", {method: "POST", body: {}}), "워크스페이스 스캔 증적을 반영했습니다."));
document.querySelector("#catalog-search-button").addEventListener("click", event => searchCatalog(event.currentTarget));
document.querySelector("#catalog-search").addEventListener("keydown", event => {
  if (event.key === "Enter") { event.preventDefault(); searchCatalog(document.querySelector("#catalog-search-button")); }
});
document.querySelector("#finding-search").addEventListener("input", event => { findingTerm = event.target.value; renderRisks(); });
document.querySelector("#audit-search").addEventListener("input", event => {
  auditTerm = event.target.value.trim();
  document.querySelectorAll("#audit-list tr[data-decision-id]").forEach(row => {
    row.classList.toggle("hidden", Boolean(auditTerm) && !row.textContent.toLowerCase().includes(auditTerm.toLowerCase()));
  });
});
document.querySelector("#mcpscan-test").addEventListener("click", async event => {
  try {
    const body = await withButton(event.currentTarget, "확인 중", () => api("/api/mcp-scan/connection-test", {method: "POST", body: {}}));
    toast(body.message, body.ok ? "ok" : "bad");
  } catch (error) { toast(error.message, "bad"); }
});
document.querySelector("#verify-chain").addEventListener("click", async event => {
  const box = document.querySelector("#chain-result");
  try {
    const body = await withButton(event.currentTarget, "검증 중", () => api("/api/audit/verify"));
    box.textContent = body.intact
      ? `무결 · 연결된 항목 ${body.checked}건 · head ${String(body.head).slice(0, 16)}`
      : `끊김 · ${body.broken_at ?? "-"}행 · ${body.reason}`;
    box.className = `chain-result ${body.intact ? "ok" : "bad"}`;
  } catch (error) { box.textContent = error.message; box.className = "chain-result bad"; }
});

const intakeForm = document.querySelector("#intake-form");
const purposeBox = intakeForm.querySelector("[name=purpose]");
purposeBox.addEventListener("input", () => {
  document.querySelector("#purpose-count").textContent = purposeBox.value.length;
});
// 서버가 422로 되돌려주기 전에 그 자리에서 알려준다.
function validateIntake(form) {
  const problems = {};
  const name = form.display_name.value.trim();
  const url = form.repository_url.value.trim();
  const purpose = form.purpose.value.trim();
  if (name.length < 2) problems.display_name = "2자 이상 입력하세요.";
  if (!/^https:\/\/github\.com\/[^/\s]+\/[^/\s]+$/.test(url.replace(/\.git$/, "")))
    problems.repository_url = "https://github.com/조직/저장소 형식만 제출할 수 있습니다.";
  if (purpose.length < 10) problems.purpose = `${10 - purpose.length}자 더 필요합니다.`;
  document.querySelectorAll("[data-error]").forEach(node => { node.textContent = problems[node.dataset.error] || ""; });
  return Object.keys(problems).length === 0;
}
intakeForm.addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!validateIntake(form)) { toast("입력을 확인하세요.", "bad"); return; }
  const button = form.querySelector("button[type=submit]");
  try {
    const body = await withButton(button, "제출 중", () =>
      api("/api/mcp-requests", {method: "POST", body: Object.fromEntries(new FormData(form))}));
    form.reset();
    document.querySelector("#purpose-count").textContent = "0";
    toast(body.message);
    await loadConsole();
  } catch (error) { toast(error.message, "bad"); }
});

document.querySelector("#send-button").addEventListener("click", sendPrompt);
document.querySelector("#prompt").addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); sendPrompt(); }
});
document.querySelector("#new-session").addEventListener("click", () => {
  sessionId = null; pendingRequest = null; sessionStorage.removeItem(SESSION_KEY);
  toast("새 실행 세션을 시작합니다.");
});
document.querySelector("#approve-button").addEventListener("click", async event => {
  const id = currentResult?.gateway_result?.approval_id;
  if (!id || busy) return;
  busy = true;
  try {
    renderResult({gateway_result: await withButton(event.currentTarget, "승인 중", () => api(`/approvals/${id}/approve`, {method: "POST", body: {}}))});
    await loadConsole();
  } catch (error) { toast(error.message, "bad"); }
  finally { busy = false; }
});
document.querySelector("#theme-toggle").addEventListener("click", cycleTheme);
document.querySelector("#audit-more").addEventListener("click", () => { auditLimit += AUDIT_PAGE; renderAudit(); });
document.querySelectorAll('.view[data-view="audit"] th.sortable').forEach(header => {
  header.addEventListener("click", () => {
    const key = header.dataset.sort;
    auditSort = auditSort.key === key
      ? {key, dir: auditSort.dir === "asc" ? "desc" : "asc"}
      : {key, dir: key === "created_at" ? "desc" : "asc"};
    auditLimit = AUDIT_PAGE;
    renderAudit();
  });
});
document.querySelector("#logout-button").addEventListener("click", async () => {
  try { await api("/auth/logout", {method: "POST", body: {}}); } finally { redirectToLogin(); }
});
window.addEventListener("hashchange", () => navigate(currentPage(), true));
// 상대 시간이 멈춰 있으면 실시간처럼 보이지 않는다.
setInterval(() => { if (liveRows.length) renderLive(); }, 20000);

async function init() {
  initTheme();
  if (!token) return redirectToLogin();
  await loadConsole();
}
init().catch(error => {
  // 첫 로딩 실패를 토스트로만 알리면 4초 뒤 빈 화면만 남는다.
  toast(error.message, "bad");
  showLoadError(error.message);
});
