const TOKEN_KEY = "bob_mock_sso_token";
const SESSION_KEY = "bob_agent_session";
const token = sessionStorage.getItem(TOKEN_KEY);
const promptInput = document.querySelector("#prompt");
const sendButton = document.querySelector("#send-button");
const resultPanel = document.querySelector("#result-panel");
let currentUser = null;
let currentResult = null;
let sessionId = sessionStorage.getItem(SESSION_KEY);
let pendingRequest = null;
let busy = false;

function redirectToLogin() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(SESSION_KEY);
  window.location.replace("/login");
}
async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: {Authorization: `Bearer ${token}`, "Content-Type": "application/json"},
    ...(body === undefined ? {} : {body: JSON.stringify(body)})
  });
  if (response.status === 401) { redirectToLogin(); throw new Error("다시 로그인하세요."); }
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "요청 형식을 확인하세요.");
  return data;
}
function setText(selector, text) { document.querySelector(selector).textContent = text; }
function renderResult(body) {
  currentResult = body;
  const outcome = body.gateway_result;
  const decision = outcome?.decision || (body.status === "no_tool" ? "No Tool" : "Error");
  const executed = outcome?.upstream_executed;
  resultPanel.classList.remove("hidden", "allowed", "blocked");
  resultPanel.classList.add(executed ? "allowed" : "blocked");
  const badge = document.querySelector("#decision-badge");
  badge.className = `decision-badge ${executed ? "allowed" : "blocked"}`;
  badge.textContent = decision;
  const labels = {Allow: "요청을 실행했습니다", Alert: "실행하고 열람 경보를 남겼습니다", Restrict: "범위를 제한해 실행했습니다", Approval: "승인 전까지 실행을 보류했습니다", Block: "요청을 차단했습니다"};
  setText("#result-title", labels[decision] || (decision === "No Tool" ? "실행할 도구가 없습니다" : "처리 상태를 확인하세요"));
  setText("#result-message", body.message || outcome?.reason || "");
  setText("#result-user", currentUser?.name || "-");
  setText("#result-request-id", body.request_id || outcome?.request_id || "-");
  setText("#result-session", body.session_id || "-");
  setText("#result-tool", body.tool_call?.tool_name || outcome?.tool_name || "-");
  setText("#result-path", body.tool_call?.arguments?.path || body.tool_call?.arguments?.document_id || "-");
  setText("#result-policy", outcome?.policy_id || body.error_code || "-");
  setText("#result-effect", outcome ? `${executed ? "실행 확인" : outcome.upstream_attempted ? "통신 실패 · 효과 확인 필요" : "실행 안 됨"} · 효과 ${outcome.effect_before} → ${outcome.effect_after}` : "MCP 결과 없음");
  setText("#result-trace", outcome?.trace_id || "-");
  setText("#result-json", JSON.stringify(body, null, 2));
  document.querySelector("#approve-button").classList.toggle("hidden", !(decision === "Approval" && currentUser?.roles.includes("admin")));
}
async function refreshHistory() {
  if (!sessionId) { setText("#history", "아직 요청이 없습니다."); return; }
  const data = await api(`/sessions/${sessionId}`);
  const parent = document.querySelector("#history");
  parent.replaceChildren();
  data.runs.forEach(run => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item";
    button.textContent = `${run.response?.gateway_result?.decision || run.status} · ${run.message}`;
    button.addEventListener("click", () => { if(run.response) renderResult(run.response); });
    parent.append(button);
  });
}
async function approve(id) {
  if (busy) return;
  busy = true;
  const button = document.querySelector("#approve-button");
  button.disabled = true;
  try {
    const outcome = await api(`/approvals/${id}/approve`, {});
    renderResult({request_id: outcome.request_id, session_id: outcome.request_payload?._agent_context?.session_id, message: outcome.reason, gateway_result: outcome});
    await refreshApprovals();
  } catch (error) { setText("#result-message", error.message); }
  finally { busy = false; button.disabled = false; }
}
async function refreshApprovals() {
  if (!currentUser?.roles.includes("admin")) return;
  document.querySelector("#approval-queue").classList.remove("hidden");
  const data = await api("/approvals");
  const parent = document.querySelector("#approval-list");
  parent.replaceChildren();
  if (!data.approvals.length) parent.textContent = "승인 대기 요청이 없습니다.";
  data.approvals.forEach(item => {
    const button = document.createElement("button");
    button.type = "button"; button.className = "history-item";
    button.textContent = `${item.tool_name} · ${item.requested_by} · ${item.id.slice(0,8)} · 승인하기`;
    button.addEventListener("click", () => approve(item.id));
    parent.append(button);
  });
}
async function sendPrompt() {
  const message = promptInput.value.trim();
  if (busy || !message) return;
  busy = true; sendButton.disabled = true; sendButton.textContent = "정책 확인 중";
  if (!pendingRequest || pendingRequest.message !== message || pendingRequest.session_id !== sessionId) {
    pendingRequest = {message, request_id: crypto.randomUUID(), session_id: sessionId};
  }
  try {
    const body = await api("/chat", pendingRequest);
    sessionId = body.session_id;
    sessionStorage.setItem(SESSION_KEY, sessionId);
    pendingRequest = null;
    renderResult(body);
    await refreshHistory();
    await refreshApprovals();
  } catch (error) {
    // Retain the same request ID after a network failure; the server prevents duplicate effects.
    renderResult({status: "failed", message: error.message});
  } finally { busy = false; sendButton.disabled = false; sendButton.textContent = "요청 보내기"; }
}
document.querySelectorAll(".example-button").forEach(button => button.addEventListener("click", () => {
  promptInput.value = button.dataset.prompt; promptInput.focus();
}));
document.querySelector("#logout-button").addEventListener("click", async () => {
  try { await api("/auth/logout", {}); redirectToLogin(); }
  catch (error) { setText("#readiness", "로그아웃 실패: " + error.message); }
});
document.querySelector("#new-session").addEventListener("click", () => {
  sessionId = null; pendingRequest = null; sessionStorage.removeItem(SESSION_KEY);
  resultPanel.classList.add("hidden"); refreshHistory();
});
document.querySelector("#approve-button").addEventListener("click", () => approve(currentResult.gateway_result.approval_id));
document.querySelector("#refresh-history").addEventListener("click", () => refreshHistory().catch(e => setText("#history", e.message)));
document.querySelector("#refresh-approvals").addEventListener("click", () => refreshApprovals().catch(e => setText("#approval-list", e.message)));
sendButton.addEventListener("click", sendPrompt);
promptInput.addEventListener("keydown", event => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); sendPrompt(); } });
async function init() {
  if (!token) return redirectToLogin();
  currentUser = await api("/auth/me");
  setText("#user-name", currentUser.name);
  setText("#user-department", currentUser.department + " · " + currentUser.roles.join(", "));
  setText("#user-avatar", currentUser.name.slice(0, 1));
  const ready = await api("/api/readiness");
  setText("#readiness", `${ready.status === "ready" ? "시나리오 준비됨" : "설정 확인 필요"} · ${ready.model.mode === "mock" ? "모의 모델 (외부 API 호출 없음)" : "설정한 모델 API"} · 사용자 JWT(30분) + Agent 위임 증명(60초) · Gateway가 actor·요청 무결성을 검증합니다`);
  await refreshHistory(); await refreshApprovals();
}
init().catch(error => setText("#readiness", error.message));
