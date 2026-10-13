"""Generate an offline browser reader from the same Markdown used by agents."""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import mistune

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {"papers": "논문·기술문서", "sources": "자료 원문", "solutions": "상용·오픈소스",
              "methodology": "구축 방법론", "experiments": "실험·대상 MCP",
              "threats": "위협·정책 매핑", "status": "개발 현황", "templates": "작성 양식"}


def safe_url(url):
    # Browser source text is untrusted; never activate local executables or script URLs.
    decoded = html.unescape(url).strip()
    if re.search(r"[\x00-\x20\x7f]", decoded) or decoded.startswith(("//", "\\")):
        return "#harmful-link"
    if urlsplit(decoded).scheme.lower() not in ("", "https", "http", "mailto"):
        return "#harmful-link"
    return decoded


class ResearchRenderer(mistune.HTMLRenderer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.heading_counts = {}

    def heading(self, text, level, **attrs):
        plain = html.unescape(re.sub(r"<[^>]+>", "", text)).lower()
        slug = re.sub(r"[^\w\s-]", "", plain).strip().replace(" ", "-") or "section"
        number = self.heading_counts.get(slug, 0)
        self.heading_counts[slug] = number + 1
        identifier = slug + (f"-{number}" if number else "")
        return f'<h{level} id="{html.escape(identifier, quote=True)}">{text}</h{level}>\n'

    def link(self, text, url, title=None):
        return super().link(text, safe_url(url), title)

    def image(self, text, url, title=None):
        # Do not send browser requests to third-party images embedded in downloaded material.
        return self.link("이미지: " + html.escape(text), url, title)


def render_markdown(source):
    return mistune.create_markdown(renderer=ResearchRenderer(escape=True),
                    plugins=["table", "strikethrough", "task_lists", "url"])(source)


def build():
    pages = []
    for file in sorted(ROOT.rglob("*.md")):
        relative = file.relative_to(ROOT)
        if relative.parts[0] in ("web", "tools", "local-sources") or "__pycache__" in relative.parts:
            continue
        source = file.read_text(encoding="utf-8-sig")
        heading = re.search(r"^#\s+(.+)$", source, re.MULTILINE)
        pages.append({"path": relative.as_posix(), "title": heading[1] if heading else file.stem,
                      "category": CATEGORIES.get(relative.parts[0], "시작 안내"),
                      "markdown": source, "html": render_markdown(source)})
    catalogs = {}
    for file in sorted((ROOT / "catalogs").glob("*.json")):
        catalogs[file.stem] = json.loads(file.read_text(encoding="utf-8-sig"))
    web = ROOT / "web"
    web.mkdir(exist_ok=True)
    text_sources = {}
    text_folder = web / "source-text"
    if text_folder.exists():
        for stale in text_folder.glob("*.txt"):
            assert stale.resolve().is_relative_to(text_folder.resolve())
            stale.unlink()
    for source in (ROOT / "sources").rglob("*"):
        if source.suffix.lower() in (".html", ".htm", ".svg", ".xml"):
            relative = source.relative_to(ROOT).as_posix()
            target = web / "source-text" / (relative.replace("/", "_") + ".txt")
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, target)
            text_sources[relative] = target.relative_to(ROOT).as_posix()
    for source in (ROOT / "local-sources").rglob("*"):
        if source.suffix.lower() in (".html", ".htm", ".svg", ".xml"):
            target = source.with_suffix(source.suffix + ".txt")
            shutil.copyfile(source, target)
            text_sources[source.relative_to(ROOT).as_posix()] = target.relative_to(ROOT).as_posix()
    result = {"generated_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
              "pages": pages, "catalogs": catalogs, "text_sources": text_sources}
    payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    (web / "content.js").write_text("window.WIKI_DATA=" + payload + ";\n", encoding="utf-8")
    (web / "manifest.json").write_text(json.dumps({"generated_at": result["generated_at"],
                        "page_count": len(pages), "catalog_counts": {k: len(v) for k,v in catalogs.items()}},
                        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pages": len(pages), "catalogs": {k: len(v) for k,v in catalogs.items()}}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    build()
