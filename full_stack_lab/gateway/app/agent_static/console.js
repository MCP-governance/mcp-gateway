const TOKEN_KEY = "bob_mock_sso_token";
const SESSION_KEY = "bob_agent_session";
const token = sessionStorage.getItem(TOKEN_KEY);

const NAV = [
  {page: "overview", group: "GOVERNANCE", label: "운영 현황"},
  {page: "intake", group: "GOVERNANCE", label: "MCP 도입"},
  {page: "verification", group: "GOVERNANCE", label: "검증 파이프라인"},
  {page: "risks", group: "GOVERNANCE", label: "위험 분석"},
  {page: "policy", group: "GOVERNANCE", label: "정책 관리대장"},
  {page: "execution", group: "OPERATIONS", label: "MCP 실행"},
  {page: "audit", group: "OPERATIONS", label: "감사 기록"},
];
// 화면마다 다른 빠른 요청. 협력업체 직원에게 중요문서 버튼을 보여줄 이유가 없다.
const PROMPTS = {
  partner: [["공개 문서를 읽어줘", "공개 문서 읽기"], ["감사 대응 사본을 읽어줘", "예외 적용 열람"], ["현재 시간을 알려줘", "시간 조회"]],
  employee: [["공개 문서를 읽어줘", "공개 문서 읽기"], ["중요 계약 초안을 읽어줘", "중요 문서 열람"], ["내부 업무 메모를 수정해줘", "내부 메모 수정"], ["현재 시간을 알려줘", "시간 조회"]],
  admin: [["공개 문서를 읽어줘", "공개 문서 읽기"], ["중요 계약 초안을 읽어줘", "중요 문서 열람"], ["공개 공지를 외부에 전송해줘", "외부 전송"], ["중요 계약을 외부에 전송해줘", "중요 외부 전송"], ["현재 시간을 알려줘", "시간 조회"]],
};
const INTAKE_STATUS = {
  HOLD: "보류", VALIDATION_QUEUED: "검증 대기", VALIDATING: "검증 중",
  VALIDATED: "검증 통과", APPROVED: "승인", REJECTED: "거부", FAILED: "검증 실패",
};
const SERVER_STATUS = {READY: "운영", DISABLED: "비활성", BLOCKED_SUPPLY_CHAIN: "공급망 차단", ERROR: "오류"};

let state = null;
let allowed = [];
let sessionId = sessionStorage.getItem(SESSION_KEY);
let pendingRequest = null;
let currentResult = null;
let busy = false;
let severityFilter = "ALL";

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}
function count(value) { return Number(value || 0); }
function currentPage() {
  const page = location.hash.replace("#/", "");
  return allowed.includes(page) ? page : allowed[0] || "execution";
}
function redirectToLogin() { sessionStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(SESSION_KEY); window.location.replace("/login"); }
function showNotice(message, error = false) {
  const box = document.querySelector("#notice");
  box.textContent = message; box.classList.toggle("error", error); box.classList.remove("hidden");
}
function clearNotice() { document.querySelector("#notice").classList.add("hidden"); }
function formatDate(value) { return value ? new Intl.DateTimeFormat("ko-KR", {dateStyle:"short", timeStyle:"short"}).format(new Date(value)) : "-"; }
function isAdmin() { return (state?.viewer?.roles || []).includes("admin"); }

// FastAPI의 422는 detail이 객체 배열이다. String()으로 밀면 [object Object]가
// 나와서 "무엇이 틀렸는지"가 사라진다. 입력 검증 실패는 사용자가 고칠 수 있는
// 유일한 오류이므로 가장 정확하게 보여야 한다.
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
    headers: {Authorization: `Bearer ${token}`, ...(options.body ? {"Content-Type":"application/json"} : {})},
    ...(options.body ? {body: JSON.stringify(options.body)} : {}),
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) { redirectToLogin(); throw new Error("다시 로그인하세요."); }
  if (!response.ok) throw new Error(errorMessage(data, response.status));
  return data;
}

function renderNav() {
  const visible = NAV.filter(item => allowed.includes(item.page));
  let group = null;
  document.querySelector("#side-nav-list").innerHTML = visible.map(item => {
    const heading = item.group !== group ? `<p class="nav-group">${item.group}</p>` : "";
    group = item.group;
    return `${heading}<button data-page="${item.page}" type="button">${escapeHtml(item.label)}</button>`;
  }).join("");
}

