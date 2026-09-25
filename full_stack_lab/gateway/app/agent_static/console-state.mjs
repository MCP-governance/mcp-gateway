// Activity-feed state, kept free of the DOM so `node --test` can check it
// (full_stack_lab/tests/console-state.test.mjs). The server already scopes rows to
// the signed-in viewer; nothing here may widen that.
export const FEED_LIMIT = 500;

/** Newest first, one row per numeric id. A poll that overlaps a page load must not
 * show a call twice, and a malformed row must not push a real decision out. */
export function mergeRows(current, incoming, limit = FEED_LIMIT) {
  const rows = new Map();
  for (const row of [...(current || []), ...(incoming || [])]) {
    const id = Number(row?.id);
    if (Number.isSafeInteger(id) && id > 0) rows.set(id, row);
  }
  return [...rows.values()].sort((a, b) => Number(b.id) - Number(a.id)).slice(0, limit);
}

const SEARCHED = ["who", "department", "workstation", "server", "tool", "target", "policy_id", "trace_id", "reason"];

/** Search over what is already loaded: person, PC, tool, target, policy or trace id. */
export function searchRows(rows, query = "") {
  const term = String(query).trim().toLocaleLowerCase();
  if (!term) return rows;
  return rows.filter((row) => SEARCHED.some((key) => String(row?.[key] ?? "").toLocaleLowerCase().includes(term))
    || `${row?.server}.${row?.tool}`.toLocaleLowerCase().includes(term));
}

const pad = (n) => String(n).padStart(2, "0");
const clock = (t) => { const d = new Date(t); return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; };

/** One status sentence. It never calls a view fresh after a failed poll. */
export function liveLabel({ live, lastOk = 0, failing = false, pending = 0 }) {
  if (failing) return `갱신 실패 — ${lastOk ? `마지막 성공 ${clock(lastOk)}, ` : ""}화면이 최신이 아닐 수 있습니다. 자동으로 다시 시도합니다.`;
  if (!live) return `일시정지${pending ? ` · 새 판정 ${pending}건 대기` : ""}`;
  return lastOk ? `실시간 · ${clock(lastOk)} 확인` : "실시간 · 연결 중";
}
