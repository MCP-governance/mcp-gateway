const TOKEN_KEY = "bob_mock_sso_token";
const SESSION_KEY = "bob_agent_session";
const token = sessionStorage.getItem(TOKEN_KEY);
const pages = new Set(["overview", "intake", "verification", "risks", "policy", "execution", "audit"]);
let state = null;
let sessionId = sessionStorage.getItem(SESSION_KEY);
let pendingRequest = null;
let currentResult = null;
let busy = false;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}
function count(value) { return Number(value || 0); }
function currentPage() { return pages.has(location.hash.replace("#/", "")) ? location.hash.replace("#/", "") : "overview"; }
function redirectToLogin() { sessionStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(SESSION_KEY); window.location.replace("/login"); }
function showNotice(message, error = false) { const box = document.querySelector("#notice"); box.textContent = message; box.classList.toggle("error", error); box.classList.remove("hidden"); }
function clearNotice() { document.querySelector("#notice").classList.add("hidden"); }
function statusClass(status) { return ({READY:"", HOLD:"hold", VALIDATION_QUEUED:"queue", REJECTED:"rejected", DISABLED:"disabled"}[status] || "hold"); }
function displayStatus(status) { return ({READY:"운영", HOLD:"보류", VALIDATION_QUEUED:"검증 대기", REJECTED:"거부", DISABLED:"비활성"}[status] || status || "확인 중"); }
function formatDate(value) { return value ? new Intl.DateTimeFormat("ko-KR", {dateStyle:"short", timeStyle:"short"}).format(new Date(value)) : "-"; }

async function api(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || "GET",
    headers: {Authorization: `Bearer ${token}`, ...(options.body ? {"Content-Type":"application/json"} : {})},
    ...(options.body ? {body: JSON.stringify(options.body)} : {}),
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) { redirectToLogin(); throw new Error("다시 로그인하세요."); }
  if (!response.ok) throw new Error(data.detail || "요청을 처리하지 못했습니다.");
  return data;
}

function navigate(page, replace = false) {
  if (!pages.has(page)) page = "overview";
  document.querySelectorAll("[data-view]").forEach(view => view.classList.toggle("hidden", view.dataset.view !== page));
  document.querySelectorAll(".side-nav [data-page]").forEach(button => button.classList.toggle("active", button.dataset.page === page));
  if (location.hash !== `#/${page}`) {
    if (replace) history.replaceState(null, "", `#/${page}`); else location.hash = `/${page}`;
  }
}

function renderOverview() {
  const components = state.health.components || {};
  const active = state.registry.filter(server => server.status === "READY").length;
  const awaiting = state.intake.filter(request => request.status !== "REJECTED").length;
  const severity = state.severity;
  document.querySelector("#overview-cards").innerHTML = [
    ["운영 MCP", active, `${state.registry.length}개 Registry 항목`, active ? "good" : ""],
    ["도입 검토", awaiting, "보류 및 검증 대기 요청", awaiting ? "warning" : ""],
    ["공급망 고위험", severity.critical + severity.high, `Critical ${severity.critical} · High ${severity.high}`, severity.critical + severity.high ? "critical" : "good"],
    ["실행 증적", state.upstream_effect_count, "독립 upstream 효과 기록", "good"],
  ].map(([label, value, note, tone]) => `<article class="metric-card ${tone}"><span>${label}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>`).join("");
  document.querySelector("#registry-summary").innerHTML = state.registry.map(server => {
    const status = server.status || "HOLD";
    return `<div class="server-row"><span class="server-icon ${statusClass(status)}">${escapeHtml((server.id || "M").slice(0, 2).toUpperCase())}</span><div><b>${escapeHtml(server.display_name || server.name || server.id)}</b><small>${escapeHtml(server.transport || server.source_ref || "등록 정보 확인 중")}</small></div><span class="status-pill ${statusClass(status)}">${displayStatus(status)}</span></div>`;
  }).join("") || '<p class="empty-state">등록된 MCP가 없습니다.</p>';
  const decisions = ["Allow", "Alert", "Approval", "Restrict", "Block"].map(label => ({label, value: state.decisions.filter(item => item.decision === label).length}));
  const max = Math.max(1, ...decisions.map(item => item.value));
  document.querySelector("#decision-total").textContent = `${state.decisions.length}건`;
  document.querySelector("#decision-chart").innerHTML = decisions.map(item => `<div class="bar-item"><strong>${item.value}</strong><i class="bar ${item.label.toLowerCase()}" style="height:${Math.max(3, Math.round(item.value / max * 110))}px"></i><span>${item.label}</span></div>`).join("");
  const model = state.model;
  document.querySelector("#model-summary").textContent = model.mode === "mock"
    ? "현재는 규칙 기반 변환을 사용합니다. LiteLLM 연결 시에도 Agent는 OpenAI 호환 단일 경계만 사용합니다."
    : "LiteLLM 호환 모델 경계가 도구 호출 후보를 만들고 있습니다. 실행 권한은 Gateway에만 있습니다.";
  const guard = state.supply_chain.find(report => report.scanner === "AI-Infra-Guard mcp-scan");
  document.querySelector("#guard-summary").textContent = guard
    ? `mcp-scan 결과 ${count(guard.summary?.total || guard.summary?.findings?.length)}건을 공급망 증적으로 연결했습니다.`
    : "mcp-scan은 첫 실행 위험 분석 단계에 연결돼 있습니다. 현재 결과는 아직 반영되지 않았습니다.";
  const set = state.ledger?.policy_set || {};
  const enforcing = (state.ledger?.policies || []).filter(policy => policy.status === "운영" || policy.status === "제한").length;
  document.querySelector("#policy-summary").textContent =
    `정책집 ${set.version || state.policy?.id || "확인 중"} · 집행 ${enforcing}건 · ${components.opa ? "정상" : "확인 필요"} · 기본 DENY`;
}

