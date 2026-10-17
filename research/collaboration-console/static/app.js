"use strict";
const $ = id => document.getElementById(id);
const state = { cursor: 0, events: [], tasks: [], runs: [], wbs: null, connected: false, channel: "overview", selectedTask: null };
const labels = { queued: "대기열", running: "작업 중", waiting: "응답 대기", completed: "완료", passed: "통과", failed: "실패", blocked: "차단됨", cancelled: "중단됨" };
const outcomes = { running: "실행 중", completed: "완료", turn_error: "턴 오류", usage_limit: "사용량 한도", task_failed: "작업 실패", model_mismatch: "모델 불일치", cancelled: "중단됨" };
const modelChecks = { confirmed: "응답 모델 확인됨", mismatch: "응답 모델 불일치", unreported: "응답 모델 미보고" };
const kinds = { message: "메시지", task: "작업 상태", check: "검증" };
const inactive = new Set(["completed", "passed", "failed", "blocked", "cancelled"]);
const activeTaskStates = new Set(["queued", "running", "waiting"]);
const CHANNEL_META = {
  overview: { title: "개요", topic: "두 에이전트가 공유한 메시지, 맡은 작업, 수행한 검증을 실시간으로 확인합니다." },
  wbs: { title: "wbs", topic: "목표 G01–G10의 구현·회귀·배포·실제환경·검수 근거별 진척입니다." },
  tasks: { title: "작업", topic: "task_id별 스레드입니다. 작업을 눌러 관련 기록만 봅니다." },
  runs: { title: "codex-실행", topic: "Claude·Codex CLI 실행마다 요청/응답 모델, 도구 호출, 결과를 보여 줍니다." },
  checks: { title: "검증", topic: "수행한 검증(check) 기록만 모아서 봅니다." },
};

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

function eventMatchesFilter(event, author, query) {
  return (author === "all" || event.author === author) && (!query || `${event.body} ${event.task_id}`.toLocaleLowerCase().includes(query));
}

function renderFeed(container, events, { follow } = {}) {
  const previousScroll = container.scrollTop;
  const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 90;
  container.replaceChildren();
  if (!events.length) {
    container.append(node("div", "empty", "표시할 기록이 없습니다."));
    return;
  }
  for (const event of events) {
    const entry = node("article", `event event-${event.author.toLowerCase()}`);
    const avatar = node("span", `avatar avatar-${event.author.toLowerCase()}`, event.author[0]);
    const body = node("div", "event-body-wrap");
    const meta = node("div", "event-meta");
    meta.append(node("strong", "author", event.author), node("span", "kind", kinds[event.kind]), node("span", `state state-${event.state}`, labels[event.state]), node("time", "", time(event.timestamp)));
    body.append(meta, node("span", "task-reference", event.task_id), node("p", "event-text", event.body));
    entry.append(avatar, body);
    container.append(entry);
  }
  if (follow === false) { container.scrollTop = previousScroll; return; }
  if ((follow === undefined && nearBottom) || follow) container.scrollTop = container.scrollHeight;
  else container.scrollTop = previousScroll;
}

function renderOverview() {
  const tasks = state.tasks;
  $("running-count").textContent = tasks.filter(task => task.state === "running").length;
  $("completed-count").textContent = tasks.filter(task => ["completed", "passed"].includes(task.state)).length;
  $("attention-count").textContent = tasks.filter(task => ["failed", "blocked", "waiting"].includes(task.state)).length;
  $("event-count").textContent = state.events.length;
  if (state.wbs) {
    $("mini-progress").textContent = state.wbs.summary.progress + "%";
    $("mini-progress-bar").value = state.wbs.summary.progress;
    $("mini-complete").textContent = `최종 완료 ${state.wbs.summary.complete} / ${state.wbs.summary.total}`;
  }
  const author = $("overview-author").value, query = $("overview-search").value.trim().toLocaleLowerCase();
  const events = state.events.filter(event => eventMatchesFilter(event, author, query));
  renderFeed($("overview-feed"), events, { follow: $("follow").checked });
}

function renderTaskList() {
  $("task-list").replaceChildren();
  const tasks = state.tasks.slice().sort((a, b) => b.id - a.id);
  $("task-badge").hidden = !tasks.length;
  $("task-badge").textContent = tasks.length;
  if (!tasks.length) { $("task-list").append(node("p", "empty", "등록된 작업이 없습니다.")); return; }
  for (const task of tasks) {
    const card = node("button", "task-card" + (state.selectedTask === task.task_id ? " selected" : ""));
    const top = node("div", "task-top");
    top.append(node("strong", "", task.task_id), node("span", `state state-${task.state}`, labels[task.state]));
    card.append(top, node("span", "task-author", `${task.author} 담당`), node("p", "task-body", task.body), node("time", "", time(task.timestamp)));
    if (!inactive.has(task.state) && Date.now() - new Date(task.timestamp).getTime() > 600000) card.append(node("span", "stale", "10분 이상 갱신 없음"));
    card.addEventListener("click", () => { state.selectedTask = task.task_id; renderTasks(); });
    $("task-list").append(card);
  }
}

