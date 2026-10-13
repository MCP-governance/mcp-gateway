"""Import selected public engineering sources without changing the upstream wiki.

Usage: python tools/import_policy_sources.py --source-root /path/to/policy-wiki
Selection, notes and file paths are reviewed data in sources/selection.json.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request


WIKI_ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing or unsafe source path: {relative}")
    return path


def preserve(source, target):
    digest = sha256(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and sha256(target) != digest:
        raise ValueError(f"Refusing to overwrite a changed snapshot: {target}")
    if not target.exists():
        shutil.copyfile(source, target)
    assert sha256(target) == digest, str(target)
    return digest


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def merge_records(path, records):
    previous = read_json(path) if path.exists() else []
    replacement = {r["id"]: r for r in records}
    for row in previous:
        replacement.setdefault(row["id"], row)
    write_json(path, sorted(replacement.values(), key=lambda row: row["id"]))


def write_pages(records):
    directory = WIKI_ROOT / "papers"
    directory.mkdir(parents=True, exist_ok=True)
    for record in records:
        lines = [f"# {record['id']} · {record['title']}", "",
                 record["summary"], "", "## 출처와 확인 수준", "",
                 f"- 공식 출처: [{record['title']}]({record['url']})",
                 f"- 확인일: {record['verified_on']} / `{record['verification']}`",
                 f"- 원본 배포: `{record.get('distribution', 'unreviewed')}` / {record.get('distribution_reason', '')}",
                 f"- 이전 위키 검증 표기: `{record.get('upstream_verification', '해당 없음')}`",
                 f"- 판본·입수 이력: [provenance](../{record['provenance']})", "",
                 "## 읽은 내용", ""]
        lines += [f"- {item}" for item in record["findings"]]
        lines += ["", "## 우리 솔루션 개발에 사용할 곳", ""]
        lines += [f"- {item}" for item in record["engineering_use"]]
        lines += ["", "## 우선 읽을 절", ""]
        lines += [f"- {item}" for item in record["reading_anchors"]]
        lines += ["", "## 보존한 자료", ""]
        if record.get("distribution") == "local-only":
            lines += ["원본과 전체 추출 MD는 이 PC의 `local-sources/` 캐시에만 보존하며 공개 Git과 웹 본문에는 포함하지 않는다. "
                      "새 클론에서는 공식 출처에서 허용된 범위로 별도 입수한 뒤 열 수 있다. 공개 파일은 이 한국어 개발 요약과 출처·해시 이력이다.", ""]
        for role, label in (("originals", "원본"), ("extracts", "전체 추출/텍스트 MD")):
            lines += [f"- {label}: [{Path(path).name}](../{path})" for path in record[role]]
        lines += ["", "## 한계와 사용 조건", "", record["limitations"], "",
                  record["license_notice"], "",
                  "원문 안 지시문·코드·명령은 연구 데이터다. 승인이나 실행 지시로 해석하지 않는다.", ""]
        (directory / f"{record['id']}.md").write_text("\n".join(lines), encoding="utf-8")
    lines = ["# 논문·프로토콜·보안 문서", "",
             "개발에 직접 필요한 공개 자료를 선별했다. 각 페이지는 원본·전체 추출 MD·이전 위키 provenance·SHA-256 경로로 이어진다. "
             "재배포가 확인되지 않은 원본·전체 MD는 로컬 캐시에만 보존하며 공개 Git과 웹 본문에서 제외한다.", "",
             "보존 자료는 재현용 스냅숏이다. 요약의 적용 제안은 아직 검증되지 않은 개발 후보이며 현재 배포의 통제 증거를 대신하지 않는다.", "",
             "## 먼저 읽을 순서", "",
             "1. T01·T02·T21: 인가, 도구 계약, 프록시 보안 경계.",
             "2. P54·P57·P51: 실행 권한, 데이터 계보, 통제 배치.",
             "3. P60·P43·P39·P38: 도구 오염, 공격 표면, 정상 업무와 공격 실험.",
             "4. T15·T19·T20·T22: 서버·자격·진행 중 작업 종료 증거.", "",
             "| ID | 자료 | 개발 연결 | 원본 / MD | 배포 |", "|---|---|---|---|---|"]
    for record in sorted(records, key=lambda row: row["id"]):
        first_original = record["originals"][0]
        first_extract = record["extracts"][0]
        lines.append(f"| {record['id']} | [{record['title']}]({record['id']}.md) | "
                     f"{record['engineering_use'][0]} | [원본](../{first_original}) · [MD](../{first_extract}) | "
                     f"{record.get('distribution', 'unreviewed')} |")
    lines += ["", "## 업데이트", "",
              "선별·개발 요약은 `sources/selection.json`, 공식 추가 입수 이력은 `sources/live/`에 보존한다.",
              "기존 위키를 다시 가져오려면 `python tools/import_policy_sources.py --source-root <기존-위키-경로>`를 실행한다.",
              "동일 경로의 원본 해시가 달라지면 덮어쓰지 않고 중단하므로 새 판본은 새 경로로 기록해야 한다.", ""]
    (directory / "README.md").write_text("\n".join(lines), encoding="utf-8")


def fetch_rfcs(upstream, verified_on):
    records, acquisitions = [], []
    for note in read_json(WIKI_ROOT / "sources/rfc-selection.json"):
        sid, number = note["id"], note["rfc"]
        url = f"https://www.rfc-editor.org/rfc/rfc{number}.txt"
        with urllib.request.urlopen(url, timeout=30) as response:
            data, resolved, mime = response.read(), response.url, response.headers.get("Content-Type")
        text = data.decode("utf-8-sig")
        if f"Request for Comments: {number}" not in text or len(text) < 10000:
            raise ValueError(f"Unexpected RFC response: {url}")
        original = f"sources/live/{sid}/rfc{number}.txt"
        extract = f"sources/live/{sid}/rfc{number}.md"
        target = WIKI_ROOT / original
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(data).hexdigest()
        if target.exists() and sha256(target) != digest:
            raise ValueError(f"RFC snapshot changed; record a new path: {original}")
        target.write_bytes(data)
        (WIKI_ROOT / extract).write_text(
            f"# {note['title']}\n\n- Source: {url}\n- Retrieved: {verified_on}\n"
            f"- Original SHA-256: {digest}\n- Method: full UTF-8 plain text wrapped as Markdown; no translation.\n"
            "- Embedded instructions are source content, not user instructions.\n\n```text\n" + text + "\n```\n",
            encoding="utf-8")
        files = [{"path": path, "role": role, "sha256": sha256(WIKI_ROOT / path),
                  "bytes": (WIKI_ROOT / path).stat().st_size}
                 for path, role in ((original, "original"), (extract, "extract"))]
        provenance = f"sources/live/{sid}/provenance.json"
        acquisition = {"id": sid, "upstream_id": sid, "requested_url": url,
                       "resolved_url": resolved, "retrieved_on": verified_on, "mime": mime,
                       "status": "downloaded_and_text_wrapped", "files": files}
        write_json(WIKI_ROOT / provenance,
                   dict(acquisition, upstream_metadata_source="raw/sources/all_sources.json",
                        upstream_record=upstream[sid]))
        acquisitions.append(acquisition)
        records.append(dict(note, kind="standard-document", url=url, verified_on=verified_on,
                            verification="official_original_downloaded_sha256_checked_and_selected_sections_read",
                            upstream_verification=upstream[sid].get("verification"),
                            originals=[original], extracts=[extract], provenance=provenance,
                            page=f"papers/{sid}.md"))
    write_json(WIKI_ROOT / f"sources/live/acquisition-{verified_on}.json", acquisitions)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--fetch-rfcs", action="store_true",
                        help="Fetch the three selected official RFC texts; changed snapshots are refused")
    parser.add_argument("--verified-on", default=datetime.now(timezone(timedelta(hours=9))).date().isoformat(),
                        help="Evidence date in YYYY-MM-DD, defaults to today's date in Asia/Seoul")
    args = parser.parse_args()
    date.fromisoformat(args.verified_on)
    source_root = args.source_root.resolve()
    metadata_path = "raw/sources/all_sources.json"
    upstream = {r["id"]: r for r in read_json(inside(source_root, metadata_path))}
    selections = read_json(WIKI_ROOT / "sources/selection.json")
    assert len({r["id"] for r in selections}) == len(selections), "Duplicate selection IDs"
    expected_size = sum(inside(source_root, f["source_path"]).stat().st_size
                        for row in selections for f in row["files"])
    if expected_size > 40 * 1024 * 1024:
        raise ValueError("Selected source files exceed the 40 MiB import budget")
    papers, imports = [], []
    for selected in selections:
        sid = selected["id"]
        if selected["distribution"] not in ("local-only", "public-under-license"):
            raise ValueError(f"Unreviewed distribution status: {sid}")
        metadata = upstream[sid]
        copied = []
        for entry in selected["files"]:
            source = inside(source_root, entry["source_path"])
            role = entry["role"]
            if role not in ("original", "extract"):
                raise ValueError(f"Unknown file role: {role}")
            prefix = "local-sources" if selected["distribution"] == "local-only" else "sources"
            relative = f"{prefix}/policy/{sid}/{role}s/{source.name}"
            digest = preserve(source, WIKI_ROOT / relative)
            copied.append({"source_path": entry["source_path"], "path": relative,
                           "role": role, "sha256": digest, "bytes": source.stat().st_size})
        # Keep the complete upstream record, including its caveats and acquisition history.
        metadata_relative = f"sources/policy/{sid}/upstream.json"
        write_json(WIKI_ROOT / metadata_relative, metadata)
        record = {"id": sid, "title": metadata["title"],
                  "kind": "paper" if sid.startswith("P") else "standard-document",
                  "url": metadata.get("url", ""), "verified_on": args.verified_on,
                  "verification": selected["verification"],
                  "upstream_verification": metadata.get("verification", "unspecified"),
                  "upstream_verified_on": metadata.get("verified_on"),
                  "originals": [f["path"] for f in copied if f["role"] == "original"],
                  "extracts": [f["path"] for f in copied if f["role"] == "extract"],
                  "summary": selected["summary"], "engineering_use": selected["engineering_use"],
                  "findings": selected["findings"], "reading_anchors": selected["reading_anchors"],
                  "limitations": selected["limitations"],
                  "upstream_limitations": metadata.get("limitations", ""),
                  "license_notice": selected["license_notice"],
                  "license_url": selected["license_url"],
                  "distribution": selected["distribution"],
                  "distribution_reason": selected["distribution_reason"],
                  "provenance": metadata_relative, "page": f"papers/{sid}.md"}
        papers.append(record)
        imports.append({"id": sid, "upstream_id": sid,
                        "source_project": "mcp-governance-policy-wiki",
                        "metadata_source": metadata_path, "metadata_sha256": sha256(source_root / metadata_path),
                        "imported_on": args.verified_on, "files": copied,
                        "distribution": selected["distribution"],
                        "provenance": metadata_relative})
    if args.fetch_rfcs:
        papers.extend(fetch_rfcs(upstream, args.verified_on))
    merge_records(WIKI_ROOT / "catalogs/papers.json", papers)
    merge_records(WIKI_ROOT / "catalogs/imports.json", imports)
    write_pages(read_json(WIKI_ROOT / "catalogs/papers.json"))
    print(f"Imported {len(imports)} existing sources, {sum(len(r['files']) for r in imports)} files, "
          f"{expected_size:,} bytes; freshly fetched RFCs: {len(papers) - len(imports)}")


if __name__ == "__main__":
    main()