function renderIntake() {
  const isAdmin = state.viewer.roles.includes("admin");
  document.querySelector("#intake-total").textContent = `${state.intake.length}건`;
  document.querySelector("#intake-list").innerHTML = state.intake.map(request => `<article class="request-row"><div class="request-top"><div><h3>${escapeHtml(request.display_name)}</h3><a href="${escapeHtml(request.repository_url)}" target="_blank" rel="noreferrer">${escapeHtml(request.repository_url)}</a></div><span class="status-pill ${statusClass(request.status)}">${displayStatus(request.status)}</span></div><p>${escapeHtml(request.purpose)}</p><div class="request-meta"><span>${escapeHtml(request.requested_transport)}</span><span>위험도 ${escapeHtml(request.risk_level)}</span><span>${formatDate(request.created_at)}</span></div>${isAdmin && request.status === "HOLD" ? `<button class="small-action" data-queue="${escapeHtml(request.id)}" type="button">검증 대기열로 이동</button>` : ""}${request.review_note ? `<p class="form-note">검토 메모: ${escapeHtml(request.review_note)}</p>` : ""}</article>`).join("") || '<p class="empty-state">보류 또는 검증 대기 요청이 없습니다.</p>';
}

function renderVerification() {
  document.querySelector("#coverage-list").innerHTML = (state.coverage.servers || []).map(item => `<div class="coverage-row"><b>${escapeHtml(item.server_id)}</b><span>${escapeHtml(item.scan_path || "스캔 경로 미설정")}</span><small>${count(item.reports)}개 증적 · C ${count(item.critical_count)}</small></div>`).join("") || '<p class="empty-state">연결된 공급망 증적이 없습니다.</p>';
}

function findingRows() {
  return state.supply_chain.flatMap(report => {
    const summary = report.summary || {};
    const findings = Array.isArray(summary.findings) ? summary.findings : [];
    return findings.map(item => ({scanner: report.scanner, severity: item.severity || "INFO", title: item.title || item.message || item.id || item.rule || "세부 정보 없음", reference: item.id || item.rule || item.path || "-", path: item.target || item.path || ""}));
  });
}

