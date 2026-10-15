"""Consolidate current three-stage evidence; never convert a static plan to a pass."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
REPORTS = ROOT / 'status/reports'


def read(name, jsonl=False):
    path = REPORTS / name
    content = path.read_text(encoding='utf-8')
    return json.loads(content.splitlines()[-1] if jsonl else content)


def main():
    preserve = read('2026-10-14-risk-preserve.json')
    reset = read('2026-10-14-risk-db-reset.json')
    before = read('2026-10-14-risk-db-before.jsonl', True)
    after = read('2026-10-14-risk-db-after.jsonl', True)
    deployed = read('2026-10-14-risk-db-deployed-final.jsonl', True)
    deployment = read('2026-10-14-risk-deployment.json')
    postdeploy = read('2026-10-14-risk-postdeploy-pj1.json')
    assert postdeploy['ok'] and postdeploy['managed_mcp_initialize_status'] == 200
    integrity = read('2026-10-14-risk-reference-integrity.json')
    assert integrity['ok'] and len(integrity['references']) == 4 and integrity['diff_check_exit'] == 0
    assert preserve['result'] == 'passed' and len(preserve['evidence']) == 5
    assert reset['database_reset'] and reset['marker_absent_after']
    assert before['ok'] and len(before['cases']) == 5
    assert sum(bool(c.get('known_finding_exposed')) for c in before['cases']) == 2
    assert after['ok'] and deployed['ok'] and after['expect_atomic'] and deployed['expect_atomic']
    assert all(not c.get('known_finding_exposed') for c in deployed['cases'])
    assert deployment['ok'] and deployment['before'] == deployment['after']
    files = [p for p in REPORTS.glob('2026-10-14-risk-*') if p.suffix in ('.json', '.jsonl', '.patch') and p.name != '2026-10-14-risk-scenarios.json']
    sources = ['full_stack_lab/gateway/app/endpoint_plane.py',
               'research/llm-wiki/experiments/risk-scenarios/pj1_preserve_check.py',
               'research/llm-wiki/experiments/risk-scenarios/stateful_endpoint_check.py',
               'research/llm-wiki/analysis/risk-scenarios/static-endpoint.json',
               'research/llm-wiki/analysis/risk-scenarios/solution-references.json']
    hashes = [{'path': str(p.relative_to(REPO)).replace('\\', '/'),
               'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files + [REPO / s for s in sources]]
    static = json.loads((ROOT / 'analysis/risk-scenarios/static-endpoint.json').read_text(encoding='utf-8'))
    result = dict(date=datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds'),
        branch='10/14-risk-scenarios', baseline_head='ab6936c64f3578de8360b840f1928681714fa7bb',
        preserved_dirty_baseline=True, stage1=dict(type='static', report='analysis/risk-scenarios/static-endpoint.md',
            static_scenarios=len(static['scenario_matrix']), predicted_issues=['conditional local cached bearer delivery', 'state/event partial commit']),
        stage2=preserve, stage3=dict(reset=reset, before=before, after=after, deployed_image=deployed),
        deployment=deployment, postdeploy=postdeploy, reference_integrity=integrity,
        risk_scope=['LOCAL-RISK-01', 'LOCAL-RISK-08', 'LOCAL-RISK-11'],
        actual_model_harness_run=False, new_local_tool_calls=False, all_92_tools_tested=False,
        limitations=['PostgreSQL fixture schema and controlled failure/race injection, not real kernel attestation.',
            'Revocation journal failure returns an error and rolls back revocation; the caller must retry. No emergency deny store was added.',
            'Root/admin tampering, Windows kernel enforcement and arbitrary local bridges are outside the live test scope.',
            'Managed Unix socket cached bearer can remain locally deliverable until cache expiry; Gateway current-state validation is a separate boundary.'],
        evidence=hashes)
    (REPORTS / '2026-10-14-risk-scenarios.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    md = '''# 2026-10-14 위험매핑 기반 3단계 시험과 수정

- 작업자: Codex, Luna 3명(정적검토·DB시험코드·공식사례 분담)
- 코드 기준: `10/14-risk-scenarios`, HEAD `ab6936c64f3578de8360b840f1928681714fa7bb` + 기존 dirty 보존. 새 제품 변경은 `endpoint_plane.py`의 활성화·철회 두 함수.
- 시작 근거: LOCAL-RISK-01/08, E12/E13, PAC07/22/23/24. 새 결함은 LOCAL-RISK-11에 등록.
- 완료 기준: 정적 예상과 실제 결과 구분, 제품 DB 보존 시험, 전용 DB 실제 초기화, 실패 원인·공식 비교·수정·재검증·실제 배포 증거 확보.

## 결과

정적검토 → DB 보존 동적시험 → 전용 DB 초기화 후 선별시험을 수행했다. 감사기록 INSERT가 실패할 때 **활성화와 철회가 상태만 commit되는 결함 두 경로**를 실제 PostgreSQL에서 재현했다. 상태 변경과 감사기록을 같은 연결·트랜잭션으로 묶어 오류 시 함께 rollback하도록 수정했다. 정상 장치 승인/철회, 만료 heartbeat, 잘못된 epoch, 부적합 보고의 격리, 승인 시점 경합 대조군을 유지했다.

수정은 솔루션 머신의 실제 Gateway·agent-service·SSE image에 배포했고, 재빌드 image에서 같은 DB 5개 시나리오를 다시 통과했다. 배포 후에도 fresh PJ1 장치의 active/compliant·서비스 active·MCP initialize200을 [재확인](2026-10-14-risk-postdeploy-pj1.json)했다. 운영 DB `mcp_governance`의 PostgreSQL 시작시각과 principal 10·장치 12·설치 grant 14 건수는 배포 전후 동일했다. 이 건수 확인은 모든 DB 내용의 바이트 동일성을 증명하지 않는다.

## 1. 정적분석

[Luna 정적검토](../../analysis/risk-scenarios/static-endpoint.md)에는 함수·호출자·코드라인·판본 hash와 6개 예상 시나리오를 남겼다. static finding은 실제 우회 성공으로 세지 않았다.

| 시나리오 | 관련 위험 | 코드상 예상 | 실제 증거 경계 |
| --- | --- | --- | --- |
| pending·만료·철회·타 주체·다른 epoch | LOCAL-RISK-08 | `managed_failure`에서 거부 | DB 함수·실제 PJ1 만료는 아래 별도 증거 |
| 정상 OS점검 + 최근 heartbeat | LOCAL-RISK-08 | 활성 상태·최신 policy일 때 허용 | 실제 PJ1 initialize 200 |
| stdio 실행·loopback 접근 | LOCAL-RISK-01 | 승인 실행과 UID/profile의 네트워크 범위 밖 거부 | Node와 TCP22에 한정한 커널 확인 |
| 폐기 직후 Unix helper cache | LOCAL-RISK-08 | 로컬 bearer 전달은 최대120초 남을 수 있음; Gateway는 현재 장치 상태 재검사 | 전달 자체는 신규 실기기 재현하지 않았음; 권한우회로 분류하지 않음 |
| 활성화/철회 이벤트 INSERT 실패 | LOCAL-RISK-11 | 서로 다른 transaction이어서 상태만 commit 예상 | 실제 PG trigger 재현 후 수정 |

## 2. DB를 초기화하지 않은 동적시험

PJ1의 **설치된 코드와 실제 커널 정책**을 사용했다. 장치 키/JWT를 출력하지 않았고 DB timestamp를 조작하지 않았다. 장치의 보고 서비스만 일시 중지한 뒤 실제 188.91초 기다렸으며 finally에서 서비스와 정상 heartbeat를 복구했다.

| ID | 시험 | 독립 효과·결과 |
| --- | --- | --- |
| D01 | 활성 장치 MCP initialize | `/mcp/github/` HTTP200; 실제 설치 점검 정상 |
| D02 | fresh 관리 shell·승인 목적지·비승인 Node | enforce profile 확인, Gateway TCP443 exit0, Node exit126 |
| D03 | loopback TCP22 | root 연결 성공으로 수신자 존재 확인, 관리 UID 연결 exit1 |
| D04 | 실제 heartbeat 만료 | 아직 만료 전인 JWT도 HTTP403 `ENDPOINT-MANAGED-001`; 새 token 발급403 |
| D05 | 복구 | 서비스 active·정상 heartbeat·새 token initialize200 |

원본: [DB 보존 결과](2026-10-14-risk-preserve.json). initialize는 연결/인증 증거이며, 자연어 모델의 tools/call 또는 upstream 도구 효과로 세지 않는다. 기존 로컬 MCP 92개 도구의 재시험으로도 세지 않는다.

## 3. DB 초기화 후 선별시험

솔루션 머신에 공개 포트·제품 볼륨 없이 task label이 붙은 별도 PostgreSQL 컨테이너를 준비했다. **전용 DB `risk_scenarios_20261014`만 DROP/CREATE**했다. 초기화 전 marker 1행, 이후 marker table 부재를 독립 SQL로 확인했다. 운영·기존 interoperability DB는 초기화하지 않았다.

실제 `endpoint_plane` 함수의 DB 연결을 전용 DB의 고유 schema에 제한했다. 필요한 최소 fixture schema와 합성 장치/정상 health 입력을 사용했으므로 이 단계는 DB 상태·트랜잭션 시험이며 커널 점검 진실성의 증거가 아니다. 경합은 barrier, 감사 INSERT 실패는 PostgreSQL trigger로 주입하고 finally에서 trigger/schema를 정리했다.

| 묶음 | 초기 코드 | 수정 코드·재빌드 image |
| --- | --- | --- |
| pending→승인→만료→복구→epoch 불일치→철회 | 예상과 일치 | 통과 |
| 잘못된 policy heartbeat | quarantined, 감사1건 | 통과 |
| stale 활성화 CAS 경합 | pending 유지·승인 거부 | 통과 |
| 활성화 감사 INSERT 실패 | **active, 이벤트0건: 결함** | pending으로 rollback, 이벤트0건 |
| 철회 감사 INSERT 실패 | **revoked, 이벤트0건: 결함** | active로 rollback, 이벤트0건 |

기본 재현모드의 `ok=true`는 **결함이 예상대로 관측됐다는 뜻**이다. 제품 안전성 통과로 해석하지 않는다. 수정 검증은 `--expect-atomic` 별도 기준이다.

원본: [초기화](2026-10-14-risk-db-reset.json), [수정 전](2026-10-14-risk-db-before.jsonl), [수정 후](2026-10-14-risk-db-after.jsonl), [배포 image 최종](2026-10-14-risk-db-deployed-final.jsonl). 최초 image시험 raw도 [별도 보존](2026-10-14-risk-db-deployed.jsonl)했다. [재현 코드](../../experiments/risk-scenarios/stateful_endpoint_check.py)는 DB명 guard와 독립 연결 확인을 포함한다. [전용 DB 초기화 코드](../../experiments/risk-scenarios/reset_lab.py)는 솔루션 머신 전용이며 제품 DB명이나 컨테이너를 받지 않는다.

## 문제·타 솔루션·해결안

| 문제 | 공식 비교 근거 | 도출한 해결안·반영 |
| --- | --- | --- |
| 상태와 감사기록의 부분 commit | [PostgreSQL18 transaction](https://www.postgresql.org/docs/18/tutorial-transactions.html), [etcd Txn](https://etcd.io/docs/v3.6/learning/api/) | 기존 `db.transaction` 재사용, 동일 연결로 UPDATE+INSERT. 새로운 큐나 저장소 추가 없이 구현 |
| heartbeat 최신성과 실제 집행의 혼동 | [Kubernetes Lease](https://kubernetes.io/docs/concepts/architecture/leases/) | freshness와 점검을 별도 조건으로 검증; 실제 만료 시험188.91초. 원격 attestation을 구현했다고 주장하지 않음 |
| Unix socket same-UID 신원을 프로세스 권한으로 일반화 | [SPIRE 공식사례](../../analysis/risk-scenarios/solution-references.md) | UID 인증·OS 집행·Gateway 현재상태 검사 분리. 프로세스별 workload identity는 미구현 후속 과제 |

참조 판본·commit·license·읽은 범위·source hash는 [사례 정본](../../analysis/risk-scenarios/solution-references.json)에 보존했다. parent가 PostgreSQL18 transaction·etcd·Kubernetes 공식 문서를 별도 대조하고, **4개 pinned source 원문을 다시 확보해 hash 일치**를 [확인](2026-10-14-risk-reference-integrity.json)했다. PostgreSQL17 locking 비교 자료를 실행한 PostgreSQL18 image 판본으로 혼동하지 않는다. 이전 dirty와 분리한 실제 제품 delta는 [57줄 patch](2026-10-14-risk-implementation.patch)다.

## 검증·한계

- Linux 환경에서 기존 managed check 단위9개, Windows에서 inventory 단위6개 통과. pyflakes와 diff 공백 검사 통과.
- Windows Python의 Linux `grp` import로 managed check 실행은 실패했다. 같은 검사9개를 WSL/Linux에서 실행해 통과한 것이며 Windows 실제 방화벽 시험으로 세지 않는다.
- 실패한 철회는 **완료되지 않는다**. 감사 INSERT 장애 시 active로 rollback하고 API 오류를 반환하므로 운영자가 장애를 복구하고 재시도해야 한다. 감사 저장소와 독립적인 긴급 deny 경로를 구현한 것은 아니다.
- 로컬 bearer cache, Windows 실행/loopback, 임의 Blender/Ghidra bridge, 이름 변경 관측, 외부 전송·PII·계약·provider 철회 전체는 새 live시험 범위 밖이다. 기존 E01~E13 전체를 passed로 바꾸지 않았다.
- root/admin 변조는 관리 일반계정의 보안 경계 밖이다. kernel 정책 본문·실행파일 attestation은 후속 과제다.

## 다음 작업·필요 입력

DEV-23~26의 기존 Windows/loopback/전체도구/GUI/Windows report-lock 과제를 보존하고, DEV-27에 이번 수정과 실패한 철회 재시도 의미를 기록했다. 다음 우선순위는 승인된 실제 MCP의 도구 호출·수신 효과를 붙인 E12/E13 확대와 Windows 실제 기기 시험이다. 현재 수정에 추가 사용자 입력은 없음.
'''
    (REPORTS / '2026-10-14-risk-scenarios.md').write_text(md, encoding='utf-8')
    print(json.dumps(dict(stages=3, live_preserve_cases=5, reset_cases=5, confirmed_failure_paths=2,
                          fixed_deployed=True, evidence_files=len(hashes))))


if __name__ == '__main__':
    main()
