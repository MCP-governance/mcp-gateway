// Static extraction of the Korean text the console can put on screen: string and template
// literals in the scripts (code and comments are not scanned for text, only literals) and
// text nodes and title/placeholder/aria-label attributes in the HTML. `${...}` becomes `{}`.
// A template that holds markup is split at its tags, so each piece is one DOM text node.
import { readFileSync } from "node:fs";

const HANGUL = /[가-힣]/;
const TAG = /<\/?[a-zA-Z][^\s>/]*(?:\s+[^\s=>/]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?)*\s*\/?>/g;
const ATTR = /\b(?:placeholder|title|aria-label|alt)\s*=\s*(?:"([^"]*)"|'([^']*)')/g;
const REGEX_AFTER = new Set(["return", "typeof", "case", "delete", "void", "in", "of", "else", "do", "throw", "new"]);
const BREAK = "\u0001";

/** Every string and template literal of a script: [{text, line}]. */
export function literals(source) {
  const out = [];
  let i = 0;
  const lineOf = (at) => source.slice(0, at).split("\n").length;
  const escape = () => {
    const c = source[i + 1];
    i += 2;
    if (c === "n" || c === "t" || c === "r") return " ";
    if (c === "u") { const hex = source.slice(i, i + 4); i += 4; return String.fromCharCode(parseInt(hex, 16)); }
    if (c === "x") { const hex = source.slice(i, i + 2); i += 2; return String.fromCharCode(parseInt(hex, 16)); }
    return c ?? "";
  };
  function string(quote) {
    const at = i;
    let text = "";
    i += 1;
    while (i < source.length && source[i] !== quote && source[i] !== "\n") text += source[i] === "\\" ? escape() : source[i++];
    i += 1;
    out.push({ text, line: lineOf(at), template: false });
  }
  function template() {
    const at = i;
    let text = "";
    i += 1;
    while (i < source.length && source[i] !== "`") {
      if (source[i] === "\\") text += escape();
      else if (source[i] === "$" && source[i + 1] === "{") { i += 2; text += "{}"; code(true); } else text += source[i++];
    }
    i += 1;
    out.push({ text, line: lineOf(at), template: true });
  }
  function regex() {
    i += 1;
    let inClass = false;
    while (i < source.length) {
      const c = source[i];
      if (c === "\\") { i += 2; continue; }
      if (c === "[") inClass = true; else if (c === "]") inClass = false;
      else if (c === "/" && !inClass) { i += 1; break; }
      i += 1;
    }
    while (/[a-z]/.test(source[i] ?? "")) i += 1;
  }
  function code(untilBrace) {
    let depth = 0, prev = "", word = "";
    while (i < source.length) {
      const c = source[i], n = source[i + 1];
      if (c === "/" && n === "/") { while (i < source.length && source[i] !== "\n") i += 1; continue; }
      if (c === "/" && n === "*") { const end = source.indexOf("*/", i + 2); i = end < 0 ? source.length : end + 2; continue; }
      if (c === '"' || c === "'") { string(c); prev = '"'; word = ""; continue; }
      if (c === "`") { template(); prev = "`"; word = ""; continue; }
      if (c === "/") {
        if (!prev || "(,=:[!&|?{};+-*%<>~^".includes(prev) || REGEX_AFTER.has(word)) { regex(); prev = "/"; word = ""; continue; }
        i += 1; prev = c; word = ""; continue;
      }
      if (/[A-Za-z_$]/.test(c)) {
        let end = i;
        while (/[\w$]/.test(source[end] ?? "")) end += 1;
        word = source.slice(i, end); prev = "a"; i = end; continue;
      }
      if (c === "{") depth += 1;
      if (c === "}") { if (untilBrace && depth === 0) { i += 1; return; } depth -= 1; }
      if (!/\s/.test(c)) { prev = /\d/.test(c) ? "0" : c; word = ""; }
      i += 1;
    }
  }
  code(false);
  return out;
}

const clean = (text) => text.replace(/\s+/g, " ").trim();

/** Text nodes and visible attributes of a piece of markup (or plain text). */
export function pieces(text) {
  const found = [];
  const rest = text.replace(ATTR, (_, double, single) => { found.push(double ?? single); return " "; });
  found.push(...rest.replace(TAG, BREAK).split(BREAK));
  return found.map(clean).filter((piece) => HANGUL.test(piece));
}

/** Text that sits directly in a button or link (and `confirm:` labels): where a word is a verb, not a status. */
export function buttonTexts(path) {
  const found = new Set();
  const source = readFileSync(path, "utf8");
  for (const { text } of literals(source)) {
    for (const match of text.matchAll(/<(button|a)\b([^>]*)>([^<]*)/g)) {
      if (match[1] === "button" && /class="[^"]*\btab\b/.test(match[2])) continue;
      for (const piece of pieces(match[3])) found.add(piece);
    }
  }
  for (const match of source.matchAll(/confirm:\s*(?:[^"'`\n]*\?\s*)?"([^"]*[가-힣][^"]*)"/g)) found.add(clean(match[1]));
  return found;
}

/** Unique Korean fragments of one file: Map(fragment -> first line). */
export function fragments(path) {
  const source = readFileSync(path, "utf8");
  const found = new Map();
  const add = (text, line) => { for (const piece of pieces(text)) if (!found.has(piece)) found.set(piece, line); };
  if (/\.html$/.test(path)) {
    const body = source.replace(/<!--[\s\S]*?-->/g, "");
    body.split("\n").forEach((line, index) => add(line, index + 1));
  } else for (const { text, line } of literals(source)) add(text, line);
  return found;
}
