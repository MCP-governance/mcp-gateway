# DEV-69 처리·저장 위치와 국외 이전 규칙

- 작업자: Codex sol / 결정 D-138 / 브랜치 `10/20-data-residency`
- 시작 commit: `09220f515bea70a498b921f4e23eafd605e8444b`. 이후 변경은 미커밋 작업 트리다.
- 정본: [원자 요구사항](requirements.json), [작업 보고](../../status/reports/2026-10-20-dev69-data-residency.md).
- 증거 수준: 코드·설정·순수 함수·정적 검사. OPA 및 게이트웨이 이미지 통합·배포·실제 MCP·PJ1·화면 렌더링은 미검증이다.

## 동작과 저장

도입 등록과 원격 계약 심사의 `residency`는 `processing_countries`·`storage_countries`(ISO alpha-2 목록), `processor`(처리 주체), `evidence_ref`(공급 문서 등 위치 근거), `transfer_basis`(표준계약·영향평가·인증·동의 등의 근거 참조)다. 국가 두 목록의 합집합으로 판정하며 일부라도 빠지면 내부 이상 등급은 차단한다. 공급자 문서가 없는 값을 IP로 채우지 않는다.

기존 `REGISTRY_RUNTIME_DIR/servers.json` 사양·등록 이력, 도입의 원격 심사 JSON, append-only 승인 이벤트에 저장한다. 판정 당시 사실은 기존 원장의 `policy_input.pac.facts.residency`, 승인 결속은 기존 PAC baseline의 `residency_sha256`에 보존한다. 새 테이블·열·라우트·의존성은 없다. 원장 행을 수정하지 않는다.

공급자 호스팅은 서버 자신의 심사 속성을 쓴다. 내부 ACTIVE 실행기 및 검토 카탈로그의 내부 서버는 조직 기기 위치를 쓴다. 등록 주소의 점 유무로 내부 실행을 증명하지 않는다. 카탈로그 `deployment=internal`은 Git 심사 경계이고 콘솔 등록은 ACTIVE 실행기 조회로만 내부 실행을 증명한다.

```toml
# registry/catalog.toml 또는 registry/field/catalog.toml의 조직 설정 예시
[organization.machine_location]
processing_countries = ["KR"]
storage_countries = ["KR"]
processor = "조직"
evidence_ref = "기기 배치 문서 참조"

[organization.destination_locations."reviewed.example"]
processing_countries = ["US"]
storage_countries = ["US"]
processor = "심사된 처리자"
evidence_ref = "공급자 위치 문서 참조"
transfer_basis = "검토된 이전 근거 참조"
```

위 예시는 실제 공급자 사실이 아니다. 초기 `machine_location=KR`은 운영자 확인이 필요한 배치 설정이다. 인자에 포함된 외부 URL·메일 목적지는 정확한 호스트/도메인에 대응하는 위치만 사용하며, 와일드카드·국가 도메인·서버의 위치로 대신하지 않는다. 목적지 누락 시 내부 이상 전송은 차단된다. 기존 카탈로그의 `provider` 서버도 별도 위치 심사가 없으면 이 기본 차단 대상이다.

## 조직 팩과 변경

정본은 `full_stack_lab/registry/data_residency.json`, 생성물은 `full_stack_lab/opa/residency.json`이다. `python3 registry/render_residency.py`로 생성하고 함께 검토한다. `field up`은 `--check`로 오래된 생성물을 거부한다. 게이트웨이는 두 JSON을 다시 대조하고, OPA는 실제 로드한 팩의 해시를 비교한다. 팩 오류는 명명된 차단이고 OPA 자체 불능은 기존 `P-CONTROL-FAIL-CLOSED`다.

| 데이터 등급 | KR | 그 밖 국가 | 위치 없음 |
| --- | --- | --- | --- |
| 공개 | 허용 | 허용 | 허용 |
| 내부 | 허용 | 승인 필요 | 차단 |
| 중요 | 허용 | 금지 | 차단 |

이는 국가 규정 표가 아닌 잠정 조직 기본값이다. 모든 등급별 `*` 규칙과 개별 국가 덮어쓰기를 지원한다. 공개 외 국외 이전에서 `transfer_basis`가 비면 허용 국가도 승인 필요로 둔다. 문자열의 존재가 적법성 검증은 아니다. 금지 국가·미확인 위치는 승인으로 풀리지 않는다. 판정 사유 및 정책 ID는 기존 원장에 기록된다. 허용 시 기존 허용 ID를 사용한다.

