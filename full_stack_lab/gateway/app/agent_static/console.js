/* MCP Governance Console
 *
 * 이 파일의 규칙 하나: 화면은 권한을 판단하지 않는다. 무엇을 보여줄지는 서버가
 * /api/console에서 이미 걸러서 준다. 여기서 숨기기만 하면 개발자 도구를 여는
 * 순간 통제가 사라진다.
 */

const TOKEN_KEY = "mcp-console-token";
const VERDICTS = ["Allow", "Alert", "Restrict", "Approval", "Block"];
const PAGE_TITLES = {
  overview: "운영 현황", intake: "MCP 도입", verification: "검증", risks: "위험 분석",
  mcpscan: "AI 코드 감사", endpoints: "엔드포인트", termination: "종료·폐기",
  policy: "정책", accounts: "신원", execution: "도구 실행", audit: "감사",
};
const PAGE_GROUPS = [
  ["집행", ["overview", "execution", "audit"]],
  ["도입·검증", ["intake", "verification", "risks", "mcpscan"]],
  ["자산·경로", ["endpoints", "termination"]],
  ["관리", ["policy", "accounts"]],
];

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const token = () => localStorage.getItem(TOKEN_KEY) || "";
const state = {
  console: null, page: null, scan: null, endpoints: null, aig: null,
  seenDecision: 0, chat: [], session: null, findFilter: "all", termCase: null,
};

/* ── 공통 ────────────────────────────────────────────────────────────────── */

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function when(value, withSeconds = false) {
  if (!value) return "-";
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return String(value);
  return at.toLocaleString("ko-KR", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    ...(withSeconds ? { second: "2-digit" } : {}), hour12: false,
  });
}

function clock(value) {
  if (!value) return "--:--:--";
  const at = new Date(value);
  return Number.isNaN(at.getTime()) ? "--:--:--"
    : at.toLocaleTimeString("ko-KR", { hour12: false });
}

function toast(message, tone = "good") {
  const node = document.createElement("div");
  node.className = "toast";
  node.dataset.tone = tone;
  node.textContent = message;
  $("#toasts").append(node);
  setTimeout(() => node.remove(), tone === "bad" ? 7000 : 4000);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "content-type": "application/json",
      authorization: "Bearer " + token(),
      ...(options.headers || {}),
    },
  });
  if (response.status === 401) {
    localStorage.removeItem(TOKEN_KEY);
    location.href = "/login";
    throw new Error("unauthenticated");
  }
  const text = await response.text();
  let body = {};
  try { body = text ? JSON.parse(text) : {}; } catch { body = { detail: text }; }
  if (!response.ok) throw new Error(body.detail || `요청이 거절됐습니다 (HTTP ${response.status})`);
  return body;
}

function verdictTag(value) {
  return `<span class="verdict" data-v="${esc(value)}">${esc(value || "-")}</span>`;
}

function tag(text, tone = "") {
  return `<span class="tag"${tone ? ` data-tone="${tone}"` : ""}>${esc(text)}</span>`;
}

function figure(label, value, note = "", tone = "") {
  return `<div class="figure"${tone ? ` data-tone="${tone}"` : ""}>
    <dt>${esc(label)}</dt><dd>${esc(value)}</dd>
    ${note ? `<small>${esc(note)}</small>` : ""}</div>`;
}

function emptyRow(message, span = 6) {
  return `<tr><td class="empty" colspan="${span}">${esc(message)}</td></tr>`;
}

function fill(node, html, emptyText) {
  if (!node) return;
  node.innerHTML = html || `<p class="empty">${esc(emptyText || "표시할 항목이 없습니다.")}</p>`;
}

/* ── 이동 ────────────────────────────────────────────────────────────────── */

function buildRail(pages) {
  const badges = pageBadges();
  const html = PAGE_GROUPS.map(([label, keys]) => {
    const items = keys.filter((key) => pages.includes(key));
    if (!items.length) return "";
    return `<div class="rail-group"><span>${esc(label)}</span></div>` + items.map((key) =>
      `<a href="#${key}" data-page="${key}">${esc(PAGE_TITLES[key])}<em>${esc(badges[key] || "")}</em></a>`).join("");
  }).join("");
  $("#rail").innerHTML = html;
}

function pageBadges() {
  const data = state.console;
  if (!data) return {};
  const badges = {};
  const approvals = (data.approvals || []).length;
  if (approvals) badges.overview = String(approvals);
  const overdue = (data.termination?.cases || []).filter((c) => c.overdue).length;
  if (overdue) badges.termination = String(overdue);
  const shadow = data.endpoints?.coverage?.shadow || 0;
  const listeners = (data.endpoints?.listeners || []).filter((l) => l.classification === "shadow").length;
  if (shadow + listeners) badges.endpoints = String(shadow + listeners);
  return badges;
}

function show(page) {
  const pages = state.console?.viewer?.pages || [];
  const target = pages.includes(page) ? page : pages[0];
  if (!target) return;
  state.page = target;
  $$(".view").forEach((view) => view.classList.toggle("on", view.dataset.view === target));
  $$("#rail a").forEach((link) =>
    link.setAttribute("aria-current", link.dataset.page === target ? "page" : "false"));
  if (location.hash.slice(1) !== target) history.replaceState(null, "", "#" + target);
  document.title = `${PAGE_TITLES[target]} · MCP Governance`;
  if (target === "mcpscan") loadScan();
  if (target === "endpoints") loadEndpoints();
  if (target === "risks") loadRiskCatalog();
}

/* ── 상단 ────────────────────────────────────────────────────────────────── */

function renderTop() {
  const data = state.console;
  const viewer = data.viewer;
  $("#who-name").textContent = viewer.name;
  $("#who-role").textContent = `${viewer.role_label} · ${viewer.department}`;

  const health = data.health || {};
  const wire = $("#wire");
  wire.dataset.state = health.status === "ok" ? "ok" : health.status ? "degraded" : "down";
  const down = Object.entries(health.components || {})
    .filter(([key, value]) => value === false && key !== "github_mcp").map(([key]) => key);
  $("b", wire).textContent = down.length ? `저하 · ${down.join(", ")}` : "정상";

  const mode = data.monitor?.enforcement;
  const tagNode = $("#mode-tag");
  if (mode) {
    tagNode.hidden = false;
    tagNode.textContent = mode === "enforce" ? "집행" : "관찰";
    tagNode.dataset.tone = mode === "enforce" ? "good" : "warn";
  } else {
    tagNode.hidden = true;
  }
}

/* ── 운영 현황 ───────────────────────────────────────────────────────────── */

