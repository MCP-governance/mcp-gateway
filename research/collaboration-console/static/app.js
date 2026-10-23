"use strict";
const $ = id => document.getElementById(id);
const state = { cursor: 0, events: [], tasks: [], runs: [], worker: null, wbs: null, backlog: null, connected: false, channel: ["overview", "discussions", "wbs", "tasks", "runs", "checks"].includes(window.location?.hash?.slice(1)) ? window.location.hash.slice(1) : "overview", selectedTask: null };
const labels = { queued: "대기열", running: "작업 중", waiting: "응답 대기", completed: "완료", passed: "통과", failed: "실패", blocked: "차단됨", cancelled: "중단됨" };
const outcomes = { waiting_quota:"한도 회복 대기", waiting_budget:"사용량·예비량 대기", waiting_service:"제공자 복구 대기", needs_attention:"확인 필요", expired:"기한 종료", closed:"확인 완료", paused:"일시 중지", orphan_running:"이전 실행 확인 필요", running: "실행 중", completed: "완료", turn_error: "턴 오류", usage_limit: "사용량 한도", task_failed: "작업 실패", model_mismatch: "모델 불일치", cancelled: "중단됨" };
const modelChecks = { confirmed: "응답 모델 확인됨", mismatch: "응답 모델 불일치", unreported: "응답 모델 미보고" };
const kinds = { message: "메시지", task: "작업 상태", check: "검증" };
const inactive = new Set(["completed", "passed", "failed", "blocked", "cancelled"]);
const activeTaskStates = new Set(["queued", "running", "waiting", "waiting_quota", "waiting_service", "waiting_budget"]);
Object.assign(labels, {waiting_quota:"한도 회복 대기", waiting_service:"제공자 복구 대기", waiting_budget:"사용량·예비량 대기", needs_attention:"확인 필요", closed:"확인 완료", expired:"기한 종료", paused:"일시 중지", unverified:"과거 상태·현재 미확인"});
function currentTasks() {
  const tasks = new Map();
  for (const task of state.tasks.slice().sort((a,b) => new Date(a.timestamp) - new Date(b.timestamp))) { const value = {...task, author:task.author === "System" && ["Claude","Codex","Gemini"].includes(task.to) ? task.to : task.author}; tasks.set(task.task_id, activeTaskStates.has(task.state) && Date.now() - new Date(task.timestamp) > 600000 ? {...value, state:"unverified"} : value); }
  for (const job of [...(state.worker?.jobs || [])].sort((a,b) => a.updated - b.updated)) {
    if (job.phase === "communication") continue;
    tasks.set(job.task_id, {id:job.updated, task_id:job.task_id, author:providerNames[job.provider] || job.provider, state:job.state, body:job.title, timestamp:new Date(job.updated * 1000).toISOString(), managed:true});
  }
  for (const job of state.worker?.jobs || []) {
    if (job.phase === "communication" || !activeTaskStates.has(job.state)) continue;
    const current = tasks.get(job.task_id);
    if (current?.state === "running") continue;
    tasks.set(job.task_id, {...current, state:job.state, author:providerNames[job.provider] || job.provider, timestamp:new Date(job.updated * 1000).toISOString()});
  }
  return [...tasks.values()];
}
const rendered = new Map();
const feeds = new WeakMap();
let pollTimer, polling = false;
const CHANNEL_META = {
  overview: { title: "개요", topic: "현재 실행·대기·사용량과 최근 공유 기록" },
  discussions: { title: "에이전트 협의", topic: "작업 결과·질문 → 자동 인계 → 실제 응답·추가 질문. 수신자·답장 번호·대기 사유를 확인합니다." },
  wbs: { title: "WBS", topic: "목표 G01–G10의 구현·회귀·배포·실제환경·검수 근거별 진척입니다." },
  tasks: { title: "작업·에이전트", topic: "실제 실행 큐 · 역할·사용량 · 작업별 기록" },
  runs: { title: "실행 기록", topic: "직접 호출·자동 실행의 요청 모델, 관측 응답, 결과 · 미관측 항목은 구분 표시" },
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
  const entries = new Map();
  feeds.set(container, { events, follow, entries });
  const previousScroll = container.scrollTop;
  const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 90;
  container.replaceChildren();
  if (!events.length) {
    container.append(node("div", "empty", "표시할 기록이 없습니다."));
    return;
  }
  for (const event of events) {
    const existing = previous?.entries?.get(event.id);
    if (existing?.event === event) { container.append(existing.entry); entries.set(event.id, existing); continue; }
    const entry = node("article", `event event-${event.author.toLowerCase()}`);
    const avatar = node("span", `avatar avatar-${event.author.toLowerCase()}`, event.author[0]);
    const body = node("div", "event-body-wrap");
    const meta = node("div", "event-meta");
    meta.append(node("strong", "author", event.author), node("span", "kind", kinds[event.kind]), node("span", `state state-${event.state}`, labels[event.state]), node("time", "", time(event.timestamp)));
    if (event.to) meta.append(node("span", "kind", `→ ${event.to === "All" ? "전체" : event.to}`));
    if (event.reply_to) meta.append(node("span", "kind", `↳ #${event.reply_to} 답장`));
    const reference = node("button", "task-reference link-button", event.task_id);
    reference.addEventListener("click", () => { state.selectedTask = event.task_id; setChannel("tasks"); });
    body.append(meta, reference, eventBody(event.body));
    entry.append(avatar, body);
    container.append(entry);
    entries.set(event.id, {event, entry});
  }
  if (follow === false) { container.scrollTop = previousScroll; return; }
  if ((follow === undefined && nearBottom) || follow) container.scrollTop = container.scrollHeight;
  else container.scrollTop = previousScroll;
}