function navigate(page, replace = false) {
  if (!allowed.includes(page)) page = allowed[0] || "execution";
  document.querySelectorAll("[data-view]").forEach(view => view.classList.toggle("hidden", view.dataset.view !== page));
  document.querySelectorAll(".side-nav [data-page]").forEach(button => button.classList.toggle("active", button.dataset.page === page));
  if (location.hash !== `#/${page}`) {
    if (replace) history.replaceState(null, "", `#/${page}`); else location.hash = `/${page}`;
  }
}

function cards(target, rows) {
  document.querySelector(target).innerHTML = rows.map(([label, value, note, tone]) =>
    `<article class="metric-card ${tone || ""}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>`).join("");
}

function renderOverview() {
  if (!allowed.includes("overview")) return;
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
  }).join("") || '<p class="empty-state">등록된 MCP가 없습니다.</p>';

  const buckets = ["Allow", "Alert", "Approval", "Restrict", "Block"].map(label => ({label, value: state.decisions.filter(item => item.decision === label).length}));
  const max = Math.max(1, ...buckets.map(item => item.value));
  document.querySelector("#decision-total").textContent = state.decisions.length;
  document.querySelector("#decision-chart").innerHTML = buckets.map(item =>
    `<div class="bar-item"><strong>${item.value}</strong><i class="bar ${item.label.toLowerCase()}" style="height:${Math.max(2, Math.round(item.value / max * 120))}px"></i><span>${item.label}</span></div>`).join("");

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

function intakeCard(request, withActions) {
  const status = request.status;
  const evidence = request.evidence || {};
  const tone = {VALIDATED: "ok", APPROVED: "ok", REJECTED: "bad", FAILED: "bad", VALIDATING: "warn"}[status] || "muted";
  const meta = [
    escapeHtml(request.requested_transport),
    `위험도 ${escapeHtml(request.risk_level)}`,
    formatDate(request.created_at),
  ];
  if (request.commit_sha) meta.push(`commit ${escapeHtml(String(request.commit_sha).slice(0, 12))}`);
  if (evidence.sbom_components !== undefined) {
    meta.push(`구성요소 ${count(evidence.sbom_components)}`);
    meta.push(`C ${count(evidence.critical)} · H ${count(evidence.high)} · M ${count(evidence.medium)}`);
  }
  const actions = [];
  if (withActions && status === "HOLD") actions.push(`<button class="mini-button" data-queue="${escapeHtml(request.id)}" type="button">격리 검증 실행</button>`);
  if (withActions && status === "VALIDATED") actions.push(`<button class="mini-button" data-approve-intake="${escapeHtml(request.id)}" type="button">승인</button>`);
  if (withActions && ["HOLD", "VALIDATION_QUEUED", "VALIDATED"].includes(status)) actions.push(`<button class="mini-button danger" data-reject-intake="${escapeHtml(request.id)}" type="button">거부</button>`);
  return `<article class="request-row">
    <div class="request-top"><div><h3>${escapeHtml(request.display_name)}</h3><a href="${escapeHtml(request.repository_url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(request.repository_url)}</a></div><span class="tag ${tone}">${escapeHtml(INTAKE_STATUS[status] || status)}</span></div>
    <p>${escapeHtml(request.purpose)}</p>
    <div class="request-meta">${meta.map(item => `<span>${item}</span>`).join("")}</div>
    ${request.review_note ? `<p class="note-line">${escapeHtml(request.review_note)}</p>` : ""}
    ${actions.length ? `<div class="button-row">${actions.join("")}</div>` : ""}
  </article>`;
}

function renderIntake() {
  if (!allowed.includes("intake")) return;
  document.querySelector("#intake-total").textContent = state.intake.length;
  document.querySelector("#intake-list").innerHTML =
    state.intake.map(request => intakeCard(request, isAdmin())).join("") || '<p class="empty-state">요청이 없습니다.</p>';
}

