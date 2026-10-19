# DEV-66 사고 증빙 수정 정본

2026-10-20 · Codex sol · D-144 보강 · 시작 `a29320c560028281ce741c9d29e3a2517ce3e803`, 병합 상대 `48436fa2344bfdc95ca070199c19855414aef6bc`.

[원검토](../review-1020/c5-incident-pack.md)의 과거 판정을 보존하며 다음 변경으로 대체한다. 아래 통과는 순수 함수/실제 함수 AST와 DB·HTTP 대역 수준이다. 기기 검증 완료를 의미하지 않는다. 코드 행·정규화 SHA-256은 [source-snapshot.json](source-snapshot.json), 실행 기록은 [작업 보고](../../status/reports/2026-10-20-incident-pack-revision.md)에 둔다.

| 요구사항 | 변경·코드 심볼 | 정상·음성·경계·실패·경쟁·복구 증거 | 남은 검증 |
| --- | --- | --- | --- |
| IP-01 / 검토 1 | `incidents.detail`: 서버 목록 `ANY(%s::text[])`, 무형식 NULL 매개변수 제거 | 서버 미지정 주체 범위에서 호출의 서버 참조 추출·SQL 투영 확인 | 서버 지정/미지정 실제 psycopg 바인딩은 `IncidentPostgresPlanCheck` EXPLAIN |
| IP-02 / 검토 2 | `create`, `supplement`, `CASE_SELECT`: 탐지와 영향 기간 분리, 추가 전용 확대 | 탐지 후 2시간 범위 생성·초기 사건 원자 저장·축소 거부·INSERT만 확인; min/max 합집합 코드 | 실제 병렬 확대·재시도·장애 복구 |
| IP-03 / 검토 3 | `incident_pack.deadlines`: NIS2 중간·최종·진행·처리 후 최종 | 기산점 미확정·기존 저장 시각만 존재 시 수동; 실제 통지 기산·1월31일→2월28일·윤년·연말·처리 전후 분기 | 실제 보고/타이머·관할 현지 달력 |
| IP-04 / 검토 4 | CRA 유형별 단계와 최종 기산점 | 유형 미정 수동·각 유형 3단계·수정 가능 후14일·실제 통지 후1개월 | 고객 적용성·현지시각 확인 |
| IP-05 / 검토 5 | `check_deadlines`, `ops_response.tick`: 성공 후 heartbeat·별도 실패 경계 | 경보 저장 실패 후 다음 사고 검사·반복 실패·성공 시 실패 해제·기존 세 운영 검사 지속 | 실 DB 경보 고유키/재시작·다중 worker 경합 |
| IP-06 / 검토 6 | `detail`: 영향 호출 기간과 `history_until` 분리 | 이전 승인과 지속 중지·탐지 후 대응을 담는 조회 조건·패키지 조립 | 실제 이력 선별·기준 시각 주변 동시 변경 |
| IP-07 / 검토 7 | 실제 호출 `approval_id`, 서버 및 도입 관계 연결 | 주체만 지정한 범위·승인 대상 목록·등록 관계 필드·원문/관리자 원식별자 제외 | 실제 승인·철회 사건 수 일치 |
| IP-08 / 검토 8 | 주석 상관 투영·`clean_row`, 콘솔 세 건수 | 무효 주석 범위/순서·관리자/사유 해시·전체1/무효1/유효0·무주석 투영·건수/패키지 해시 | 실제 주석 동시 생성·브라우저 표시 |
| IP-09 / 검토 9 | 생성 시 `pack_snapshot`, 시행/지원 범위 | CRA·한국 시행 직전/당일·과거 사고·고정 판본 계산·판본 없는 기존 사고 수동·완료 이력이 수동 상태를 가리지 않음 | 실제 DB 저장 뒤 파일 교체/재시작 |
| IP-10 / 검토 10 | 당시 `policy_version`, `reason_code=policy_id`, `reason_ref` | 당시 판본 보존·누락은 null·자유서술 사유/주석/주체 불포함 | 원장 판본과 실제 사건 대조 |

기존 시험 클래스의 AST와 기대값은 시작 commit과 동일하다. `tests/incident_pack_check.py`에만 사례를 추가했다. 원장 UPDATE/DELETE·기존 정책 ID/우선순위·OPA 변경은 없다. DB는 `v2_tables.sql` 끝에 nullable 열만 추가했다. `status/current.md`는 작업 지시에 따라 수정하지 않는다.

## 근거·OSS·공개 스킬 탐색

- 재사용: `gateway/requirements.txt`의 psycopg 3.3.5(LGPL-3.0), FastAPI 0.141.1(MIT); Python 3 표준 `calendar`/`datetime`(PSF). SDK 신규 채택 없음. 저장소의 append-only 이력·관할 대조표·무효 주석·기존 `emit_alert`를 확장한다.
- 외부 탐색: [borghei incident-commander](https://github.com/borghei/Claude-Skills/blob/main/engineering/incident-commander/SKILL.md)는 검색 결과상 판본1.2.0·MIT+Commons Clause·2026-06-17 갱신을 표방한다. [Apache Magpie](https://github.com/apache/magpie/blob/main/skills/security-issue-import/SKILL.md)는 사고 보고 서비스가 아닌 이슈 분류 흐름이다. 검색 결과만 확인했으며 commit·배포물 라이선스·현재 유지보수는 고정/검증하지 못했다. 외부 코드를 채택하거나 스크립트를 실행하지 않았다. 기존 소규모 정책/DB 연동 수정에 전체 IR 제품이나 스킬을 설치하지 않는다.
- 법령: [NIS2 Art.23](https://eur-lex.europa.eu/eli/dir/2022/2555/oj/eng), [CRA Art.14](https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng)를 조회했으나 공식 사이트의 자동화 확인 화면으로 본문을 새로 열람하지 못했다. 법령 근거는 저장소 [개발 계획 6장](../compliance/dev-plan/README.md)·[시행일](../compliance/key-dates.md)의 기존 본문 확인 기록에 한정한다. 새 현행성 전수 확인이 아니다.
- 원격 `git ls-remote --symref origin HEAD`는 GitHub:443 연결 실패. 병합 상대는 이미 사람이 준비한 로컬 `MERGE_HEAD`로 확인했다.

## 수동 확인과 제품 경계

월은 UTC 달력 연산이며 지역별 휴일/기간 계산 특례는 자동화하지 않는다. 한국 정보통신망법 시행 경계는 한국 시각이다. CRA 시행 경계의 관할 현지시각은 수동 심사 대상이다. 기타 팩의 `supported_from`은 법정 시행일을 새로 주장하는 값이 아니다. 사고 타입을 입력하지 않은 CRA·실제 기산 사실이 없는 단계·지원하지 않는 과거 판본·판본 없는 기존 사고는 수동 확인으로 남긴다. 기존 보고의 저장 시각만으로 통지 제출 시각을 만들어내지 않는다.

증빙의 사유 코드는 기존 원장에 저장된 선택 정책 ID이며 상세 사유 원문은 SHA-256 참조다. 정책 ID보다 세밀한 사유 분류를 과거 기록에서 복원하지 않는다. 무효 주석과 사슬 정상은 별개다. 전체/유효 건수에서 유효는 **추가 무효 주석이 없는 행**을 뜻하며 사건 내용의 진실을 보증하지 않는다. 대응 이력은 기준 시각까지의 연관 서버/승인 이력이므로 개별 사건과의 인과관계를 자동 확정하지 않는다.
