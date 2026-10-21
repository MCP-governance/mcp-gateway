# 2026-10-21 DEV-77 출처 서명·빌드 증명 검증

- 작업자: Codex
- 코드 기준: `512c30b38a587a1751c57c7e93f5689ddf487827` (`main`, `origin/main` 로컬 추적값); 원격 `origin/HEAD` 조회 실패. Git 브랜치 생성이 `.git/refs/heads` 권한 거부로 실패해 변경은 현재 체크아웃의 미커밋 상태다. 보조 체크아웃은 만들지 않았다.
- 시작 근거: DEV-77 / D-179 예약, 방향 갱신 10-20 3장, DEV-73 F3 및 arbitration, D-114, D-137, TC260 6.2.2(방향 문서 인용).
- 해결할 문제와 완료 조건: 출처 서명·빌드 증명을 도입 승인과 실행기 시작에서 검증하고, 불일치는 보류, 미제공은 표시만, 검증 불가는 별도 보류한다.

상태: **부분 구현**. 확인 가능한 저장형 SLSA DSSE proof 검사와 부팅 재검사는 연결했으나, OCI referrer/릴리스 증명을 자동 수집해 제안값으로 채우는 입력 경로는 미구현이다. 따라서 요청된 실제 OCI 이미지/릴리스 증명 검증 완료로 간주하지 않는다.

## 결과

기존 `cryptography==50.0.1`로 DSSE PAE의 Ed25519 서명을 검증하는 모듈을 추가했다. 대상은 in-toto Statement v1 / SLSA Provenance v1이며, 관리자 설정 키 ID와 허용 builder ID 및 intake 기록 SHA-256이 모두 맞아야 `검증됨`이 된다. 신뢰 키는 읽기 전용 `/provenance-trust-keys.json`에서 읽는다. 처음 관찰한 키는 신뢰하지 않는다.

관리자 승인 경로에서 서명 상태를 보관하고 콘솔에 `검증됨`·`확인 안 됨` 등을 표시한다. 불일치와 검증 불가는 기존 `MCP-SUPPLY-001`로 보류한다. runtime-worker는 승인 당시 저장한 envelope와 source archive digest를 빌드 전 및 활성 런타임 재조정 때 확인한다. 증명 부재는 계속 진행한다. 실행 중 OCI image ID 확인과 D-114 고정 commit/recipe 흐름은 유지한다. DEV-73 `local_jobs.py`, `endpoint-agent/local-runner.py`는 변경하지 않았다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 신규 시험 | `python -X utf8 full_stack_lab/tests/provenance_verify_check.py`, Windows Python 3.10 | 실패: `ModuleNotFoundError: No module named 'cryptography'`. 프로젝트 requirements에 고정된 의존성이나 이 로컬 Python에는 미설치, pip cache도 없음 | 콘솔 결과 |
| 정적 Python 구문 | `python -m py_compile full_stack_lab/gateway/app/artifact_provenance.py full_stack_lab/gateway/app/agent_service.py full_stack_lab/runtime/worker.py full_stack_lab/tests/provenance_verify_check.py` | 통과 | 종료 코드 0 |
| Node 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 | 종료 코드 0 |
| 기존 콘솔 상태 시험 | `node --test full_stack_lab/tests/console-state.test.mjs` | 통과: 15/15 | stdout |
| 무인증 라우트 | `python -X utf8 full_stack_lab/tests/open_endpoints.py` | 통과: 무인증 1개, 인증 필요 84개 | stdout PASS |
| pyflakes | `python -m pyflakes ...` | 미실행: `No module named 'pyflakes'` | 콘솔 결과 |
| 배포·실기기/PJ1 | 사용자 범위 제외 | 미실행 | |

## 실패·미완료·한계

- 새 시험 파일은 요구한 정상 서명, 불일치 및 정책 ID, 미제공 허용, 검증 경로 오류 구분, 기동 시 고정 digest, 미설정 신뢰 키 비신뢰를 다룬다. 의존성이 없는 현지 Python에서 실제 암호 검증 실행을 완료하지 못했다.
- 구현은 이미 저장된 DSSE proof를 소비한다. OCI referrer/릴리스 proof 자동 발견, Cosign bundle/keyless/Rekor, RSA/ECDSA, OCI registry manifest digest 검증은 미구현이다. 현재 제품 데이터 경로가 증명을 공급하지 않으면 `확인 안 됨`으로 진행하므로 실제 공급자 서명 적용률을 증명하지 않는다.
- TC260 6.2.2는 방향 문서의 인용을 사용했으며 공식 원문 조항 사본을 다시 확인하지 않았다. 사용자 요청대로 기기·PJ1 검증은 하지 않았다.
- Git 브랜치 생성 거부: `.git/refs/heads/10/21-dev77-provenance.lock` 생성 권한 없음. 변경은 미커밋이며 사용자가 지정한 대로 현재 체크아웃에 남겼다.

## 다음 작업

1. 지정된 작업 클론에서 기존 `cryptography` 런타임 의존성이 있는 환경으로 새 시험을 실행한다.
2. 적대 검토 후, OCI image referrers/Cosign 또는 DSSE proof 제공 경로를 정확한 배포 범위로 추가한다.
3. 제품 기기 배포와 PJ1 하네스 검증은 별도 승인된 작업에서 수행한다.

## 사용자에게 필요한 입력

관리자가 승인할 issuer public-key PEM과 허용 builder URI 목록, 실제 OCI/signed-release 증명 제공 지점이 필요하다. 공개 키는 `full_stack_lab/registry/provenance-trust-keys.json`에 등록한다. 자격 값은 저장하지 않는다.