원격 위치 변경은 기존 승인 해시와 불일치하므로 재심사해야 한다. 운영 중인 사양을 같은 도입 승인으로 교체하는 것도 거부한다. 콘솔의 임의 위치 수정 API는 만들지 않았다. 검토 카탈로그·조직 팩 변경은 Git 심사로 관리한다. 호출 시와 실제 호출 직전 PAC를 다시 만들며 위치·팩·목적지가 달라지면 이전 건별 승인의 digest가 맞지 않는다. 재판정 이후 실제 dispatch 사이 파일 변경을 원자적으로 봉쇄하지는 않는다.

## 근거와 OSS 선택

[개발 계획 DEV-69](../compliance/dev-plan/README.md)의 CAP-4·REQ-L01-11·REQ-M06-27·REQ-M29-12/14 등을 [규제 매트릭스](../compliance/README.md), [시행일](../compliance/key-dates.md), [POL 매핑](../drive-curation/policy-id-mapping.json)과 연결했다. 한국 [LIB-L01](../../papers/LIB-L01.md) 28조의8, EU [LIB-M06](../../papers/LIB-M06.md) Ch.V, 중국 [LIB-M29](../../papers/LIB-M29.md) 38·40의 서로 다른 이전 모델을 단일 국가 허용 목록으로 바꾸지 않았다. 기존 위키의 10-17 판본을 사용했고 국가별 최신 적용 요건 전체를 재검증한 것은 아니다. 인도 등의 시행 전·부분 시행 요건은 [시행일](../compliance/key-dates.md)의 미확정 상태를 유지한다.

GitHub 공개 스킬/OSS 탐색에서 직접 적용할 위치 통제 스킬은 확인하지 못했다. [OPA 저장소](https://github.com/open-policy-agent/opa)(Apache-2.0, 유지보수 중)와 [공식 data 설명](https://www.openpolicyagent.org/docs/external-data), [언어 문서](https://www.openpolicyagent.org/docs/policy-language)를 확인했다. 기존 OPA 1.20.2-static, commit `b2c26708e9d55645d7f837db495031f7e4152594`는 [고정 의존성 분석](../oss-deep/deps-sdk-authlib-opa.md)의 값이다. 이번 tag ref API/원격 HEAD는 조회 실패하여 새 commit 확인으로 세지 않는다. 신규 SDK·법규 엔진·MCP 서버는 도입하지 않았고 기존 OPA/Pydantic/stdlib만 사용했다. 인기도는 선택 근거로 쓰지 않았다.

## 재현 및 남은 검증

로컬 `python -X utf8 full_stack_lab/tests/data_residency_check.py`의 8건만 실행했다. 게이트웨이 이미지에서는 같은 파일에 `--gateway`를 붙여 실제 모듈의 등록 경계·승인 digest를 AsyncMock DB로 확인한다. 모듈 import가 실패하면 exit 1이며 통과/건너뛰기로 바꾸지 않는다. Rego는 기존 시험 기대값을 건드리지 않고 파일 끝에 사례를 추가했다. [검증 로그](local-checks.txt).

```bash
# 솔루션 기기 full_stack_lab에서, 배포 전 일회성 검사
docker run --rm --entrypoint /opa -v "$PWD/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy
# 빌드한 게이트웨이 이미지에서 실행. 로컬 스택을 기동하지 않는다.
docker run --rm --entrypoint python -v "$PWD/tests:/checks/tests:ro" -v "$PWD/registry:/checks/registry:ro" -v "$PWD/opa:/checks/opa:ro" -e PYTHONPATH=/app "$(docker compose images -q gateway)" /checks/tests/data_residency_check.py --gateway
```

배포 후 PJ1의 실제 관리 하네스와 승인된 공개 OSS MCP로 같은 등급·도구의 국내 허용/국외 승인/금지/속성 누락을 비교해야 한다. 차단은 `decision`·`policy_id`와 `upstream_attempted=false` 및 독립 수신 로그를 대조하고, 정상군의 실제 실행도 확인한다. 위치/팩 교체·승인 만료·철회·동시 실행·실행 직전 변경·오류 복구도 실제 DB/OPA에서 확인해야 한다. 이 파일의 DB 대역과 합성 위치는 실제 MCP 실행 증거가 아니다.

서버 내부의 숨은 송신·하위 처리자·클라우드 실측·실제 저장/보존·리디렉션 전체·국외 이전의 적법성·LLM 공급자 경로는 이 기능의 검증 범위 밖이다. 기존 분류/PAC-12/엔드포인트 통제를 대체하지 않는다.
