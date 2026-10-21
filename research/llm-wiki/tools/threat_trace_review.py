"""Render the frozen independent review; never refresh its evidence hashes."""


def review_references(policy, evidence):
    return [*policy["code_references"], *policy["regression_tests"],
            *(evidence[eid] for eid in policy["evidence_ids"]),
            *(r for eid in policy["evidence_ids"] for r in evidence[eid].get("supporting_references", []))]


def link(reference):
    label = reference["symbol"] or reference["path"].split("/")[-1]
    return f"[{label}:{reference['line']}](../../../../{reference['path']}#L{reference['line']})"


def render_review(path, review, stale):
    lines = ["# DEV-03 원본 위협표와 구현 추적 독립 검토", "",
        f"검토자: {review['reviewer']} · 기준: `{review['reviewed_commit']}` · {review['reviewed_on']}", "",
        "원본 PAC01~24(정책 최종본 5~28행)를 의미로 대조했다. 런타임 PAC-01~15·정책50과 번호로 대응시키지 않는다. "
        "24행 모두 부분 근거가 있으며 전체 요구 충족·현재 배포 검수를 판정하지 않는다. "
        "최초 검토에서 12건의 매핑 결함/오독 위험을 정정했고 제품 코드와 기존 시험은 변경하지 않았다.", "",
        "## 정본·판본·검토 방법", "",
        "[구조화 검토](review.json)는 원본 요구, 코드 심볼/행/파일 SHA-256, 회귀 범위, 증거 층과 정정 전 매핑을 보존한다. "
        "[카탈로그](../../catalogs/threats.json)와 [통제 지도](../../threats/control-map.md)는 "
        "`python research/llm-wiki/tools/map_threats.py`로 재생성한다. "
        "심볼은 AST로 확인하고 함수 본문·호출 경계·시험 단언을 대조했다. 기존 매핑에는 심볼 자체가 없었으며 "
        "없는 파일/심볼 결함은 발견하지 않았다. 파일 존재만으로 통제 전체를 해석할 수 있는 범위는 아래에서 축소했다.", "",
        f"XLSM 원본 SHA-256: `{review['source_sha256']}`. "
        "[보존 추출본](../../threats/extracted/policies.json)의 정책명·본문·행을 사용했다. "
        "이번 XLSM 원본 바이트 재검증/매크로 실행/재저장은 하지 않았다. "
        "정상·음성·경계·실패·경쟁·복구의 일부 시험을 여섯 조건 전체 또는 모든 MCP의 검수로 합산하지 않는다.", "",
        "[아키텍처](../../../../docs/ai/ARCHITECTURE.md)·[경계](../../../../docs/ai/SECURITY_BOUNDARIES.md)·"
        "[정책](../../../../docs/ai/POLICY.md)·[결정](../../../../docs/ai/DECISIONS.md)과 "
        "기존 고정 SDK·OPA·[OSS 심층 비교](../oss-deep/README.md)를 재사용했다. "
        "최초 검토의 원격 GitHub HEAD 조회는 연결 실패였고 새 외부 스킬·OSS·의존성은 도입하지 않았다. "
        "별도 D-번호가 지정되지 않아 새 번호를 만들지 않았다.", "",
        "검토 결정: 관리대장 ID·제품 코드·회귀 시험을 구분한다. PG/OPA 함수 시험·실제 MCP·PJ1·독립 효과·현재 배포도 구분한다. "
        "최초 실패/미실행과 후속 성공이 함께 있으면 마지막 추가 기록을 그 판본의 보고 증거로 채택하며 원시 출력 부재를 명시한다.", "",
        f"참조 파일과 검토 스냅샷 대조: {'불일치 — 재검토 필요: ' + ', '.join(sorted(stale)) if stale else '일치'}. "
        "파일 변경 시 생성기는 과거 심볼 행/해시를 갱신하지 않고 낡은 검토로 표시한다.", "",
        "## 24개 정책별 대조", "",
        "회귀 칸은 시험 소스의 범위이며 이번 실행 통과를 뜻하지 않는다. E번호는 아래의 당시 판본·수준·한계와 함께 읽는다.", "",
        "| 원본·셀·정책 | 통제 위치·런타임 후보 | 코드 심볼·근거 행 | 회귀 시험·범위 | 실험/실기기 근거 | 남은 한계 |",
        "| --- | --- | --- | --- | --- | --- |"]
    if refresh := review.get("refresh"):
        # Keep the previous bytes available when a later review supersedes its anchors and claims.
        lines[4:4] = [
            f"현 판본 재대조: [변경별 근거]({refresh['analysis']}) · "
            f"[이전 검토 원본]({refresh['previous_snapshot']}) "
            f"(SHA-256 `{refresh['previous_sha256']}`). "
            f"{refresh['changed_files']}개 파일·{refresh['stale_unique_references']}개 낡은 참조를 재대조했다. "
            "정적 추적 재대조·외부 독립 적대 검토·실행 검수는 별개이며 판정은 작업 보고를 따른다.", ""]
    for p in review["policies"]:
        code = "<br>".join(link(r) for r in p["code_references"])
        tests = "<br>".join(f"{link(r)} — {r['coverage']}" for r in p["regression_tests"])
        evidence = ", ".join(f"[{eid}](#{eid.lower()})" for eid in p["evidence_ids"]) or "실제 위임 검증 없음"
        lines.append(f"| {p['source_id']} · {p['source_cells']}<br>{p['title']} | "
                     f"{' · '.join(p['control_locations'])}<br>({', '.join(p['runtime_candidates']) or '정책 ID 없음'}) | "
                     f"{code} | {tests} | {evidence} | {p['limitations']} |")
    lines += ["", "## 오류·누락·과대 해석 위험", "",
        "매핑 결함을 제품 기능의 전체 부재로 자동 환산하지 않는다. 정정 전 값은 review.json에 보존했다.", "",
        "| ID·원본 | 유형·기존 문제 | 정정·남긴 판단 | 근거 행 | 상태 |", "| --- | --- | --- | --- | --- |"]
    for f in review["findings"]:
        refs = "<br>".join(link(r) for r in f["evidence_references"])
        lines.append(f"| {f['id']} · {', '.join(f['source_ids'])} | {f['category']}: {f['original']} | "
                     f"{f['correction']} | {refs} | {f['status']} |")
    lines += ["", "## 실험·실기기 증거 목록", "",
        "E03~E06의 실제 PostgreSQL/OPA 통과 수치는 후속 보고를 확인한 것이다. 이번 독립 재실행 수치가 아니며 "
        "보고서에 원시 실행 JSON이 없어 재계산하지 못했다. E02는 "
        "[보존 원장](../controls-1018/device-e2e.json), E01은 [실행기 기록](../wbs-1015/dev38-runtime.json), "
        "E07은 [실험실 기록](../wbs-1015/lab-results.jsonl)과 대조했다.", ""]
    for e in review["evidence"]:
        lines += [f"### {e['id']}", "", f"{link(e)} · {e['level']}", "",
                  e["result"] + ".", "", f"한계: {e['limitations']}.", ""]
    lines += ["## 결정 필요·후속 검수", "",
        "- PAC06: Resource·Prompt를 추가할지 원본 대비 미지원으로 유지할지 결정 필요.",
        "- PAC08~09: 검증된 에이전트 신원·위임 발급자/교집합/철회 수명주기 도입 결정 필요. 미지원 차단 유지.",
        "- PAC12: 원본 여섯 행위와 내부 r/w/x 집약의 수용 여부 결정 필요.",
        "- PAC15: 잠정 처리 국가 규칙·공급자 실제 위치/이전 근거 검토는 사람의 결정 범위.",
        "- PAC22: 요청 본문 최소화/보존과 append-only, 봉인 구간 만료 삭제/암호 삭제는 DEV-67 결정 필요.",
        "- PAC23~24: D-154 회전 기록 후보·외부 캐시/복제 자격·실행기 제거·서명 저장소 동시 복원은 별도 검수.", "",
        ("DEV-03의 현 판본 정적 재대조를 기록하며 외부 독립 검토 판정은 작업 보고를 따른다. "
         if review.get("refresh") else "DEV-03의 독립 추적 검토를 완료하며 ") + "각 기능의 검수 점수는 변경하지 않는다. "
        "기기 재실행: `dispatch_recheck_pg_check.py`, `oauth_negative_pg_check.py`, `restore_residual_pg_check.py`, "
        "`policy_selftest_pg_check.py`(과거 성공의 현 판본 확인), `dispatch_idempotency_pg_check.py`, "
        "`auto_suspend_pg_check.py`, `resource_residual_pg_check.py`(미실행 범위). "
        "솔루션 기기 `full_stack_lab`의 준비된 전용 랩에서 `tests/termination_dispatch_lab.sh run <파일>`로 실행한다. "
        "다른 사람이 사용 중인 랩을 시작/초기화/정지하지 않는다. PJ1 새 관리 하네스·OSS MCP·독립 효과 검수는 별도다.", ""]
    path.with_name("README.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
