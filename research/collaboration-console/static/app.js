"use strict";
const state = { cursor: 0, events: [], tasks: [], runs: [], connected: false };
const $ = id => document.getElementById(id);
const labels = { queued: "대기열", running: "작업 중", waiting: "응답 대기", completed: "완료", passed: "통과", failed: "실패", blocked: "차단됨", cancelled: "중단됨" };
const outcomes = { running: "실행 중", completed: "완료", turn_error: "턴 오류", usage_limit: "사용량 한도", task_failed: "작업 실패", model_mismatch: "모델 불일치", cancelled: "중단됨" };
const modelChecks = { confirmed: "응답 모델 확인됨", mismatch: "응답 모델 불일치", unreported: "응답 모델 미보고" };
const kinds = { message: "메시지", task: "작업 상태", check: "검증" };
const inactive = new Set(["completed", "passed", "failed", "blocked", "cancelled"]);
function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function time(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "시간 확인 필요" : date.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function gatewayText(run) {
  const gateway = run.gateway || {};
  if (gateway.state === "recorded") return `게이트웨이 기록 ${gateway.count}건`;
  if (gateway.state !== "none") return "게이트웨이 기록 미확인";
  return run.tool_calls > 0 ? "게이트웨이 기록 없음 · 호출은 있었음" : "게이트웨이 기록 없음 · 호출 자체가 없음";
}
function renderRuns() {
  $("run-count").textContent = `${state.runs.length}개`;
  $("runs").replaceChildren();
  if (!state.runs.length) $("runs").append(node("p", "empty", "기록된 실행이 없습니다."));
  state.runs.slice().reverse().forEach(run => {
    const card = node("article", `run-card run-${run.outcome}`);
    const top = node("div", "task-top");
    top.append(node("strong", "", `${run.agent} · ${run.task_id}`), node("span", `state run-state-${run.outcome}`, outcomes[run.outcome] || run.outcome));
    const requested = run.requested || {};
    const observed = run.observed || {};
    const answered = [...(observed.models || []), ...(observed.usage_models || []).filter(name => !(observed.models || []).includes(name))];
    card.append(top, node("span", "run-line", `요청 ${requested.model} · 강도 ${requested.effort}`),
      node("span", `run-line model-${run.model_check}`, `${answered.length ? `응답 ${answered.join(", ")}` : "응답 모델 없음"} · ${modelChecks[run.model_check]}`));
    if (run.applied) card.append(node("span", "run-line", `턴에 적용된 값 ${run.applied.model || "—"} · ${run.applied.effort || "—"}`));
    card.append(node("span", run.no_tool_call ? "run-line flag" : "run-line", run.no_tool_call ? "도구 호출 0건 (NO_TOOL_CALL)" : `도구 호출 ${run.tool_calls}건`),
      node("span", run.gateway && run.gateway.state === "none" && run.tool_calls > 0 ? "run-line flag" : "run-line", gatewayText(run)));
    if (run.error) card.append(node("p", "task-body", [run.error.code, run.error.message].filter(Boolean).join(" · ")));
    card.append(node("time", "", time(run.updated_at)));
    $("runs").append(card);
  });
}
function render() {
  renderRuns();
  const tasks = state.tasks;
  $("running-count").textContent = tasks.filter(task => task.state === "running").length;
  $("completed-count").textContent = tasks.filter(task => ["completed", "passed"].includes(task.state)).length;
  $("attention-count").textContent = tasks.filter(task => ["failed", "blocked", "waiting"].includes(task.state)).length;
  $("event-count").textContent = state.events.length;
  $("task-count").textContent = `${tasks.length}개`;
  $("tasks").replaceChildren();
  if (!tasks.length) $("tasks").append(node("p", "empty", "등록된 작업이 없습니다."));
  tasks.slice().sort((a, b) => b.id - a.id).forEach(task => {
    const card = node("article", "task-card");
    const top = node("div", "task-top");
    top.append(node("strong", "", task.task_id), node("span", `state state-${task.state}`, labels[task.state]));
    card.append(top, node("span", "task-author", `${task.author} 담당`), node("p", "task-body", task.body), node("time", "", time(task.timestamp)));
    if (!inactive.has(task.state) && Date.now() - new Date(task.timestamp).getTime() > 600000) card.append(node("span", "stale", "10분 이상 갱신 없음 · 상태 확인 필요"));
    $("tasks").append(card);
  });
  const author = $("author-filter").value, kind = $("kind-filter").value, query = $("search").value.trim().toLocaleLowerCase();
  const events = state.events.filter(event => (author === "all" || event.author === author) && (kind === "all" || event.kind === kind) && `${event.body} ${event.task_id}`.toLocaleLowerCase().includes(query));
  const feed = $("feed");
  const previousScroll = feed.scrollTop;
  const nearBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 90;
  feed.replaceChildren();
  if (!events.length) feed.append(node("div", "empty", state.events.length ? "선택한 조건에 맞는 기록이 없습니다." : "아직 공유된 기록이 없습니다. 실제 메시지와 작업 보고가 여기에 표시됩니다."));
  events.forEach(event => {
    const entry = node("article", `event event-${event.author.toLowerCase()}`);
    const meta = node("div", "event-meta");
    meta.append(node("strong", "author", event.author), node("span", "kind", kinds[event.kind]), node("span", `state state-${event.state}`, labels[event.state]), node("time", "", time(event.timestamp)));
    entry.append(meta, node("span", "task-reference", event.task_id), node("p", "event-body", event.body));
    feed.append(entry);
  });
  if ($("follow").checked || nearBottom) feed.scrollTop = feed.scrollHeight;
  else feed.scrollTop = previousScroll;
}
async function poll() {
  try {
    const response = await fetch(`/api/events?after=${state.cursor}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const runsResponse = await fetch("/api/runs", { cache: "no-store" });
    if (runsResponse.ok) state.runs = (await runsResponse.json()).runs;
    if (data.cursor < state.cursor) state.events = [];
    const ids = new Set(state.events.map(event => event.id));
    for (const event of data.events) if (!ids.has(event.id)) state.events.push(event);
    state.events = state.events.slice(-1000);
    state.cursor = data.cursor;
    state.tasks = data.tasks;
    state.connected = true;
    $("connection").textContent = "기록 연결됨";
    $("connection-dot").className = "dot connected";
    $("updated").textContent = `확인 ${time(data.server_time)}`;
    const notices = [];
    if (data.malformed_records) notices.push(`읽을 수 없는 레코드 ${data.malformed_records}개를 건너뛰었습니다.`);
    if (data.truncated || state.events.length === 1000) notices.push("최근 1,000개 기록을 표시합니다. 전체 원본은 로컬 JSONL에 보존됩니다.");
    $("notice").textContent = notices.join(" ");
    $("notice").hidden = !notices.length;
    render();
  } catch (error) {
    state.connected = false;
    $("connection").textContent = "연결 끊김 · 마지막 기록 표시";
    $("connection-dot").className = "dot disconnected";
    $("notice").textContent = `로컬 기록 서버에 연결할 수 없습니다 (${error.message}). 서버 실행 상태를 확인하세요.`;
    $("notice").hidden = false;
  } finally {
    setTimeout(poll, 2000);
  }
}
["author-filter", "kind-filter", "search"].forEach(id => $(id).addEventListener("input", render));
poll();
