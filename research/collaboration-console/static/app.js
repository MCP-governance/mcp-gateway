"use strict";
const $ = id => document.getElementById(id);
const state = { cursor: 0, events: [], tasks: [], runs: [], worker: null, wbs: null, connected: false, channel: window.location?.hash === "#discussions" ? "discussions" : "overview", selectedTask: null };
const labels = { queued: "대기열", running: "작업 중", waiting: "응답 대기", completed: "완료", passed: "통과", failed: "실패", blocked: "차단됨", cancelled: "중단됨" };
const outcomes = { running: "실행 중", completed: "완료", turn_error: "턴 오류", usage_limit: "사용량 한도", task_failed: "작업 실패", model_mismatch: "모델 불일치", cancelled: "중단됨" };
const modelChecks = { confirmed: "응답 모델 확인됨", mismatch: "응답 모델 불일치", unreported: "응답 모델 미보고" };
const kinds = { message: "메시지", task: "작업 상태", check: "검증" };
const inactive = new Set(["completed", "passed", "failed", "blocked", "cancelled"]);
const activeTaskStates = new Set(["queued", "running", "waiting"]);
const rendered = new Map();
const feeds = new WeakMap();
let pollTimer, polling = false;
const CHANNEL_META = {
  overview: { title: "개요", topic: "Codex·Claude·Gemini의 작업 요청, 검토 결과, 다음 행동을 같은 스레드에서 확인합니다." },
  discussions: { title: "에이전트 협의", topic: "에이전트가 실제로 보낸 요청·답변·이견·조치입니다. 수신자와 답장 번호로 연결됩니다." },
  wbs: { title: "wbs", topic: "목표 G01–G10의 구현·회귀·배포·실제환경·검수 근거별 진척입니다." },
  tasks: { title: "작업", topic: "task_id별 스레드입니다. 작업을 눌러 관련 기록만 봅니다." },
  runs: { title: "실행 기록", topic: "CLI의 요청/응답 모델, 도구 호출, 결과입니다. 자동 실행 상태는 작업에서 확인합니다." },
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

function renderChanged(key, inputs, draw) {
  const previous = rendered.get(key);
  if (previous && inputs.every((value, index) => value === previous[index])) return;
  draw();
  rendered.set(key, inputs);
}

function renderFeed(container, events, { follow } = {}) {
  const previous = feeds.get(container);
  if (previous && previous.follow === follow && previous.events.length === events.length &&
      events.every((event, index) => event === previous.events[index])) return;
  feeds.set(container, { events, follow });
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
    if (event.to) meta.append(node("span", "kind", `→ ${event.to === "All" ? "전체" : event.to}`));
    if (event.reply_to) meta.append(node("span", "kind", `↳ #${event.reply_to} 답장`));
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

function renderDiscussions() {
  const query = $("discussion-search").value.trim().toLocaleLowerCase();
  const agents = new Set(["Codex", "Claude", "Gemini"]);
  renderFeed($("discussion-feed"), state.events.filter(event => event.kind === "message" && event.task_id !== "MAIN" && agents.has(event.author) &&
    (agents.has(event.to) || event.to === "All") && eventMatchesFilter(event, "all", query)));
}

function renderTaskList() {
  const focusedKey = document.activeElement?.dataset.taskKey;
  $("task-list").replaceChildren();
  const tasks = state.tasks.slice().sort((a, b) => b.id - a.id);
  $("task-badge").hidden = !tasks.length;
  $("task-badge").textContent = tasks.length;
  if (!tasks.length) { $("task-list").append(node("p", "empty", "등록된 작업이 없습니다.")); return; }
  for (const task of tasks) {
    const card = node("button", "task-card" + (state.selectedTask === task.task_id ? " selected" : ""));
    card.dataset.taskKey = JSON.stringify([task.task_id, task.author]);
    const top = node("div", "task-top");
    top.append(node("strong", "", task.task_id), node("span", `state state-${task.state}`, labels[task.state]));
    card.append(top, node("span", "task-author", `${task.author} 담당`), node("p", "task-body", task.body), node("time", "", time(task.timestamp)));
    if (!inactive.has(task.state) && Date.now() - new Date(task.timestamp).getTime() > 600000) card.append(node("span", "stale", "10분 이상 갱신 없음"));
    card.addEventListener("click", () => { state.selectedTask = task.task_id; renderTasks(); });
    $("task-list").append(card);
    if (card.dataset.taskKey === focusedKey) card.focus({ preventScroll: true });
  }
}

function renderTasks() {
  renderWorker();
  renderChanged("task-list", [state.tasks, state.selectedTask,
    state.tasks.map(task => !inactive.has(task.state) && Date.now() - new Date(task.timestamp).getTime() > 600000).join()], renderTaskList);
  renderChanged("thread", [state.events, state.selectedTask], renderThread);
}

function renderThread() {
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

const agentNames = { opus: "Opus", sol: "Sol", sonnet: "Sonnet", gemini: "Gemini", luna: "Luna", haiku: "Haiku", astra: "Astra", fable: "Fable", mythos: "Mythos" };
const providerNames = { codex: "Codex", claude: "Claude", antigravity: "Gemini · Antigravity" };

function renderPolicy(policy) {
  const box = $("worker-policy");
  box.replaceChildren();
  if (!policy) { box.append(node("p", "empty", "운영 정책 연결 대기")); return; }
  const profiles = new Map((policy.profiles || []).map(profile => [profile.agent, profile]));
  const lead = profiles.get(policy.effective_lead);
  box.append(node("strong", "worker-lead", policy.enabled ? `최종 판단 역할 · ${agentNames[policy.effective_lead] || "미확인"}${lead?.model ? ` (${lead.model})` : ""}` : "계층 운영 미적용"));
  if (policy.lead_reason) box.append(node("small", "worker-note", policy.lead_reason));
  const groups = [
    ["상위 판단", ["opus"], "상세 지시·범위 판단 · Sol이 직접 투입 요청"],
    ["주 코딩·문제 해결", ["sol", "sonnet", "gemini"], "구현·일반 장애 처리 · Opus 한도 시 Sol이 최종 판단 대리"],
    ["보조 작업", ["luna", "haiku"], "주 코딩 담당이 작은 작업 단위로 위임"],
    ["고난도 자문", ["astra", "fable", "mythos"], "Opus의 반복 난항 후 Opus가 선택 · 짧은 호출 · 강도 high 이하"],
  ];
  for (const [title, agents, description] of groups) {
    const group = node("section", "worker-role");
    group.append(node("h3", "", title), node("p", "worker-note", description));
    for (const agent of agents) {
      const profile = profiles.get(agent);
      if (!profile) continue;
      const availability = profile.availability === "verified" || profile.verified ? "접근 확인" : profile.availability === "unavailable" ? "접근 불가" : "접근 미확인";
      group.append(node("small", "worker-model", `${agentNames[agent]} · 요청 ${profile.model || "미설정"} · ${profile.effort || "강도 미확인"} · ${profile.enabled ? availability : "사용 중지"}`));
    }
    box.append(group);
  }
  const caps = policy.caps || policy;
  box.append(node("p", "worker-note", `작업당 상한 · 단계 ${caps.max_stages ?? "미확인"} · 실제 호출 ${caps.max_calls ?? "미확인"} · 수정 왕복 ${caps.max_revisions ?? "미확인"}`));
}

function quotaText(quota) {
  if (!quota) return "잔여 사용량 미확인";
  const percent = quota.remaining_percent;
  if (quota.stale && quota.observed_at) return `잔여 사용량 현재 미확인 · 오래된 관측${typeof percent === "number" && Number.isFinite(percent) && percent >= 0 && percent <= 100 ? ` ${percent}%` : ""}`;
  if (typeof percent === "number" && Number.isFinite(percent) && percent >= 0 && percent <= 100) return `관측 잔여 ${percent}%${quota.status === "warning" ? " · 절약 운영" : ""}`;
  return quota.status === "exhausted" ? "사용량 한도 도달 · 잔여 수치 미보고" : "잔여 사용량 미확인";
}

function renderWorker() {
  const data = state.worker;
  $("worker-health").textContent = !data || !data.available ? data?.error || "실행 기록 연결 대기" :
    data.heartbeat_age !== null && data.heartbeat_age < 90 ? `정상 · ${Math.round(data.heartbeat_age)}초 전` : "실행기 확인 필요";
  const waiting = (data?.providers || []).map(provider => provider.until_at * 1000 > Date.now()).join();
  const detail = data ? JSON.stringify([data.available, data.policy, data.providers, data.jobs, data.workflows]) : "";
  renderChanged("worker-detail", [detail, waiting], () => {
    $("worker-policy").replaceChildren();
    $("worker-providers").replaceChildren();
    $("worker-jobs").replaceChildren();
    if (!data?.available) return;
    renderPolicy(data.policy);
    for (const provider of data.providers || []) {
      const card = node("div", "worker-provider");
      const held = provider.until_at * 1000 > Date.now();
      const quota = provider.quota;
      card.append(node("strong", "", providerNames[provider.name] || provider.name), node("small", "quota-value", quotaText(quota)));
      for (const window of quota?.windows || []) {
        const percent = window.remaining_percent;
        if (typeof percent !== "number" || !Number.isFinite(percent) || percent < 0 || percent > 100) continue;
        const minutes = window.window_minutes;
        const label = { "Weekly Limit Remaining": "주간", "Daily Limit Remaining": "일간", "Session Limit Remaining": "세션" }[window.window] ||
          (minutes > 0 ? minutes % 1440 === 0 ? `${minutes / 1440}일` : minutes % 60 === 0 ? `${minutes / 60}시간` : `${minutes}분` : "사용량 창");
        card.append(node("small", "", `${label} · ${percent}%${quota.stale ? " (이전 관측)" : " 남음"}${window.reset_at ? ` · 리셋 ${time(window.reset_at * 1000)}` : ""}`));
      }
      if (quota?.observed_at) card.append(node("small", "", `관측 ${time(quota.observed_at * 1000)}${quota.stale ? " · 갱신 필요" : ""}`));
      if (quota?.reset_at) card.append(node("small", "", `관측 리셋 ${time(quota.reset_at * 1000)}`));
      card.append(node("small", "", held ? `호출 재개 예정 ${time(provider.until_at * 1000)}` : "호출 제한 대기 없음"));
      if (held && provider.reason) card.append(node("small", "", provider.reason));
      $("worker-providers").append(card);
    }
    const flowLabels = { active: "진행", waiting: "단계 대기", ready: "검토 완료·통합 대기", needs_attention: "확인 필요", paused: "검증 대기", closed: "이전 구성 기록" };
    const phaseLabels = { plan: "상위 지시", implement: "구현", review: "검토", revise: "수정", judge: "최종 판단", request_opus: "Opus 직접 투입 요청", intervene: "Opus 직접 해결", auxiliary: "보조 작업", arbitrate: "최종 판단", consult: "고난도 자문" };
    for (const flow of data.workflows || []) {
      const row = node("button", "worker-job");
      row.append(node("strong", "", flow.id), node("small", "", `${flowLabels[flow.state] || "상태 미확인"} · ${flow.summary || ""}`));
      const progress = [];
      if (flow.phase) progress.push(`단계 ${phaseLabels[flow.phase] || flow.phase}`);
      if (flow.stage_count !== undefined) progress.push(`진행 ${flow.stage_count}단계`);
      if (flow.call_count !== undefined) progress.push(`실제 호출 ${flow.call_count}회`);
      if (progress.length) row.append(node("small", "", progress.join(" · ")));
      row.addEventListener("click", () => { state.selectedTask = flow.id; renderTasks(); });
      $("worker-jobs").append(row);
    }
    const descriptions = { running: "실행 중", queued: "대기", waiting_quota: "한도 대기", waiting_service: "모델 용량 대기", waiting_budget: "호출 예산 대기", needs_attention: "확인 필요", orphan_running: "이전 실행 확인 필요", paused: "일시 중지", completed: "완료", closed: "확인 완료", expired: "기한 종료" };
    const rank = { running: 0, needs_attention: 1, orphan_running: 1, waiting_quota: 2, waiting_service: 2, queued: 3, paused: 4, completed: 5, closed: 6, expired: 6 };
    const jobs = [...(data.jobs || [])].sort((a, b) => (rank[a.state] ?? 9) - (rank[b.state] ?? 9) || b.updated - a.updated);
    for (const job of jobs.filter(job => !["completed", "closed", "expired"].includes(job.state))) {
      const row = node("button", "worker-job");
      const top = node("div", "task-top");
      top.append(node("strong", "", job.title), node("span", "state", descriptions[job.state] || "확인 필요"));
      const schedule = job.state === "running" ? `시작 ${time(job.updated * 1000)}` : job.next_at > 0 ? `다음 시도 ${time(job.next_at * 1000)}` : "할당 대기";
      row.append(top, node("small", "", `${agentNames[job.agent] || providerNames[job.provider] || job.provider} · ${job.task_id} · ${schedule}`));
      row.append(node("small", "", `요청 ${job.model || "모델 미확인"} · ${job.effort || "강도 미확인"}`));
      row.append(node("small", "", `응답 모델 ${(job.observed_models || []).join(", ") || "미보고"}`));
      if (job.error && job.state !== "running") row.append(node("small", "worker-diagnostic", job.error));
      row.addEventListener("click", () => { state.selectedTask = job.task_id; renderTasks(); });
      $("worker-jobs").append(row);
    }
  });
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
  for (const author of ["Claude", "Codex", "Gemini", "User", "System"]) {
    const ownEvents = state.events.filter(event => event.author === author);
    const last = ownEvents[ownEvents.length - 1];
    const activeTask = state.tasks.slice().reverse().find(task => task.author === author && activeTaskStates.has(task.state));
    const recentlyActive = last && Date.now() - new Date(last.timestamp).getTime() < 600000;
    const member = node("article", "member");
    const avatarRow = node("div", "member-top");
    avatarRow.append(node("span", `avatar avatar-${author.toLowerCase()}`, author[0]), node("span", `member-dot ${recentlyActive ? "online" : "idle"}`));
    member.append(avatarRow, node("strong", "", author));
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
  const sheet = data.sheet || {};
  const sheetTime = new Date(sheet.fetched_at).toLocaleTimeString("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false });
  const basis = sheet.source === "sheet" && !sheet.error ? `시트 기준 ${sheetTime}` : "저장소 스냅샷 기준";
  const basisNode = $("wbs-as-of-small");
  basisNode.replaceChildren(document.createTextNode(basis));
  if (sheet.url && /^https?:\/\//i.test(sheet.url)) {
    const link = node("a", "", "시트");
    link.href = sheet.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    basisNode.append(document.createTextNode(" · "), link);
  }
  $("wbs-audit-time").textContent = "현장 조회 " + time(data.audit_as_of);
  $("wbs-badge").hidden = false;
  $("wbs-badge").textContent = data.summary.total - data.summary.complete;
  $("wbs-goals").replaceChildren();
  const goalSelect = $("wbs-goal-filter");
  const selectedGoal = goalSelect.value;
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
  goalSelect.value = selectedGoal;
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
  if (document.hidden) return;
  $("task-badge").hidden = !state.tasks.length;
  $("task-badge").textContent = state.tasks.length;
  $("run-badge").hidden = !state.runs.length;
  $("run-badge").textContent = state.runs.length;
  if (state.wbs) {
    $("wbs-badge").hidden = false;
    $("wbs-badge").textContent = state.wbs.summary.total - state.wbs.summary.complete;
  }
  renderChanged("members", [state.events, state.tasks,
    state.events.map(event => Date.now() - new Date(event.timestamp).getTime() < 600000).join()], renderMembers);
  if (state.channel === "overview") renderChanged("overview", [state.events, state.tasks, state.wbs], renderOverview);
  if (state.channel === "discussions") renderChanged("discussions", [state.events], renderDiscussions);
  if (state.channel === "tasks") renderChanged("tasks", [state.events, state.tasks, state.worker, state.selectedTask,
    state.tasks.map(task => !inactive.has(task.state) && Date.now() - new Date(task.timestamp).getTime() > 600000).join()], renderTasks);
  if (state.channel === "runs") renderChanged("runs", [state.runs], renderRuns);
  if (state.channel === "checks") renderChanged("checks", [state.events], renderChecks);
  if (state.channel === "wbs") renderChanged("wbs", [state.wbs], renderWbs);
}
function setChannel(channel) {
  state.channel = channel;
  window.history?.replaceState(null, "", channel === "discussions" ? "#discussions" : "#" + channel);
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
  if (document.hidden || polling) return;
  clearTimeout(pollTimer);
  polling = true;
  try {
    const response = await fetch(`/api/events?after=${state.cursor}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!document.hidden) {
      const runsResponse = await fetch("/api/runs", { cache: "no-store" });
      if (runsResponse.ok) updateSnapshot("runs", (await runsResponse.json()).runs);
    }
    try {
      if (!document.hidden) {
        const workerResponse = await fetch("/api/worker", { cache: "no-store" });
        updateSnapshot("worker", workerResponse.ok ? await workerResponse.json() : null);
      }
    } catch (_) { updateSnapshot("worker", null); }
    try {
      if (!document.hidden) {
        const wbsResponse = await fetch("/api/wbs", { cache: "no-store" });
        if (wbsResponse.ok) updateSnapshot("wbs", await wbsResponse.json());
      }
    } catch (_) { /* WBS is a secondary panel; events/runs still render if it is unavailable */ }
    if (data.cursor < state.cursor) state.events = [];
    const ids = new Set(state.events.map(event => event.id));
    const additions = data.events.filter(event => !ids.has(event.id));
    if (additions.length) state.events = state.events.concat(additions).slice(-1000);
    state.cursor = data.cursor;
    updateSnapshot("tasks", data.tasks);
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
    polling = false;
    if (!document.hidden) pollTimer = setTimeout(poll, 2000);
  }
}

function updateSnapshot(key, value) {
  if (JSON.stringify(state[key]) !== JSON.stringify(value)) state[key] = value;
}

document.addEventListener("visibilitychange", () => {
  clearTimeout(pollTimer);
  if (!document.hidden) { render(); poll(); }
});

for (const button of document.querySelectorAll(".channel")) button.addEventListener("click", () => setChannel(button.dataset.channel));
for (const button of document.querySelectorAll("[data-goto]")) button.addEventListener("click", () => setChannel(button.dataset.goto));
["overview-author", "overview-search", "follow"].forEach(id => $(id).addEventListener("input", renderOverview));
$("discussion-search").addEventListener("input", renderDiscussions);
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
