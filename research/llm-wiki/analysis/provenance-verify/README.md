# DEV-77 출처 서명·빌드 증명 검증

- 상태: 코드·단위 검증 완료, 현장 배포 전
- 기준: `512c30b38a587a1751c57c7e93f5689ddf487827` (`origin/main` 로컬 추적값, 2026-10-21 원격 조회 실패)
- 대상: 도입 승인 시 내부 반입 소스 아카이브, 승인 뒤 실행기 기동·재조정 시 동일 기록과 증거 재검사
- 분담: DEV-73은 내부 미러 allowlist·고정 digest·사전 반입만 담당한다. OCI 이미지 서명과 provenance 검증은 여기서 처리한다. DEV-73 코드 파일은 수정하지 않았다.

## 요구사항과 판정

| 조건 | 처리 |
| --- | --- |
| 신뢰 서명과 증명 subject가 도입 아카이브 SHA-256 및 허용 빌더와 일치 | `검증됨`, 승인/실행 허용 |
| 증명이 없음 | `확인 안 됨`, 기록 후 승인/실행 허용 |
| 서명 또는 subject digest·빌더 불일치 | `불일치`, `MCP-SUPPLY-001` 보류 |
| 증명·신뢰 키를 읽지 못하거나 검증 경로가 실패 | `검증 불가`, `MCP-SUPPLY-001` 보류 |
| 신뢰 키 ID가 설정에 없음 | TOFU 금지, `검증 불가`로 보류 |
| 기동 시 승인 기록의 source digest와 증명 subject가 다름 | 재검사에서 차단. 기동 시 새로 받아온 digest를 기준으로 삼지 않음 |

증명은 intake `provenance.verification.attestation`에 들어 있는 DSSE JSON envelope이며 `payloadType`은
`application/vnd.in-toto+json`, statement는 in-toto Statement v1, predicate는 SLSA Provenance v1이다.
`subject[].digest.sha256`, `predicate.buildDefinition.buildType`, `predicate.runDetails.builder.id`를 확인한다.
서명 키와 허용 builder ID는 관리자가 작성한 `/provenance-trust-keys.json`에서만 읽는다. 키 파일은 JSON의
`keyid: {"public_key": "PEM", "builders": ["https://.../builder"]}` 맵이며, 빈 기본 파일은 `{}`다.
키를 증명에서 받아 저장하거나 첫 관찰값으로 신뢰하지 않는다. Ed25519 공개키 검증은 이미 고정된
`cryptography==50.0.1`을 재사용한다.

## 도구·표준 조사