function renderRisks() {
  const severity = state.severity;
  const guard = state.supply_chain.find(report => report.scanner === "AI-Infra-Guard mcp-scan");
  const findings = findingRows();
  document.querySelector("#risk-cards").innerHTML = [
    ["Critical", severity.critical, "즉시 차단 또는 조치 필요", severity.critical ? "critical" : "good"],
    ["High", severity.high, "승인 전 우선 검토", severity.high ? "warning" : "good"],
    ["Medium", severity.medium, "개선 계획 추적", ""],
    ["MCP 위험 분석", guard ? count(guard.summary?.total || guard.summary?.findings?.length) : "대기", guard ? "AI-Infra-Guard mcp-scan" : "첫 실행 분석 결과 미반영", ""],
  ].map(([label, value, note, tone]) => `<article class="metric-card ${tone}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>`).join("");
  document.querySelector("#findings-total").textContent = `${findings.length}건`;
  document.querySelector("#finding-list").innerHTML = findings.map(item => `<article class="finding-row"><span class="finding-severity ${escapeHtml(String(item.severity).toLowerCase())}">${escapeHtml(item.severity)}</span><div><b>${escapeHtml(item.title)}</b><p>${escapeHtml(item.scanner)} · ${escapeHtml(item.reference)}</p><small>${escapeHtml(item.path)}</small></div></article>`).join("") || '<p class="empty-state">반영된 고·중요도 발견 항목이 없습니다.</p>';
  document.querySelector("#guard-detail").innerHTML = guard
    ? `<div class="guard-state"><strong>분석 결과 반영됨</strong><p>AI-Infra-Guard mcp-scan SARIF가 공급망 증적으로 저장됐습니다. 발견 항목은 왼쪽 목록에서 scanner 이름으로 구분됩니다.</p></div>`
    : `<div class="guard-state"><strong>첫 실행 분석 대기</strong><p>AI-Infra-Guard mcp-scan은 MCP 도구 설명·구현 위험을 SARIF로 남깁니다. 로컬 OpenAI 호환 분석 엔드포인트를 설정한 뒤 격리된 체크아웃에서 실행합니다.</p></div>`;
}

function renderAudit() {
  document.querySelector("#audit-total").textContent = `${state.decisions.length}건`;
  document.querySelector("#audit-list").innerHTML = state.decisions.map(item => {
    const conflicts = Array.isArray(item.conflicts) ? item.conflicts : [];
    const trace = [`v${item.policy_version || "?"}`];
    if (item.exception_id) trace.push(`예외 ${item.exception_id}`);
    if (item.would_policy_id) trace.push(`관찰: 집행 시 ${item.would_decision}/${item.would_policy_id}`);
    if (conflicts.length) trace.push(`경합 ${conflicts.map(entry => entry.policy_id).join(", ")}`);
    return `<tr><td>${formatDate(item.created_at)}</td><td>${escapeHtml(item.user_token || "-")}</td><td>${escapeHtml(item.tool_name || "-")}</td><td>${escapeHtml(item.data_class || "-")} / ${escapeHtml(item.action || "-")}</td><td><span class="decision-text ${escapeHtml(String(item.decision || "").toLowerCase())}">${escapeHtml(item.decision || "-")}</span></td><td><code>${escapeHtml(item.policy_id || "-")}</code><small class="muted-inline">${escapeHtml(trace.join(" · "))}</small></td><td>${item.upstream_executed ? "실행" : "미실행"}</td><td>${escapeHtml((item.trace_id || "-").slice(0, 12))}</td></tr>`;
  }).join("") || '<tr><td colspan="8" class="empty-state">감사 기록이 없습니다.</td></tr>';
}

