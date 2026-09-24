// The server scopes these rows to the authenticated viewer. Never widen that scope here.
export const DECISION_LIMIT = 40;

export function mergeDecisions(current, incoming, limit = DECISION_LIMIT) {
  const rows = new Map();
  for (const row of [...current, ...incoming]) {
    const id = Number(row?.id);
    if (Number.isSafeInteger(id) && id > 0) rows.set(id, row);
  }
  return [...rows.values()].sort((a, b) => Number(b.id) - Number(a.id)).slice(0, limit);
}

// A snapshot may have started before the first SSE row arrived, including an empty database.
export function reconcileSnapshot(current, incoming, requestCursor) {
  const snapshotMax = Math.max(0, ...incoming.map((row) => Number(row?.id) || 0));
  const newer = current.filter((row) => Number(row?.id) > (snapshotMax || requestCursor));
  return mergeDecisions(newer, incoming);
}

export function streamPayload(payload) {
  const rows = Array.isArray(payload) ? payload : payload?.rows ?? payload?.decisions ?? [];
  const valid = mergeDecisions([], Array.isArray(rows) ? rows : []);
  return { rows: valid, cursor: Math.max(0, ...valid.map((row) => Number(row.id))) };
}

export function filterDecisions(rows, query = "", verdict = "all", outcome = "all") {
  const term = query.trim().toLocaleLowerCase();
  return rows.filter((row) => (verdict === "all" || row.decision === verdict)
    && (outcome !== "unconfirmed" || (row.upstream_attempted && !row.upstream_executed))
    && (!term || [row.tool_name, row.policy_id, row.user_token, row.role, row.trace_id]
      .some((value) => String(value ?? "").toLocaleLowerCase().includes(term))));
}

export function executionLabel(row) {
  if (row.upstream_executed) return row.decision === "Block" ? "실행 후 출력 차단" : "실행 확인";
  if (row.upstream_attempted) return "실행 여부 미확인";
  return row.decision === "Approval" ? "승인 대기 / 미실행" : "미실행";
}

export function healthLabel(health = {}) {
  switch (health?.status) {
    case "ok": return "정상";
    case "degraded": return "일부 서비스 저하";
    case "down": return "연결 장애";
    default: return "상태 미확인";
  }
}