function renderOverview() {
  const data = state.console;
  const decisions = data.decisions || [];
  const blocked = decisions.filter((d) => d.decision === "Block").length;
  const unconfirmed = decisions.filter((d) => d.upstream_attempted && !d.upstream_executed
    && d.decision !== "Block").length;

  fill($("#figures"), [
    figure("최근 판정", decisions.length, "게이트웨이를 지난 호출"),
    figure("차단", blocked, "실행 전 거부", blocked ? "bad" : ""),
    figure("대기 승인", (data.approvals || []).length, "사람의 결정이 필요",
      (data.approvals || []).length ? "warn" : ""),
    figure("upstream 실행", data.upstream_effect_count ?? 0, "실제로 닿은 호출"),
    figure("실행 여부 미확인", unconfirmed, "응답 유실 — 성공으로 세지 않음",
      unconfirmed ? "warn" : ""),
  ].join(""));

  // 배너: 지금 사람이 해야 할 일이 있으면 그것만 말한다.
  const notes = [];
  if ((data.approvals || []).length) {
    notes.push(`승인 대기 ${data.approvals.length}건이 있습니다.`);
  }
  const overdue = (data.termination?.cases || []).filter((c) => c.overdue).length;
  if (overdue) notes.push(`기한을 넘긴 종료 케이스 ${overdue}건이 있습니다.`);
  if (data.monitor?.enforcement === "monitor") {
    notes.push(`관찰 모드입니다. 지난 주 ${data.monitor.would_have_stopped ?? 0}건이 집행 모드였다면 막혔습니다.`);
  }
  const banner = $("#banner");
  banner.innerHTML = notes.length ? `<div>${notes.map(esc).join("<br />")}</div>` : "";
  banner.dataset.tone = overdue ? "bad" : notes.length ? "warn" : "";

  // 분포
  const counts = Object.fromEntries(VERDICTS.map((v) => [v, 0]));
  decisions.forEach((d) => { if (counts[d.decision] !== undefined) counts[d.decision] += 1; });
  const max = Math.max(1, ...Object.values(counts));
  $("#dist-total").textContent = decisions.length;
  fill($("#dist"), VERDICTS.map((v) =>
    `<div class="bar"><b>${v}</b><i data-v="${v}" style="width:${(counts[v] / max) * 100}%"></i>
     <span>${counts[v]}</span></div>`).join(""));

  // 등록 MCP
  fill($("#registry"), (data.registry || []).map((server) => {
    const tone = server.status === "READY" ? "good"
      : server.status === "DISABLED" ? "" : "bad";
    const life = server.lifecycle && server.lifecycle !== "OPERATING"
      ? tag(server.lifecycle, "warn") : "";
    return `<li>
      <div class="item-top"><b>${esc(server.display_name)}</b>
        ${tag(server.status, tone)}${life}
        <span class="spacer"></span>${tag(server.transport)}</div>
      <div class="item-sub">${esc(server.advertised_name || server.id)} · ${esc(server.endpoint || server.source_ref || "")}</div>
      <div class="item-note">${esc(server.status_reason || "")}</div>
      ${server.status === "DRIFT" ? `<div class="item-acts">
        <button class="btn" data-size="sm" data-reapprove="${esc(server.id)}">계약 재승인</button>
      </div>` : ""}
    </li>`;
  }).join(""), "등록된 서버가 없습니다.");

  renderEnforcement();
  renderFeed(decisions.slice(0, 40), false);
}

function renderEnforcement() {
  const monitor = state.console.monitor || {};
  const mode = monitor.enforcement || "enforce";
  const badge = $("#enforce-tag");
  badge.textContent = mode === "enforce" ? "집행" : "관찰";
  badge.dataset.tone = mode === "enforce" ? "good" : "warn";
  const isAdmin = (state.console.viewer.roles || []).includes("admin");
  fill($("#enforce"), `
    <p class="hintline" style="margin-top:0">
      ${mode === "enforce"
        ? "판정이 그대로 집행됩니다. 무결성 통제(MCP-·P-CONTROL-·P-INPUT-·P-RATE-)는 관찰 모드에서도 항상 집행됩니다."
        : `관찰 모드입니다. 지난 ${monitor.window_hours ?? 168}시간 동안 ${monitor.would_have_stopped ?? 0}건이 집행 모드였다면 막혔고, ${monitor.affected_principals ?? 0}명이 영향을 받았습니다.`}
    </p>
    ${isAdmin ? `<div class="row" style="margin-top:10px">
      <button class="btn" data-tone="${mode === "enforce" ? "" : "primary"}" id="enforce-toggle" type="button">
        ${mode === "enforce" ? "관찰 모드로" : "집행 모드로"}
      </button></div>` : ""}
    ${(monitor.breakdown || []).length ? `<div class="scroll" style="margin-top:12px"><table>
      <thead><tr><th>가정 판정</th><th>정책</th><th>역할</th><th>도구</th><th class="num">건수</th></tr></thead>
      <tbody>${monitor.breakdown.slice(0, 10).map((row) => `<tr>
        <td>${verdictTag(row.would_decision)}</td><td class="id">${esc(row.would_policy_id)}</td>
        <td>${esc(row.role)}</td><td class="id">${esc(row.tool_name)}</td>
        <td class="num">${esc(row.calls)}</td></tr>`).join("")}</tbody></table></div>` : ""}`);
}

function renderFeed(rows, prepend) {
  const feed = $("#feed");
  const strip = $("#strip");
  const html = rows.map((row) => `<li${prepend ? ' class="fresh"' : ""} data-id="${esc(row.id)}">
      <time>${clock(row.created_at)}</time>
      ${verdictTag(row.decision)}
      <span class="what">${esc(row.tool_name)} · ${esc(row.policy_id)}</span>
      <span class="who-cell">${esc(row.role || "")}${row.upstream_executed ? " · 실행" : ""}</span>
    </li>`).join("");
  if (prepend) feed.insertAdjacentHTML("afterbegin", html);
  else feed.innerHTML = html || `<li class="empty">아직 판정이 없습니다.</li>`;
  while (feed.children.length > 120) feed.lastElementChild.remove();

  const bars = rows.map((row) =>
    `<i data-v="${esc(row.decision)}" style="height:${row.upstream_executed ? 30 : 16}px"></i>`).join("");
  if (prepend) strip.insertAdjacentHTML("afterbegin", bars);
  else strip.innerHTML = bars;
  while (strip.children.length > 160) strip.lastElementChild.remove();
  $("#stream-count").textContent = feed.querySelectorAll("li[data-id]").length;
}

/* ── 도입 ────────────────────────────────────────────────────────────────── */

function renderIntake() {
  const rows = state.console.intake || [];
  $("#intake-n").textContent = rows.length;
  const tone = { APPROVED: "good", REJECTED: "bad", VALIDATED: "info", SUBMITTED: "", VALIDATING: "warn" };
  fill($("#intake-list"), rows.map((row) => `<li>
    <div class="item-top"><b>${esc(row.display_name)}</b>
      ${tag(row.status, tone[row.status] || "")}
      ${row.risk_level ? tag(row.risk_level, row.risk_level === "HIGH" ? "bad" : "warn") : ""}
      <span class="spacer"></span><span class="item-sub">${when(row.created_at)}</span></div>
    <div class="item-sub">${esc(row.repository_url)}${row.commit_sha ? ` @ ${esc(String(row.commit_sha).slice(0, 12))}` : ""}</div>
    ${row.review_note ? `<div class="item-note">${esc(row.review_note)}</div>` : ""}
  </li>`).join(""), "아직 신청한 요청이 없습니다.");
}