function renderPolicyLedger() {
  const ledger = state.ledger || {};
  const policies = ledger.policies || [];
  const exceptions = ledger.exceptions || [];
  const set = ledger.policy_set || {};
  const enforcing = policies.filter(policy => policy.status === "운영").length;
  const suspended = policies.filter(policy => policy.status === "중지" || policy.status === "폐기").length;
  const active = exceptions.filter(item => item.status === "적용").length;
  document.querySelector("#ledger-total").textContent = `${policies.length}건`;
  document.querySelector("#ledger-cards").innerHTML = [
    ["정책집", set.version || "-", `${escapeHtml(set.id || "")} · 상태 ${escapeHtml(set.status || "-")}`, ""],
    ["집행 중", enforcing, `중지·폐기 ${suspended}건`, enforcing ? "good" : "warning"],
    ["적용 중 예외", active, `등록 예외 ${exceptions.length}건`, active ? "warning" : "good"],
    ["배포 Rego", (ledger.deployed_rego?.id || "-"), `적용환경 ${escapeHtml(ledger.environment || "-")}`, ledger.deployed_rego?.status === "ACTIVE" ? "good" : "critical"],
  ].map(([label, value, note, tone]) => `<article class="metric-card ${tone}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${note}</small></article>`).join("");
  document.querySelector("#ledger-list").innerHTML = policies.map(policy => {
    const suspendedRow = policy.status !== "운영" && policy.status !== "제한";
    return `<tr class="${suspendedRow ? "row-muted" : ""}"><td>${escapeHtml(policy.priority)}</td><td><code>${escapeHtml(policy.policy_id)}</code></td><td>${escapeHtml(policy.name)}<small class="muted-inline"> ${escapeHtml(policy.purpose || "")}</small></td><td>${escapeHtml(policy.version)}</td><td><span class="status-pill ${suspendedRow ? "disabled" : ""}">${escapeHtml(policy.status)}</span></td><td>${escapeHtml(policy.enforced_by || "-")}</td><td>${escapeHtml(policy.outcome || "-")}</td><td>${escapeHtml((policy.risk_ids || []).join(", "))} / ${escapeHtml((policy.control_ids || []).join(", "))}</td><td>${policy.exceptionable ? "가능" : "불가"}</td></tr>`;
  }).join("") || '<tr><td colspan="9" class="empty-state">정책 관리대장을 읽지 못했습니다.</td></tr>';
  document.querySelector("#exception-total").textContent = `${exceptions.length}건`;
  document.querySelector("#exception-list").innerHTML = exceptions.map(item => `<article class="request-row"><div class="request-top"><div><h3>${escapeHtml(item.id)} · ${escapeHtml(item.title)}</h3><small>${escapeHtml(item.policy_id)} → ${escapeHtml(item.effect)}</small></div><span class="status-pill ${item.status === "적용" ? "queue" : "disabled"}">${escapeHtml(item.status)}</span></div><p>${escapeHtml(item.reason)}</p><div class="request-meta"><span>범위 ${escapeHtml(JSON.stringify(item.scope))}</span><span>${formatDate(item.valid_from)} ~ ${formatDate(item.valid_until)}</span><span>승인 ${escapeHtml(item.approved_by)}</span><span>잔여위험 ${escapeHtml(item.residual_risk)}</span></div><ul class="check-list">${(item.compensating_controls || []).map(control => `<li>${escapeHtml(control)}</li>`).join("")}</ul><p class="form-note">종료계획: ${escapeHtml(item.exit_plan)}</p></article>`).join("") || '<p class="empty-state">등록된 예외가 없습니다.</p>';
}

function render() {
  document.querySelector("#viewer-name").textContent = state.viewer.name;
  document.querySelector("#viewer-role").textContent = `${state.viewer.department} · ${state.viewer.roles.join(", ")}`;
  const connection = document.querySelector("#connection-state");
  connection.classList.toggle("ready", state.health.status === "ok");
  connection.lastChild.textContent = state.health.status === "ok" ? " 연결 정상" : " 연결 확인 필요";
  renderOverview(); renderIntake(); renderVerification(); renderRisks(); renderPolicyLedger(); renderAudit();
}

async function loadConsole() {
  state = await api("/api/console");
  render();
}