function renderTasks() {
  renderTaskList();
  const heading = $("thread-heading");
  heading.replaceChildren();
  if (!state.selectedTask) {
    heading.textContent = "작업을 선택하면 해당 스레드가 보입니다.";
    renderFeed($("thread-feed"), []);
    return;
  }
  heading.append(node("strong", "", state.selectedTask), node("span", "", `· 기록 ${state.events.filter(e => e.task_id === state.selectedTask).length}건`));
  const events = state.events.filter(event => event.task_id === state.selectedTask);
  renderFeed($("thread-feed"), events);
}

function gatewayText(run) {
  const gateway = run.gateway || {};
  if (gateway.state === "recorded") return `게이트웨이 기록 ${gateway.count}건`;
  if (gateway.state !== "none") return "게이트웨이 기록 미확인";
  return run.tool_calls > 0 ? "게이트웨이 기록 없음 · 호출은 있었음" : "게이트웨이 기록 없음 · 호출 자체가 없음";
}
function renderRuns() {
  $("run-badge").hidden = !state.runs.length;
  $("run-badge").textContent = state.runs.length;
  $("runs").replaceChildren();
  if (!state.runs.length) { $("runs").append(node("p", "empty", "기록된 실행이 없습니다.")); return; }
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
    if (run.usage) card.append(node("span", "run-line", `토큰 입력 ${run.usage.input_tokens ?? "—"} · 출력 ${run.usage.output_tokens ?? "—"}`));
    if (run.native_session_id) card.append(node("span", "run-line mono", `세션 ${run.native_session_id}`));
    card.append(node("span", run.no_tool_call ? "run-line flag" : "run-line", run.no_tool_call ? "도구 호출 0건 (NO_TOOL_CALL)" : `도구 호출 ${run.tool_calls}건`),
      node("span", run.gateway && run.gateway.state === "none" && run.tool_calls > 0 ? "run-line flag" : "run-line", gatewayText(run)));
    if (run.error) card.append(node("p", "task-body", [run.error.code, run.error.message].filter(Boolean).join(" · ")));
    card.append(node("time", "", time(run.updated_at)));
    $("runs").append(card);
  });
}

function renderChecks() {
  const author = $("checks-author").value, query = $("checks-search").value.trim().toLocaleLowerCase();
  const events = state.events.filter(event => event.kind === "check" && eventMatchesFilter(event, author, query));
  renderFeed($("checks-feed"), events);
}

function renderMembers() {
  const box = $("members");
  box.replaceChildren();
  for (const author of ["Claude", "Codex", "User", "System"]) {
    const ownEvents = state.events.filter(event => event.author === author);
    const last = ownEvents[ownEvents.length - 1];
    const activeTask = state.tasks.slice().reverse().find(task => task.author === author && activeTaskStates.has(task.state));
    const recentlyActive = last && Date.now() - new Date(last.timestamp).getTime() < 600000;
    const member = node("article", "member");
    const avatarRow = node("div", "member-top");
    avatarRow.append(node("span", `avatar avatar-${author.toLowerCase()}`, author[0]), node("span", `member-dot ${recentlyActive ? "online" : "idle"}`));
    member.append(avatarRow, node("strong", "", author));
    if (author === "Claude") member.append(node("small", "model-badge", "Sonnet 5.5 · xhigh"));
    member.append(node("small", "", activeTask ? `${activeTask.task_id} · ${labels[activeTask.state]}` : "대기 중"));
    member.append(node("time", "", last ? time(last.timestamp) : "기록 없음"));
    box.append(member);
  }
}

