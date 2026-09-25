import { mergeDecisions, reconcileSnapshot, streamPayload, filterDecisions, executionLabel, healthLabel } from "./console-state.mjs";

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
  mcpscan: "AI 코드 감사", endpoints: "엔드포인트", termination: "종료 / 폐기",
  policy: "정책", accounts: "신원", execution: "도구 실행", audit: "감사",
};
const PAGE_GROUPS = [
  ["집행", ["overview", "execution", "audit"]],
  ["도입 / 검증", ["intake", "verification", "risks", "mcpscan"]],
  ["자산 / 경로", ["endpoints", "termination"]],
  ["관리", ["policy", "accounts"]],
];

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const token = () => localStorage.getItem(TOKEN_KEY) || "";
const state = {
  console: null, page: null, scan: null, scanProbe: null, activeScanJob: null,
  endpoints: null, aig: null,
  seenDecision: 0, chat: [], session: null, findFilter: "all", termCase: null,
  refreshing: false, lastSync: null, stale: false, asking: false,
  feedPaused: false, frozenFeed: [], feedHTML: null, streamRendering: false,
  streamController: null, viewerKey: null,
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
    : at.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

function toast(message, tone = "good") {
  const value = typeof message === "string" ? message : "요청을 처리하지 못했습니다. 입력과 서비스 상태를 확인하세요.";
  if ($$("#toasts .toast").some((item) => item.textContent === value)) return;
  const node = document.createElement("div");
  node.className = "toast";
  node.dataset.tone = tone;
  node.setAttribute("role", tone === "bad" ? "alert" : "status");
  node.textContent = value;
  $("#toasts").append(node);
  while ($$("#toasts .toast").length > 3) $("#toasts .toast").remove();
  setTimeout(() => node.remove(), tone === "bad" ? 7000 : 4000);
}

function apiError(detail, status) {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const labels = { display_name: "표시 이름", repository_url: "저장소 URL",
      requested_transport: "전송 방식", purpose: "도입 목적", evidence_url: "증거 문서",
      note: "검증 메모" };
    return detail.map((item) => {
      const field = item.loc?.at(-1);
      return `${labels[field] || field || "입력"}: ${item.msg || "값을 확인하세요."}`;
    }).join(" · ");
  }
  if (detail && typeof detail === "object") return detail.message || detail.reason || `요청이 거절됐습니다 (HTTP ${status})`;
  return `요청이 거절됐습니다 (HTTP ${status})`;
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
  if (!response.ok) throw new Error(apiError(body.detail, response.status));
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
  const focused = node.contains(document.activeElement) ? document.activeElement : null;
  if (state.streamRendering && focused?.matches("button, a, input, select, textarea")) return;
  const focusId = focused?.id;
  const next = html || `<p class="empty">${esc(emptyText || "표시할 항목이 없습니다.")}</p>`;
  if (node.innerHTML !== next) {
    node.innerHTML = next;
    if (focusId) document.getElementById(focusId)?.focus();
  }
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
  const rail = $("#rail-links");
  const key = pages.join(",");
  if (rail.dataset.pages !== key) {
    rail.innerHTML = html;
    rail.dataset.pages = key;
  } else {
    $$("a", rail).forEach((link) => { $("em", link).textContent = badges[link.dataset.page] || ""; });
  }
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

function setNav(open, restore = false) {
  document.body.classList.toggle("nav-open", open);
  $("#nav-toggle").setAttribute("aria-expanded", String(open));
  $("#nav-scrim").hidden = !open;
  $("#main").inert = open;
  $(".topbar").inert = open;
  if (open) requestAnimationFrame(() => { if (document.body.classList.contains("nav-open")) $("#nav-close").focus(); });
  else if (restore) $("#nav-toggle").focus();
}

function show(page, focus = false) {
  const pages = state.console?.viewer?.pages || [];
  const target = pages.includes(page) ? page : pages[0];
  if (!target) return;
  const changed = state.page !== target;
  state.page = target;
  $$(".view").forEach((view) => { view.classList.toggle("on", view.dataset.view === target); });
  $$("#rail a").forEach((link) => {
    if (link.dataset.page === target) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  if (location.hash.slice(1) !== target) history[focus ? "pushState" : "replaceState"](null, "", "#" + target);
  document.title = `${PAGE_TITLES[target]} | MCP Governance`;
  $("#page-context").textContent = PAGE_TITLES[target];
  if (changed || focus) {
    setNav(false);
    if (focus) {
      const heading = $(`[data-view="${target}"] h1`);
      heading.tabIndex = -1;
      heading.focus();
      window.scrollTo({ top: 0, behavior: "instant" });
    }
    if (target === "mcpscan") loadScan();
    if (target === "endpoints") loadEndpoints();
    if (target === "risks") loadRiskCatalog();
  }
}

function accessibleRegions() {
  $$(".scroll").forEach((region) => {
    region.tabIndex = 0;
    region.setAttribute("role", "region");
    region.setAttribute("aria-label", `${region.closest(".block")?.querySelector("h2")?.textContent || "데이터 표"} 스크롤 영역`);
  });
}

/* ── 상단 ────────────────────────────────────────────────────────────────── */

function renderTop() {
  const data = state.console;
  const viewer = data.viewer;
  $("#who-name").textContent = viewer.name;
  $("#who-role").textContent = `${viewer.role_label}  /  ${viewer.department}`;

  const health = data.health || {};
  const wire = $("#wire");
  wire.dataset.state = health.status === "ok" ? "ok" : health.status === "degraded" ? "degraded" : "down";
  const down = Object.entries(health.components || {})
    .filter(([key, value]) => value === false && key !== "github_mcp").map(([key]) => key);
  $("b", wire).textContent = health.status === "ok" ? "Gateway 정상" : healthLabel(health);
  wire.title = down.length ? `응답 없는 서비스: ${down.join(", ")}` : healthLabel(health);

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
  const unconfirmed = decisions.filter((d) => d.upstream_attempted && !d.upstream_executed).length;

  fill($("#figures"), [
    figure("최근 판정", decisions.length, "최근 조회 최대 40건"),
    figure("Block 판정", blocked, "입력 또는 출력 정책 차단", blocked ? "bad" : ""),
    figure("승인 대기 기록", (data.approvals || []).length, "만료된 대기 기록 포함",
      (data.approvals || []).length ? "warn" : ""),
    figure("누적 실행 증적", data.upstream_effect_count ?? "-", "독립 효과 증적 기준 / 누적"),
    figure("실행 여부 미확인", unconfirmed, "시도했으나 완료 확인 없음",
      unconfirmed ? "warn" : ""),
  ].join(""));

  // 배너: 지금 사람이 해야 할 일이 있으면 그것만 말한다.
  const notes = [];
  if ((data.approvals || []).length) {
    notes.push(`승인 대기 기록 ${data.approvals.length}건이 있습니다. 만료된 요청이 포함될 수 있습니다.`);
  }
  const overdue = (data.termination?.cases || []).filter((c) => c.overdue).length;
  if (overdue) notes.push(`기한을 넘긴 종료 케이스 ${overdue}건이 있습니다.`);
  if (data.monitor?.enforcement === "monitor") {
    notes.push(`관찰 모드입니다. 지난 ${data.monitor.window_hours ?? 168}시간 동안 ${data.monitor.would_have_stopped ?? 0}건이 집행 모드였다면 막혔습니다.`);
  }
  const banner = $("#banner");
  banner.innerHTML = notes.length ? `<div>${notes.map(esc).join("<br />")}</div>` : "";
  banner.dataset.tone = overdue ? "bad" : notes.length ? "warn" : "";

  const pages = data.viewer.pages || [];
  const cards = [];
  const attentionCard = (title, count, note, page, outcome = "", verdict = "") =>
    `<article class="attention-card" data-tone="${count ? "warn" : "good"}"><div><span>${esc(title)}</span><strong>${count}</strong></div><p>${esc(note)}</p>${pages.includes(page) ? `<button class="link-btn" type="button" data-jump="${page}" data-outcome="${outcome}" data-verdict="${verdict}">기록 확인 →</button>` : ""}</article>`;
  cards.push(attentionCard("실행 여부 미확인", unconfirmed, "독립 실행 증적과 대조가 필요합니다.", "audit", "unconfirmed"));
  cards.push(attentionCard("종료 기한 초과", overdue, "회수 증적과 잔존 경로를 확인하세요.", "termination"));
  const drift = (data.registry || []).filter((item) => item.status !== "READY" && item.status !== "DISABLED").length;
  cards.push(attentionCard("MCP 상태 확인", drift, "등록 상태와 검증 증적을 살펴보세요.", "verification"));
  fill($("#attention"), cards.join(""));
  $("#feed-audit").hidden = !pages.includes("audit");

  // 분포
  const counts = Object.fromEntries(VERDICTS.map((v) => [v, 0]));
  decisions.forEach((d) => { if (counts[d.decision] !== undefined) counts[d.decision] += 1; });
  const max = Math.max(1, ...Object.values(counts));
  $("#dist-total").textContent = decisions.length;
  fill($("#dist"), VERDICTS.map((v) =>
    `<div class="bar"><b>${v}</b><progress data-v="${v}" value="${counts[v]}" max="${max}" aria-label="${v} ${counts[v]}건, 최다 ${max}건"></progress>
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
      <div class="item-sub">${esc(server.advertised_name || server.id)}  /  ${esc(server.endpoint || server.source_ref || "")}</div>
      <div class="item-note">${esc(server.status_reason || "")}</div>
      ${server.status === "DRIFT" ? `<div class="item-acts">
        <button class="btn" data-size="sm" data-reapprove="${esc(server.id)}">계약 재승인</button>
      </div>` : ""}
    </li>`;
  }).join(""), "등록된 서버가 없습니다.");

  renderEnforcement();
  renderFeed();
}

function renderEnforcement() {
  const monitor = state.console.monitor || {};
  const mode = monitor.enforcement;
  const badge = $("#enforce-tag");
  badge.textContent = mode === "enforce" ? "집행" : mode === "monitor" ? "관찰" : "상태 미확인";
  badge.dataset.tone = mode === "enforce" ? "good" : "warn";
  const isAdmin = (state.console.viewer.roles || []).includes("admin");
  if (!mode) { fill($("#enforce"), "<p class=empty>집행 모드 정보를 확인하지 못했습니다.</p>"); return; }
  fill($("#enforce"), `
    <p class="hintline no-top">
      ${mode === "enforce"
        ? "판정이 그대로 집행됩니다. 무결성 통제(MCP- / P-CONTROL- / P-INPUT- / P-RATE- / P-CHAIN-)는 관찰 모드에서도 항상 집행됩니다."
        : `관찰 모드입니다. 지난 ${monitor.window_hours ?? 168}시간 동안 ${monitor.would_have_stopped ?? 0}건이 집행 모드였다면 막혔고, ${monitor.affected_principals ?? 0}명이 영향을 받았습니다.`}
    </p>
    ${isAdmin ? `<div class="row space-top">
      <button class="btn" data-tone="${mode === "enforce" ? "" : "primary"}" id="enforce-toggle" type="button">
        ${mode === "enforce" ? "관찰 모드로" : "집행 모드로"}
      </button></div>` : ""}
    ${(monitor.breakdown || []).length ? `<div class="scroll space-top"><table>
      <thead><tr><th>가정 판정</th><th>정책</th><th>역할</th><th>도구</th><th class="num">건수</th></tr></thead>
      <tbody>${monitor.breakdown.slice(0, 10).map((row) => `<tr>
        <td>${verdictTag(row.would_decision)}</td><td class="id">${esc(row.would_policy_id)}</td>
        <td>${esc(row.role)}</td><td class="id">${esc(row.tool_name)}</td>
        <td class="num">${esc(row.calls)}</td></tr>`).join("")}</tbody></table></div>` : ""}`);
}

function renderFeed() {
  const rows = state.feedPaused ? state.frozenFeed : state.console?.decisions || [];
  const filtered = filterDecisions(rows, $("#feed-q").value, $("#feed-verdict").value);
  const last = rows[0];
  $("#process-current").textContent = last
    ? `최근 ${last.tool_name} / ${last.policy_id} / ${executionLabel(last)}` : "아직 판정이 없습니다.";
  const feedHTML = filtered.map((row) => `<li data-id="${esc(row.id)}">
    <time datetime="${esc(row.created_at)}">${clock(row.created_at)}</time>
    ${verdictTag(row.decision)}
    <span class="what"><strong>${esc(row.tool_name)}</strong><small>${esc(row.policy_id)} / ${esc(row.role || "")}</small></span>
    <span class="who-cell">${esc(executionLabel(row))}</span>
  </li>`).join("") || `<li class="empty">${rows.length ? "검색 조건에 맞는 판정이 없습니다. 필터를 초기화해 보세요." : "아직 판정이 없습니다. 도구 호출이 발생하면 이곳에 표시됩니다."}</li>`;
  if (state.feedHTML !== feedHTML) { $("#feed").innerHTML = feedHTML; state.feedHTML = feedHTML; }
  $("#strip").innerHTML = rows.map((row) => `<i data-v="${esc(row.decision)}" data-executed="${Boolean(row.upstream_executed)}"></i>`).join("");
  $("#stream-count").textContent = filtered.length;
  const pending = state.feedPaused ? (state.console?.decisions || []).filter((row) => Number(row.id) > Number(rows[0]?.id || 0)).length : 0;
  const summary = `${filtered.length} / ${rows.length}건 표시${state.feedPaused ? ` / 목록 일시정지${pending ? ` / 새 판정 ${pending}건` : ""}` : " / 최신순"}`;
  if ($("#feed-summary").textContent !== summary) $("#feed-summary").textContent = summary;
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
    const terms = row.exit_terms || {};
    const remote = row.requested_transport !== "stdio";
    const verified = Boolean(terms.verified_by && terms.evidence_url &&
      ["provider_credential_disclosure", "revocation_evidence", "audit_access_retained"]
        .every((key) => terms[key] === true));
    const pending = ["HOLD", "VALIDATION_QUEUED", "VALIDATING", "VALIDATED"].includes(row.status);
    return `<li>
      <div class="item-top"><b>${esc(row.display_name)}</b>${tag(row.status)}
        <span class="spacer"></span><span class="item-sub">${when(row.validated_at || row.created_at)}</span></div>
      <div class="item-sub">${esc(row.repository_url)}</div>
      <div class="item-note">${remote ? (verified
        ? `종료 조건 확인 · ${esc(terms.verified_by)} · ${when(terms.verified_at)}`
        : "종료 조건 확인 대기 · 플랫폼 담당자 작업") : "로컬 실행 · 제공자 자격 확인 불필요"}</div>
      ${Object.keys(evidence).length ? `<div class="tags evidence-tags">${
        Object.entries(evidence).slice(0, 6).map(([key, value]) =>
          tag(`${key}=${typeof value === "object" ? "…" : value}`)).join("")}</div>` : ""}
      <div class="item-acts">
        ${row.status === "HOLD" ? `<button class="btn" data-intake-queue="${esc(row.id)}">공급망 검사 시작</button>` : ""}
        ${row.status === "VALIDATED" ? `<button class="btn" data-tone="primary" data-intake-approve="${esc(row.id)}"
          ${remote && !verified ? "disabled title='플랫폼 종료 조건 확인이 필요합니다'" : ""}>승인</button>` : ""}
        ${pending ? `<button class="btn" data-intake-reject="${esc(row.id)}">반려</button>` : ""}
      </div>
      ${remote && pending ? `<details class="review"><summary>플랫폼 종료 조건 검증</summary>
        <form data-terms-form="${esc(row.id)}">
          <p class="hintline">신청자 진술은 증거가 아닙니다. 제공자 계약 또는 검증 가능한 문서를 확인하고 기록하세요.</p>
          <label class="field"><span>증거 문서 HTTPS 주소</span><input name="evidence_url" type="url" required
            value="${esc(terms.evidence_url || "")}" placeholder="https://..." /></label>
          <label class="field"><span>확인 내용</span><textarea name="note" minlength="10" required
            placeholder="누가 어떤 조항을 확인했는지 기록">${esc(terms.note || "")}</textarea></label>
          <label class="check"><input type="checkbox" name="provider_credential_disclosure" ${terms.provider_credential_disclosure ? "checked" : ""} />하위 위임 자격 고지 조항 확인</label>
          <label class="check"><input type="checkbox" name="revocation_evidence" ${terms.revocation_evidence ? "checked" : ""} />회수 결과 증거 제공 조항 확인</label>
          <label class="check"><input type="checkbox" name="audit_access_retained" ${terms.audit_access_retained ? "checked" : ""} />종료 후 감사 접근 조항 확인</label>
          <button class="btn" type="submit">검증 기록 저장</button>
        </form></details>` : ""}
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
    `<button class="tag" data-filter="${esc(name)}" aria-pressed="${state.findFilter === name}"${state.findFilter === name ? ' data-tone="info"' : ""}>
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
        `${esc(f.severity || f.level || "")}  /  ${esc(f.title || f.id || f.ruleId || "")}`).join("<br />")}</div>` : ""}
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

function scanError(error) {
  const message = String(error || "");
  const timeout = message.match(/timed out after (\d+) seconds/);
  return timeout ? `검사 제한 시간 ${timeout[1]}초를 초과했습니다. 모델 응답 속도와 설정을 확인하세요.` : message;
}

async function loadScan() {
  const viewerKey = state.viewerKey;
  try {
    const result = await api("/api/mcp-scan");
    if (viewerKey !== state.viewerKey || !state.console.viewer.pages.includes("mcpscan")) return;
    state.scan = result;
  } catch (error) { toast(error.message, "bad"); return; }
  const { config, worker, jobs, reports, targets, servers } = state.scan;
  const badge = $("#scan-state");
  const ready = Boolean(config.configured && worker.alive && state.scanProbe?.ready_for_scan);
  const completed = (jobs || []).some((job) => job.status === "DONE");
  const failed = (jobs || []).find((job) => job.status === "FAILED");
  badge.textContent = !config.configured ? "모델 미설정" : !worker.alive ? "검사 워커 중단"
    : completed ? "실제 검사 완료" : failed ? "검사 실패 확인" : ready ? "모델 연결 확인" : "연결 미확인";
  badge.dataset.tone = completed ? "good" : failed ? "bad" : "warn";
  $("#scan-test").disabled = !config.configured;
  const banner = $("#scan-readiness");
  banner.dataset.tone = failed && !completed ? "bad" : ready ? "info" : "warn";
  const active = (jobs || []).find((job) => String(job.id) === state.activeScanJob);
  banner.textContent = !config.configured
    ? "AI 검사가 준비되지 않았습니다. 플랫폼 운영자가 검사 모델을 연결해야 합니다. 기본 설치의 Gateway 정상 표시는 AI 검사 준비를 뜻하지 않습니다."
    : !worker.alive ? "검사 워커가 응답하지 않습니다. 작업을 실행할 수 없습니다."
    : active ? `최근 요청: ${active.target_label || active.target_id} · ${active.status}${active.status === "DONE" ? ` · 발견 ${active.summary?.total ?? 0}건` : ""}${active.error ? ` · ${scanError(active.error)}` : ""}`
    : failed && !completed ? "모델 연결과 실제 검사 성공은 다릅니다. 아래 실패 원인을 확인하고, 검사에 적합한 모델 또는 처리 시간을 설정하세요."
    : ready ? "모델과 워커 연결을 확인했습니다. 실제 검사 성공은 작업 이력에서 확인하세요."
    : "모델 설정은 있지만 실제 연결을 확인하지 않았습니다. ‘연결 확인’을 먼저 실행하세요.";

  fill($("#scan-config"), `
    <p class="hintline no-top">${config.configured
      ? `모델 endpoint가 설정돼 있습니다. 키는 화면에 나오지 않습니다.`
      : `설정이 필요합니다: ${esc((config.missing || []).join(", "))}`}</p>
    <table><tbody>
      <tr><td>Base URL</td><td class="id">${esc(config.base_url || "-")}</td></tr>
      <tr><td>모델</td><td class="id">${esc(config.model || "-")}</td></tr>
      <tr><td>모델 주소</td><td>${config.local ? tag("로컬 주소", "good") : tag("외부 주소", "warn")}</td></tr>
      <tr><td>검사 증적</td><td>${tag(config.evidence_mode === "advisory" ? "참고용  /  자동 차단 없음" : config.evidence_mode || "-")}</td></tr>
    </tbody></table>`);

  fill($("#scan-worker"), `
    <p class="hintline no-top">${worker.alive
      ? `워커 ${esc(worker.worker || "")}가 살아 있습니다.`
      : "격리 워커의 생존 신호가 없습니다. 큐에 넣어도 실행되지 않습니다."}</p>
    <table><tbody>
      <tr><td>마지막 신호</td><td class="id">${when(worker.seen_at, true)}</td></tr>
      <tr><td>대기</td><td class="num">${esc(worker.queued ?? 0)}</td></tr>
      <tr><td>실행 중</td><td class="num">${esc(worker.running ?? 0)}</td></tr>
    </tbody></table>`);

  const intakeItems = (targets || []).map((row) => `<li>
    <div class="item-top"><b>${esc(row.display_name)}</b>${tag("도입 요청")}
      ${row.last_status ? tag(row.last_status, row.last_status === "DONE" ? "good" : "warn") : ""}
      <span class="spacer"></span><span class="item-sub">${esc(String(row.commit_sha || "").slice(0, 12))}</span></div>
    <div class="item-sub">${esc(row.repository_url)}</div>
    <div class="item-acts">
      <button class="btn" data-size="sm" data-scan="intake" data-id="${esc(row.id)}" data-mode="static" ${ready ? "" : "disabled"}>정적 감사</button>
    </div></li>`).join("");

  const serverItems = (servers || []).map((row) => `<li>
    <div class="item-top"><b>${esc(row.display_name)}</b>${tag("등록 서버")}
      ${tag(row.status, row.status === "READY" ? "good" : "warn")}
      ${row.last_status ? tag(row.last_status, row.last_status === "DONE" ? "good" : "warn") : ""}</div>
    <div class="item-sub">${esc(row.source_url || row.endpoint || "")}</div>
    <div class="item-acts">
      <button class="btn" data-size="sm" data-scan="server" data-id="${esc(row.id)}" data-mode="static"
        ${ready && row.scannable ? "" : "disabled title='연결 검증 또는 코드 출처가 필요합니다'"}>정적 감사</button>
      <button class="btn" data-size="sm" data-scan="server" data-id="${esc(row.id)}" data-mode="dynamic"
        ${ready && row.probeable ? "" : "disabled title='연결 검증 또는 HTTP endpoint가 필요합니다'"}>동적 점검</button>
    </div></li>`).join("");
  fill($("#scan-targets"), intakeItems + serverItems, "감사할 대상이 없습니다.");

  $("#scan-job-n").textContent = (jobs || []).length;
  const jobTone = { DONE: "good", FAILED: "bad", CANCELLED: "", RUNNING: "info", QUEUED: "warn" };
  fill($("#scan-jobs"), (jobs || []).map((job) => `<li>
    <div class="item-top"><b>${esc(job.target_label || job.target_id)}</b>
      ${tag(job.status, jobTone[job.status] || "")}${tag(job.mode)}${tag(job.target_kind)}
      <span class="spacer"></span><span class="item-sub">${when(job.created_at, true)}</span></div>
    <div class="item-sub">작업 ID ${esc(job.id)} · ${esc(job.source_ref || (job.mode === "dynamic" ? "실행 중인 MCP endpoint 점검" : "코드 출처 확인 중"))}</div>
    ${job.status === "DONE" ? `<div class="item-note">발견 ${esc(job.summary?.total ?? 0)}건 · 증거 유형 ${esc(job.summary?.evidence_mode || "미표기")}</div>` : ""}
    ${job.error ? `<div class="item-note" role="alert">실패 원인: ${esc(scanError(job.error))}</div>` : ""}
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
        ${summary.blocks_calls ? tag("호출 차단으로 이어짐", "bad") : tag("증적만")}
        <span class="spacer"></span><span class="item-sub">${when(row.imported_at)}</span></div>
      ${(summary.findings || []).slice(0, 5).map((f) =>
        `<div class="item-note">${esc(f.severity || "")}  /  ${esc(f.title || f.id || "")}</div>`).join("")}
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
  if (form.dataset.dirty !== "true") {
  form.elements.enabled.checked = !!policy.enabled;
  form.elements.probe_mcp.checked = policy.probe_mcp !== false;
  form.elements.allowed_cidrs.value = (policy.allowed_cidrs || []).join(", ");
  form.elements.ports.value = (policy.ports || []).join(", ");
  form.elements.max_hosts.value = policy.max_hosts ?? 256;
  form.elements.connect_timeout_ms.value = policy.connect_timeout_ms ?? 300;
  form.elements.interval_seconds.value = policy.interval_seconds ?? 900;

  }
  if ($("#device-form").dataset.dirty !== "true") {
  const owners = (state.console.principals || []).map((p) =>
    `<option value="${esc(p.token || "")}">${esc(p.display_name)} (${esc(p.role)})</option>`).join("");
  $("#device-owner").innerHTML = `<option value="">(소유자 없음)</option>` + owners;
  }

  fill($("#device-list"), (data.devices || []).map((device) => `<li>
    <div class="item-top"><b>${esc(device.endpoint_id)}</b>
      ${tag(device.status, device.status === "active" ? "good" : "bad")}
      ${(device.scopes || []).map((s) => tag(s, "info")).join("")}
      <span class="spacer"></span><span class="item-sub">마지막 보고 ${when(device.last_seen_at, true)}</span></div>
    <div class="item-sub">${esc(device.hostname)}  /  ${esc(device.platform)}  /  agent ${esc(device.agent_version)}
       /  소유 ${esc(device.owner_name || device.owner_token || "미지정")}</div>
    <div class="item-note">설정 섀도 ${esc(device.config_shadow ?? 0)}
       /  관측 리스너 ${esc(device.listeners_seen ?? 0)} (섀도 ${esc(device.listener_shadow ?? 0)})</div>
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

/* ── 종료 / 폐기 ───────────────────────────────────────────────────────────── */

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
    <table class="space-top"><thead><tr><th>기준</th><th>충족</th><th>근거</th></tr></thead><tbody>
      ${["C1", "C2", "C3", "C4"].map((key) => {
        const item = criteria[key] || {};
        return `<tr><td class="id">${key}</td>
          <td>${item.met ? tag("충족", "good") : tag("미충족", "bad")}</td>
          <td>${esc(item.note || item.reason || "")}</td></tr>`;
      }).join("")}
    </tbody></table>
    <h3 class="term-target-heading">회수 대상 ${(detail.targets || []).length}건</h3>
    <div class="scroll target-list"><table><tbody>
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

  const auth = ledger.authorization || {};
  fill($("#matrix"), `<div class="notice" data-tone="warn">현재 ${esc(auth.bundle_id || "미설정")}은 합성 실습용 권한 번들입니다. 조직의 승인된 권한 정책을 배포하기 전에는 운영 권한 기준으로 사용하지 마세요.</div>
    <ul class="items">${(auth.grants || []).map((grant) => `<li>
      <div class="item-top"><b>${esc(grant.id)}</b>${tag((grant.actions || []).join(", "))}</div>
      <div class="item-sub">역할 ${(grant.roles || []).map(esc).join(", ")} · 데이터 ${(grant.data_classes || []).map(esc).join(", ")}</div>
    </li>`).join("")}</ul>`, "배포된 권한 규칙이 없습니다. 기본 차단됩니다.");

  renderPolicyTable();
  $("#exc-n").textContent = (ledger.exceptions || []).length;
  fill($("#exc-list"), (ledger.exceptions || []).map((exc) => `<li>
    <div class="item-top"><b>${esc(exc.id)} ${esc(exc.title)}</b>
      ${tag(exc.policy_id, "info")}${tag(exc.effect)}${tag(exc.status, exc.status === "적용" ? "warn" : "")}
      <span class="spacer"></span><span class="item-sub">~ ${when(exc.valid_until)}</span></div>
    <div class="item-note">${esc(exc.reason || "")}</div>
    <div class="item-note">보완통제: ${esc((exc.compensating_controls || []).join("  /  "))}</div>
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
  const viewerKey = state.viewerKey;
  let data;
  try { data = await api("/api/accounts"); } catch (error) { toast(error.message, "bad"); return; }
  if (viewerKey !== state.viewerKey || !state.console.viewer.pages.includes("accounts")) return;
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
        <select aria-label="${esc(row.display_name)} 계정 상태" data-account="${esc(row.user_id)}">
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
  if (!message || state.asking) return;
  state.asking = true;
  input.value = "";
  state.chat.push({ who: "user", text: message, at: new Date().toISOString() });
  renderExecution();
  const button = $("#ask-go");
  button.disabled = true;
  button.textContent = "처리 중…";
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
    state.asking = false;
    button.disabled = false;
    button.textContent = "보내기";
    renderExecution();
    refresh();
  }
}

/* ── 감사 ────────────────────────────────────────────────────────────────── */

function renderAudit() {
  const query = ($("#audit-q")?.value || "").toLowerCase();
  const rows = filterDecisions(state.console.decisions || [], query,
    $("#audit-verdict").value, $("#audit-outcome").value);
  $("#audit-table").innerHTML = `
    <thead><tr><th>시각</th><th>판정</th><th>정책</th><th>주체</th><th>도구</th><th>등급</th><th>실행</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td class="id">${when(row.created_at, true)}</td>
      <td>${verdictTag(row.decision)}</td>
      <td class="id">${esc(row.policy_id)}</td>
      <td>${esc(row.user_token)}<div class="item-sub">${esc(row.role || "")}</div></td>
      <td class="id">${esc(row.tool_name)}</td>
      <td>${esc(row.data_class || "-")}</td>
      <td>${row.upstream_executed ? tag(executionLabel(row), row.decision === "Block" ? "bad" : "good")
        : row.upstream_attempted ? tag("실행 여부 미확인", "bad") : tag("미실행", "good")}</td>
    </tr>`).join("") || emptyRow("조건에 맞는 판정 기록이 없습니다. 검색어와 필터를 확인하세요.", 7)}</tbody>`;
}

/* ── 실시간 ──────────────────────────────────────────────────────────────── */

async function stream() {
  const controller = new AbortController();
  state.streamController?.abort();
  state.streamController = controller;
  const wire = $("#stream-wire");
  while (!controller.signal.aborted) {
    let reader;
    try {
      wire.dataset.state = "";
      $("b", wire).textContent = "연결 중";
      const response = await fetch(`/api/stream/decisions?after=${state.seenDecision}`, {
        headers: { authorization: "Bearer " + token() }, signal: controller.signal,
      });
      if (response.status === 401) {
        localStorage.removeItem(TOKEN_KEY);
        location.href = "/login";
        return;
      }
      if (!response.ok || !response.body) throw new Error("stream unavailable");
      wire.dataset.state = "ok";
      $("b", wire).textContent = "실시간 연결";
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (!controller.signal.aborted) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split(/\r?\n\r?\n/);
        buffer = frames.pop() || "";
        for (const frame of frames) {
          const data = frame.split(/\r?\n/).filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
          if (!data) continue;
          let payload;
          try { payload = streamPayload(JSON.parse(data)); } catch { continue; }
          if (!payload.rows.length || controller.signal.aborted || !state.console) continue;
          state.seenDecision = Math.max(state.seenDecision, payload.cursor);
          state.console.decisions = mergeDecisions(state.console.decisions || [], payload.rows);
          state.streamRendering = true;
          try {
            if (state.console.viewer.pages.includes("overview")) renderOverview();
            if (state.console.viewer.pages.includes("audit")) renderAudit();
          } finally { state.streamRendering = false; }
        }
      }
    } catch (error) {
      if (controller.signal.aborted) return;
    } finally {
      if (reader) { await reader.cancel().catch(() => {}); reader.releaseLock(); }
    }
    if (controller.signal.aborted) return;
    wire.dataset.state = "down";
    $("b", wire).textContent = "재연결 중";
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
}

/* ── 새로고침 ────────────────────────────────────────────────────────────── */

async function refresh({ automatic = false } = {}) {
  if (state.refreshing || (automatic && document.hidden)) return;
  // Do not replace a focused action or a form that someone is editing.
  if (automatic && document.activeElement?.closest(".main button, .main input, .main select, .main textarea")) return;
  const requestCursor = state.seenDecision;
  state.refreshing = true;
  const button = $("#refresh");
  button.disabled = true;
  button.textContent = "갱신 중…";
  $("#sync-info").textContent = "운영 데이터를 불러오는 중입니다.";
  try {
    const data = await api("/api/console");
    const key = JSON.stringify([data.viewer.user_id, data.viewer.roles, data.viewer.pages]);
    const changedViewer = state.viewerKey !== null && state.viewerKey !== key;
    if (changedViewer) {
      state.streamController?.abort();
      state.seenDecision = 0;
      state.frozenFeed = [];
      state.feedHTML = null;
      state.feedPaused = false;
      $("#feed-pause").setAttribute("aria-pressed", "false");
      $("#feed-pause").textContent = "목록 일시정지";
      $$(".view").filter((view) => !data.viewer.pages.includes(view.dataset.view)).forEach((view) => {
        $$(".items, .figures, .feed, .bars, .talk, table, #enforce, #attention, #term-detail, #scan-config, #scan-worker", view).forEach((node) => { node.replaceChildren(); });
      });
      state.aig = null; state.scan = null; state.endpoints = null; state.termCase = null;
      state.chat = [];
      state.session = null;
    }
    const rows = data.decisions || [];
    data.decisions = reconcileSnapshot(changedViewer ? [] : state.console?.decisions || [], rows, requestCursor);
    state.console = data;
    state.viewerKey = key;
    const pages = data.viewer.pages || [];
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
    $("#verify-chain").hidden = !data.viewer.roles.includes("admin");
    if (pages.includes("accounts")) renderAccounts();
    if (state.page === "endpoints" && pages.includes("endpoints")) loadEndpoints();
    show(state.page || location.hash.slice(1) || pages[0]);
    accessibleRegions();
    state.seenDecision = Math.max(state.seenDecision, ...data.decisions.map((row) => Number(row.id)));
    state.lastSync = new Date().toISOString();
    state.stale = false;
    $("#sync-error").hidden = true;
    $("#sync-info").textContent = `마지막 갱신 ${clock(state.lastSync)} / 30초마다 자동 갱신`;
    if ((pages.includes("overview") || pages.includes("audit")) && (!state.streamController || changedViewer)) stream();
  } catch (error) {
    state.stale = true;
    $("#sync-error").hidden = false;
    $("#sync-error").textContent = `${state.lastSync ? "갱신하지 못했습니다. 이전 데이터를 표시합니다." : "운영 데이터를 불러오지 못했습니다."} ${error.message} 새로고침으로 다시 시도하세요.`;
    $("#sync-info").textContent = state.lastSync ? `마지막 성공 ${clock(state.lastSync)} / 최신 정보가 아닐 수 있습니다.` : "데이터 확인 필요";
  } finally {
    state.refreshing = false;
    button.disabled = false;
    button.textContent = "새로고침";
  }
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
  addEventListener("hashchange", () => {
    if (location.hash === "#main") { $("#main").focus(); return; }
    show(location.hash.slice(1), true);
  });
  matchMedia("(max-width: 900px)").addEventListener("change", () => setNav(false));
  $("#nav-toggle").addEventListener("click", () => setNav(!document.body.classList.contains("nav-open")));
  ["#nav-close", "#nav-scrim"].forEach((id) => $(id).addEventListener("click", () => setNav(false, true)));
  document.addEventListener("keydown", (event) => {
    if (!document.body.classList.contains("nav-open")) return;
    if (event.key === "Escape") { setNav(false, true); return; }
    if (event.key === "Tab") {
      const items = $$("#rail button, #rail a");
      const first = items[0], last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  $(".skip-link").addEventListener("click", (event) => {
    event.preventDefault(); $("#main").focus();
  });
  $("#feed-q").addEventListener("input", renderFeed);
  $("#feed-verdict").addEventListener("change", renderFeed);
  $("#feed-reset").addEventListener("click", () => {
    $("#feed-q").value = ""; $("#feed-verdict").value = "all"; renderFeed(); $("#feed-q").focus();
  });
  $("#feed-pause").addEventListener("click", () => {
    state.feedPaused = !state.feedPaused;
    state.frozenFeed = state.feedPaused ? [...(state.console?.decisions || [])] : [];
    $("#feed-pause").setAttribute("aria-pressed", String(state.feedPaused));
    $("#feed-pause").textContent = state.feedPaused ? "목록 재개" : "목록 일시정지";
    renderFeed();
  });
  $("#feed-audit").addEventListener("click", () => {
    $("#audit-q").value = $("#feed-q").value;
    $("#audit-verdict").value = $("#feed-verdict").value;
    $("#audit-outcome").value = "all";
    renderAudit(); show("audit", true);
  });
  ["#audit-verdict", "#audit-outcome"].forEach((id) => $(id).addEventListener("change", renderAudit));
  ["#scan-policy-form", "#device-form"].forEach((id) => {
    ["input", "change"].forEach((type) => $(id).addEventListener(type, () => { $(id).dataset.dirty = "true"; }));
  });

  document.addEventListener("click", async (event) => {
    const link = event.target.closest("#rail a");
    if (link) { event.preventDefault(); show(link.dataset.page, true); return; }

    const target = event.target.closest("button") || event.target;
    const jump = target.closest("[data-jump]");
    if (jump && state.console.viewer.pages.includes(jump.dataset.jump)) {
      if (jump.dataset.jump === "audit") {
        $("#audit-q").value = "";
        $("#audit-verdict").value = jump.dataset.verdict || "all";
        $("#audit-outcome").value = jump.dataset.outcome || "all";
        renderAudit();
      }
      show(jump.dataset.jump, true); return;
    }
    const intakeQueue = target.closest("[data-intake-queue]");
    if (intakeQueue) await act(() => api(`/api/mcp-requests/${intakeQueue.dataset.intakeQueue}/queue-validation`,
      { method: "POST" }), (r) => r.message);
    const intakeApprove = target.closest("[data-intake-approve]");
    if (intakeApprove) await act(() => api(`/api/mcp-requests/${intakeApprove.dataset.intakeApprove}/approve`,
      { method: "POST" }), (r) => r.message);
    const intakeReject = target.closest("[data-intake-reject]");
    if (intakeReject) {
      const note = prompt("반려 근거를 기록하세요 (2자 이상).");
      if (note && note.trim().length >= 2) await act(() => api(
        `/api/mcp-requests/${intakeReject.dataset.intakeReject}/reject`,
        { method: "POST", body: JSON.stringify({ note: note.trim() }) }), (r) => r.message);
    }
    if (target.id === "catalog-refresh") {
      await act(() => api("/api/registry/refresh", { method: "POST" }), "Catalog를 다시 대조했습니다.");
    } else if (target.id === "enforce-toggle") {
      const next = state.console.monitor?.enforcement === "enforce" ? "monitor" : "enforce";
      if (!confirm(`${next === "monitor" ? "관찰 모드로 바꾸면 일부 정책은 실행을 차단하지 않습니다." : "집행 모드로 바꾸면 정책 판정에 따라 실행이 차단됩니다."} 변경하시겠습니까?`)) return;
      await act(() => api("/api/enforcement", { method: "PUT", body: JSON.stringify({ mode: next }) }),
        `집행 모드를 ${next === "enforce" ? "집행" : "관찰"}로 바꿨습니다.`);
    } else if (target.id === "import-evidence") {
      await act(() => api("/api/supply-chain/import", { method: "POST" }), "워크스페이스 증적을 반영했습니다.");
    } else if (target.id === "verify-chain") {
      const result = await api("/api/audit/verify").catch((e) => ({ error: e.message }));
      const node = $("#chain-out");
      node.dataset.tone = result.intact ? "" : "bad";
      node.innerHTML = `<div>${result.error ? esc(result.error)
        : result.intact ? `연쇄 정상  /  ${esc(result.checked)}건 확인`
        : `연쇄 불일치  /  ${esc(result.reason || "")} (id ${esc(result.broken_at ?? "?")})`}</div>`;
    } else if (target.id === "scan-test") {
      try {
        state.scanProbe = await api("/api/mcp-scan/connection-test", { method: "POST" });
        toast(state.scanProbe.message, state.scanProbe.ready_for_scan ? "good" : "bad");
      } catch (error) {
        state.scanProbe = null;
        toast(error.message, "bad");
      }
      await loadScan();
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
      $("#device-form input").focus();
    } else if (target.id === "device-cancel") {
      $("#device-form-wrap").hidden = true;
      $("#device-secret").hidden = true;
      $("#device-new").focus();
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
        state.activeScanJob = result.job_id;
        toast("검사 작업을 등록했습니다. 아래 작업 이력에서 진행 상태를 확인할 수 있습니다.");
      } catch (error) {
        if (error.message.includes("외부")) {
          if (confirm(error.message + "\n\n그래도 실행하시겠습니까?")) {
            body.acknowledge_external_model = true;
            const result = await act(() => api("/api/mcp-scan/run", { method: "POST", body: JSON.stringify(body) }),
              "검사 작업을 등록했습니다. 작업 이력에서 진행 상태를 확인하세요.");
            if (result) state.activeScanJob = result.job_id;
          }
        } else { toast(error.message, "bad"); }
      }
      await loadScan();
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

  $("#verify-list").addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-terms-form]");
    if (!form) return;
    event.preventDefault();
    const body = {
      evidence_url: form.elements.evidence_url.value.trim(),
      note: form.elements.note.value.trim(),
      provider_credential_disclosure: form.elements.provider_credential_disclosure.checked,
      revocation_evidence: form.elements.revocation_evidence.checked,
      audit_access_retained: form.elements.audit_access_retained.checked,
    };
    await act(() => api(`/api/mcp-requests/${form.dataset.termsForm}/exit-terms`,
      { method: "PUT", body: JSON.stringify(body) }), (r) => r.message);
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
  intakeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    if (form.dataset.busy === "true" || !form.reportValidity()) return;
    const body = {
      display_name: form.elements.display_name.value.trim(),
      repository_url: form.elements.repository_url.value.trim(),
      requested_transport: form.elements.requested_transport.value,
      purpose: form.elements.purpose.value.trim(),
    };
    $$(".err", form).forEach((node) => { node.textContent = ""; });
    if (body.purpose.length < 10) {
      $('[data-err="purpose"]', form).textContent = "도입 목적을 10자 이상 적어주세요.";
      form.elements.purpose.setAttribute("aria-invalid", "true");
      form.elements.purpose.focus();
      return;
    }
    form.elements.purpose.removeAttribute("aria-invalid");
    form.dataset.busy = "true";
    $("button[type=submit]", form).disabled = true;
    const created = await act(() => api("/api/mcp-requests",
      { method: "POST", body: JSON.stringify(body) }), (r) => r.message);
    form.dataset.busy = "false";
    $("button[type=submit]", form).disabled = false;
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
      form.dataset.dirty = "false";
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
  $("#ask").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); ask(); } });
}

/* ── 기동 ────────────────────────────────────────────────────────────────── */

(async function start() {
  const saved = localStorage.getItem("mcp-console-theme");
  if (["dark", "light"].includes(saved)) document.documentElement.dataset.theme = saved;
  if (!token()) { location.href = "/login"; return; }
  wire();
  await refresh();
  setInterval(() => refresh({ automatic: true }), 30000);
  setInterval(() => {
    if (state.page === "mcpscan" && state.scan?.jobs?.some((job) =>
      ["QUEUED", "RUNNING"].includes(job.status))) loadScan();
  }, 5000);
})();