function exitTermsVerdict(form) {
  const checked = ["provider_credential_disclosure", "revocation_evidence", "audit_access_retained"]
    .filter((name) => form.elements[name]?.checked);
  const node = $("#exit-verdict");
  if (checked.length === 3) {
    node.textContent = "세 조건이 모두 있으면 종료 시 T1 판정이 가능합니다.";
  } else if (!checked.includes("provider_credential_disclosure")) {
    node.textContent = "하위 위임 자격 고지가 없으면 이 이용 관계는 끝낼 때 반드시 T3(판단 불가)가 됩니다.";
  } else {
    node.textContent = "회수 증적이나 감사 접근이 빠지면 종료 판정이 T2 이하로 내려갑니다.";
  }
}

/* ── 검증 ────────────────────────────────────────────────────────────────── */

function renderVerification() {
  const data = state.console;
  const rows = data.intake || [];
  const coverage = data.coverage?.servers || [];
  const unwired = coverage.filter((s) => s.scan_path && !s.reports).length;
  fill($("#verify-figures"), [
    figure("치명", data.severity?.critical ?? 0, "실행을 막는 등급",
      data.severity?.critical ? "bad" : "good"),
    figure("높음", data.severity?.high ?? 0, ""),
    figure("보통", data.severity?.medium ?? 0, ""),
    figure("증적 미연결", unwired, "스캔 경로는 있으나 보고서 없음", unwired ? "warn" : "good"),
  ].join(""));

  $("#verify-n").textContent = rows.length;
  fill($("#verify-list"), rows.map((row) => {
    const evidence = row.evidence || {};
    return `<li>
      <div class="item-top"><b>${esc(row.display_name)}</b>${tag(row.status)}
        <span class="spacer"></span><span class="item-sub">${when(row.validated_at || row.created_at)}</span></div>
      <div class="item-sub">${esc(row.repository_url)}</div>
      ${Object.keys(evidence).length ? `<div class="tags" style="margin-top:7px">${
        Object.entries(evidence).slice(0, 6).map(([key, value]) =>
          tag(`${key}=${typeof value === "object" ? "…" : value}`)).join("")}</div>` : ""}
    </li>`;
  }).join(""), "검증 대상이 없습니다.");

  fill($("#coverage-list"), coverage.map((row) => `<li>
    <div class="item-top"><b>${esc(row.display_name || row.server_id)}</b>
      ${row.reports ? tag(`보고서 ${row.reports}`, "good") : tag("증적 없음", row.scan_path ? "warn" : "")}
      <span class="spacer"></span>${row.critical ? tag(`치명 ${row.critical}`, "bad") : ""}</div>
    <div class="item-sub">${esc(row.scan_path || "스캔 경로 없음 (원격 전용)")}</div>
  </li>`).join(""), "공급망 대상이 없습니다.");
}

/* ── 위험 ────────────────────────────────────────────────────────────────── */

function renderRisks() {
  const reports = state.console.supply_chain || [];
  const severity = state.console.severity || {};
  fill($("#risk-figures"), [
    figure("보고서", reports.length, "가져온 스캔 결과"),
    figure("치명", severity.critical ?? 0, "", severity.critical ? "bad" : "good"),
    figure("높음", severity.high ?? 0, "", severity.high ? "warn" : ""),
    figure("보통", severity.medium ?? 0, ""),
  ].join(""));

  const scanners = [...new Set(reports.map((r) => r.scanner))];
  fill($("#find-filter"), ["all", ...scanners].map((name) =>
    `<button class="tag" data-filter="${esc(name)}"${state.findFilter === name ? ' data-tone="info"' : ""}>
      ${esc(name === "all" ? "전체" : name)}</button>`).join(""));
  renderFindings();
}

function renderFindings() {
  const query = ($("#find-q")?.value || "").toLowerCase();
  const rows = (state.console.supply_chain || [])
    .filter((r) => state.findFilter === "all" || r.scanner === state.findFilter)
    .filter((r) => !query || JSON.stringify(r.summary || {}).toLowerCase().includes(query)
      || (r.source_ref || "").toLowerCase().includes(query));
  $("#find-n").textContent = rows.length;
  fill($("#find-list"), rows.map((row) => {
    const summary = row.summary || {};
    const findings = summary.findings || summary.items || [];
    return `<li>
      <div class="item-top"><b>${esc(row.scanner)}</b>
        ${row.scanner_version ? tag(row.scanner_version) : ""}
        ${row.critical_count ? tag(`치명 ${row.critical_count}`, "bad") : ""}
        ${row.high_count ? tag(`높음 ${row.high_count}`, "warn") : ""}
        ${summary.evidence_mode ? tag(summary.evidence_mode, summary.evidence_mode === "live" ? "good" : "") : ""}
        <span class="spacer"></span><span class="item-sub">${when(row.imported_at)}</span></div>
      <div class="item-sub">${esc(row.source_ref || "")}</div>
      ${findings.length ? `<div class="item-note">${findings.slice(0, 4).map((f) =>
        `${esc(f.severity || f.level || "")} · ${esc(f.title || f.id || f.ruleId || "")}`).join("<br />")}</div>` : ""}
    </li>`;
  }).join(""), "발견 항목이 없습니다.");
}