function score(value) { return node("span", value === 1 ? "filled" : value === 0.5 ? "half" : "open", value === 1 ? "●" : value === 0.5 ? "◐" : "○"); }
function section(title, values) { const box = node("section"); box.append(node("h3", "", title)); for (const value of values) box.append(node("p", "", value)); return box; }
function showWbsDetail(row) {
  const data = state.wbs;
  $("detail-id").textContent = `${row.id} · ${row.goal_id} · ${row.progress}%`;
  $("detail-title").textContent = row.title;
  const box = $("detail-content");
  box.replaceChildren();
  box.append(section("완료조건", [row.completion_condition]));
  for (const [key, label] of Object.entries(data.rubric.stage_labels)) {
    const line = node("div", "stage-line");
    line.append(score(row.stage_scores[key]), node("b", "", ` ${label} · ${row.stage_scores[key]}점`), node("p", "", row.stage_notes[key]));
    box.append(line);
  }
  box.append(section("남은 공백", [row.known_gap]));
  box.append(section("정책 매핑", [`정책: ${(row.pol_ids || []).join(" · ") || "—"}`, `원본 PAC: ${(row.source_pac_ids || []).join(" · ") || "—"}`]));
  const sourceBox = node("section");
  sourceBox.append(node("h3", "", "코드·함수와 시험 후보"));
  for (const path of [...(row.code_symbols_files || []), ...(row.regression_test_candidates || [])]) sourceBox.append(node("code", "path", path));
  box.append(sourceBox);
  const evidenceBox = node("section");
  evidenceBox.append(node("h3", "", "검수 근거 · 로컬 정본 경로"));
  for (const evidence of row.evidence || []) {
    evidenceBox.append(node("code", "path", evidence.path));
    if (evidence.sha256) evidenceBox.append(node("div", "hash", "SHA-256 " + evidence.sha256));
  }
  box.append(evidenceBox);
  $("detail").showModal();
}
function renderWbsRows() {
  const data = state.wbs;
  if (!data) return;
  const query = $("wbs-search").value.trim().toLowerCase(), goal = $("wbs-goal-filter").value, status = $("wbs-status-filter").value;
  const rows = data.items.filter(row => (!goal || row.goal_id === goal) &&
    (!query || [row.id, row.title, row.known_gap, row.backlog_id || "", ...(row.pol_ids || []), ...(row.source_pac_ids || [])].join(" ").toLowerCase().includes(query)) &&
    (!status || (status === "remaining" && !row.complete) || (status === "missing" && row.stage_scores.implementation === 0) ||
      (status === "partial" && row.stage_scores.implementation === 0.5) || (status === "complete" && row.complete) ||
      (status === "p0" && row.priority === "P0") || (status === "planned" && row.kind === "추가 개발")));
  $("wbs-rows").replaceChildren();
  for (const row of rows) {
    const tr = node("tr");
    const first = node("td");
    const button = node("button", "row-title", row.title);
    button.type = "button";
    button.addEventListener("click", () => showWbsDetail(row));
    first.append(button, node("span", "row-id", row.id + (row.backlog_id ? " · " + row.backlog_id : "") + (row.kind === "추가 개발" ? " · 추가 개발" : "")));
    tr.append(first);
    const pac = node("td");
    pac.append(node("span", "pac", (row.pol_ids || []).join(" · ") || "—"));
    tr.append(pac, node("td", "pct", row.progress + "%"));
    for (const key of Object.keys(data.rubric.stage_labels)) {
      const td = node("td", "stage");
      const mark = score(row.stage_scores[key]);
      mark.setAttribute("aria-label", `${data.rubric.stage_labels[key]} ${row.stage_scores[key]}점`);
      td.append(mark);
      tr.append(td);
    }
    const priority = node("td");
    priority.append(node("span", "priority " + row.priority.toLowerCase(), row.priority));
    tr.append(priority);
    $("wbs-rows").append(tr);
  }
  $("wbs-row-count").textContent = `${rows.length} / ${data.items.length}개`;
  $("wbs-empty").hidden = !!rows.length;
}
function renderWbs() {
  const data = state.wbs;
  if (!data) { $("load-error").hidden = false; $("load-error").textContent = "WBS 데이터를 불러오지 못했습니다."; return; }
  $("load-error").hidden = true;
  $("wbs-progress").textContent = data.summary.progress + "%";
  $("wbs-overall-progress").value = data.summary.progress;
  $("wbs-complete").textContent = `${data.summary.complete} / ${data.summary.total}`;
  $("wbs-implemented").textContent = data.summary.implementation_full + "개";
  $("wbs-partial").textContent = `부분 ${data.summary.implementation_partial}개 · 미구현 ${data.summary.implementation_missing}개`;
  $("wbs-as-of-small").textContent = new Date(data.as_of).toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul" });
  $("wbs-audit-time").textContent = "현장 조회 " + time(data.audit_as_of);
  $("wbs-badge").hidden = false;
  $("wbs-badge").textContent = data.summary.total - data.summary.complete;
  $("wbs-goals").replaceChildren();
  const goalSelect = $("wbs-goal-filter");
  goalSelect.replaceChildren(node("option", "", "모든 목표"));
  goalSelect.firstChild.value = "";
  for (const goal of data.goals) {
    const row = node("a", "goal");
    row.href = "#";
    row.addEventListener("click", event => { event.preventDefault(); goalSelect.value = goal.id; renderWbsRows(); });
    const progress = node("progress"); progress.max = 100; progress.value = goal.progress;
    row.append(node("span", "goal-id", goal.id), node("span", "goal-name", goal.title), progress, node("span", "goal-value", goal.progress + "%"));
    $("wbs-goals").append(row);
    const option = node("option", "", `${goal.id} ${goal.title}`);
    option.value = goal.id;
    goalSelect.append(option);
  }
  $("wbs-stage-totals").replaceChildren();
  for (const [key, label] of Object.entries(data.rubric.stage_labels)) {
    const div = node("div", "stage-total");
    const progress = node("progress"); progress.max = data.items.length; progress.value = data.summary.stage_equivalent_counts[key];
    div.append(node("span", "", label), progress, node("strong", "", `${progress.value} / ${data.items.length}점`));
    $("wbs-stage-totals").append(div);
  }
  $("wbs-exclusions").replaceChildren();
  for (const item of data.exclusions || []) $("wbs-exclusions").append(node("li", "", item));
  renderWbsRows();
}