function renderResult(body) {
  currentResult = body;
  const outcome = body.gateway_result || {};
  const decision = outcome.decision || (body.status === "no_tool" ? "No Tool" : "Error");
  const titles = {Allow:"실행 완료", Alert:"실행 완료 · 경보 기록", Restrict:"제한 적용 후 실행", Approval:"승인 대기", Block:"실행 차단", "No Tool":"실행 대상 없음", Error:"처리 확인 필요"};
  document.querySelector("#result-title").textContent = titles[decision] || "실행 결과";
  document.querySelector("#result-message").textContent = body.message || outcome.reason || "처리 결과를 확인하세요.";
  const facts = [
    ["정책", outcome.policy_id || body.error_code || "-"],
    ["정책 버전", outcome.policy_version || "-"],
    ["판정", decision],
    ["적용 예외", outcome.exception?.id ? `${outcome.exception.id} (~${String(outcome.exception.valid_until || "").slice(0, 10)})` : "없음"],
    ["증적·의무", (outcome.obligations || []).join(", ") || "-"],
    ["경합 정책", (outcome.conflicts || []).map(entry => entry.policy_id).join(", ") || "없음"],
    ["도구", body.tool_call?.tool_name || outcome.tool_name || "-"],
    ["실행", outcome.upstream_executed ? "upstream 실행 확인" : "실행되지 않음"],
    ["Trace", outcome.trace_id || "-"],
    ["세션", body.session_id || "-"],
  ];
  document.querySelector("#result-facts").innerHTML = facts.map(([key, value]) => `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
  const approval = document.querySelector("#approve-button");
  approval.classList.toggle("hidden", !(decision === "Approval" && state.viewer.roles.includes("admin")));
}

async function sendPrompt() {
  const prompt = document.querySelector("#prompt");
  const message = prompt.value.trim();
  if (busy || !message) return;
  busy = true;
  const button = document.querySelector("#send-button"); button.disabled = true; button.textContent = "정책 확인 중";
  if (!pendingRequest || pendingRequest.message !== message || pendingRequest.session_id !== sessionId) pendingRequest = {message, request_id: crypto.randomUUID(), session_id: sessionId};
  try {
    const body = await api("/chat", {method:"POST", body:pendingRequest});
    sessionId = body.session_id; sessionStorage.setItem(SESSION_KEY, sessionId); pendingRequest = null;
    renderResult(body); await loadConsole();
  } catch (error) { renderResult({status:"failed", message:error.message}); }
  finally { busy = false; button.disabled = false; button.textContent = "정책 검증 후 실행"; }
}

async function approveCurrent() {
  const id = currentResult?.gateway_result?.approval_id;
  if (!id || busy) return;
  busy = true;
  try { renderResult({gateway_result: await api(`/approvals/${id}/approve`, {method:"POST", body:{}})}); await loadConsole(); }
  catch (error) { showNotice(error.message, true); }
  finally { busy = false; }
}

document.addEventListener("click", async event => {
  const pageButton = event.target.closest("[data-page]");
  if (pageButton) { navigate(pageButton.dataset.page); return; }
  const queueButton = event.target.closest("[data-queue]");
  if (queueButton) {
    queueButton.disabled = true;
    try { const body = await api(`/api/mcp-requests/${queueButton.dataset.queue}/queue-validation`, {method:"POST", body:{}}); showNotice(body.message); await loadConsole(); }
    catch (error) { showNotice(error.message, true); queueButton.disabled = false; }
    return;
  }
  const promptButton = event.target.closest("[data-prompt]");
  if (promptButton) { document.querySelector("#prompt").value = promptButton.dataset.prompt; document.querySelector("#prompt").focus(); }
});

document.querySelector("#refresh-console").addEventListener("click", () => loadConsole().catch(error => showNotice(error.message, true)));
document.querySelector("#refresh-registry").addEventListener("click", async () => { try { await api("/api/registry/refresh", {method:"POST", body:{}}); showNotice("현재 Catalog를 Registry 계약과 다시 비교했습니다."); await loadConsole(); } catch (error) { showNotice(error.message, true); } });
document.querySelector("#import-evidence").addEventListener("click", async () => { try { await api("/api/supply-chain/import", {method:"POST", body:{}}); showNotice("격리 스캐너가 만든 증적을 반영했습니다."); await loadConsole(); } catch (error) { showNotice(error.message, true); } });
document.querySelector("#intake-form").addEventListener("submit", async event => { event.preventDefault(); const form = new FormData(event.currentTarget); try { const body = await api("/api/mcp-requests", {method:"POST", body:Object.fromEntries(form)}); event.currentTarget.reset(); showNotice(body.message); await loadConsole(); } catch (error) { showNotice(error.message, true); } });
document.querySelector("#send-button").addEventListener("click", sendPrompt);
document.querySelector("#prompt").addEventListener("keydown", event => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); sendPrompt(); } });
document.querySelector("#new-session").addEventListener("click", () => { sessionId = null; pendingRequest = null; sessionStorage.removeItem(SESSION_KEY); showNotice("새 실행 세션을 시작합니다."); });
document.querySelector("#approve-button").addEventListener("click", approveCurrent);
document.querySelector("#logout-button").addEventListener("click", async () => { try { await api("/auth/logout", {method:"POST", body:{}}); } finally { redirectToLogin(); } });
window.addEventListener("hashchange", () => navigate(currentPage(), true));

async function init() {
  if (!token) return redirectToLogin();
  navigate(currentPage(), true);
  await loadConsole();
}
init().catch(error => showNotice(error.message, true));
