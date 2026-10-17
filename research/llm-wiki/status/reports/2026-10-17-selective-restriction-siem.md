# 2026-10-17 작업 I — 선택적 제한·SIEM 전달

- 작업자: Codex, 실제 작업 2026-10-18 KST. 파일 날짜는 요청한 경로를 따른다.
- 코드 기준: `fd904c24250b6029061283bb8a57fa4efe0b5b17`, 시작 clean, `10/18-selective-siem`. 요청 브랜치 생성은 공용 `.git` 쓰기 거부, 원격 HEAD 재조회는 GitHub 네트워크 차단으로 실패. 기존 작업 브랜치에서 변경했고 커밋·푸시·병합은 하지 않았다.
- 시작 근거: DEV-52/G02.06/POL-37·43, DEV-61/G06.06/POL-38·42, 기능명세 10-17 리뷰, D-69·D-122, RFC 8417·OCSF.
- 해결할 문제와 완료 조건: 확정된 변경 도구만 제한하고 정상 도구 심사를 유지한다. 판정·감사·실제 경보를 원문 없이 영속 큐에서 전달한다. 구현·로컬 검사와 배포/실기기 검수를 구분한다.
- 요청문 한글 일부가 `?`로 손상되어 명세·백로그를 기준으로 범위를 명시했고 비동기 확인 메시지를 남겼다. 추가 답변은 작업 중 수신하지 않았다.

## 결과

**D-127:** `selective.py`가 변경·소멸·위험 설명의 도구 범위를 계산하고 `catalog_snapshots.restricted_tools`에 추가한다. 영향 미확정은 `NULL`로 서버 전체 차단이다. 도구별 계약·MCP 목록·관리형 서버 목록·같은 연결 재확인·최종 dispatch·관리자 도구 상태를 맞췄다. 정상 도구의 버전 승계를 독립 적용하고 버전 변경도 스냅샷에 남긴다. D-122 중지·공급망·폐기는 해제하지 않으며 승인본 원복과 새 계약의 사람 승인 경로를 구분한다.

**D-128:** INSERT 트리거가 원장과 같은 트랜잭션에서 소스 참조를 큐에 추가한다. 별도 `siem-worker`가 OCSF 1.4.0 Base Event JSON을 HTTPS POST하고, 실패 행을 버리지 않고 최대 1시간 간격으로 재시도한다. 본문·인자·사유·오류·클라이언트 보고는 보내지 않으며 식별자는 해시 참조다. 합성 경보는 제외한다. 수신기가 중복 제거할 고정 UID를 제공한다. 기존 OTLP/Jaeger 구성은 추적이며 이 구현과 분리한다.

감사 화면에는 전달 대기·재시도·시각만 추가했다. `/api/audit/siem`은 `Depends(admin_caller)`이며 브라우저에 수신 주소·자격·응답 본문을 내리지 않는다. 새 개발 설명·enum 상태 표식은 추가하지 않았다. 새 MCP 서버·의존성은 추가하지 않았다.

실제 변경 파일·심볼·행·SHA-256·원자 조건은 [requirements.json](../../analysis/selective-restriction-siem/requirements.json), 설계·공식 원문 선택과 한계는 [분석 정본](../../analysis/selective-restriction-siem/README.md), 정확한 명령/종료 코드는 [checks.json](../../analysis/selective-restriction-siem/checks.json)에 보존한다.

## 검증

