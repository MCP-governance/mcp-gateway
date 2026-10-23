// Screen language. Korean is the source text; English is a dictionary (i18n-en.mjs) applied
// after each render, so every render path (innerHTML, textContent, dialogs, attributes) is
// covered without wrapping each string. The dictionary is loaded only in English.
export const LANG_KEY = "mcp-console-lang";
const HANGUL = /[가-힣]/;
const ATTRS = ["placeholder", "title", "aria-label", "alt"];
const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "PRE"]);
const SEPARATORS = [" · ", ", ", " / ", " | "];
const PLAIN = "([^가-힣]+?)";

export function lang() {
  try { return localStorage.getItem(LANG_KEY) === "en" ? "en" : "ko"; } catch { return "ko"; }
}
export const locale = () => (lang() === "en" ? "en-US" : "ko-KR");
/** Clock and date text in the screen language; English uses a 24-hour clock. */
export const clockText = (date, options = {}) => date.toLocaleTimeString(locale(), lang() === "en" ? { hourCycle: "h23", ...options } : options);
export const dateTimeText = (date) => (lang() === "en"
  ? date.toLocaleString("en-US", { dateStyle: "medium", timeStyle: "medium", hourCycle: "h23" }) : date.toLocaleString("ko-KR"));

const escapeRe = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Dictionary keys: `{}` captures any text, `{n}` text without Korean (a number, time, id).
 * Values use `{1}`, `{2}`, ... for the captures and `{1?one:many}` to choose by whether capture 1 is "1".
 * A key `[button] 승인` applies only to text inside a button or link, where the same Korean word
 * is a verb rather than a status; `[label]` does the same for form labels.
 */
export function makeTranslator(dictionary) {
  const exact = new Map();
  const patterns = [];
  for (const [key, value] of Object.entries(dictionary)) {
    if (!/\{n?\}/.test(key)) { exact.set(key, value); continue; }
    const source = key.split(/(\{n?\})/).map((part) => (part === "{}" ? "(.+?)" : part === "{n}" ? PLAIN : escapeRe(part))).join("");
    patterns.push({ key, re: new RegExp(`^${source}$`), value, weight: key.replace(/\{n?\}/g, "").length });
  }
  patterns.sort((a, b) => b.weight - a.weight);

  // A whole phrase: dictionary entry or pattern. Null when the dictionary does not know it.
  function phrase(text, context = "") {
    if (context && exact.has(`[${context}] ${text}`)) return exact.get(`[${context}] ${text}`);
    if (exact.has(text)) return exact.get(text);
    for (const p of patterns) {
      const match = p.re.exec(text);
      if (!match) continue;
      return p.value.replace(/\{(\d+)\?([^:}]*):([^}]*)\}/g, (_, i, one, many) => (match[i].trim() === "1" ? one : many))
        .replace(/\{(\d+)\}/g, (_, i) => translate(match[i]));
    }
    return null;
  }
  // Runtime joins of known phrases ("읽기 · 내부", "예상 T1 종료"). All or nothing, so a
  // sentence from the server is never half translated.
  function composed(text) {
    for (const separator of SEPARATORS) {
      if (!text.includes(separator)) continue;
      const parts = text.split(separator).map((part) => (HANGUL.test(part) ? phrase(part) ?? composed(part) : part));
      if (parts.every((part) => part !== null)) return parts.join(separator);
    }
    // Only where a code or number is mixed in ("예상 T1 종료"): a run of plain Korean words is a sentence or a name from the server.
    const words = text.split(" ");
    if (words.length < 2 || words.length > 6 || words.every((word) => HANGUL.test(word))) return null;
    const out = [];
    for (let i = 0; i < words.length;) {
      let taken = 0;
      for (let j = words.length; j > i; j -= 1) {
        const span = words.slice(i, j).join(" ");
        const found = HANGUL.test(span) ? phrase(span) : j === i + 1 ? span : null;
        if (found !== null) { out.push(found); taken = j - i; break; }
      }
      if (!taken) return null;
      i += taken;
    }
    return out.join(" ");
  }
  function translate(text, context = "") {
    if (typeof text !== "string" || !HANGUL.test(text)) return text;
    const core = text.trim().replace(/\s+/g, " ");
    const out = phrase(core, context) ?? composed(core);
    return out === null ? text : text.slice(0, text.length - text.trimStart().length) + out + text.slice(text.trimEnd().length);
  }
  return { translate, phrase, exact: (text) => exact.get(text.trim()) ?? text, patterns, size: exact.size + patterns.length };
}

// ── English ─────────────────────────────────────────────────────────────────
const english = lang() === "en" ? makeTranslator((await import("./i18n-en.mjs")).EN) : null;
export const t = (text) => (english ? english.translate(text) : text);

function contextOf(node) {
  const element = node.parentNode;
  if (!element || element.nodeType !== 1) return "";
  const explicit = element.closest("[data-i18n-ctx]")?.getAttribute("data-i18n-ctx");
  if (explicit) return explicit;
  if (element.tagName === "LABEL") return "label";
  if (/^H[1-4]$/.test(element.tagName)) return "heading";
  if (element.tagName === "TH") return "column";
  if (element.tagName === "BUTTON" && element.classList.contains("tab")) return "tab";
  return element.tagName === "A" || element.tagName === "BUTTON" ? "button" : "";
}
function translateText(node) {
  if (!HANGUL.test(node.data) || SKIP.has(node.parentNode?.tagName)) return;
  const next = english.translate(node.data, contextOf(node));
  if (next !== node.data) node.data = next;
}
function setIfChanged(element, name, value, next) { if (next !== value) element.setAttribute(name, next); }
function translateAttributes(element) {
  for (const name of ATTRS) {
    const value = element.getAttribute(name);
    if (value && HANGUL.test(value)) setIfChanged(element, name, value, english.translate(value, element.getAttribute("data-i18n-ctx") || ""));
  }
  // Defaults a dialog pre-fills (a reason, a note) are written to the record in this language.
  const value = element.tagName === "INPUT" && element.getAttribute("value");
  if (value && HANGUL.test(value) && element.closest?.("#dialog")) setIfChanged(element, "value", value, english.exact(value));
}
export function translateTree(node) {
  if (!english) return;
  if (node.nodeType === 3) { translateText(node); return; }
  if (node.nodeType === 1) {
    if (SKIP.has(node.tagName)) return;
    translateAttributes(node);
  } else if (node.nodeType !== 9 && node.nodeType !== 11) return;
  for (const child of node.childNodes) translateTree(child);
}

function start() {
  const root = document.documentElement;
  root.lang = lang();
  for (const button of document.querySelectorAll("[data-lang-toggle]")) button.textContent = lang() === "en" ? "한국어" : "English";
  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-lang-toggle]")) return;
    try { localStorage.setItem(LANG_KEY, lang() === "en" ? "ko" : "en"); } catch { return; }
    location.reload();
  });
  if (!english) return;
  translateTree(root);
  new MutationObserver((records) => {
    for (const record of records) {
      if (record.type === "childList") record.addedNodes.forEach(translateTree);
      else if (record.type === "characterData") translateText(record.target);
      else translateAttributes(record.target);
    }
  }).observe(root, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: [...ATTRS, "value"] });
}
if (typeof document !== "undefined") start();
