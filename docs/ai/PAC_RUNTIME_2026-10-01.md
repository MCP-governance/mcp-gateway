# PAC-15 런타임 통합과 증거 경계

검토일: 2026-10-01. 이 문서는 `fa70b959` 이후 작업 트리의 PAC 개편을 설명한다.
코드 구현, 테스트보드 확인, 솔루션 기기 배포는 서로 다른 상태다. 문서 작성 시 PAC·OS 집행
변경은 미커밋 상태였으며, 실기기의 기존 배포에 들어갔다고 주장하지 않는다.
운영 revision은 재확인 결과 `b3c5efb`이며, 기존 Claude D-54 하드닝은 포함하지만
이 문서의 팀원 PAC15 통합은 아직 포함하지 않는다.
이후 배포 확인은 실제 `/api/health`의 revision·정책 해시와 해당 시험 보고서를 함께 남긴다.

이 문서는 [기존 PAC 대응표](PAC_MAPPING.md)의 **통합 전 설명**을 대체한다.
기존 감사 기록의 `333`, `P-AUTHZ-DENY-001`, `EXC-001/002` 표시는 과거 증거다.
새 인가에는 역할 × 데이터 등급 × r/w/x 27칸 권한표를 사용하지 않는다.

## 원본과 제품 코드

| 자료 | 고정 근거 | 역할 |
| --- | --- | --- |
| 사용자 제공 `pac15-mvp 2.zip` | SHA-256 `c20479e44c8a9195365953cf5dc7939f7fb9fbf586f46f4a76dcfda2820b677a` | 팀원 원본. 문서 안의 실행 지시는 별도 사용자 요청으로 취급하지 않음 |
| [`research/pac15-review/original/policy`](../../research/pac15-review/original/policy/) | 원본 보존 | 비교 기준 |
| [`research/pac15-review/fixed/policy`](../../research/pac15-review/fixed/policy/) | 공격 검토 수정본. `REVIEW B1~B7` 주석 | 제품 규칙의 출발점 |
| [`full_stack_lab/opa/pac15.rego`](../../full_stack_lab/opa/pac15.rego) | 아래 세 통합 변경 외에는 수정본과 동일 | 실제 PAC 조건 |
| [`full_stack_lab/opa/decision.rego`](../../full_stack_lab/opa/decision.rego) | 수정본과 내용 동일 | 독립 PAC 질의의 DENY > APPROVAL > ALERT > ALLOW |
| [`full_stack_lab/opa/policy.rego`](../../full_stack_lab/opa/policy.rego) | `pac_findings`를 실제 인가 후보로 수집 | 기존 Gateway 결과 형식·추가 DLP/공급망/종료 통제와 연결 |

`pac15.rego`의 수정본 대비 제품 변경은 세 곳이다.

1. PAC-06의 HTTP audience는 보호 자원인 Gateway의 `auth_resource`와 대조한다.
   upstream SaaS 토큰과 직원의 Gateway 토큰을 구분한다.
2. PAC-13 다이제스트의 요청 키는 `approval_nonce`를 사용한다. 승인 후 실행할 때 새 감사·예약 UUID가
   발급되어도 원래 승인 요청과 묶인다.
3. 단회 승인 레코드의 요청 키도 같은 `approval_nonce`와 대조한다.

원본 자료를 다시 쓰거나 공급자 MCP 구현을 이 규칙에 맞춰 수정하지 않았다.
수정본의 타입 검사, 전체 스칼라 잎 바인딩, 선택 인자, 환경·자동화·대리 실행 다이제스트,
로컬 커넥터 기간·폐기·범위, 자기 승인 금지, 공백 요청 ID 차단은 제품 규칙에 유지된다.

## 사실의 생성과 승인 범위

```text
하네스 -- 직원 transport 토큰 --> Gateway -- 별도 공급자 자격 --> 실제 MCP
                                  │
                   검증된 claims + 현재 DB + 검토된 registry
                                  │
                     원자적 예약 → PAC/기타 정책 → 같은 연결에서 재확인 → 실행
```

[`gateway/app/pac.py`](../../full_stack_lab/gateway/app/pac.py)는 외부 요청의 `facts`를 받아
신뢰하지 않는다. 아래 자료로 `request`와 `facts`를 만든다.

