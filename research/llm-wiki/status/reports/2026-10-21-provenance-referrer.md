미커밋

# 2026-10-21 DEV-77 OCI referrer 수집과 되돌림 증명 재검증

- 작업자: Codex
- 코드 기준: `be09c9706b30b105b7dc9e2ded7b67c6a64889fb` (`main`, 작업 시작 시 clean). 요청에 따라 브랜치·fetch·commit은 하지 않았다. `origin/HEAD` 읽기 조회는 네트워크 차단으로 실패했다.
- 시작 근거: DEV-77 / D-179 잔여; `analysis/provenance-verify/README.md`; `analysis/runtime-rollback/defects-1021.md`; OCI Distribution v1.1.1, in-toto v1.2.0, Cosign v3.1.3 조사 기록.
- 해결할 문제와 완료 조건: 승인 제안에 허용된 OCI referrer를 자동으로 제안값으로 채우고, 수집 실패는 `확인 안 됨`, 발견된 증명 불일치 및 되돌린 판본의 현재 신뢰 키 검증 실패는 차단한다.

## 결과

- `artifact_provenance.py`에 표준 라이브러리 OCI Distribution referrer 조회와 `sha256-<hex>` tag fallback을 추가했다. 최대 4개 설정 registry origin만 조회하고 외부 origin redirect를 거부한다. 응답은 요청당 2 MiB, 개별 요청 timeout 3초, 전체 조회 8초, descriptor 16개, manifest blob 8개로 제한한다. cosign CLI와 새 런타임 의존성은 추가하지 않았다.
- `agent_service` 승인 미리보기에서 `MCP_PROVENANCE_REGISTRY_ALLOWLIST` 설정을 읽고 찾은 DSSE envelope를 제안의 `provenance.verification.attestation`에 넣는다. 새 증명이 없거나 네트워크·인증·형식 조회가 실패하면 `확인 안 됨`으로 남긴다. 찾은 증명은 기존 검증기로 확인하며 불일치·검증 불가는 `MCP-SUPPLY-001` blocker가 된다. 제안 승인 시에도 현재 키로 다시 확인한다. 실제 설정 전달을 위해 base compose의 agent-service에 allowlist 환경 변수를 연결했다.
- `worker.py`는 되돌림 대상 evidence에 in-toto DSSE envelope가 있으면 현재 trust key 파일로 큐잉 전, 그리고 rollback job 실행 전에 다시 검증한다. 거부된 대상은 `runtime-rollback-refused` 사건을 남기고 새 세대를 만들지 않는다. 검증한 상태는 새 세대 evidence에 기록한다. 증명이 없으면 기존대로 진행한다. 이후 실행 중 키가 회수된 경우에는 기존 active-runtime 검증과 `stop_refused` 재큐잉 방지 경로가 적용된다.
- 기존 intake 데이터에는 OCI 이미지 digest가 없고 `artifact.sha256`은 source archive digest다. 따라서 구현은 그 digest가 OCI subject로 게시된 경우에 한해 referrer를 찾는다. 로컬 빌드 image manifest digest와의 연계는 이 작업에서 만들지 않았다.
- 신규 시험 `provenance_referrer_check.py`와 `runtime_rollback_provenance_check.py`를 추가했다. 지정된 기존 시험 파일은 수정하지 않았다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| Python 구문 | `python -m py_compile` 대상 gateway·worker·신규 시험 5개, Windows Python 3.10.5 | 통과, 종료 코드 0 | 이번 실행 stdout 없음 |
| diff 공백 검사 | `git diff --check` | 통과, 종료 코드 0 | 이번 실행 stdout 없음 |
| 신규·기존 Python 시험 | 요청된 7개 시험 파일 개별 실행, Windows Python 3.10.5 | 전부 실행 불가: `cryptography` 미설치. `runtime_worker_check.py`는 추가로 Python 3.11 이전 기본 라이브러리인 `tomllib`도 없음 | 콘솔 오류: `ModuleNotFoundError` |
| WSL 대체 실행 | `wsl.exe -d kali-linux -- python3 --version` | 미실행: WSL 서비스가 `E_ACCESSDENIED` 반환 | 콘솔 오류 |
| 변경 민감도 확인 | 수정별 원복 후 시험 재실행 | 미완료: 시험 실행 환경 부재 | |
| 기기·PJ1 | 사용자 요청 범위 제외 | 미실행 | |

## 실패·미완료·한계

- 새 시험과 기존 회귀 시험의 실행 결과를 확인할 수 없어 작업 완료/회귀 통과로 판정하지 않는다. 프로젝트 의존성이 있는 Python 환경에서 두 신규 파일과 지정된 기존 5개 시험을 실행하고, 수정별 민감도 확인을 이어야 한다.
- OCI query 입력은 현행 저장소 intake의 source artifact SHA-256이다. OCI 이미지 manifest digest와 source archive digest는 같다고 가정하지 않는다. OCI 이미지 referrer를 제품 intake 증명에 연결하려면 이미지 digest와 repository 좌표를 공급하는 신뢰된 경로가 추가로 필요하다.
- registry 인증 정보는 도입하지 않았다. 인증이 필요한 registry 응답은 편의 수집 실패로 간주되어 `확인 안 됨`으로 남는다.
- 로컬 정적 검사와 단위 시험만 대상이며 실제 OCI registry, 배포 기기, PJ1에서 확인하지 않았다.

## 다음 작업

1. 프로젝트 고정 `cryptography` 및 Python 3.11+가 설치된 격리 환경에서 신규·기존 시험을 실행한다.
2. OCI artifact digest 수집 경로를 보강한다면 registry origin allowlist와 image repository/digest의 신뢰된 연결원을 먼저 정한다.
3. 적대 검토 후 필요하면 솔루션 기기와 PJ1에서 별도로 검증한다.

## 사용자에게 필요한 입력

운영 시 공개 registry origin이 있으면 `MCP_PROVENANCE_REGISTRY_ALLOWLIST`에 HTTPS origin 목록을 설정한다. 비공개 registry를 쓰려면 자격을 저장하지 않는 인증 제공 방식을 별도 결정해야 한다. 이 작업에는 자격 값이 필요하지 않았다.

## 방향 제안

현재 intake는 GitHub 소스 저장소를 사전 반입해 로컬에서 image를 빌드하므로, 도입 미리보기 시점에는 그 실행 image의 manifest digest가 존재하지 않는다. 실제 image digest의 OCI referrer를 도입 승인 제안에 넣으려면 빌드 후 증명과 도입 승인 순서를 바꾸거나, 별도 승인된 OCI image 입력 경로를 설계해야 한다. 이번 코드는 현재 보유한 source artifact digest로 조회 범위를 한정했다.