async function loadRiskCatalog() {
  if (state.aig) return;
  try {
    state.aig = await api("/api/risk-catalog");
  } catch { return; }
  const rows = state.aig.categories || [];
  $("#aig-table").innerHTML = `
    <thead><tr><th>범주</th><th>이름</th><th>집행</th><th>정책</th><th>통제</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td class="id">${esc(row.id)}</td>
      <td>${esc(row.title_ko)}<div class="item-sub">${esc(row.title_en)}</div></td>
      <td>${tag(row.gate === "blocking" ? "차단" : "증적", row.gate === "blocking" ? "bad" : "")}</td>
      <td class="id">${(row.mapped_policy_ids || []).map(esc).join("<br />")}</td>
      <td class="id">${(row.mapped_control_ids || []).map(esc).join(", ")}</td>
    </tr>`).join("") || emptyRow("대조표가 비어 있습니다.", 5)}</tbody>`;
}

/* ── AI 코드 감사 ────────────────────────────────────────────────────────── */

async function loadScan() {
  try { state.scan = await api("/api/mcp-scan"); } catch (error) { toast(error.message, "bad"); return; }
  const { config, worker, jobs, reports, targets, servers } = state.scan;
  const badge = $("#scan-state");
  badge.textContent = config.configured ? (worker.alive ? "실행 가능" : "워커 없음") : "설정 필요";
  badge.dataset.tone = config.configured && worker.alive ? "good" : "warn";

  fill($("#scan-config"), `
    <p class="hintline" style="margin-top:0">${config.configured
      ? `모델 endpoint가 설정돼 있습니다. 키는 화면에 나오지 않습니다.`
      : `설정이 필요합니다: ${esc((config.missing || []).join(", "))}`}</p>
    <table><tbody>
      <tr><td>Base URL</td><td class="id">${esc(config.base_url || "-")}</td></tr>
      <tr><td>모델</td><td class="id">${esc(config.model || "-")}</td></tr>
      <tr><td>로컬 endpoint</td><td>${config.local ? tag("예 — 코드가 조직 밖으로 나가지 않음", "good") : tag("아니오 — 외부로 나감", "warn")}</td></tr>
    </tbody></table>`);

  fill($("#scan-worker"), `
    <p class="hintline" style="margin-top:0">${worker.alive
      ? `워커 ${esc(worker.worker_id || "")}가 살아 있습니다.`
      : "격리 워커의 생존 신호가 없습니다. 큐에 넣어도 실행되지 않습니다."}</p>
    <table><tbody>
      <tr><td>마지막 신호</td><td class="id">${when(worker.last_seen_at, true)}</td></tr>
      <tr><td>대기</td><td class="num">${esc(worker.queued ?? 0)}</td></tr>
      <tr><td>실행 중</td><td class="num">${esc(worker.running ?? 0)}</td></tr>
    </tbody></table>`);

  const intakeItems = (targets || []).map((row) => `<li>
    <div class="item-top"><b>${esc(row.display_name)}</b>${tag("도입 요청")}
      ${row.last_status ? tag(row.last_status, row.last_status === "SUCCEEDED" ? "good" : "warn") : ""}
      <span class="spacer"></span><span class="item-sub">${esc(String(row.commit_sha || "").slice(0, 12))}</span></div>
    <div class="item-sub">${esc(row.repository_url)}</div>
    <div class="item-acts">
      <button class="btn" data-size="sm" data-scan="intake" data-id="${esc(row.id)}" data-mode="static">정적 감사</button>
    </div></li>`).join("");

  const serverItems = (servers || []).map((row) => `<li>
    <div class="item-top"><b>${esc(row.display_name)}</b>${tag("등록 서버")}
      ${tag(row.status, row.status === "READY" ? "good" : "warn")}
      ${row.last_status ? tag(row.last_status, row.last_status === "SUCCEEDED" ? "good" : "warn") : ""}</div>
    <div class="item-sub">${esc(row.source_url || row.endpoint || "")}</div>
    <div class="item-acts">
      <button class="btn" data-size="sm" data-scan="server" data-id="${esc(row.id)}" data-mode="static"
        ${row.scannable ? "" : "disabled title='국소 코드 감사 대상이 아닙니다'"}>정적 감사</button>
      <button class="btn" data-size="sm" data-scan="server" data-id="${esc(row.id)}" data-mode="dynamic"
        ${row.probeable ? "" : "disabled title='HTTP endpoint가 없습니다'"}>동적 점검</button>
    </div></li>`).join("");
  fill($("#scan-targets"), intakeItems + serverItems, "감사할 대상이 없습니다.");

  $("#scan-job-n").textContent = (jobs || []).length;
  const jobTone = { SUCCEEDED: "good", FAILED: "bad", CANCELLED: "", RUNNING: "info", QUEUED: "warn" };
  fill($("#scan-jobs"), (jobs || []).map((job) => `<li>
    <div class="item-top"><b>${esc(job.target_label || job.target_id)}</b>
      ${tag(job.status, jobTone[job.status] || "")}${tag(job.mode)}${tag(job.target_kind)}
      <span class="spacer"></span><span class="item-sub">${when(job.created_at, true)}</span></div>
    ${job.error ? `<div class="item-note">${esc(job.error)}</div>` : ""}
    <div class="item-acts">
      ${["QUEUED", "RUNNING"].includes(job.status)
        ? `<button class="btn" data-size="sm" data-job-cancel="${esc(job.id)}">취소</button>` : ""}
      ${["FAILED", "CANCELLED"].includes(job.status)
        ? `<button class="btn" data-size="sm" data-job-retry="${esc(job.id)}">재시도</button>` : ""}
    </div></li>`).join(""), "작업 이력이 없습니다.");

  $("#scan-find-n").textContent = (reports || []).length;
  fill($("#scan-finds"), (reports || []).map((row) => {
    const summary = row.summary || {};
    return `<li>
      <div class="item-top"><b>${esc(row.source_ref)}</b>
        ${summary.evidence_mode ? tag(summary.evidence_mode, summary.evidence_mode === "live" ? "good" : "") : ""}
        ${row.critical_count ? tag(`치명 ${row.critical_count}`, "bad") : ""}
        ${summary.blocks ? tag("호출 차단으로 이어짐", "bad") : tag("증적만")}
        <span class="spacer"></span><span class="item-sub">${when(row.imported_at)}</span></div>
      ${(summary.findings || []).slice(0, 5).map((f) =>
        `<div class="item-note">${esc(f.severity || "")} · ${esc(f.title || f.id || "")}</div>`).join("")}
    </li>`;
  }).join(""), "감사 결과가 없습니다.");
}

/* ── 엔드포인트 평면 ─────────────────────────────────────────────────────── */

async function loadEndpoints() {
  const data = state.console.endpoints || {};
  state.endpoints = data;
  const coverage = data.coverage || {};
  const listeners = data.listeners || [];
  const shadowListeners = listeners.filter((l) => l.classification === "shadow").length;

  fill($("#ep-figures"), [
    figure("알려진 단말", coverage.known_endpoints ?? 0, "분모는 모릅니다"),
    figure("최근 보고", coverage.reporting_recently ?? 0, "15분 이내"),
    figure("섀도 설정", coverage.shadow ?? 0, "설정에 있는 미등록 서버",
      coverage.shadow ? "warn" : "good"),
    figure("섀도 리스너", shadowListeners, "망에서 실제로 떠 있는 것",
      shadowListeners ? "bad" : "good"),
    figure("폐기 잔존", coverage.retired_residue ?? 0, "회수되지 않은 경로",
      coverage.retired_residue ? "bad" : "good"),
  ].join(""));

  const policy = data.scan_policy || {};
  const form = $("#scan-policy-form");
  form.elements.enabled.checked = !!policy.enabled;
  form.elements.probe_mcp.checked = policy.probe_mcp !== false;
  form.elements.allowed_cidrs.value = (policy.allowed_cidrs || []).join(", ");
  form.elements.ports.value = (policy.ports || []).join(", ");
  form.elements.max_hosts.value = policy.max_hosts ?? 256;
  form.elements.connect_timeout_ms.value = policy.connect_timeout_ms ?? 300;
  form.elements.interval_seconds.value = policy.interval_seconds ?? 900;

  const owners = (state.console.principals || []).map((p) =>
    `<option value="${esc(p.token || "")}">${esc(p.display_name)} (${esc(p.role)})</option>`).join("");
  $("#device-owner").innerHTML = `<option value="">(소유자 없음)</option>` + owners;

  fill($("#device-list"), (data.devices || []).map((device) => `<li>
    <div class="item-top"><b>${esc(device.endpoint_id)}</b>
      ${tag(device.status, device.status === "active" ? "good" : "bad")}
      ${(device.scopes || []).map((s) => tag(s, "info")).join("")}
      <span class="spacer"></span><span class="item-sub">마지막 보고 ${when(device.last_seen_at, true)}</span></div>
    <div class="item-sub">${esc(device.hostname)} · ${esc(device.platform)} · agent ${esc(device.agent_version)}
      · 소유 ${esc(device.owner_name || device.owner_token || "미지정")}</div>
    <div class="item-note">설정 섀도 ${esc(device.config_shadow ?? 0)}
      · 관측 리스너 ${esc(device.listeners_seen ?? 0)} (섀도 ${esc(device.listener_shadow ?? 0)})</div>
    ${device.status === "active" ? `<div class="item-acts">
      <button class="btn" data-size="sm" data-tone="danger" data-device-revoke="${esc(device.endpoint_id)}">자격 폐기</button>
    </div>` : ""}
  </li>`).join(""), "발급된 장치 자격이 없습니다.");

  $("#listener-n").textContent = listeners.length;
  const classTone = { registered: "good", shadow: "bad", "retired-residue": "warn" };
  $("#listener-table").innerHTML = `
    <thead><tr><th>분류</th><th>출처</th><th>주소</th><th>MCP</th><th>서버</th><th>프로세스</th><th>단말</th><th></th></tr></thead>
    <tbody>${listeners.map((row) => `<tr>
      <td>${tag(row.classification, classTone[row.classification] || "")}</td>
      <td class="id">${esc(row.source)}</td>
      <td class="id">${esc(row.address)}${row.port ? ":" + esc(row.port) : ""}</td>
      <td>${tag(row.mcp_evidence, row.mcp_evidence === "confirmed" ? "info" : "")}</td>
      <td class="id">${esc(row.server_name || "-")}${row.server_version ? " " + esc(row.server_version) : ""}</td>
      <td class="id">${esc((row.process_name || "-").slice(0, 28))}</td>
      <td>${esc(row.hostname)}<div class="item-sub">${esc(row.owner_name || row.owner_token || "")}</div></td>
      <td>${row.classification !== "registered" && row.mcp_evidence === "confirmed" && row.port
        ? `<button class="btn" data-size="sm" data-listener-scan="${esc(row.id)}">A.I.G 점검</button>` : ""}</td>
    </tr>`).join("") || emptyRow("관측된 리스너가 없습니다. 탐색 범위를 켜고 에이전트를 돌리세요.", 8)}</tbody>`;

  const entries = data.entries || [];
  $("#inv-n").textContent = entries.length;
  $("#inv-table").innerHTML = `
    <thead><tr><th>분류</th><th>서버 이름</th><th>전송</th><th>주소 또는 명령</th><th>단말</th><th>보고</th></tr></thead>
    <tbody>${entries.map((row) => `<tr>
      <td>${tag(row.classification, classTone[row.classification] || "")}</td>
      <td>${esc(row.server_label)}</td>
      <td class="id">${esc(row.transport)}</td>
      <td class="id">${esc(row.endpoint_ref)}</td>
      <td>${esc(row.hostname)}</td>
      <td class="id">${when(row.reported_at, true)}</td>
    </tr>`).join("") || emptyRow("보고된 설정이 없습니다.", 6)}</tbody>`;
}

/* ── 종료·폐기 ───────────────────────────────────────────────────────────── */

function renderTermination() {
  const cases = state.console.termination?.cases || [];
  const overdue = cases.filter((c) => c.overdue).length;
  const banner = $("#term-banner");
  banner.innerHTML = overdue
    ? `<div>기한을 넘긴 케이스 ${overdue}건. 차단은 했지만 회수가 끝나지 않은 상태가 이어지고 있습니다.</div>` : "";
  banner.dataset.tone = overdue ? "bad" : "";

  $("#term-n").textContent = cases.length;
  const gradeTone = { T1: "good", T2: "warn", T3: "bad" };
  fill($("#term-list"), cases.map((row) => `<li>
    <div class="item-top"><b>${esc(row.engagement_label || row.server_id)}</b>
      ${tag(row.status)}${row.grade ? tag(row.grade, gradeTone[row.grade] || "") : ""}
      ${row.overdue ? tag("기한 초과", "bad") : ""}
      <span class="spacer"></span><span class="item-sub">${when(row.opened_at)}</span></div>
    <div class="item-note">${esc(row.reason || "")}</div>
    <div class="item-acts"><button class="btn" data-size="sm" data-case="${esc(row.id)}">상세</button></div>
  </li>`).join(""), "종료 케이스가 없습니다.");
}

async function openCase(caseId) {
  let detail;
  try { detail = await api(`/api/termination/cases/${caseId}`); }
  catch (error) { toast(error.message, "bad"); return; }
  state.termCase = detail;
  const c = detail.case || {};
  const criteria = c.criteria || {};
  fill($("#term-detail"), `
    <div class="item-top"><b>${esc(c.engagement_label || c.server_id)}</b>
      ${tag(c.status)}${c.grade ? tag(c.grade, { T1: "good", T2: "warn", T3: "bad" }[c.grade] || "") : ""}</div>
    <p class="item-note">${esc(c.reason || "")}</p>
    <table style="margin-top:10px"><thead><tr><th>기준</th><th>충족</th><th>근거</th></tr></thead><tbody>
      ${["C1", "C2", "C3", "C4"].map((key) => {
        const item = criteria[key] || {};
        return `<tr><td class="id">${key}</td>
          <td>${item.met ? tag("충족", "good") : tag("미충족", "bad")}</td>
          <td>${esc(item.note || item.reason || "")}</td></tr>`;
      }).join("")}
    </tbody></table>
    <h3 style="font-size:12.5px;margin:16px 0 6px">회수 대상 ${(detail.targets || []).length}건</h3>
    <div class="scroll" style="max-height:200px"><table><tbody>
      ${(detail.targets || []).map((t) => `<tr>
        <td class="id">${esc(t.kind)}</td><td>${esc(t.label)}</td>
        <td>${tag(t.status, t.status === "REVOKED" ? "good" : t.status === "UNVERIFIABLE" ? "bad" : "warn")}</td>
        <td class="id">${esc(t.holder)}</td></tr>`).join("") || emptyRow("회수 대상이 없습니다.", 4)}
    </tbody></table></div>
    <div class="item-acts">
      <button class="btn" data-size="sm" data-case-act="probe" data-id="${esc(c.id)}">도달 확인</button>
      <button class="btn" data-size="sm" data-case-act="assess" data-id="${esc(c.id)}">판정</button>
    </div>`);
}

/* ── 정책 ────────────────────────────────────────────────────────────────── */

function renderPolicy() {
  const ledger = state.console.ledger || {};
  const policies = ledger.policies || [];
  const set = ledger.policy_set || {};
  const enforcing = policies.filter((p) => ["운영", "제한"].includes(p.status)).length;
  fill($("#policy-figures"), [
    figure("정책", policies.length, `정책집 ${set.version || "-"}`),
    figure("집행 중", enforcing, "운영 또는 제한 상태"),
    figure("예외", (ledger.exceptions || []).length, "완화가 걸린 항목",
      (ledger.exceptions || []).length ? "warn" : ""),
    figure("적용 환경", ledger.environment || "-", set.register || ""),
  ].join(""));

  const roles = ["partner", "employee", "admin"];
  const classes = ["public", "nonimportant", "important"];
  const grid = { partner: { public: "r" }, employee: { public: "r", nonimportant: "rw", important: "r" },
    admin: { public: "rwx", nonimportant: "rwx", important: "rwx" } };
  fill($("#matrix"), `<table class="matrix"><thead><tr><th></th>${
    classes.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>${
    roles.map((role) => `<tr><th>${role}</th>${classes.map((cls) => {
      const value = grid[role][cls] || "-";
      return `<td style="color:var(--${value === "-" ? "block" : "allow"})">${value}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table>
    <p class="hintline">27칸이 이 실습의 정책 어휘 전부입니다. 권한이 있어도 승인·제한·경보·누적 승격이 그 위에 겹칩니다.</p>`);

  renderPolicyTable();
  $("#exc-n").textContent = (ledger.exceptions || []).length;
  fill($("#exc-list"), (ledger.exceptions || []).map((exc) => `<li>
    <div class="item-top"><b>${esc(exc.id)} ${esc(exc.title)}</b>
      ${tag(exc.policy_id, "info")}${tag(exc.effect)}${tag(exc.status, exc.status === "적용" ? "warn" : "")}
      <span class="spacer"></span><span class="item-sub">~ ${when(exc.valid_until)}</span></div>
    <div class="item-note">${esc(exc.reason || "")}</div>
    <div class="item-note">보완통제: ${esc((exc.compensating_controls || []).join(" · "))}</div>
  </li>`).join(""), "등록된 예외가 없습니다.");
}

function renderPolicyTable() {
  const query = ($("#policy-q")?.value || "").toLowerCase();
  const rows = (state.console.ledger?.policies || []).filter((p) => !query
    || p.policy_id.toLowerCase().includes(query)
    || (p.control_ids || []).join(" ").toLowerCase().includes(query)
    || (p.risk_ids || []).join(" ").toLowerCase().includes(query)
    || (p.name || "").toLowerCase().includes(query));
  $("#policy-table").innerHTML = `
    <thead><tr><th class="num">우선</th><th>정책</th><th>판단</th><th>상태</th><th>위험</th><th>통제</th><th>PaC</th></tr></thead>
    <tbody>${rows.map((p) => `<tr>
      <td class="num">${esc(p.priority)}</td>
      <td class="id">${esc(p.policy_id)}<div class="item-sub">${esc(p.name)}</div></td>
      <td>${esc(p.outcome || "-")}</td>
      <td>${tag(p.status, p.status === "운영" ? "good" : p.status === "중지" ? "" : "warn")}
        ${p.exceptionable ? tag("예외 가능") : ""}</td>
      <td class="id">${(p.risk_ids || []).map(esc).join(", ")}</td>
      <td class="id">${(p.control_ids || []).map(esc).join(", ")}</td>
      <td class="id">${esc(p.pac_candidate_id || "-")}</td>
    </tr>`).join("") || emptyRow("일치하는 정책이 없습니다.", 7)}</tbody>`;
}

/* ── 신원 ────────────────────────────────────────────────────────────────── */

async function renderAccounts() {
  let data;
  try { data = await api("/api/accounts"); } catch (error) { toast(error.message, "bad"); return; }
  const me = state.console.viewer.user_id;
  const tone = { active: "good", disabled: "", locked: "bad" };
  $("#account-table").innerHTML = `
    <thead><tr><th>이름</th><th>이메일</th><th>역할</th><th>부서</th><th>상태</th><th>변경</th><th></th></tr></thead>
    <tbody>${(data.accounts || []).map((row) => `<tr>
      <td>${esc(row.display_name)}<div class="item-sub">${esc(row.employee_no || "")} ${esc(row.job_title || "")}</div></td>
      <td class="id">${esc(row.email)}</td>
      <td>${tag(row.role, row.role === "admin" ? "info" : "")}</td>
      <td>${esc(row.department || "-")}</td>
      <td>${tag(row.status, tone[row.status] || "")}</td>
      <td class="id">${row.status_changed_at ? `${when(row.status_changed_at)}<div class="item-sub">${esc(row.status_changed_by || "")}</div>` : "-"}</td>
      <td>${row.user_id === me ? `<span class="item-sub">본인</span>` : `
        <select data-account="${esc(row.user_id)}">
          ${["active", "disabled", "locked"].map((s) =>
            `<option value="${s}"${s === row.status ? " selected" : ""}>${s}</option>`).join("")}
        </select>`}</td>
    </tr>`).join("") || emptyRow("계정이 없습니다.", 7)}</tbody>`;
}

/* ── 실행 ────────────────────────────────────────────────────────────────── */

function renderExecution() {
  const model = state.console.health?.model || state.console.readiness?.model;
  const badge = $("#model-tag");
  if (model) {
    badge.textContent = model.mode === "mock" ? "결정론적 모의 모델" : `모델 ${model.model || "provider"}`;
    badge.dataset.tone = model.configured ? "good" : "warn";
  }
  fill($("#talk"), state.chat.map((turn) => `
    <article class="turn" data-who="${esc(turn.who)}">
      <header><span>${esc(turn.who === "user" ? state.console.viewer.name : "게이트웨이")}</span>
        <span>${clock(turn.at)}</span>
        ${turn.verdict ? verdictTag(turn.verdict) : ""}
        ${turn.policy ? tag(turn.policy, "info") : ""}</header>
      <div>${esc(turn.text)}</div>
      ${turn.detail ? `<pre>${esc(turn.detail)}</pre>` : ""}
    </article>`).join(""), "아직 요청이 없습니다.");
  $("#talk").scrollTop = $("#talk").scrollHeight;
}

async function ask() {
  const input = $("#ask");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  state.chat.push({ who: "user", text: message, at: new Date().toISOString() });
  renderExecution();
  const button = $("#ask-go");
  button.disabled = true;
  try {
    const body = {
      message,
      request_id: crypto.randomUUID(),
      ...(state.session ? { session_id: state.session } : {}),
    };
    const result = await api("/chat", { method: "POST", body: JSON.stringify(body) });
    state.session = result.session_id || state.session;
    const gateway = result.gateway_result || {};
    state.chat.push({
      who: "gateway",
      at: new Date().toISOString(),
      verdict: gateway.decision,
      policy: gateway.policy_id,
      text: result.message || gateway.reason || `상태: ${result.status}`,
      detail: result.tool_call ? JSON.stringify(result.tool_call, null, 2) : "",
    });
  } catch (error) {
    state.chat.push({ who: "gateway", at: new Date().toISOString(), text: error.message });
  } finally {
    button.disabled = false;
    renderExecution();
    refresh();
  }
}

/* ── 감사 ────────────────────────────────────────────────────────────────── */

function renderAudit() {
  const query = ($("#audit-q")?.value || "").toLowerCase();
  const rows = (state.console.decisions || []).filter((row) => !query
    || (row.tool_name || "").toLowerCase().includes(query)
    || (row.policy_id || "").toLowerCase().includes(query)
    || (row.user_token || "").toLowerCase().includes(query));
  $("#audit-table").innerHTML = `
    <thead><tr><th>시각</th><th>판정</th><th>정책</th><th>주체</th><th>도구</th><th>등급</th><th>실행</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td class="id">${when(row.created_at, true)}</td>
      <td>${verdictTag(row.decision)}</td>
      <td class="id">${esc(row.policy_id)}</td>
      <td>${esc(row.user_token)}<div class="item-sub">${esc(row.role || "")}</div></td>
      <td class="id">${esc(row.tool_name)}</td>
      <td>${esc(row.data_class || "-")}</td>
      <td>${row.upstream_executed ? tag("실행 확인", "warn")
        : row.upstream_attempted ? tag("실행 여부 미확인", "bad") : tag("미실행", "good")}</td>
    </tr>`).join("") || emptyRow("판정 기록이 없습니다.", 7)}</tbody>`;
}

/* ── 실시간 ──────────────────────────────────────────────────────────────── */

async function stream() {
  const wire = $("#stream-wire");
  while (true) {
    try {
      wire.dataset.state = "ok";
      $("b", wire).textContent = "연결";
      const response = await fetch(`/api/stream/decisions?after=${state.seenDecision}`, {
        headers: { authorization: "Bearer " + token() },
      });
      if (!response.ok || !response.body) throw new Error("stream unavailable");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() || "";
        for (const frame of frames) {
          const line = frame.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          let rows;
          try { rows = JSON.parse(line.slice(5).trim()); } catch { continue; }
          const list = Array.isArray(rows) ? rows : rows.decisions || [];
          if (!list.length) continue;
          state.seenDecision = Math.max(state.seenDecision, ...list.map((r) => r.id || 0));
          renderFeed(list.slice().reverse(), true);
        }
      }
    } catch {
      wire.dataset.state = "down";
      $("b", wire).textContent = "재연결 중";
    }
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
}

/* ── 새로고침 ────────────────────────────────────────────────────────────── */

async function refresh() {
  try {
    state.console = await api("/api/console");
  } catch (error) {
    toast(error.message, "bad");
    return;
  }
  const pages = state.console.viewer.pages || [];
  buildRail(pages);
  renderTop();
  if (pages.includes("overview")) renderOverview();
  if (pages.includes("intake")) renderIntake();
  if (pages.includes("verification")) renderVerification();
  if (pages.includes("risks")) renderRisks();
  if (pages.includes("termination")) renderTermination();
  if (pages.includes("policy")) renderPolicy();
  if (pages.includes("audit")) renderAudit();
  if (pages.includes("execution")) renderExecution();
  if (pages.includes("accounts")) renderAccounts();
  if (state.page === "endpoints") loadEndpoints();
  show(state.page || location.hash.slice(1) || pages[0]);
  const ids = (state.console.decisions || []).map((d) => d.id || 0);
  if (ids.length) state.seenDecision = Math.max(state.seenDecision, ...ids);
}

/* ── 동작 ────────────────────────────────────────────────────────────────── */

function csv(value) {
  return String(value || "").split(",").map((s) => s.trim()).filter(Boolean);
}

async function act(fn, okMessage) {
  try {
    const result = await fn();
    if (okMessage) toast(typeof okMessage === "function" ? okMessage(result) : okMessage);
    await refresh();
    return result;
  } catch (error) {
    toast(error.message, "bad");
    return null;
  }
}

function wire() {
  $("#theme").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("mcp-console-theme", next);
  });

  $("#logout").addEventListener("click", async () => {
    try { await api("/auth/logout", { method: "POST" }); } catch { /* 이미 만료 */ }
    localStorage.removeItem(TOKEN_KEY);
    location.href = "/login";
  });

  $("#refresh").addEventListener("click", () => refresh());
  addEventListener("hashchange", () => show(location.hash.slice(1)));

  document.addEventListener("click", async (event) => {
    const link = event.target.closest("#rail a");
    if (link) { event.preventDefault(); show(link.dataset.page); return; }

    const target = event.target;
    if (target.id === "catalog-refresh") {
      await act(() => api("/api/registry/refresh", { method: "POST" }), "Catalog를 다시 대조했습니다.");
    } else if (target.id === "enforce-toggle") {
      const next = state.console.monitor?.enforcement === "enforce" ? "monitor" : "enforce";
      await act(() => api("/api/enforcement", { method: "PUT", body: JSON.stringify({ mode: next }) }),
        `집행 모드를 ${next === "enforce" ? "집행" : "관찰"}로 바꿨습니다.`);
    } else if (target.id === "import-evidence") {
      await act(() => api("/api/supply-chain/import", { method: "POST" }), "워크스페이스 증적을 반영했습니다.");
    } else if (target.id === "verify-chain") {
      const result = await api("/api/audit/verify").catch((e) => ({ error: e.message }));
      const node = $("#chain-out");
      node.dataset.tone = result.intact ? "" : "bad";
      node.innerHTML = `<div>${result.error ? esc(result.error)
        : result.intact ? `연쇄 정상 · ${esc(result.checked)}건 확인`
        : `연쇄 불일치 · ${esc(result.reason || "")} (id ${esc(result.broken_at ?? "?")})`}</div>`;
    } else if (target.id === "scan-test") {
      await act(() => api("/api/mcp-scan/connection-test", { method: "POST" }),
        (r) => r.ok ? "모델 endpoint가 응답했습니다." : `응답 없음: ${r.detail || ""}`);
      loadScan();
    } else if (target.id === "q-go") {
      const out = $("#q-out");
      try {
        const found = await api(`/api/mcp-catalog/search?q=${encodeURIComponent($("#q").value)}`);
        fill(out, (found.results || []).map((row) => `<div class="item-top">
          <b>${esc(row.display_name)}</b>${tag(row.status)}
          <span class="item-sub">${esc(row.repository_url || "")}</span></div>`).join(""),
          "일치하는 신청이나 승인 기록이 없습니다. 새로 신청하세요.");
      } catch (error) { toast(error.message, "bad"); }
    } else if (target.id === "device-new") {
      $("#device-form-wrap").hidden = false;
    } else if (target.id === "device-cancel") {
      $("#device-form-wrap").hidden = true;
      $("#device-secret").hidden = true;
    }

    const reapprove = target.closest("[data-reapprove]");
    if (reapprove) {
      // 재승인은 "무엇이 바뀌었는지 보고 사람이 누른다"가 통제의 전부다.
      // 사유 없이 누를 수 있으면 나중에 그 승인을 설명할 수 없다.
      const note = prompt("계약 변경을 검토한 근거를 적으세요 (5자 이상). 이 값이 재승인 기록에 남습니다.");
      if (note && note.trim().length >= 5) {
        await act(() => api(`/api/registry/${encodeURIComponent(reapprove.dataset.reapprove)}/approve-contract`,
          { method: "POST", body: JSON.stringify({ note: note.trim() }) }),
          (r) => r.changed?.length ? `${r.changed.length}개 도구의 계약을 재승인했습니다.` : r.note);
      }
    }

    const filter = target.closest("[data-filter]");
    if (filter) { state.findFilter = filter.dataset.filter; renderRisks(); }

    const scanBtn = target.closest("[data-scan]");
    if (scanBtn) {
      const body = { target_kind: scanBtn.dataset.scan, target_id: scanBtn.dataset.id,
        mode: scanBtn.dataset.mode, acknowledge_external_model: false };
      try {
        const result = await api("/api/mcp-scan/run", { method: "POST", body: JSON.stringify(body) });
        toast(result.message);
      } catch (error) {
        if (error.message.includes("외부")) {
          if (confirm(error.message + "\n\n그래도 실행하시겠습니까?")) {
            body.acknowledge_external_model = true;
            await act(() => api("/api/mcp-scan/run", { method: "POST", body: JSON.stringify(body) }),
              (r) => r.message);
          }
        } else { toast(error.message, "bad"); }
      }
      loadScan();
    }

    const cancelJob = target.closest("[data-job-cancel]");
    if (cancelJob) {
      await act(() => api(`/api/mcp-scan/jobs/${cancelJob.dataset.jobCancel}/cancel`, { method: "POST" }),
        "작업을 취소했습니다.");
      loadScan();
    }
    const retryJob = target.closest("[data-job-retry]");
    if (retryJob) {
      await act(() => api(`/api/mcp-scan/jobs/${retryJob.dataset.jobRetry}/retry`, { method: "POST" }),
        "작업을 다시 큐에 넣었습니다.");
      loadScan();
    }

    const revoke = target.closest("[data-device-revoke]");
    if (revoke && confirm(`${revoke.dataset.deviceRevoke} 의 장치 자격을 폐기합니다. 그 단말의 보고가 즉시 멈춥니다.`)) {
      await act(() => api(`/api/endpoint/devices/${encodeURIComponent(revoke.dataset.deviceRevoke)}`,
        { method: "DELETE" }), "장치 자격을 폐기했습니다.");
      loadEndpoints();
    }

    const listenerScan = target.closest("[data-listener-scan]");
    if (listenerScan) {
      const id = listenerScan.dataset.listenerScan;
      const run = (ack) => api(`/api/endpoint/listeners/${id}/scan`,
        { method: "POST", body: JSON.stringify({ listener_id: Number(id), acknowledge_external_model: ack }) });
      try { toast((await run(false)).message); }
      catch (error) {
        if (error.message.includes("외부") && confirm(error.message + "\n\n그래도 실행하시겠습니까?")) {
          await act(() => run(true), (r) => r.message);
        } else { toast(error.message, "bad"); }
      }
    }

    const caseBtn = target.closest("[data-case]");
    if (caseBtn) openCase(caseBtn.dataset.case);
    const caseAct = target.closest("[data-case-act]");
    if (caseAct) {
      await act(() => api(`/api/termination/cases/${caseAct.dataset.id}/${caseAct.dataset.caseAct}`,
        { method: "POST" }), "처리했습니다.");
      openCase(caseAct.dataset.id);
    }
  });

  document.addEventListener("change", async (event) => {
    const account = event.target.closest("[data-account]");
    if (account) {
      await act(() => api(`/api/accounts/${account.dataset.account}/status`,
        { method: "PUT", body: JSON.stringify({ status: account.value, note: "console" }) }),
        (r) => r.message);
      renderAccounts();
    }
  });

  document.addEventListener("input", (event) => {
    if (event.target.id === "find-q") renderFindings();
    if (event.target.id === "policy-q") renderPolicyTable();
    if (event.target.id === "audit-q") renderAudit();
    if (event.target.name === "purpose") {
      $("#purpose-n").textContent = event.target.value.length;
    }
  });

  const intakeForm = $("#intake-form");
  intakeForm.addEventListener("change", () => exitTermsVerdict(intakeForm));
  intakeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const body = {
      display_name: form.elements.display_name.value.trim(),
      repository_url: form.elements.repository_url.value.trim(),
      requested_transport: form.elements.requested_transport.value,
      purpose: form.elements.purpose.value.trim(),
      exit_terms: {
        provider_credential_disclosure: form.elements.provider_credential_disclosure.checked,
        revocation_evidence: form.elements.revocation_evidence.checked,
        audit_access_retained: form.elements.audit_access_retained.checked,
      },
    };
    $$(".err", form).forEach((node) => { node.textContent = ""; });
    if (body.purpose.length < 10) {
      $('[data-err="purpose"]', form).textContent = "도입 목적을 10자 이상 적어주세요.";
      return;
    }
    const created = await act(() => api("/api/mcp-requests",
      { method: "POST", body: JSON.stringify(body) }), "도입 요청을 제출했습니다.");
    if (created) { form.reset(); $("#purpose-n").textContent = "0"; }
  });

  $("#scan-policy-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    $('[data-err="scan-policy"]').textContent = "";
    const body = {
      enabled: form.elements.enabled.checked,
      probe_mcp: form.elements.probe_mcp.checked,
      allowed_cidrs: csv(form.elements.allowed_cidrs.value),
      ports: csv(form.elements.ports.value).map(Number).filter((n) => n > 0 && n < 65536),
      max_hosts: Number(form.elements.max_hosts.value) || 256,
      connect_timeout_ms: Number(form.elements.connect_timeout_ms.value) || 300,
      interval_seconds: Number(form.elements.interval_seconds.value) || 900,
    };
    try {
      await api("/api/endpoint/scan-policy", { method: "PUT", body: JSON.stringify(body) });
      toast("탐색 범위를 저장했습니다. 에이전트가 다음 회전에서 받아 갑니다.");
      await refresh();
      loadEndpoints();
    } catch (error) {
      $('[data-err="scan-policy"]').textContent = error.message;
    }
  });

  $("#device-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    $('[data-err="device"]').textContent = "";
    const scopes = ["inventory", "netscan"].filter((name) => form.elements[name].checked);
    if (!scopes.length) {
      $('[data-err="device"]').textContent = "권한을 하나 이상 고르세요.";
      return;
    }
    try {
      const result = await api("/api/endpoint/devices", {
        method: "POST",
        body: JSON.stringify({
          endpoint_id: form.elements.endpoint_id.value.trim(),
          hostname: form.elements.hostname.value.trim(),
          platform: "unknown",
          owner_token: form.elements.owner_token.value || null,
          scopes,
        }),
      });
      const secret = $("#device-secret");
      secret.hidden = false;
      secret.textContent = `ENDPOINT_DEVICE_KEY=${result.enrollment_key}\n\n${result.note}`;
      await refresh();
      loadEndpoints();
    } catch (error) {
      $('[data-err="device"]').textContent = error.message;
    }
  });

  $("#ask-go").addEventListener("click", ask);
  $("#ask").addEventListener("keydown", (event) => { if (event.key === "Enter") ask(); });
}

/* ── 기동 ────────────────────────────────────────────────────────────────── */

(async function start() {
  const saved = localStorage.getItem("mcp-console-theme");
  if (saved) document.documentElement.dataset.theme = saved;
  if (!token()) { location.href = "/login"; return; }
  wire();
  await refresh();
  stream();
  setInterval(refresh, 30000);
})();
