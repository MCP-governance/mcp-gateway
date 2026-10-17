# 선택적 계약 제한과 SIEM 전달 — DEV-52·61

기준 `fd904c24250b6029061283bb8a57fa4efe0b5b17`, 작업 브랜치 `10/18-selective-siem`. 요청 이름 `10/18-selective-restriction-siem` 생성은 공용 Git 디렉터리 권한으로 실패했다. 시작 작업 트리는 clean이었다. 로컬 구현·시험이며 배포·실제 MCP/하네스·SIEM 제품 검수가 아니다.

결정은 [D-127·128](../../../../docs/ai/DECISIONS.md), 동작 정본은 [운영 대응](../../../../docs/ai/OPS_RESPONSE.md), 원자 요구사항과 코드 지문은 [requirements.json](requirements.json), 명령·출력·종료 코드는 [checks.json](checks.json), 작업 보고는 [보고서](../../status/reports/2026-10-17-selective-restriction-siem.md)다. 기능명세의 G02.06·G06.06과 POL-37·43 / POL-38·42를 연결하며 최종 검수 점수는 올리지 않는다.

## 동작과 영향 범위

| 조건 | 결과 | 근거 |
| --- | --- | --- |
| 승인 도구 a의 설명·스키마 변경, 소멸, 위험 설명 | a만 제한. b는 기존 신원·조직·자산·사용 기한·OPA 심사 유지 | 스냅샷 `restricted_tools`, 요청 도구의 승인 해시 |
| 서버 버전만 변경, 미승인 도구 변경 | 승인 도구의 해시는 유지. 변경과 버전 승계 기록 | D-69 유지 |
| 영향 미확정·이전 `exact_match=false`와 `restricted_tools=NULL` | 해당 서버의 모든 도구 차단 | 실패 시 차단 |
| 이미 D-122 중지·공급망 차단·폐기 | 전체 차단 유지 | 기존 상태 우선 |
| 승인본으로 복귀 | 새 관측 스냅샷을 추가하고 해당 제한 해소 | 이전 변경 증거 보존 |
| 새 계약 채택 | 기존 사람 승인·새 도입 심사 필요 | TOFU 없음 |

도구별 모든 사용자에게 같은 계약 제한을 적용한다. 호출별 신원·부서/자산 정책을 새로 추정하거나 허용하지 않는다. 사용자별 변경 영향 추론 모델은 추가하지 않았다. 서버 상태 `DRIFT`는 전체 변경 증거이므로 관리형 서버 목록에서 서버 자체를 빼지 않고 MCP 도구 목록에서 제한 도구만 제외한다. 서버 목록에 남았다는 사실이 도구 실행 권한을 뜻하지 않는다.

카탈로그 스냅샷 공개는 서버 행 배타 잠금 안에서 수행한다. 최종 dispatch는 서버 공유 잠금을 먼저 얻은 뒤 다음 문장으로 최신 스냅샷과 도구 해시를 확인한다. 실제 DB에서 READ COMMITTED 잠금 대기 후 새 스냅샷을 보는 시험을 `dispatch_intent_pg_check.py::selective_cutover`에 추가했으나 실행하지 않았다. 이미 전송된 호출·원격 프로세스를 취소한 증거는 없다.

## 전달 계약

판정·사람 감사·실제 경보 INSERT 트리거가 같은 트랜잭션에서 소스 테이블·ID를 큐에 추가한다. 합성 경보는 제외한다. 큐에는 본문을 복제하지 않으며 워커는 명시한 열만 SELECT한다. 요청/응답·정책 입력·사유·에러·scope·클라이언트 보고는 출력에서 제외한다. 주체·서버·도구·대상은 SHA-256 참조로 보내고 실제 이름은 내부 원장에서 대조한다. 참조 해시는 익명화 보증이 아니다.

OCSF 1.4.0 Base Event의 필수 분류·시각·제품 필드와 `unmapped`의 MINT 필드를 사용한다. 하나의 HTTPS POST가 한 이벤트이며 2xx를 수신 확인으로 본다. 수신기는 원격 저장을 끝낸 뒤 확인하고 `metadata.uid`/`Idempotency-Key`로 중복 제거하는 계약이 필요하다. 본 작업은 실제 수신 제품의 저장·인덱싱·OCSF 전체 스키마 검증을 수행하지 않았다.

전송 실패는 5초부터 최대 1시간 간격으로 무기한 재시도한다. 소켓 비활동 제한은 5초, 한 회차 최대 50건이며 잠긴 행은 `SKIP LOCKED`로 건너뛴다. DNS·전체 응답의 총기한은 없어 조금씩 응답하는 느린 수신기는 워커를 지연시킬 수 있다. 4xx·비정상 원본도 삭제하지 않는다. 실패 후 재시각이 지정된 행 뒤의 정상 행은 이후 회차에서 처리할 수 있다. 2xx 수신 후 DB 커밋 전 중단은 재전송되므로 정확히 한 번·전역 순서를 보장하지 않는다. DB/큐 파일시스템·백업 유실로부터의 보존은 별도 운영 영역이다.

