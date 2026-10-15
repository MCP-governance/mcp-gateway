"""Register scholarly metadata and our analysis without claiming downloaded fulltext."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
references=json.loads((ROOT/"analysis/reference-updates.json").read_text())
file=ROOT/"catalogs/papers.json"
papers=json.loads(file.read_text(encoding="utf-8-sig"))
for r in references[:3]:
    if any(p["id"]==r["id"] for p in papers):
        continue
    page=f"papers/{r['id']}.md"
    papers.append({"id":r["id"],"title":r["title"],"kind":"journal_metadata","url":r["source_url"],
      "verified_on":r["verified_on"],"verification":r["verification"],"publication_status":r["publication_status"],
      "originals":[],"extracts":[],"summary":r["methodology_adaptation"],"engineering_use":[r["methodology_adaptation"]],
      "limitations":r["reading_scope"],"distribution":"public-under-license",
      "distribution_reason":"public bibliographic facts and our analysis only; no fulltext copy",
      "license_notice":r["license"],"page":page,"metadata_evidence":r["metadata_evidence"]})
    md=[f"# {r['title']}","",f"ID `{r['id']}` · {r['venue']} · {r['published_on']}","",
      f"[공식 근거]({r['source_url']}) · DOI `{r['doi']}`","","## 확인 범위","",r["reading_scope"],"",
      "## 개발 적용","",r["methodology_adaptation"],"","## 한계","",
      "정식 서지·선별 내용 확인입니다. 전문 정독·방법 전체 재현·우리 제품 성능을 증명하지 않습니다. IF 수치는 검증하지 않았습니다.","",
      r["license"],"전문 PDF/번역 MD를 새로 확보·공개 복제하지 않았습니다.","",
      f"[메타데이터 hash 기록](../{r['metadata_evidence']['path']}) · [방법론](../methodology/evidence-methodology.md)",""]
    (ROOT/page).write_text("\n".join(md),encoding="utf-8")
file.write_text(json.dumps(papers,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(f"Registered {len(papers)} records; 3 additions are metadata/selected-source only")
