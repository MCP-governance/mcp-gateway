# 2026-10-23 클라우드 감사·AI 통제 벤치마크

- 작업자: Claude Code (Sonnet 5.5, 조사 레인)
- 코드 기준: `origin/main 7b7ad6d`에서 분기한 `10/23-cloud-control-benchmark`. 제품 코드 변경 없음. 변경 파일은 위키 문서·카탈로그·출처 manifest뿐이다.
- 시작 근거: 사용자 질문(10-23) "CloudTrail 등 상용 솔루션처럼 클라우드의 방식을 온프레미스에 차용할 수 있는가, CloudTrail 외 클라우드 MCP·LLM 통제 솔루션 기능 벤치마킹"
- 해결할 문제와 완료 조건: 클라우드 감사·AI 통제 방식을 MINT에 대응시켜 이미 있는 것·차용 가능·부적합으로 나눈다. 개발 제안은 5개 이내이며 구현하지 않는다.

## 결과

- [벤치마크 README](../../analysis/cloud-control-benchmark-1023/README.md): 기능 16행 비교표, MINT 코드 근거, 차용 가능·부적합 표, 개발 제안 5개.
- [제품 요약](../../solutions/cloud-control-planes.md): AWS·Azure·Google·Cloudflare 요약과 후보 OSS 라이선스 확인. Kong은 기존 요약에 재확인 문장만 추가했다.
- [출처 manifest](../../analysis/cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json): 45건(공식 문서 38, OSS 메타데이터 7)의 URL·확보 시각·SHA-256·열람 범위. 원본은 ignored `local-sources/cloud-control-benchmark-1023/`.
- `catalogs/solutions.json`에 4건을 추가했다. 위키에는 이 제품들에 대한 기존 분석이 없었으므로 중복 조사는 없다.
- 결론: 기록 모델(제어/데이터 평면)과 증거 신뢰 모델(서명 digest)은 차용 가능, 관리형 레이크와 클라우드 분류 API는 부적합. 차용 우선순위는 ① 제어 평면 변경 이벤트 완전 기록·해시 연결 ② 서명 정기 digest ③ 정책 단위 그림자 모드 ④ 기준선 이상 탐지 ⑤ what-if 조회.
- 코드 관찰(정적 grep): `PUT /api/enforcement`가 이력 없이 덮어쓰며(`main.py:981-987`, `core.py:1190-1198`), 감사 체인 head는 같은 PostgreSQL에만 있다(`core.py:2039,2079`). 둘 다 "미발견"이지 부재 증명이 아니다.
- 클라우드 문서의 정정 사항: CloudTrail Lake 신규 고객 중단 표시(2026-05-31), Google 에이전트 문서의 이름 변경.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 공식 문서 확보 | curl, 2026-10-23, 45건 | 모두 HTTP 200. AWS 두 페이지는 안내용 껍데기여서 실제 URL로 교체 | manifest |
| 위키 검사 | `check_wiki.py --ci-ignored-local-sources`, 2026-10-23 | 종료 0, 오류 0. 경고는 기존 policy 원본의 ignored local-sources 부재뿐이며 이번 원본은 해당 없음 | 콘솔 출력 |
| 추적 검사 | `check_trace.py`, 2026-10-23 | 종료 0, 오류 0, 경고 6(기존) | 콘솔 출력 |
| 실제 클라우드 서비스 시험 | — | 미실행 | — |
| MINT 기능 실행·배포·PJ1 | — | 미실행. 정적 코드 읽기만 | — |
| upstream 효과 | — | 미확인 | — |

## 실패·미완료·한계

- 문서는 대부분 도입부와 관련 절만 읽었고 전문 정독이 아니다. 확보했으나 읽지 않은 문서는 manifest에 표시했다(D11, E4).
- 미확인: AWS IAM 정책 시뮬레이터, Cedar 진단 형식, GCP 보존 수치, Entra 보존, APIM 도구별 정책 차등, 각 제품 가격, Dogwood 라이선스·판본, OpenSearch 이상 탐지 호환성.
- 코드 근거는 지정한 모듈을 grep과 부분 읽기로 확인한 것이다. 인프라·운영 스크립트가 보완하는지는 확인하지 못했다.
- 제안 5개는 구현·승인·실기기 통과가 아니다.

## 다음 작업

개발 제안 1(제어 평면 변경 이벤트 완전 기록)과 2(서명 digest)를 우선 검토한다. 구현 결정은 소유자 확인 후 `status/backlog.md`에 등록한다. 이번 작업은 백로그 항목을 만들지 않았다.

## 사용자에게 필요한 입력

- 읽기 전용 감사자 역할을 추가해도 단독 운영 결정과 충돌하지 않는지 확인이 필요하다(제안 밖 후속 후보).
- 클라우드 분류 API를 고객이 허용하는 하이브리드 선택 연동으로 둘지는 별도 결정이다.