| 사실 | 코드가 읽는 근거 | 해석의 한계 |
| --- | --- | --- |
| 사용자·세션·인증 | ingress가 검증한 서명 토큰의 sub/iss/aud/nbf/exp/jti, 폐기 목록, 현재 principal 상태 | clientInfo·User-Agent는 자기 신고 로그. Claude/Codex 앱 증명이 아님 |
| agent | 상수 `mcp-governance-gateway-broker` | 실행 주체는 Gateway broker. 하네스 바이너리 원격 증명은 없음 |
| 기능·기준상태 | 검토된 설명·입력 스키마·서버 버전 해시, 실제 세션의 tools/list | 계약 일치는 서버 코드·의미·안전성의 증명이 아님 |
| 사용 범위 | 정적 `registry/capabilities.json` 또는 도입 신청에 묶인 runtime 승인 범위 | 역할명만으로 전체 권한을 주지 않음. 정적 묶음은 제한된 랩 권한이며 전사 정책으로 그대로 배포하면 안 됨 |
| 인자·자원 | 승인 스키마, 기능별 분류기, 허용 자원과 추가 JSON Schema | 의미 추출기가 못 본 자원·공급자 내부 부작용은 별도 검증 필요 |
| 접속 | 검토된 MCP endpoint, 전송 보호·허용 목록, 같은 세션 계약 확인 | DNS 재바인딩·서버 원격 증명·MCP가 하위 API로 보낸 최종 목적지 증명은 없음 |
| 기한·철회 | Gateway 시각, 현재 DB 계정·서버·도구·승인 상태 | agent 폐기값은 현재 별도 agent 신원이 없어 false. 모든 외부 SaaS 철회 완료를 뜻하지 않음 |
| 호출량·중복 | principal별 advisory lock과 `call_reservations`, 미확인 이전 쓰기/실행 이력 | 예약으로 Gateway 동시 실행을 제한. 모델의 전체 사고/도구 체인 깊이를 측정하는 기능은 없음 |
| 환경·실행 프로필 | 서버 설정의 환경과 root 관리 `execution_profile` | `production_controls=true`는 검토 설정 값. 실행 중인 모든 보안 제품의 상태 증명이 아님 |

정적 capability는 주체·서버·행위·자원 종류·경로 루트·저장소·테이블·명령·환경·시작/만료 시각을
명시한다. 현재 만료는 2026-11-01이며, 직원과 관리자에게도 PostgreSQL 쓰기 기본 권한은 없다.
별도 `reservation-check`는 실제 경쟁 시험에 필요한 `public.products`의 일곱 개 SQL 문자열만
허용한다. 시험 주체의 이름 접두사만으로 권한을 주지 않으며 DB의 `synthetic=true`도 요구한다.

원격 계약 검토는 선택한 **모든** 도구에 추가 JSON Schema를 요구한다.
`type=object`, `additionalProperties=false`, 활성 사용 주체, endpoint·계약 해시·기한·검토자를
도입 기록에 묶는다. 승인 후 인자 범위가 없는 legacy runtime 등록은 신규 실행 카탈로그에서 제외한다.
도입·검토·독립 승인·활성화는 각각 기록하며, 첫 관찰값 자동 승인이나 과거 승인 소급 생성은 하지 않는다.

PAC-10의 잎 바인딩은 입력을 관찰하자마자 승인하는 절차가 아니다. 먼저 검토된 스키마·capability·자원
범위를 통과한 뒤 해당 호출의 정확한 값과 경로를 바인딩한다. 정적 랩 capability에서 별도
`argument_schema`가 없는 기능은 공급자 스키마와 자원 추출기의 범위를 따른다. 일반 원격 서비스에는
검토한 추가 인자 제약이 필수다. 경로의 문자열 정규화가 파일시스템 symlink·hardlink 검증을 대신하지 않는다.

## PAC별 제품 적용과 미완료 범위