function updateChannelChrome() {
  const meta = CHANNEL_META[state.channel];
  $("channel-title").textContent = meta.title;
  $("channel-topic").textContent = meta.topic;
  document.title = `#${meta.title} · MINT 개발 현황`;
  for (const button of document.querySelectorAll(".channel")) button.classList.toggle("selected", button.dataset.channel === state.channel);
  for (const view of document.querySelectorAll(".view")) view.classList.toggle("active", view.id === `view-${state.channel}`);
}
function render() {
  renderMembers();
  renderOverview();
  renderTasks();
  renderRuns();
  renderChecks();
  if (state.wbs) renderWbs();
}
function setChannel(channel) {
  state.channel = channel;
  updateChannelChrome();
  render();
  if (window.matchMedia("(max-width: 900px)").matches) closeSidebars();
}
function closeSidebars() {
  $("channel-sidebar").classList.remove("open");
  $("member-sidebar").classList.remove("open");
  $("sidebar-toggle").setAttribute("aria-expanded", "false");
  $("member-toggle").setAttribute("aria-expanded", "false");
}

async function poll() {
  try {
    const response = await fetch(`/api/events?after=${state.cursor}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const runsResponse = await fetch("/api/runs", { cache: "no-store" });
    if (runsResponse.ok) state.runs = (await runsResponse.json()).runs;
    try {
      const wbsResponse = await fetch("/api/wbs", { cache: "no-store" });
      if (wbsResponse.ok) state.wbs = await wbsResponse.json();
    } catch (_) { /* WBS is a secondary panel; events/runs still render if it is unavailable */ }
    if (data.cursor < state.cursor) state.events = [];
    const ids = new Set(state.events.map(event => event.id));
    for (const event of data.events) if (!ids.has(event.id)) state.events.push(event);
    state.events = state.events.slice(-1000);
    state.cursor = data.cursor;
    state.tasks = data.tasks;
    state.connected = true;
    $("connection").textContent = "연결됨";
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
    $("connection").textContent = "연결 끊김";
    $("connection-dot").className = "dot disconnected";
    $("notice").textContent = `서버에 연결할 수 없습니다 (${error.message}).`;
    $("notice").hidden = false;
  } finally {
    setTimeout(poll, 2000);
  }
}

for (const button of document.querySelectorAll(".channel")) button.addEventListener("click", () => setChannel(button.dataset.channel));
for (const button of document.querySelectorAll("[data-goto]")) button.addEventListener("click", () => setChannel(button.dataset.goto));
["overview-author", "overview-search", "follow"].forEach(id => $(id).addEventListener("input", renderOverview));
["checks-author", "checks-search"].forEach(id => $(id).addEventListener("input", renderChecks));
["wbs-search", "wbs-goal-filter", "wbs-status-filter"].forEach(id => $(id).addEventListener("input", renderWbsRows));
$("close").addEventListener("click", () => $("detail").close());
$("sidebar-toggle").addEventListener("click", () => {
  const open = $("channel-sidebar").classList.toggle("open");
  $("sidebar-toggle").setAttribute("aria-expanded", String(open));
});
$("member-toggle").addEventListener("click", () => {
  const open = $("member-sidebar").classList.toggle("open");
  $("member-toggle").setAttribute("aria-expanded", String(open));
});
updateChannelChrome();
poll();