기본 미기동 중에도 설치 이후 참조가 쌓인다. 마이그레이션 전 원장 소급, 다중 수신처, 보존 정책, 자동 삭제, CEF/syslog, SET/SSF 송수신은 추가하지 않았다. 워커 활성화·비밀 파일·네트워크는 [운영 대응](../../../../docs/ai/OPS_RESPONSE.md)을 따른다. HTTPS/TLS 실패·수신 거부는 호출 실행 경로와 분리한다. 원장·큐의 공통 DB 저장 실패는 기록 성공으로 숨기지 않는다.

## 선행 공개 자료 검토

2026-10-18 공식 원문을 읽었으며 외부 스크립트나 스킬은 실행하지 않았다. 기존 [공백 지도](../../papers/policy50-gap-references.md)의 LIB-K30을 재사용했다. 최신성·전체 구현 적합성은 아래의 열람 범위로 한정한다.

| 자료 | 판본·라이선스·열람 | 채택/제외와 한계 |
| --- | --- | --- |
| [RFC 8417](https://www.rfc-editor.org/rfc/rfc8417) §5.2·5.3·6 | 2018 RFC, IETF Trust. 본문 선택 절 읽음 | 전달·순서를 별도로 정의해야 한다는 경계만 적용. SET 호환이라고 부르지 않음 |
| [OCSF Base Event](https://raw.githubusercontent.com/ocsf/ocsf-schema/v1.4.0/events/base_event.json), [Metadata](https://raw.githubusercontent.com/ocsf/ocsf-schema/v1.4.0/objects/metadata.json), [라이선스](https://github.com/ocsf/ocsf-schema/blob/v1.4.0/LICENSE) | 태그 v1.4.0, Apache-2.0. 해당 JSON과 라이선스 열람. 태그 commit SHA는 API 접근 실패로 미확보 | 필드 매핑만 구현. 소스 복제·외부 SDK 설치 없음. 전체 스키마 적합성 인증 없음 |
| [OCSF API Activity](https://raw.githubusercontent.com/ocsf/ocsf-schema/v1.4.0/events/application/api_activity.json), [Detection Finding](https://raw.githubusercontent.com/ocsf/ocsf-schema/v1.4.0/events/findings/detection_finding.json) | v1.4.0, Apache-2.0. 요구 필드와 설명 읽음 | 확인되지 않은 src_endpoint나 모든 허용 호출을 탐지 경보로 만들지 않기 위해 Base Event 선택 |
| [OpenTelemetry Collector Resiliency](https://opentelemetry.io/bn/docs/collector/resiliency/) | 공식 문서 선택 본문. Collector 고정 코드·라이선스/commit 분석 미수행 | 영속 큐와 별도 저장소 요구 비교. 현재 compose는 Jaeger OTLP traces이며 SIEM logs 수신기가 아님. 새 Collector 배포 대신 기존 PostgreSQL 재사용 |
| [anthropics/skills](https://github.com/anthropics/skills), [security-review 후보](https://github.com/anthropics/skills/pull/803/files) | 공개 스킬 검색·목록/PR 수준만 확인. 선택 스킬 없음, commit·라이선스 상세 미검증 | 이번 계약 집행/전송을 구현하는 재사용 런타임을 확인하지 못해 채택하지 않음. 인기 수치를 기능 근거로 쓰지 않음 |

외부 검색은 선행 대조이며 실행 증거가 아니다. 실제 유지보수 상태의 고정 commit 분석은 미완료로 표시한다. 자체 코드는 기존 게이트웨이 정책 범위 계산·DB 전달 연동에 한정하며 새 MCP 서버는 만들지 않았다.

## 로컬 시험 범위

`selective_restriction_siem_check.py`는 제품 함수 본문을 AST로 불러오고 DB·OPA·MCP 클라이언트 연결을 단위 대역으로 격리한다. 실제 모듈 의존성 import·PostgreSQL 쿼리 실행·MCP 서버 실행 증거가 아니다. 수신 시험만 일회성 `127.0.0.1` HTTP 서버로 실제 HTTP를 왕복하며 `finally`/정리 콜백으로 종료한다. HTTPS/TLS 성공 증거로 올리지 않는다.

정상/변경·소멸·위험 설명·미승인·버전·복구·반복·기존 중지, 같은 연결 요청 도구 확인과 정확한 차단 policy_id, 수신 503→200·302·401·타임아웃·자격 파일 교체·커밋 실패 후 중복 UID·합성 경보 배제를 검증한다. 기존 제품 import 기반 카탈로그 회귀는 Python 3.10의 `datetime.UTC` 부재로 실행 실패했고, `pyflakes`는 미설치다. WSL은 접근 거부, Docker/OPA는 실행 파일을 찾지 못해 실행하지 않았다. 이 제한은 성공으로 세지 않는다.