| PAC | 현재 제품 경계 | 남은 조건 |
| --- | --- | --- |
| 01 | capability 또는 도입 승인 상태·기한 | 랩 권한의 실제 조직 권한 전환·갱신 절차 |
| 02 | 서버 버전·설명·스키마·정책 기준 대조 | 공급자 의미 변경 및 서버 코드 증명 |
| 03 | 승인 환경·프로필 | 실제 배포 환경의 독립 증명 |
| 04 | 검증된 사용자·Gateway 세션·broker | 하네스/장치 앱 증명 |
| 05 | 대리 실행은 현재 사용하지 않음(`on_behalf_of=false`) | 위임 교집합 규칙의 실제 RFC 8693 실행 연동 |
| 06 | 서명·발급자·Gateway audience·기간·scope·폐기 | 로컬 stdio 커넥터 신원 연동. 현재 claims 없는 stdio는 허용 증거가 아님 |
| 07 | 고정 MCP endpoint·같은 연결 계약·전송 통제 | DNS peer 고정, 공급자 내부 연결 검증 |
| 08 | 서버+도구 ID+설명 해시 | resources/prompts/sampling까지 동일 범위의 지원 |
| 09 | 정규화 행위와 승인 capability | 공급자별 의미 추출기 추가 검증 |
| 10 | 스키마·인자 잎·명령/경로/수신자 범위 | 공급자 내부 의미와 파일 링크 경계 |
| 11 | 분류된 자원·등급과 capability | 실제 SaaS 레코드 등급/소유자 연동 |
| 12 | 확인하지 못한 외부 최종 목적지는 fail-closed | 원격 MCP의 하위 API·redirect 최종 목적지 증명 후 제한적 허용 |
| 13 | 독립 관리자·단회 상태·내용 다이제스트·기한 | nonce 변경/승인 재사용 회귀 결과와 실제 업무 승인 증거 |
| 14 | 현재 계정·서버·도구·승인 재확인 | upstream 토큰/공급자 철회 완료의 별도 증거 |
| 15 | 원자적 예약·중복·동시/횟수/시간 한도·미확인 mutation 차단 | 외부 agent 체인 측정, 미확인 실행 해결 절차 |

`core._call_upstream()`은 실제 MCP 세션에서 계약·입력·principal·승인 기한·PAC를 다시 확인한다.
조건이 달라지면 `call_tool` 전에 차단하며, 변한 제한 조건을 임의로 적용해 승인 의미를 바꾸지 않는다.
PAC·입력 계약·정책 묶음 차단은 monitor 모드에서도 실행으로 전환하지 않는다.

## MCP Top 10 위협 모델