function renderVerification() {
  if (!allowed.includes("verification")) return;
  const validated = state.intake.filter(request => request.status !== "HOLD");
  document.querySelector("#validation-total").textContent = validated.length;
  document.querySelector("#validation-list").innerHTML =
    validated.map(request => intakeCard(request, isAdmin())).join("") || '<p class="empty-state">격리 검증을 실행한 요청이 없습니다.</p>';
  document.querySelector("#coverage-list").innerHTML = (state.coverage.servers || []).map(item =>
    `<div class="coverage-row"><b>${escapeHtml(item.server_id)}</b><span>${escapeHtml(item.scan_path || "스캔 경로 없음")}</span><small>증적 ${count(item.reports)} · Critical ${count(item.critical_count)}</small></div>`).join("")
    || '<p class="empty-state">연결된 공급망 증적이 없습니다.</p>';
}

// 스캐너마다 심각도 어휘가 다르다. 한 화면에서 거르려면 한 축으로 모아야 한다.
const SEVERITY_ALIAS = {ERROR: "HIGH", WARNING: "MEDIUM", INFO: "LOW", UNKNOWN: "LOW"};

function findingRows() {
  return state.supply_chain.flatMap(report => {
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

function renderRisks() {
  if (!allowed.includes("risks")) return;
  const severity = state.severity;
  const all = findingRows();
  cards("#risk-cards", [
    ["Critical", severity.critical, "즉시 조치", severity.critical ? "bad" : "good"],
    ["High", severity.high, "승인 전 검토", severity.high ? "warn" : "good"],
    ["Medium", severity.medium, "개선 계획", ""],
    ["스캔 보고서", state.supply_chain.length, "가져온 증적", ""],
  ]);
  const counts = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"];
  document.querySelector("#finding-filter").innerHTML = counts.map(level => {
    const total = level === "ALL" ? all.length : all.filter(item => item.severity === level).length;
    return `<button class="chip ${severityFilter === level ? "active" : ""}" data-severity="${level}" type="button">${level} ${total}</button>`;
  }).join("");
  const shown = severityFilter === "ALL" ? all : all.filter(item => item.severity === severityFilter);
  document.querySelector("#findings-total").textContent = shown.length;
  document.querySelector("#finding-list").innerHTML = shown.slice(0, 200).map(item =>
    `<article class="finding-row"><span class="sev ${escapeHtml(item.severity.toLowerCase())}">${escapeHtml(item.severity)}</span><div><b>${escapeHtml(item.title)}</b><p>${escapeHtml(item.scanner)} · ${escapeHtml(item.reference)}</p><small>${escapeHtml(item.path)}</small></div></article>`).join("")
    || '<p class="empty-state">해당 심각도의 발견 항목이 없습니다.</p>';
}

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
  }).join("") || '<tr><td colspan="9" class="empty-state">정책 관리대장을 읽지 못했습니다.</td></tr>';
  document.querySelector("#exception-total").textContent = exceptions.length;
  document.querySelector("#exception-list").innerHTML = exceptions.map(item =>
    `<article class="request-row"><div class="request-top"><div><h3>${escapeHtml(item.id)} · ${escapeHtml(item.title)}</h3><small>${escapeHtml(item.policy_id)} → ${escapeHtml(item.effect)}</small></div><span class="tag ${item.status === "적용" ? "warn" : "muted"}">${escapeHtml(item.status)}</span></div>
      <p>${escapeHtml(item.reason)}</p>
      <div class="request-meta"><span>범위 ${escapeHtml(JSON.stringify(item.scope))}</span><span>${formatDate(item.valid_from)} ~ ${formatDate(item.valid_until)}</span><span>승인 ${escapeHtml(item.approved_by)}</span><span>잔여위험 ${escapeHtml(item.residual_risk)}</span></div>
      <ul class="tick-list">${(item.compensating_controls || []).map(control => `<li>${escapeHtml(control)}</li>`).join("")}</ul>
      <p class="note-line">종료계획: ${escapeHtml(item.exit_plan)}</p></article>`).join("") || '<p class="empty-state">등록된 예외가 없습니다.</p>';
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
    `<article class="request-row"><div class="request-top"><div><h3>${escapeHtml(item.request_payload?.tool_name || "tool")}</h3><small>요청자 ${escapeHtml(item.requested_by)} · 만료 ${formatDate(item.expires_at)}</small></div><span class="tag warn">대기</span></div>
      <div class="button-row"><button class="mini-button" data-approve="${escapeHtml(item.id)}" type="button">승인</button><button class="mini-button danger" data-reject="${escapeHtml(item.id)}" type="button">거부</button></div></article>`).join("")
    || '<p class="empty-state">승인 대기 중인 요청이 없습니다.</p>';
}

