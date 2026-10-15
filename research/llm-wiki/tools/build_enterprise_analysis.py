"""Refresh structural evidence around curated atomic acceptance criteria, never test results."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
OUT = ROOT / "analysis"


def dump(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, check=True).stdout


def evidence(path, symbol=None):
    file = REPO / path
    raw = file.read_bytes()
    nodes = ast.walk(ast.parse(raw.decode("utf-8-sig"))) if file.suffix == ".py" else []
    matched = next((n for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    and n.name == symbol), None)
    base = git("show", "HEAD:" + path)
    modified = raw.replace(b"\r\n", b"\n") != base.replace(b"\r\n", b"\n")
    return {"path": path, "symbol": symbol or "module/config", "line_start": matched.lineno if matched else 1,
            "line_end": matched.end_lineno if matched else len(raw.splitlines()),
            "sha256": hashlib.sha256(raw).hexdigest(), "head_sha256": hashlib.sha256(base).hexdigest(),
            "normalized_sha256": hashlib.sha256(raw.replace(b"\r\n",b"\n")).hexdigest(),
            "source_state": "worktree_modified" if modified else "committed_source",
            "symbol_found": matched is not None if symbol else True}


# One row is one acceptance condition. These are engineering criteria, not claims of implementation.
GROUPS = [
 ("도입", "full_stack_lab/supply_chain/intake_worker.py", None, [
  ("고정 출처", "서버·패키지·직접/전이 의존성을 고정 digest로 연결", "moving tag·출처 불일치"),
  ("검사 격리", "검사 과정의 파일/망/CPU/시간 권한을 시험 자원에 한정", "검사 스크립트의 외부 통신"),
  ("검사 실패", "스캐너 오류·미완료·timeout은 도입 실패로 남김", "빈 리포트를 취약점0으로 처리"),
  ("라이선스", "실제 배포 판본의 라이선스·NOTICE·재배포 조건 확인", "현재 main 라이선스를 과거 판본에 전이"),
  ("재검사", "소스/의존 변경은 이전 승인과 분리하고 다시 검사", "승인 이후 dependency 변경")]),
 ("계약", "full_stack_lab/gateway/app/core.py", "refresh_catalog", [
  ("최초 승인", "첫 관찰은 자동 승인하지 않고 독립 검토자 승인 필요", "TOFU 자동 허용"),
  ("입력 schema", "description·inputSchema의 승인 hash와 실행 전 관찰 hash 일치", "동명 도구의 인자 형식 변경"),
  ("계약 복귀", "A→B→A 최신 관찰·재승인 내용도 A로 복귀", "과거 hash 존재로 관찰 B 잔존"),
  ("실행 직전", "discovery 후 승인·도구·권한 변경을 dispatch 전에 재검증", "tools/list 후 도구 설명 변경"),
  ("출력 schema", "outputSchema를 독립 승인·잠금·결과 검증과 연결", "미승인 출력 schema 광고")]),
 ("신원", "full_stack_lab/gateway/app/agent_contract.py", "authenticated_user", [
  ("서명", "transport 토큰의 signature·issuer·audience·시간 검증", "다른 issuer/audience·만료·변조"),
  ("scope", "Console 토큰과 MCP 토큰의 사용처를 구분", "관리자 role만으로 MCP scope 대체"),
  ("상태", "현재 계정·세션·기기 철회를 호출 시 재검증", "유효 JWT를 가진 폐기 기기"),
  ("자기 선언", "인자/header/clientInfo의 사용자·agent 값은 신원에 사용하지 않음", "x-user/principal 인자 위조"),
  ("OBO", "프록시의 agent 위임은 검증된 사용자·audience·권한 교집합에 결합", "공유 서비스 토큰으로 전체 사용자 대체")]),
 ("권한", "full_stack_lab/gateway/app/pac.py", "scope", [
  ("도구 목록", "tools/list와 실제 tools/call의 승인 서버/도구 범위 일치", "목록 숨김만 적용하고 직접 호출 허용"),
  ("자산", "조직·사용자·자산 소유권·행위 권한의 교집합 적용", "타 repo/table/key 접근"),
  ("SQL 효과", "읽기 도구 이름이 아닌 SQL AST의 실제 읽기/쓰기/실행 분류", "CTE·함수·읽기 위장 쓰기"),
  ("캐시", "철회·조직 이동·빈/누락 범위는 권한 확대 없이 반영", "unknown alias가 전체 목록으로 fallback"),
  ("입력", "승인 schema와 정규 인자를 정책 전/dispatch 전에 검사", "추가 필드·잘못된 타입·동등 인자 우회")]),
 ("승인", "full_stack_lab/gateway/app/core.py", "execute_call", [
  ("효과 전", "Approval 상태에서는 수신/쓰기/전송 효과0", "승인 대기 중 선실행"),
  ("인자 결합", "승인은 principal·도구·정규 인자 digest·nonce에 결합", "다른 수신자·본문으로 승인 재사용"),
  ("독립 검토", "신청자가 자신의 중요 실행을 승인하지 않음", "자가 승인·역할 위조"),
  ("fresh 인증", "승인 실행 시 새 요청자 인증과 현재 권한·철회 재검증", "만료 bearer를 승인됐다는 이유로 허용"),
  ("경쟁", "동시 승인·철회·재사용에서도 승인당 허용 효과 상한 유지", "승인 실행 중 다른 worker 재실행")]),
 ("데이터", "full_stack_lab/gateway/app/privacy.py", "mask_payload", [
  ("입력 PII", "MCP 인자의 합성 한국어 개인정보·secret 외부 반출 검사", "주민번호 하이픈·인코딩 변형"),
  ("결과 값", "중첩 배열/JSON 값까지 공식 Presidio로 검사·마스킹", "structured 값의 PII 원문 노출"),
  ("결과 키", "민감정보가 JSON 키에 있으면 schema를 바꾸지 않고 보류", "이메일/토큰을 객체 key로 반환"),
  ("검사 장애", "검사기 오류·잘못된 결과·미완전 anonymizer는 보류/차단", "timeout을 탐지0으로 처리"),
  ("코퍼스", "정상/공격·한국어/다국어별 오탐·미탐과 성능을 함께 측정", "정상 이메일·코드·로그 과잉 차단")]),
 ("주입", "full_stack_lab/gateway/app/core.py", "_guarded_result", [
  ("출처", "도구 설명·외부 콘텐츠를 권한 지시와 구분", "외부 문서가 관리자 명령으로 승격"),
  ("decoded 문자열", "text/structuredContent의 실제 줄바꿈과 중첩 문자열 검사", "JSON escape로 위조 대화록 누락"),
  ("정상군", "문서·로그의 동일 표지가 실제 정상 업무를 방해하는지 대조", "공격 표지만으로 모든 읽기 차단"),
  ("승인 후 변경", "공식 OSS 설정의 설명 override 변경을 계약 차이로 검증", "승인 뒤 공격 설명으로 교체"),
  ("대형 결과", "크기 상한과 병적 regex/JSON 처리 시간의 전체 deadline 검증", "긴 공백/줄바꿈으로 이벤트루프 정지")]),
 ("외부통신", "full_stack_lab/gateway/app/upstream.py", "session", [
  ("목적지", "정규 URL·IP·DNS·redirect의 최종 승인 대상 검사", "loopback·IPv6·내부 IP 표기 우회"),
  ("자격", "직원 JWT를 upstream으로 전달하지 않고 별도 자격 사용", "직원 Authorization 재전달"),
  ("바인딩", "공급자 자격은 정확한 HTTPS endpoint·principal·기한에 결합", "다른 host/principal·만료 자격"),
  ("조회 장애", "목적지 정책 데이터 결측/타입 오류는 거부", "None을 빈 allow 목록으로 취급"),
  ("서버 egress", "MCP 서버→외부 API의 별도 목적지·자격·효과를 관찰·집행", "승인 MCP가 Gateway 밖으로 재전송")]),
 ("실행", "full_stack_lab/gateway/app/core.py", "_call_upstream", [
  ("중복", "동일 principal/도구/정규 인자의 중복 효과를 실행 전 제한", "동시 중복 호출"),
  ("상한", "호출량·동시성·TTL의 경계 시각과 다중 worker를 검증", "창 경계·reservation 만료 경합"),
  ("사망", "dispatch 전 durable intent와 사망 뒤 uncertain을 보존", "응답 미수신을 미실행으로 오판"),
  ("재시도", "쓰기의 무조건 자동 재시도로 부수효과를 중복하지 않음", "네트워크 응답 손실 후 두 번째 발송"),
  ("효과 증거", "하네스→요청→원장→독립 서버 수신/실제 효과를 연결", "동일 내용 덮어쓰기1을 실행1로 추정")]),
 ("MCP결과", "full_stack_lab/gateway/app/mcp_facade.py", "_render", [
  ("구조화 보존", "검사·마스킹된 structuredContent를 공식 SDK로 보존", "결과를 text만 반환해 데이터 손실"),
  ("구형 호환", "구조화-only 결과에 동일 안전 JSON의 TextContent 제공", "구형 client가 빈 결과로 인식"),
  ("보류 경계", "Block/Approval/withheld/unknown에서는 잔존 payload도 반환하지 않음", "상태와 result가 모순돼 데이터 노출"),
  ("결과 형식", "structuredContent는 JSON 객체, 미지원 rich content는 보류", "배열/scalar·image/audio 우회"),
  ("확장 기능", "resources/prompts/sampling/tasks 지원/거부 범위를 명시", "MCP 전체 명세 지원으로 오인")]),
 ("엔드포인트", "endpoint-agent/enforce-linux.py", "profile", [
  ("실제 launcher", "fresh 하네스의 UID·실행 파일·AppArmor 전이를 확인", "일반 pj1 CLI를 managed 증거로 사용"),
  ("직접 stdio", "비승인 공식 OSS stdio 실행의 실제 시도·OS 거부 확인", "모델이 실행 안 했는데 차단으로 집계"),
  ("localhost", "IPv4/IPv6 loopback 직접 MCP 접속의 수신0 확인", "127.0.0.1만 막고 ::1 우회"),
  ("기기 입구", "active·fresh heartbeat·hash·checks와 독립 활성화 확인", "설치/pending을 활성 통과로 처리"),
  ("관측 공백", "collector 마지막 성공/실패·전체 집계를 구분", "최근200건/무수신을 전체 차단0으로 표시")]),
 ("감사", "full_stack_lab/gateway/app/core.py", "_record_decision", [
  ("상태 분리", "attempted/executed/response disposition과 원인 정책을 별도 기록", "Block만으로 미실행 주장"),
  ("append-only", "신규 기록 추가·검증 유지하고 기존 원장 변경 금지", "시험 후 원장 삭제로 초기화"),
  ("시각", "v7 created_at UTC canonical·변조검출과 이전 체인 검증 유지", "시각만 바꿔도 검증 통과"),
  ("외부 anchor", "관리자 DB 변경과 원장 head 외부 보존/검증을 구분", "동일DB head 재작성 가능성 무시"),
  ("비밀 최소화", "토큰·원본 민감본문을 공개 원장/로그/Excel에서 제외", "exception/vendor 응답에 자격 노출")]),
 ("종료", "full_stack_lab/gateway/app/decommission.py", "assess", [
  ("즉시 거부", "종료 시작 이후 Gateway 신규 실행은 즉시 거부", "설정 삭제 완료까지 실행 허용"),
  ("회수", "PAT/refresh/access/session별 실제 provider 재접근 검증", "삭제 API200만으로 권한 철회 판단"),
  ("잔존", "사용자 설정·자격·MCP 저장 데이터의 잔존 목록 확인", "설정 제거를 모든 데이터 폐기로 주장"),
  ("증거 수준", "C1~C4 조건별 증거와 T1~T3 최소 상태를 연결", "증거 없는 provider 보유 상태를 완료"),
  ("공유 환경", "시험 관계/자격만 원복하고 다른 사용자의 종료 관계 유지", "전체lab reset·기존 PAT 폐기")]),
 ("LiteLLM", "full_stack_lab/llm/litellm.yaml", None, [
  ("배치", "lab profile 존재와 실제 field 활성 상태를 별도 검증", "이미지/config 존재만으로 연동 완료"),
  ("API", "ChatCompletions/Responses/Anthropic messages 정상·streaming·오류 검증", "health200을 실제 모델 응답으로 대체"),
  ("MCP 경로", "하네스 병렬경로와 LiteLLM MCP aggregation 실행을 구분", "따로 성공한 discovery/model을 E2E로 집계"),
  ("프록시 신원", "LiteLLM 집계에서 verified user/device/위임 범위를 보존", "shared token·untrusted x-user 대체"),
  ("private host", "고객 private LiteLLM host/TLS/CA/CONNECT를 명시 승인", "OpenAI/Anthropic 도메인 allow만으로 호환 주장")]),
 ("비밀저장소", "full_stack_lab/gateway/app/upstream.py", "credential_headers", [
  ("공식 SDK", "Vault/OpenBao/AWS/Azure/GCP 공식 SDK·배포 라이선스 구분", "Enterprise 전용 연동을 OSS 기능으로 기재"),
  ("workload 신원", "AppRole/IAM/ManagedIdentity/WorkloadIdentity의 최소 권한 적용", "장기 root/master key 공유"),
  ("회전", "회전·철회·lease 만료·캐시 TTL과 실행 직전 상태 대조", "회전 뒤 기존 credential 무기한 캐시"),
  ("장애", "secret 조회 실패·TLS/CA 실패는 anonymous fallback 금지", "secret 오류 후 무자격 실행"),
  ("전달", "공급자 자격만 readonly mount·TTL·로그 최소화로 전달", "secret.value/JWT를 대화·설정·Excel에 출력")]),
 ("운영", "full_stack_lab/gateway/app/system_metrics.py", None, [
  ("자원 범위", "CPU/메모리 Linux VM·container quota·물리 PC 범위 구분", "미측정 CPU를0으로 표시"),
  ("연결 범위", "내부 TCP ms·endpoint RTT·jitter·실패율/패킷손실 구분", "HTTP health 처리 시간을 network RTT로 표시"),
  ("게시", "Tailnet Caddy·모델 proxy의 정확한 주소/포트/프로토콜만 게시", "wildcard·DB·추가 포트 노출"),
  ("복구", "backup/restore·DB migration·rollback·서비스 장애 복구 검증", "health 정상만으로 복구 성공"),
  ("HA", "다중 replica 예약·세션·원장·policy版本 일관성 검증", "단일기기 통과를 기업 HA 완료로 기재")])
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    head = git("rev-parse", "HEAD").decode().strip()
    metadata = {"head": head, "branch": git("branch", "--show-current").decode().strip(),
                "scope": "structural_inventory_and_curated_acceptance_conditions",
                "deployment_inferred": False, "runtime_test_results_inferred": False}
    modules = []
    for path in sorted([*REPO.glob("full_stack_lab/gateway/app/*.py"), *REPO.glob("full_stack_lab/supply_chain/*.py"),
                        *REPO.glob("endpoint-agent/*.py")]):
        rel = path.relative_to(REPO).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                calls = sorted({ast.unparse(c.func) for c in ast.walk(node) if isinstance(c, ast.Call)})
                functions.append({"symbol": node.name, "line_start": node.lineno, "line_end": node.end_lineno,
                                  "async": isinstance(node, ast.AsyncFunctionDef), "call_expressions": calls,
                                  "analysis_scope": "AST_body_calls_not_dynamic_dispatch_resolution"})
        imports = [ast.unparse(n) for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        modules.append({**evidence(rel), "imports": imports, "functions": functions})
    pipeline = [
      ("HTTP ingress", "main.py", "caller"), ("MCP transport identity", "mcp_facade.py", "_caller"),
      ("JWT/current state", "agent_contract.py", "authenticated_user"), ("approved listing", "mcp_facade.py", "_approved_tools"),
      ("execution boundary", "core.py", "execute_call"), ("resource/action classification", "classify.py", "classify"),
      ("principal scope", "pac.py", "scope"), ("policy document", "pac.py", "build"),
      ("PDP", "core.py", "_policy"), ("final contract/admission/policy", "core.py", "_call_upstream"),
      ("credential binding", "upstream.py", "credential_headers"), ("official MCP client", "upstream.py", "session"),
      ("result size/shape/injection", "core.py", "_guarded_result"), ("Presidio masking", "privacy.py", "mask_payload"),
      ("audit append", "core.py", "_record_decision"), ("wire result", "mcp_facade.py", "_render")]
    tests = [{"path": p.relative_to(REPO).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
              "reading_scope": "file_inventory_not_assertion_execution"} for p in sorted(REPO.glob("full_stack_lab/tests/*")) if p.is_file()]
    dump("code-structure.json", {"schema_version": 1, "metadata": metadata, "modules": modules,
         "pipeline": [{"step": i+1, "purpose": label, **evidence("full_stack_lab/gateway/app/"+file, symbol)}
                      for i, (label, file, symbol) in enumerate(pipeline)], "test_inventory": tests})
    # Existing human-reviewed conditions/results are canonical. Refresh links, never
    # reseed their statuses or silently discard new evidence on subsequent runs.
    existing = OUT / "requirements.json"
    if existing.exists():
        document = json.loads(existing.read_text(encoding="utf-8"))
        for row in document["records"]:
            row["code_evidence"] = [evidence(e["path"], None if e["symbol"] == "module/config" else e["symbol"])
                                    for e in row["code_evidence"]]
            for e in row["test_evidence"]:
                if e.get("symbol"):
                    raw = (REPO / e["path"]).read_bytes()
                    node = next(n for n in ast.walk(ast.parse(raw.decode("utf-8")))
                                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == e["symbol"])
                    e.update(line_start=node.lineno, line_end=node.end_lineno,
                             assertion_lines=sorted({n.lineno for n in ast.walk(node) if isinstance(n, ast.Call)
                                                     and isinstance(n.func, ast.Attribute) and n.func.attr.startswith("assert")}),
                             normalized_sha256=hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest())
        document["metadata"] = metadata
        dump("requirements.json", document)
        print(json.dumps({"requirements": len(document["records"]), "modules": len(modules),
                          "functions": sum(len(m["functions"]) for m in modules), "mode": "refresh_links_preserve_conditions_results"}))
        return
    gaps = {("계약", "출력 schema"), ("신원", "OBO"), ("주입", "대형 결과"), ("외부통신", "서버 egress"),
            ("실행", "사망"), ("실행", "효과 증거"), ("MCP결과", "확장 기능"), ("엔드포인트", "관측 공백"),
            ("감사", "외부 anchor"), ("LiteLLM", "MCP 경로"), ("LiteLLM", "프록시 신원"),
            ("LiteLLM", "private host"), ("운영", "복구"), ("운영", "HA")}
    unit = {("MCP결과", x) for x in ["구조화 보존", "구형 호환", "보류 경계", "결과 형식"]} | {("데이터", "결과 키")}
    rows = []
    for gi, (area, path, symbol, conditions) in enumerate(GROUPS, 1):
        for ci, (feature, acceptance, negative) in enumerate(conditions, 1):
            status = "verified_unit" if (area, feature) in unit else "gap" if (area, feature) in gaps or area == "비밀저장소" else "source_only"
            test = "full_stack_lab/tests/mcp_result_contract_check.py" if status == "verified_unit" else None
            rows.append({"id": f"REQ-{gi:02d}-{ci:02d}", "area": area, "requirement": feature,
                         "acceptance": acceptance, "negative_cases": [negative], "code_evidence": [evidence(path, symbol)],
                         "test_evidence": [{"path": test, "assertion": feature, "verification": "7_regressions_passed_2026-10-13"}] if test else [],
                         "status": status, "priority": "P0" if area in {"신원", "권한", "승인", "데이터", "외부통신", "실행", "MCP결과"} else "P1",
                         "gap": "실제 상용/OSS MCP와 독립 효과·정상/음성/경계·복구 조건의 실기기 검증 필요" if status != "gap" else "조건 전체 구현/운영 연결은 현재 증거로 충족하지 못함",
                         "source_refs": ["analysis/code-structure.json", "experiments/README.md"]})
    dump("requirements.json", {"schema_version": 1, "metadata": metadata, "records": rows})
    manifest = json.loads((ROOT / "solutions/evidence/manifest.json").read_text(encoding="utf-8"))
    comparisons = []
    products = [
      ("ibm-contextforge", "IBM ContextForge", ["도입", "계약", "신원", "권한", "데이터", "주입", "실행"], "공식 설정/코드의 사전·사후 훅/PDP/OAuth·PII 구현. 활성 구성은 항목별 확인"),
      ("ibm-cpex", "IBM CPEX", ["실행", "데이터", "주입"], "공개 원자 호출량·검사 플러그인. 외부framework 배선은 별도"),
      ("ms-mcp-gateway", "Microsoft MCP Gateway", ["도입", "권한", "신원"], "역할·소유권 평가. 실제 조직 설정/집행은 미실행"),
      ("ms-wassette", "Microsoft Wassette", ["엔드포인트", "외부통신", "운영"], "Wasm/WASI 도구 실행 권한 경계. OS전체/MCP원격 통제와 별도"),
      ("litellm", "LiteLLM", ["LiteLLM", "권한", "신원", "비밀저장소"], "명시 MCP 서버 scope·session 상한. nativeSecretManager 라이선스 별도"),
      ("kong-ai-gateway", "Kong AI Gateway", ["LiteLLM", "신원", "권한"], "공식문서 MCP proxy·ACL·OAuth. 실제 배치/동등시험 미실행"),
      ("beyondtrust-pathfinder", "BeyondTrust Pathfinder", ["신원", "승인", "종료"], "공식문서 사이트·사용자 활성/기한 토큰. 운영회수 미실행"),
      ("lunar-mcpx", "Lunar MCPX", ["외부통신", "권한", "감사"], "공급자 MCPX+별도Gateway egress 연동 설명. 제품간효과 비교 미실행")]
    for key, product, areas, feature in products:
        page = ROOT / "solutions" / (key+".md")
        assert page.is_file(), key
        items = [m for m in manifest if m["solution_id"] == key]
        for row in rows:
            if row["area"] not in areas:
                continue
            ref = items[0] if items else None
            comparisons.append({"id": f"CMP-{len(comparisons)+1:03d}", "requirement_id": row["id"],
                "product": product, "version_or_commit": ref["commit"] if ref else "official_document_2026-10-13",
                "feature": feature, "evidence_url": ref["repository"]+"/blob/"+ref["commit"]+"/"+ref["source_path"] if ref else "solutions/"+key+".md",
                "evidence_paths": [m["path"] for m in items], "evidence_kind": "pinned_source" if ref else "vendor_documentation",
                "control_level_verification": "individual_condition_not_equivalent_tested",
                "our_gap": row["gap"], "verification": "unknown_for_this_atomic_condition", "analysis_page": "solutions/"+key+".md"})
    # A product's broad category is not proof of every atomic condition. Retain only explicit source facts.
    facts = [
      ("ibm-contextforge","REQ09-02","unified_pdp.py","PDP default deny and 60-second decision cache; expiry/revocation cache test still required"),
      ("ibm-contextforge","REQ03-05","oauth_manager.py","RFC8693 subject token/audience/scope construction; our OBO is not implemented by this fact"),
      ("ibm-contextforge","REQ06-02","config.yaml","PII plugin mode enforce, block_on_detection false; masking is not blanket blocking"),
      ("ibm-contextforge","REQ09-03","watchdog.py","pre/post elapsed-time inspection; active-process interruption is not proven"),
      ("ibm-contextforge","REQ07-04","unified_pdp.py","tool_pre_invoke PDP deny stops processing; not equivalent to contract drift detection"),
      ("ibm-cpex","REQ09-02","redis_backend.rs","Redis Lua batches counter/TTL operations atomically for rate windows"),
      ("ibm-cpex","REQ06-04","framework_bridge","external cpex.framework import; public plugin code is not whole exception contract"),
      ("ms-mcp-gateway","REQ04-02","SimplePermissionProvider.cs","management read owner/admin/RequiredRoles; write owner/admin; empty required roles do not permit general user"),
      ("ms-mcp-gateway","REQ04-01","BuiltinToolAuthorizer.cs","built-in tool authorization checks ClaimsPrincipal roles with admin/configured roles"),
      ("ms-wassette","REQ08-05","http.rs","component HTTP URI host/scheme allowlist with HttpRequestDenied"),
      ("ms-wassette","REQ11-02","wasistate.rs","WASI preopened directories and no inherited network; not employee-wide process control"),
      ("ms-wassette","REQ01-02","runtime_context.rs","Wasmtime component model and explicit WASI/HTTP/config linker assembly"),
      ("litellm","REQ04-04","server.py","explicit unresolved MCP server names return empty list, not all allowed servers"),
      ("litellm","REQ03-05","mcp_server_manager.py","session resource scope caps explicitly scoped credentials and submitted server union"),
      ("litellm","REQ14-03","server.py","MCP aggregation path exists in pinned source; our current config lacks mcp_servers"),
      ("kong-ai-gateway","REQ04-01","https://developer.konghq.com/plugins/ai-mcp-proxy/","documented MCP proxy/tool ACL; actual configured deny/list/call behavior untested"),
      ("kong-ai-gateway","REQ03-01","https://developer.konghq.com/plugins/ai-mcp-proxy/","documented OAuth integration; deployment issuer/audience validation requires real tests"),
      ("beyondtrust-pathfinder","REQ05-04","https://docs.beyondtrust.com/bt-docs/docs/configure-pathfinder-mcp","site enable/read-only/per-user token expiry; not arbitrary MCP per-call approval"),
      ("beyondtrust-pathfinder","REQ13-02","https://docs.beyondtrust.com/bt-docs/docs/configure-pathfinder-mcp","token revoke vs expired-token delete; site off disconnects existing tokens per docs"),
      ("lunar-mcpx","REQ08-05","https://www.lunar.dev/post/safely-running-untrusted-mcp-servers-with-lunar-mcpx-and-gateway-integration","MCPX plus separate Gateway mediates server outbound API paths; bypass coverage unproven"),
      ("lunar-mcpx","REQ04-01","https://www.lunar.dev/post/mcp-gateway-access-controls-defining-permissions-for-llm-agents","global/consumer/service/tool ACL; consumer-tag example is not cryptographically verified employee identity")]
    comparisons = []
    for key, req, selected, fact in facts:
        req = req.replace("REQ", "REQ-", 1)
        row = next(r for r in rows if r["id"] == req)
        product = next(p[1] for p in products if p[0] == key)
        ref = next((m for m in manifest if m["solution_id"] == key and selected in m["source_path"] and "line_ranges" in m), None)
        assert ref or selected.startswith("https://"), (key, selected)
        comparisons.append({"id": f"CMP-{len(comparisons)+1:03d}", "requirement_id": req, "product": product,
            "version_or_commit": ref["commit"] if ref else "official_document_2026-10-13", "feature": fact,
            "evidence_url": ref["repository"]+"/blob/"+ref["commit"]+"/"+ref["source_path"]+"#L"+str(ref["line_ranges"][0][0]) if ref else selected,
            "evidence_paths": [ref["path"]] if ref else [], "evidence_kind": "pinned_source" if ref else "vendor_documentation",
            "our_gap": row["acceptance"]+": "+row["gap"], "verification": "source_pattern_partial_condition_not_equivalent_tested",
            "analysis_page": "solutions/"+key+".md"})
    dump("competitor-mapping.json", {"schema_version": 1, "metadata": metadata, "records": comparisons})
    print(json.dumps({"requirements": len(rows), "modules": len(modules), "functions": sum(len(m["functions"]) for m in modules),
                      "comparisons": len(comparisons), "scope": metadata["scope"]}))


if __name__ == "__main__":
    main()