function eventBody(text) {
  if (text.length <= 700) return node("p", "event-text", text);
  const details = node("details", "event-expanded");
  details.append(node("summary", "event-text", (text.split("\n").filter(line => line.trim() && !/^(#|시각:|제공자:|역할 모델:|요청 모델:|요청 노력:|응답 모델:|세션:|ACK |CHECKED:|원문:)/.test(line)).join("\n").slice(0, 220) || text.slice(0, 220)) + "… 전체 보기"), node("p", "event-text", text));
  return details;
}

function renderOverview() {
  const tasks = currentTasks();
  const operational = $("operational-status");
  operational.replaceChildren();
  const worker = state.worker;
  operational.append(node("strong", "", worker?.available && worker.heartbeat_age !== null && worker.heartbeat_age < 90 ? "실행기 정상" : "실행기 연결·생존 확인 필요"));
  for (const provider of worker?.providers || []) {
    const jobs = (worker.jobs || []).filter(job => job.provider === provider.name);
    const running = jobs.find(job => job.state === "running");
    const pending = jobs.filter(job => activeTaskStates.has(job.state) && job.state !== "running").length;
    operational.append(node("p", "", `${providerNames[provider.name]} · ${running ? `실행 중: ${running.task_id}` : "자동 실행 없음"} · 대기 ${pending}건 · ${quotaText(provider.quota)}`));
  }
  $("running-count").textContent = tasks.filter(task => task.state === "running").length;
  $("completed-count").textContent = tasks.filter(task => ["completed", "passed"].includes(task.state)).length;
  $("attention-count").textContent = tasks.filter(task => ["failed", "blocked", "needs_attention", "waiting"].includes(task.state)).length;
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
  const latest = new Map();
  for (const row of [...(state.worker?.handoffs || [])].sort((a,b) => b.updated - a.updated)) { const key = row.root || row.request; if (!latest.has(key)) latest.set(key, row); }
  const rows = [...latest.values()].filter(row => !query || row.task.toLocaleLowerCase().includes(query)).sort((a,b) => Number(a.state === "done") - Number(b.state === "done") || b.updated - a.updated);
  renderChanged("discussion-status", [JSON.stringify(rows)], () => {
    const panel = $("discussion-status"); panel.replaceChildren(node("h2", "", "자동 협의 상태"));
    if (state.worker?.handoffs_truncated) panel.append(node("p", "", `협의 ${state.worker.handoffs_truncated}건은 조회 상한을 넘어 생략됨`));
    if (!rows.length) panel.append(node("p", "", "새 작업 결과 또는 응답 요청을 기다립니다."));
    const status = {done:"응답 완료",forwarded:"다음 단계로 전달",blocked:"확인 필요",delayed:"미응답 5분 경과",queued:"응답 대기",running:"응답 작성 중",waiting_budget:"사용량·예비량 대기",waiting_quota:"한도 회복 대기",waiting_service:"제공자 복구 대기"};
    for (const row of rows.slice(0,8)) panel.append(node("p", "", `${row.task} · ${row.model || row.provider} · ${status[row.state] || status[row.job_state] || "확인 필요"} · 응답 ${row.round}/4`));
  });
  renderFeed($("discussion-feed"), state.events.filter(event => event.kind === "message" && event.task_id !== "MAIN" &&
    (agents.has(event.author) || (event.author === "System" && event.source_id?.startsWith("handoff-"))) &&
    (agents.has(event.to) || event.to === "All") && eventMatchesFilter(event, "all", query)));
}

function renderTaskList() {
  const focusedKey = document.activeElement?.dataset.taskKey;
  $("task-list").replaceChildren();
  const query = $("task-search").value.trim().toLocaleLowerCase(), status = $("task-status").value;
  const tasks = currentTasks().filter(task => (!query || `${task.task_id} ${task.author} ${task.body}`.toLocaleLowerCase().includes(query)) && (!status || (status === "active" ? activeTaskStates.has(task.state) : status === "attention" ? ["failed","blocked","needs_attention","orphan_running"].includes(task.state) : ["completed","passed","closed"].includes(task.state)))).sort((a,b) => new Date(b.timestamp) - new Date(a.timestamp));
  $("task-result-count").textContent = `${tasks.length}개 작업`;

  if (!tasks.length) { $("task-list").append(node("p", "empty", "등록된 작업이 없습니다.")); return; }
  for (const task of tasks) {
    const card = node("button", "task-card" + (state.selectedTask === task.task_id ? " selected" : ""));
    card.dataset.taskKey = JSON.stringify([task.task_id, task.author]);
    const top = node("div", "task-top");
    top.append(node("strong", "", task.task_id), node("span", `state state-${task.state}`, labels[task.state]));
    card.append(top, node("span", "task-author", `${task.author} 담당`), node("p", "task-body", task.body.split("\n")[0].slice(0, 220)), node("time", "", time(task.timestamp)));
    if (activeTaskStates.has(task.state) && Date.now() - new Date(task.timestamp).getTime() > 600000) card.append(node("span", "stale", "10분 이상 갱신 없음"));
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
    if (data.workflows_truncated) $("worker-jobs").append(node("p", "notice", `진행 흐름 ${data.workflows_truncated}건은 조회 상한을 넘어 생략됨`));
    if (data.jobs_truncated) $("worker-jobs").append(node("p", "notice", `진행·대기 작업 ${data.jobs_truncated}건은 화면 상한을 넘어 생략됨`));
    renderPolicy(data.policy);
    for (const provider of data.providers || []) {
      const card = node("div", "worker-provider");
      const held = provider.until_at * 1000 > Date.now();
      const quota = provider.quota;
      card.append(node("strong", "", providerNames[provider.name] || provider.name), node("small", "quota-value", Object.keys(provider.quota_groups || {}).length ? "모델 묶음별 사용량" : quotaText(quota)));
      for (const [group,value] of Object.entries(provider.quota_groups || {})) card.append(node("small", "", `${group === "Gemini Models" ? "Gemini 묶음" : "Claude·GPT 묶음"} · ${quotaText(value)}${value.reset_at ? ` · 회복 ${time(value.reset_at * 1000)}` : ""}${value.observed_at ? ` · 관측 ${time(value.observed_at * 1000)}` : ""}`));
      for (const window of Object.keys(provider.quota_groups || {}).length ? [] : quota?.windows || []) {
        const percent = window.remaining_percent;
        if (typeof percent !== "number" || !Number.isFinite(percent) || percent < 0 || percent > 100) continue;
        const minutes = window.window_minutes;
        const label = { "Weekly Limit Remaining": "주간", "Daily Limit Remaining": "일간", "Session Limit Remaining": "세션" }[window.window] ||
          (minutes > 0 ? minutes % 1440 === 0 ? `${minutes / 1440}일` : minutes % 60 === 0 ? `${minutes / 60}시간` : `${minutes}분` : "사용량 창");
        card.append(node("small", "", `${label} · ${percent}%${quota.stale ? " (이전 관측)" : " 남음"}${window.reset_at ? ` · 리셋 ${time(window.reset_at * 1000)}` : ""}`));
      }
      if (!Object.keys(provider.quota_groups || {}).length && quota?.observed_at) card.append(node("small", "", `관측 ${time(quota.observed_at * 1000)}${quota.stale ? " · 갱신 필요" : ""}`));
      if (!Object.keys(provider.quota_groups || {}).length && quota?.reset_at) card.append(node("small", "", `관측 리셋 ${time(quota.reset_at * 1000)}`));
      card.append(node("small", "", held ? `호출 재개 예정 ${time(provider.until_at * 1000)}` : quota?.stale ? "실시간 한도 미확인" : quota?.remaining_percent === 0 || quota?.status === "exhausted" ? "사용량 소진 · 회복 대기" : "추가 호출 대기 없음"));
      if (held && provider.reason) card.append(node("small", "", provider.reason));
      $("worker-providers").append(card);
    }
    const flowLabels = { active: "진행", waiting: "단계 대기", ready: "검토 완료·통합 대기", needs_attention: "확인 필요", paused: "검증 대기", closed: "이전 구성 기록" };
    const phaseLabels = { plan: "상위 지시", implement: "구현", review: "검토", revise: "수정", judge: "최종 판단", request_opus: "Opus 직접 투입 요청", intervene: "Opus 직접 해결", auxiliary: "보조 작업", arbitrate: "최종 판단", consult: "고난도 자문" };
    for (const flow of (data.workflows || []).filter(flow => !["closed", "ready"].includes(flow.state))) {
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
    const rank = { running: 0, needs_attention: 1, orphan_running: 1, waiting_quota: 1, waiting_service: 1, waiting_budget: 1, queued: 3, paused: 4, completed: 5, closed: 6, expired: 6 };
    const jobs = [...(data.jobs || [])].sort((a, b) => (rank[a.state] ?? 9) - (rank[b.state] ?? 9) || b.updated - a.updated);
    for (const job of jobs.filter(job => !["completed", "closed", "expired", "paused"].includes(job.state))) {
      const row = node("button", "worker-job");
      const top = node("div", "task-top");
      top.append(node("strong", "", job.title), node("span", "state", descriptions[job.state] || "확인 필요"));
      const schedule = job.state === "running" ? `시작 ${time(job.updated * 1000)}` : job.next_at * 1000 > Date.now() ? `다음 시도 ${time(job.next_at * 1000)}` : activeTaskStates.has(job.state) ? "선행 조건·할당 대기" : "재개 전 확인 필요";
      row.append(top, node("small", "", `${agentNames[job.agent] || providerNames[job.provider] || job.provider} · ${job.task_id} · ${schedule}`));
      row.append(node("small", "", `요청 ${job.model || "모델 미확인"} · ${job.effort || "강도 미확인"}`));
      row.append(node("small", "", `응답 모델 ${(job.observed_models || []).join(", ") || "미보고"}`));
      if (job.error && job.state !== "running") row.append(node("small", "worker-diagnostic", diagnostic(job.error)));
      row.addEventListener("click", () => { state.selectedTask = job.task_id; renderTasks(); });
      $("worker-jobs").append(row);
    }
  });
}

function diagnostic(error) {
  if (/max_turns|maximum number of turns/i.test(error)) return "응답 턴 상한 도달 · 실행 기록에서 상세 확인";
  if (/quota|usage.limit|rate.limit/i.test(error)) return "사용량 제한 · 회복 시각과 재개 상태 확인";
  if (/timeout|timed out/i.test(error)) return "실행 시간 초과 · 부분 결과 확인 필요";
  if (/capacity|overloaded/i.test(error)) return "제공자 용량 부족 · 재시도 대기";
  if (/\{[\s\S]*["'][a-z_]+["']\s*:/.test(error)) return "CLI 오류 · 실행 기록에서 상세 확인";
  return error.length > 180 ? error.slice(0, 180) + "…" : error;
}

function gatewayText(run) {
  const gateway = run.gateway || {};
  if (gateway.state === "recorded") return `게이트웨이 기록 ${gateway.count}건`;
  if (gateway.state !== "none") return "게이트웨이 기록 미확인";
  return run.tool_calls === null ? "게이트웨이 기록 없음 · 도구 호출 수 미관측" : run.tool_calls > 0 ? "게이트웨이 기록 없음 · 호출은 있었음" : "게이트웨이 기록 없음 · 호출 자체가 없음";
}
function renderRuns() {
  $("run-badge").hidden = !state.runs.length;
  $("run-badge").textContent = state.runs.length;
  $("runs").replaceChildren();
  if (!state.runs.length) { $("runs").append(node("p", "empty", "기록된 실행이 없습니다.")); return; }
  const query = $("run-search").value.trim().toLocaleLowerCase(), status = $("run-status").value;
    const runs = state.runs.filter(run => (!query || `${run.task_id} ${run.agent} ${run.requested?.model}`.toLocaleLowerCase().includes(query)) && (!status || (status === "attention" ? !["completed", "running"].includes(run.outcome) : run.outcome === status))).sort((a,b) => new Date(b.updated_at) - new Date(a.updated_at));
    $("run-result-count").textContent = `${runs.length} / ${state.runs.length}건`;
    if (!runs.length) $("runs").append(node("p", "empty", "조건에 맞는 실행이 없습니다."));
    runs.forEach(run => {
    const card = node("article", `run-card run-${run.outcome}`);
    const top = node("div", "task-top");
    top.append(node("strong", "", `${run.agent} · ${run.task_id}`), node("span", `state run-state-${run.outcome}`, outcomes[run.outcome] || run.outcome));
    if (run.title) card.append(node("p", "task-body", run.title));
    const requested = run.requested || {};
    const observed = run.observed || {};
    const answered = [...(observed.models || []), ...(observed.usage_models || []).filter(name => !(observed.models || []).includes(name))];
    card.append(top, node("span", "run-line", `요청 ${requested.model} · 강도 ${requested.effort}`),
      node("span", `run-line model-${run.model_check}`, `${answered.length ? `응답 ${answered.join(", ")}` : "응답 모델 없음"} · ${modelChecks[run.model_check]}`));
    if (run.applied) card.append(node("span", "run-line", `턴에 적용된 값 ${run.applied.model || "—"} · ${run.applied.effort || "—"}`));
    if (run.usage && (run.usage.input_tokens > 0 || run.usage.output_tokens > 0 || run.source !== "durable_worker")) card.append(node("span", "run-line", `토큰 입력 ${run.usage.input_tokens ?? "—"} · 출력 ${run.usage.output_tokens ?? "—"}`));
    else if (run.source === "durable_worker") card.append(node("span", "run-line", "토큰 수 미확인 · 공식 잔여량과 별도"));
    if (run.source === "durable_worker") card.append(node("span", "run-line", "자동 실행 큐 · 시도 합산 관측"));
    if (run.native_session_id) { const detail = node("details", "run-line"); detail.append(node("summary", "", "실행 식별 정보"), node("code", "mono", `세션 ${run.native_session_id}`)); card.append(detail); }
    card.append(node("span", run.no_tool_call ? "run-line flag" : "run-line", run.no_tool_call ? "도구 호출 0건 (NO_TOOL_CALL)" : run.tool_calls === null ? "도구 호출 수 미관측" : `도구 호출 ${run.tool_calls}건`),
      node("span", run.gateway && run.gateway.state === "none" && run.tool_calls > 0 ? "run-line flag" : "run-line", gatewayText(run)));
    if (run.error) { const detail = node("details", "run-diagnostic"); detail.append(node("summary", "", diagnostic(run.error.message || run.error.code)), node("p", "event-text", run.error.message || run.error.code)); card.append(detail); }
    card.append(node("time", "", time(run.updated_at)));
    $("runs").append(card);
  });
}

function renderChecks() {
  const author = $("checks-author").value, query = $("checks-search").value.trim().toLocaleLowerCase();
  const events = state.events.filter(event => event.kind === "check" && !event.body.startsWith("실행 전 인계 전달") && eventMatchesFilter(event, author, query));
  renderFeed($("checks-feed"), events);
}

function renderMembers() {
  const box = $("members");
  box.replaceChildren();
  for (const author of ["Claude", "Codex", "Gemini"]) {
    const ownEvents = state.events.filter(event => event.author === author);
    const last = ownEvents[ownEvents.length - 1];
    const provider = {Codex:"codex", Claude:"claude", Gemini:"antigravity"}[author];
    const activeTask = (state.worker?.jobs || []).find(job => job.provider === provider && job.state === "running");
    const waiting = (state.worker?.jobs || []).filter(job => job.provider === provider && activeTaskStates.has(job.state)).length;
    const recentlyActive = last && Date.now() - new Date(last.timestamp).getTime() < 600000;
    const member = node("article", "member");
    const avatarRow = node("div", "member-top");
    avatarRow.append(node("span", `avatar avatar-${author.toLowerCase()}`, author[0]), node("span", `member-dot ${recentlyActive ? "online" : "idle"}`));
    member.append(avatarRow, node("strong", "", author));
    member.append(node("small", "", activeTask ? `자동 실행: ${activeTask.task_id}` : waiting ? `대기 ${waiting}건` : provider ? "자동 실행 없음" : "공유 기록"));
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
    (!query || [row.id, row.title, data.goals.find(goal => goal.id === row.goal_id)?.title || "", row.known_gap, row.backlog_id || "", ...(row.pol_ids || []), ...(row.source_pac_ids || [])].join(" ").toLowerCase().includes(query)) &&
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
  const basis = sheet.source === "sheet" && !sheet.error ? `시트 조회 ${sheetTime}` : `저장소 스냅샷 ${data.audit_as_of ? time(data.audit_as_of) : "시각 미확인"}${sheet.error ? " · 시트 동기화 실패" : ""}`;
  const basisNode = $("wbs-as-of-small");
  basisNode.replaceChildren(document.createTextNode(basis));
  if (sheet.url && /^https?:\/\//i.test(sheet.url)) {
    const link = node("a", "", "시트");
    link.href = sheet.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    basisNode.append(document.createTextNode(" · "), link);
  }
  $("wbs-audit-time").textContent = "현장 근거 기준 " + time(data.audit_as_of);
  const age = Math.floor((Date.now() - new Date(data.audit_as_of)) / 86400000);
  $("wbs-freshness").hidden = !(age > 1 || sheet.error);
  $("wbs-freshness").textContent = `${age > 1 ? `현장 근거 ${age}일 경과 · 시트 조회 시각과 실제 검증 시각은 다릅니다.` : ""}${sheet.error ? " 시트 동기화 실패 · 저장된 자료 표시 중" : ""}`;
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

function renderBacklog() {
  const box = $("backlog-rows"); box.replaceChildren();
  if (!state.backlog) { box.append(node("p", "empty", "개발 목록 조회 중 · 조회 실패는 상단 알림에서 확인")); return; }
  const query = $("backlog-search").value.trim().toLocaleLowerCase();
  const rows = state.backlog.filter(row => !query || Object.values(row).join(" ").toLocaleLowerCase().includes(query));
  $("backlog-count").textContent = `${rows.length} / ${state.backlog.length}개`;
  for (const row of rows) {
    const entry = node("details", "backlog-entry");
    entry.append(node("summary", "", `${row.ID} · ${row["작업"]} · ${row["상태"] || "상태 미확인"}`),
      section("진행", [row["진행"] || "—"]), section("완료 조건", [row["완료 조건"] || "—"]), section("관련 WBS·결정", [row.WBS || "—", row["결정"] || "—"]));
    const evidence = section("근거", []);
    for (const match of (row["근거 자료"] || "").matchAll(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g)) { const link = node("a", "path", match[1]); link.href = match[2]; link.target = "_blank"; link.rel = "noopener noreferrer"; evidence.append(link); }
    entry.append(evidence);
    box.append(entry);
  }
  if (!rows.length) box.append(node("p", "empty", "조건에 맞는 개발 항목이 없습니다."));
}

function updateChannelChrome() {
  const meta = CHANNEL_META[state.channel];
  $("channel-title").textContent = meta.title;
  $("channel-topic").textContent = meta.topic;
  document.title = `#${meta.title} · MINT 개발 현황`;
  for (const button of document.querySelectorAll(".channel")) { const selected = button.dataset.channel === state.channel; button.classList.toggle("selected", selected); button.setAttribute("aria-current", selected ? "page" : "false"); }
  for (const view of document.querySelectorAll(".view")) view.classList.toggle("active", view.id === `view-${state.channel}`);
}
function render() {
  if (document.hidden) return;
  const active = currentTasks().filter(task => activeTaskStates.has(task.state)).length;
  $("task-badge").hidden = !active;
  $("task-badge").textContent = active;
  $("run-badge").hidden = !state.runs.length;
  $("run-badge").textContent = state.runs.length;
  if (state.wbs) {
    $("wbs-badge").hidden = false;
    $("wbs-badge").textContent = state.wbs.summary.total - state.wbs.summary.complete;
  }
  renderChanged("members", [state.events, state.tasks, state.worker,
    state.events.map(event => Date.now() - new Date(event.timestamp).getTime() < 600000).join()], renderMembers);
  if (state.channel === "overview") renderChanged("overview", [state.events, state.tasks, state.wbs, state.worker], renderOverview);
  if (state.channel === "discussions") renderChanged("discussions", [state.events, state.worker], renderDiscussions);
  if (state.channel === "tasks") renderChanged("tasks", [state.events, state.tasks, state.worker, state.selectedTask,
    state.tasks.map(task => !inactive.has(task.state) && Date.now() - new Date(task.timestamp).getTime() > 600000).join()], renderTasks);
  if (state.channel === "runs") renderChanged("runs", [state.runs], renderRuns);
  if (state.channel === "checks") renderChanged("checks", [state.events], renderChecks);
  if (state.channel === "wbs") { renderChanged("wbs", [state.wbs], renderWbs); renderChanged("backlog", [state.backlog], renderBacklog); }
}
function setChannel(channel) {
  state.channel = channel;
  if (!CHANNEL_META[channel]) return;
  if (window.location?.hash !== "#" + channel) window.history?.pushState(null, "", "#" + channel);
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
    let data = await response.json();
    if (data.cursor < state.cursor) {
      const reset = await fetch("/api/events?after=0", {cache:"no-store"});
      if (!reset.ok) throw new Error(`HTTP ${reset.status}`);
      data = await reset.json();
      state.events = [];
    }
    const sourceErrors = [];
    if (!document.hidden) {
      try {
        const runsResponse = await fetch("/api/runs", { cache: "no-store" });
        if (runsResponse.ok) { const snapshot = await runsResponse.json(); updateSnapshot("runs", snapshot.runs); if (snapshot.sources?.durable_worker === "unavailable") sourceErrors.push("자동 실행 기록"); if (snapshot.sources?.cli_log === "unavailable") sourceErrors.push("직접 호출 기록"); }
        else sourceErrors.push("실행 기록");
      } catch (_) { sourceErrors.push("실행 기록"); }
    }
    try {
      if (!document.hidden) {
        const workerResponse = await fetch("/api/worker", { cache: "no-store" });
        if (workerResponse.ok) updateSnapshot("worker", await workerResponse.json());
        else sourceErrors.push("실행기");
      }
    } catch (_) { sourceErrors.push("실행기"); }
    try {
      if (!document.hidden) {
        if (state.channel === "wbs") {
          try { const backlogResponse = await fetch("/api/backlog", {cache:"no-store"}); if (backlogResponse.ok) updateSnapshot("backlog", await backlogResponse.json()); else sourceErrors.push("개발 백로그"); } catch (_) { sourceErrors.push("개발 백로그"); }
        }
        const wbsResponse = await fetch("/api/wbs", { cache: "no-store" });
        if (wbsResponse.ok) updateSnapshot("wbs", await wbsResponse.json());
        else sourceErrors.push("WBS");
      }
    } catch (_) { sourceErrors.push("WBS"); }
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
    $("history-scope").textContent = data.truncated || state.events.length === 1000 ? "최근 1,000개 기록 · 전체 원본 보존" : `공유 기록 ${state.events.length}건`;
    if (sourceErrors.length) notices.push(sourceErrors.join(" · ") + " 조회 실패 — 마지막 성공 자료 표시");
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
["task-search", "task-status"].forEach(id => $(id).addEventListener("input", renderTaskList));
["run-search", "run-status"].forEach(id => $(id).addEventListener("input", renderRuns));
$("refresh").addEventListener("click", () => poll());
window.addEventListener?.("popstate", () => { const channel = window.location.hash.slice(1); state.channel = CHANNEL_META[channel] ? channel : "overview"; updateChannelChrome(); render(); });
document.addEventListener("keydown", event => { if (event.key === "Escape") closeSidebars(); });
$("discussion-search").addEventListener("input", renderDiscussions);
["checks-author", "checks-search"].forEach(id => $(id).addEventListener("input", renderChecks));
["wbs-search", "wbs-goal-filter", "wbs-status-filter"].forEach(id => $(id).addEventListener("input", renderWbsRows));
$("backlog-search").addEventListener("input", renderBacklog);
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