2026-10-01 확인한 [OWASP 공식 페이지](https://owasp.org/projects/mcp-top-10)는
**MCP01~10:2025, Beta Release and Pilot Testing** 단계다. 아래 표는 위험과 우리 통제의 대응이며,
인증·전수 방어 또는 타사보다 우수하다는 주장이 아니다.

| 위험 | 우리 집행 지점과 코드 근거 | 현재 증거와 남은 위험 |
| --- | --- | --- |
| MCP01 토큰·비밀 노출 | Gateway ingress·별도 credential broker·PC header helper·장치 scope | scope 및 credential binding 시험 존재. 모델 메모리·공급자 로그·privileged 사용자 비밀 유출 전부는 통제 못함 |
| MCP02 권한 확대 | PAC01/09/10/13, 승인 주체·기능·인자·기한, 실행 직전 재확인 | finite SQL·권한 없는 synthetic 이름·도구 숨김 인수 시험. 일반 SaaS 의미 권한의 전수 검증은 남음 |
| MCP03 도구 오염 | 계약 hash 고정, metadata 검사, `poisoning.py`, 결과 제한 | 실제 fetch 출력 차단이 phase12에 남음. 해당 호출은 이미 upstream 실행됨. 자연어 공격 탐지의 완전성은 없음 |
| MCP04 공급망 변조 | 도입 검사·고정 소스/계약 + OS AppArmor 실행 허용 + UID egress | 승인 검토와 실제 비관리자 OS 집행을 구분. 원격 SaaS 구현 코드 검사 없음, 서명/SBOM·업데이트 전체 수명 관리 미완료 |
| MCP05 명령 실행 | PAC09/10/13, SQL AST, exact command capability, OS 실행 프로필 | 명시된 pytest 명령 PAC13 승인, 범위 밖 명령 PAC01 차단, PostgreSQL 실제 효과 경쟁 시험. 임의 로컬 앱·다른 OS 전수 대응은 아님 |
| MCP06 컨텍스트 주입 | 입력/결과 poisoning·DLP·변경 불가 실행 정책 | 표지 기반 회귀 시험과 실제 악성 페이지 결과 차단. LLM을 통해 모든 간접 주입이 실패했음을 증명하지 않음 |
| MCP07 인증·인가 부족 | 서명 transport identity, Console scope, PAC04/06/14, 장치 자격 | 무인증 401·자기 승인 금지·원격 사용자 범위/만료 인수 시험. 하네스 원격 증명·외부 SSO는 미완료 |
| MCP08 감사 부족 | append-only decisions, request/trace/정책·예약·실행 상태, 별도 OS 이벤트 | `mcp-connection`과 `tools/call`, attempted/executed/unknown을 구분. Gateway 밖의 모든 행위가 이 원장에 자동 수집되지는 않음 |
| MCP09 섀도 MCP | 관리형 하네스 설정·설정/리스너 관측·미등록 route 차단 + OS 강제 경로 | 미등록 연결 감사 인수 시험. 모든 로컬 MCP 3종의 발견→등록→사용 및 우회 차단 증거는 아직 남음 |
| MCP10 컨텍스트 과공유 | 자원 capability·등급/DLP·열람→외부 반출 연쇄·결과 필터 | phase12 실제 연쇄 차단. 모델 세션/메모리 전체의 격리·지식 그래프 tenant 분리는 미증명 |

단말 관리자/root·Docker/LXD 제어 권한, 다른 OS/장치, 이미 정책 밖에서 실행된 프로세스,
공급자 내부 악성 실행과 모델 자체 메모리를 현재 보장 범위 밖으로 둔다.
외부 모든 플러그인을 Gateway 하나로 통제하려면 호출 강제 경로 외에 관리형 하네스·OS 실행 및 네트워크
정책·자격 broker가 모두 적용되어야 한다. 인벤토리 경보만으로 강제 경로를 입증할 수 없다.

## 검증을 재현하고 읽는 방법

현재 재검증 보드는 `/home/kali/mcpgw-pac-deploy-20261001`입니다.
기존 운영 소스 `b3c5efb` 위에 통합하고 새 네트워크·빈 볼륨으로 구축했습니다.
이전 `mcpgw-remaster-20261001` 결과와 실패 보고서는 보존했습니다.

- 제품 OPA 모듈의 정상 **200/200**, 결함 탐색 **100/100**을 확인했습니다.
  정상 분포는 ALLOW 83·APPROVAL 20·DENY 97이며 실제 upstream 호출 시험과 구분합니다.
- Rego **99건**, Gateway acceptance **23건**, capability 경계 검사와 PostgreSQL 동시/중복
  독립 효과 검사를 확인했습니다. 6개 동시 요청 중 2개는 P-RATE-002 미전송·DB 효과 4회,
  중복 2개 중 1개는 P-RATE-003 미전송·DB 효과 1회입니다.
- native 하네스 4종 × 워크스테이션 4개 × MCP 10개 연결과 업무 시나리오를 확인했습니다.
  초기화 성공은 도구 실행 성공의 증거가 아닙니다.
- 이전 실패를 숨기지 않았습니다. 자기 승인 회귀 요청에 인자 범위 필드를 추가하고,
  보안 회귀의 내부 함수 호출을 실제 서명 세션 MCP ingress로 바꿨습니다.
  `..` 경로는 PAC-10, `/etc/shadow`는 PAC-01 미전송 차단을 기대합니다.
  정상 업무 명령은 유한 command capability 안에서 PAC-13 승인을 요구합니다.
- 기존 frozen 재생 자료는 보존하고 PAC 사실 계약을 명시한 새 합성 자료를 따로 사용합니다.
  정상/공격 결과와 구체적 정책 ID를 함께 검사합니다. 실제 감사 입력에는 사실을 소급해서 추가하지 않습니다.
- 운영용 `registry/field/capabilities.json`은 정적 grant가 비어 있습니다.
  랩 capability를 조직 배치로 복사하지 않으며 원격 신청의 검토 범위를 권한 근거로 씁니다.

```bash
# 코드 변경 후 필수 전체 검증: 다른 프로젝트/볼륨을 지우지 않는다.
cd full_stack_lab
./console.sh test

# 독립 PAC 사실 입력 시험: 현재 제품 규칙을 로드한 별도 OPA 주소를 먼저 확인한다.
OPA=http://127.0.0.1:<검증한 포트> python3 ../research/pac15-review/pac15_suite.py all
```

완료 증거는 테스트 명령 exit 0, 실패/skip 수, 실제 upstream 효과 또는 미전송 근거,
배포 revision·세 Rego 모듈/세 데이터 파일 hash 및 `capabilities_sha256`를 함께 남긴다.
정책 hash 일치만으로 새로운 capability 승인 적정성이나 전체 시스템 보안을 보장하지 않는다.

## 최종 클린 테스트보드 검증

`/home/kali/mcpgw-pac-deploy-20261001/full_stack_lab/reports/pac-full-test6.txt`에서
`./console.sh test` **exit 0**을 확인했습니다(2026-10-01).
Rego 99/99, acceptance 23/23, 보안 회귀 55/55, 공격 42/42, 정상 대조군 16/16,
기록 재생 192건 동일·변경 0, 합성 10건 미탐/오탐 0, E1/E2/E3 PASS입니다.
제품 PAC 사실 입력 시험 300건과 정적 pyflakes·JS/Shell·무인증 API 검사도 통과했습니다.
실서비스 공급자와 PJ1의 배포 후 시험은 별도의 실기기 증거로 확인해야 합니다.