| 확인 종류 | 명령·환경 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 단위·일회성 HTTP | `python -X utf8 -m unittest discover -s full_stack_lab/tests -p selective_restriction_siem_check.py -v`, Windows Python 3.10 | 14개 통과. DB·OPA·MCP 연결은 단위 대역, 수신만 실제 루프백 HTTP | [명령 출력](../../analysis/selective-restriction-siem/checks.json) |
| 콘솔 상태 | `node --test full_stack_lab/tests/console-state.test.mjs` | 15개 통과 | 같은 파일 |
| 정적 | `node --check`, Python AST 구문 검사, `bash -n`, `open_endpoints.py`, `console_copy_check.py`, `git diff --check` | 통과 | 같은 파일 |
| pyflakes | `python -m pyflakes` | 미설치로 실행 실패. 구문 검사로 대체했다고 통과 처리하지 않음 | 같은 파일 |
| 기존 카탈로그 회귀 | `unittest ... catalog_refresh_check.py` | import 실패: Python 3.10에 `datetime.UTC` 없음. 기존 회귀 대역은 새 트랜잭션/스냅샷 형식으로 갱신 | 같은 파일 |
| Rego | 일회성 `opa test` | 미실행: Docker/OPA 미발견, WSL 접근 거부. Rego 파일 변경 없음 | 작업 도구 출력 |
| 위키 | `capture_status.py`, `map_threats.py`, `build_wiki.py`, `check_wiki.py` | 스냅샷·정적 코드 지문 갱신/목록 확인 통과. 최종 전체 검사는 기존 비공개 원본 provenance 29건 누락으로 실패하며 신규 링크/코드 지문 오류는 없음 | [명령 출력](../../analysis/selective-restriction-siem/checks.json) |
| 프로토콜·실제 모델/하네스·upstream 효과 | 솔루션/PJ1/pj3 접속 없음 | 미실행·미확인 | 없음 |
| 배포·실제 SIEM 저장·TLS·실제 DB 트리거/재시작·경합 | compose 기동 없음 | 미실행 | 없음 |

## 실패·미완료·한계

- 실제 PostgreSQL 경합 시험 `dispatch_intent_pg_check.py::selective_cutover`와 합성 계약 fixture/스키마 적용 순서를 준비했으나 실행하지 않았다. 단위 대역은 행 잠금·트리거·내구성·다중 워커 동작의 실제 증거가 아니다.
- HTTPS 인증서·신뢰 교체·인증 실패, 진짜 SIEM의 OCSF 파싱·내구 저장·검색·중복 제거는 아직 검증하지 않았다. 로컬 HTTP 왕복을 HTTPS/제품 성공으로 표시하지 않는다.
- 전송은 적어도 한 번을 목표로 하는 재시도다. 2xx 수신 후 로컬 DB 커밋 전 중단은 중복될 수 있다. 2xx는 원격 저장 완료 보증이 아니고 DB/디스크 유실·백업 복원·무한 용량을 해결하지 않는다. 큐 보존·정리는 미구현이다.
- 소켓 비활동 제한은 5초이나 DNS·전체 응답의 총기한은 없어 느린 수신기가 전달 워커를 지연시킬 수 있다. 호출 실행 경로와는 분리되며 실제 장시간 장애 검수는 남았다.
- 기본 워커 미기동에서도 설치 이후 큐가 쌓인다. 과거 원장 소급·다중 목적지·CEF/syslog·SET/SSF는 제외했다. OCSF 전체 스키마 적합성 및 외부 OSS tag의 commit SHA 고정은 미확인이다.
- `AGENTS.md` 요구에 따라 종료·폐기 모델과 원장 원문은 바꾸지 않았으며 배포·완료 검수 점수를 올리지 않았다.

## 다음 작업

메인 담당자가 변경을 검토·통합하고 Python 3.11+ 제품 의존성 환경에서 pyflakes·기존 카탈로그/운영 대응·DB 회귀를 수행한다. DEV-52는 정상/변경 도구를 가진 승인 OSS MCP와 실제 하네스에서 목록·정책 ID·외부 효과·복구·중지 경합을 확인한다. DEV-61은 실제 PostgreSQL 트리거·두 워커·송신 중 중단/재시작·TLS·수신 장애/복구·UID 중복 제거·원격 검색을 확인한다. 솔루션 배포는 소유자 규칙의 솔루션 기기 `field up --with-siem`, 이후 PJ1 실제 하네스 순서를 따른다.

## 사용자에게 필요한 입력

현재 로컬 작업에는 없음. 실제 SIEM 활성화 단계에는 승인 수신 URL·CA 파일·필요한 자격 파일·중복 제거/확인 응답 계약이 필요하다. 자격 값은 보고서·채팅에 기록하지 않는다. 브랜치 생성/커밋은 공용 Git 디렉터리에 쓰기 가능한 메인 담당자가 수행해야 한다.