function renderAudit() {
  if (!allowed.includes("audit")) return;
  document.querySelector("#audit-total").textContent = state.decisions.length;
  document.querySelector("#audit-list").innerHTML = state.decisions.map(item => {
    const conflicts = Array.isArray(item.conflicts) ? item.conflicts : [];
    const trail = [`v${item.policy_version || "?"}`];
    if (item.exception_id) trail.push(`예외 ${item.exception_id}`);
    if (item.would_policy_id) trail.push(`관찰: 집행 시 ${item.would_decision}/${item.would_policy_id}`);
    if (conflicts.length) trail.push(`경합 ${conflicts.map(entry => entry.policy_id).join(", ")}`);
    return `<tr><td>${formatDate(item.created_at)}</td><td>${escapeHtml(item.user_token || "-")}</td><td>${escapeHtml(item.tool_name || "-")}</td><td>${escapeHtml(item.data_class || "-")} / ${escapeHtml(item.action || "-")}</td><td><span class="decision ${escapeHtml(String(item.decision || "").toLowerCase())}">${escapeHtml(item.decision || "-")}</span></td><td><code>${escapeHtml(item.policy_id || "-")}</code><small class="sub">${escapeHtml(trail.join(" · "))}</small></td><td>${item.upstream_executed ? "실행" : "미실행"}</td><td>${escapeHtml((item.trace_id || "-").slice(0, 12))}</td></tr>`;
  }).join("") || '<tr><td colspan="8" class="empty-state">감사 기록이 없습니다.</td></tr>';
  document.querySelector("#audit-chain-panel").classList.toggle("hidden", !isAdmin());
}

function render() {
  document.querySelector("#viewer-name").textContent = state.viewer.name;
  document.querySelector("#viewer-role").textContent = `${state.viewer.department} · ${state.viewer.role_label}`;
  const connection = document.querySelector("#connection-state");
  connection.classList.toggle("ready", state.health.status === "ok");
  connection.querySelector("b").textContent = state.health.status === "ok" ? "연결 정상" : "연결 확인";
  renderOverview(); renderIntake(); renderVerification(); renderRisks();
  renderPolicyLedger(); renderExecution(); renderAudit();
}

async function loadConsole() {
  state = await api("/api/console");
  allowed = state.viewer.pages || ["execution"];
  if (allowed.includes("overview")) {
    state.enforcement = await api("/api/enforcement").catch(() => ({}));
  }
  renderNav();
  navigate(currentPage(), true);
  render();
}

function renderResult(body) {
  currentResult = body;
  const outcome = body.gateway_result || {};
  const decision = outcome.decision || (body.status === "no_tool" ? "No Tool" : "Error");
  const titles = {Allow:"실행 완료", Alert:"실행 완료 · 경보", Restrict:"제한 적용 후 실행", Approval:"승인 대기", Block:"실행 차단", "No Tool":"실행 대상 없음", Error:"처리 확인 필요"};
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
}

async function sendPrompt() {
  const prompt = document.querySelector("#prompt");
  const message = prompt.value.trim();
  if (busy || !message) return;
  busy = true;
  const button = document.querySelector("#send-button");
  button.disabled = true; button.textContent = "정책 확인 중";
  if (!pendingRequest || pendingRequest.message !== message || pendingRequest.session_id !== sessionId) {
    pendingRequest = {message, request_id: crypto.randomUUID(), session_id: sessionId};
  }
  try {
    const body = await api("/chat", {method:"POST", body:pendingRequest});
    sessionId = body.session_id; sessionStorage.setItem(SESSION_KEY, sessionId); pendingRequest = null;
    renderResult(body); await loadConsole();
  } catch (error) { renderResult({status:"failed", message:error.message}); }
  finally { busy = false; button.disabled = false; button.textContent = "정책 검증 후 실행"; }
}

async function act(run, successMessage) {
  if (busy) return;
  busy = true;
  try { const body = await run(); showNotice(body?.message || successMessage); await loadConsole(); }
  catch (error) { showNotice(error.message, true); }
  finally { busy = false; }
}