| 후보 | 판본·출처·라이선스 | 실제 범위와 판단 |
| --- | --- | --- |
| Sigstore Cosign | `v3.1.3`, 릴리스 커밋 `11926fa`(GitHub 검증 서명 표시), Apache-2.0. [공식 릴리스](https://github.com/sigstore/cosign/releases/tag/v3.1.3), [라이선스](https://github.com/sigstore/cosign/blob/v3.1.3/LICENSE) | OCI 이미지 서명과 keyless/key-based 검증, bundle 기반 오프라인 검증을 제공한다. 전체 CLI를 실행기 이미지에 추가하지 않았다. 이번 구현은 key-based DSSE/in-toto SLSA envelope의 Ed25519 경로만 검증하며 Cosign OCI referrer 조회, Sigstore bundle 인증서·Rekor 통합, keyless 신원 검증은 지원하지 않는다. |
| in-toto Attestation Framework | `v1.2.0`, 릴리스 커밋 `df02077`(GitHub 검증 서명 표시), Apache-2.0 프로젝트. [공식 릴리스](https://github.com/in-toto/attestation/releases/tag/v1.2.0), [프레임워크](https://github.com/in-toto/attestation), [봉투 규격](https://github.com/in-toto/attestation/blob/v1.2.0/spec/v1/envelope.md) | 표준 DSSE envelope가 payload type과 payload를 PAE로 함께 서명하는 방식을 정의한다. 프로젝트 코드나 SDK는 추가하지 않고 envelope 형식만 구현했다. |
| SLSA Provenance | v1 predicate, [공식 규격](https://slsa.dev/spec/v1.1/provenance) | 빌드 정의, builder, subject digest를 연결한다. 구현은 v1 형식과 configured signer-builder pair 및 subject 해시를 확인한다. 빌더의 신뢰성·빌드 격리·모든 input dependency 완전성까지 증명하지 않는다. |
| OCI Distribution Referrers API | `opencontainers/distribution-spec` v1.1.1, 릴리스 커밋 `a139cc4`, Apache-2.0. [공식 릴리스](https://github.com/opencontainers/distribution-spec/releases/tag/v1.1.1), [규격](https://github.com/opencontainers/distribution-spec/blob/v1.1.1/spec.md), [라이선스](https://github.com/opencontainers/distribution-spec/blob/v1.1.1/LICENSE) | OCI artifact를 subject digest에 연결하는 배포 방식이다. 현재 소스 intake는 OCI registry referrer를 직접 조회하지 않으므로 채택 구현에서 제외했다. OCI image의 원격 서명 유무 자동 탐지는 아직 미완료다. |

Cosign은 공식적으로 유지되는 상용/OSS 도구로 조사했으나, 현재 D-114 실행기는 자체 고정 레시피로 내부 미러 소스를 빌드하고 Gateway는 이미 `cryptography`를 보유한다. 이 범위에서 CLI·Go 바이너리·네트워크 검증 의존성을 늘리지 않고 표준 DSSE 검증만 추가했다. 추후 실제 OCI 이미지에 적용할 때는 Sigstore bundle 또는 OCI referrers와 Cosign 전체 검증 경로를 추가 검토해야 한다.

## 기존 기능과 경계

- `full_stack_lab/supply_chain/`: 소스 트리 SHA-256, 라이선스/SBOM, Trivy·Semgrep·Gitleaks 분석은 유지한다. 이 검사는 서명·빌드 증명 검증으로 간주하지 않는다.
- D-137 공급자 보증 필드는 바꾸지 않는다. 법인·연락처·지원 종료·보안 정책 등 사람 제출 보증과 암호학적 artifact 증명은 다른 증거다.
- D-114 실행기는 계속 내부 미러 commit과 보관본 해시를 대조하고 고정 레시피로 빌드한다. 이 변경은 그 경계를 완화하지 않는다.
- 승인 때 증명은 기존 provenance JSON에 저장되고 콘솔에 상태를 표시한다. 시작 때 저장된 증명과 기존 source SHA-256을 다시 검사하고, 실행 중 이미지 ID의 기존 동일성 확인을 유지한다.
- D-179의 현재 구현은 사전 저장된 증명 envelope만 소비한다. OCI referrer/릴리스 서명 수집기, Sigstore keyless 루트, Ed25519 외 키 알고리즘, 외부 HSM/KMS 연동, 실제 공급자 증명 검증은 대상 밖이며 기기·PJ1에서 확인하지 않았다.

## 요구사항-코드-시험 연결

| 요구사항 | 코드 | 시험 |
| --- | --- | --- |
| DSSE PAE 서명·SLSA builder·subject 해시 확인 | `full_stack_lab/gateway/app/artifact_provenance.py` | `full_stack_lab/tests/provenance_verify_check.py` |
| 승인 시 불일치/검증 불가 보류, 미제공 표시 | `full_stack_lab/gateway/app/agent_service.py`, `agent_static/console.js` | 새 증명 시험 및 intake 검증 |
| 기동·재조정 시 기존 증명 재검사 | `full_stack_lab/runtime/worker.py`, `runtime/Dockerfile`, `compose.field.yaml` | 새 증명 시험 |

TC260 6.2.2는 방향 문서가 DEV-77 근거로 인용한 요구사항으로 연결했다. 이 작업에서는 공식 원문 조항 사본의 별도 재검증은 하지 않았다.