document.addEventListener("click", async event => {
  const target = event.target.closest("button");
  if (!target) return;
  const data = target.dataset;
  if (data.page) return navigate(data.page);
  if (data.prompt) { const box = document.querySelector("#prompt"); box.value = data.prompt; box.focus(); return; }
  if (data.severity) { severityFilter = data.severity; renderRisks(); return; }
  if (data.enforcement) return act(() => api("/api/enforcement", {method:"PUT", body:{mode:data.enforcement}}), "집행 모드를 바꿨습니다.");
  if (data.queue) return act(() => api(`/api/mcp-requests/${data.queue}/queue-validation`, {method:"POST", body:{}}), "격리 검증을 시작했습니다.");
  if (data.approveIntake) return act(() => api(`/api/mcp-requests/${data.approveIntake}/approve`, {method:"POST", body:{}}), "승인했습니다.");
  if (data.rejectIntake) {
    const note = window.prompt("거부 사유를 입력하세요.");
    if (!note || note.trim().length < 2) return showNotice("거부에는 사유가 필요합니다.", true);
    return act(() => api(`/api/mcp-requests/${data.rejectIntake}/reject`, {method:"POST", body:{note:note.trim()}}), "거부했습니다.");
  }
  if (data.approve) return act(() => api(`/approvals/${data.approve}/approve`, {method:"POST", body:{}}), "승인 후 재검증했습니다.");
  if (data.reject) {
    const note = window.prompt("거부 사유를 입력하세요.");
    if (!note || !note.trim()) return showNotice("거부에는 사유가 필요합니다.", true);
    return act(() => api(`/approvals/${data.reject}/reject`, {method:"POST", body:{note:note.trim()}}), "거부했습니다.");
  }
});

document.querySelector("#refresh-console").addEventListener("click", () => { clearNotice(); loadConsole().catch(error => showNotice(error.message, true)); });
document.querySelector("#refresh-registry").addEventListener("click", () => act(() => api("/api/registry/refresh", {method:"POST", body:{}}), "현재 Catalog를 Registry 계약과 다시 비교했습니다."));
document.querySelector("#import-evidence").addEventListener("click", () => act(() => api("/api/supply-chain/import", {method:"POST", body:{}}), "워크스페이스 스캔 증적을 반영했습니다."));
document.querySelector("#verify-chain").addEventListener("click", async () => {
  const box = document.querySelector("#chain-result");
  try {
    const body = await api("/api/audit/verify");
    box.textContent = body.intact
      ? `무결 · 연결된 항목 ${body.checked}건 · head ${String(body.head).slice(0, 16)}`
      : `끊김 · ${body.broken_at ?? "-"}행 · ${body.reason}`;
    box.className = `chain-result ${body.intact ? "ok" : "bad"}`;
  } catch (error) { box.textContent = error.message; box.className = "chain-result bad"; }
});
document.querySelector("#intake-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    const body = await api("/api/mcp-requests", {method:"POST", body:Object.fromEntries(form)});
    event.currentTarget.reset(); showNotice(body.message); await loadConsole();
  } catch (error) { showNotice(error.message, true); }
});
document.querySelector("#send-button").addEventListener("click", sendPrompt);
document.querySelector("#prompt").addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); sendPrompt(); }
});
document.querySelector("#new-session").addEventListener("click", () => {
  sessionId = null; pendingRequest = null; sessionStorage.removeItem(SESSION_KEY);
  showNotice("새 실행 세션을 시작합니다.");
});
document.querySelector("#approve-button").addEventListener("click", async () => {
  const id = currentResult?.gateway_result?.approval_id;
  if (!id || busy) return;
  busy = true;
  try { renderResult({gateway_result: await api(`/approvals/${id}/approve`, {method:"POST", body:{}})}); await loadConsole(); }
  catch (error) { showNotice(error.message, true); }
  finally { busy = false; }
});
document.querySelector("#logout-button").addEventListener("click", async () => {
  try { await api("/auth/logout", {method:"POST", body:{}}); } finally { redirectToLogin(); }
});
window.addEventListener("hashchange", () => navigate(currentPage(), true));

async function init() {
  if (!token) return redirectToLogin();
  await loadConsole();
}
init().catch(error => showNotice(error.message, true));
