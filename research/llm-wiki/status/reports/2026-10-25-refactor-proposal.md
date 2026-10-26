# 2026-10-25 리팩토링·최적화 제안서 — main v0.9.0 진단, 3평면 재설계, 설치 편의, 외부 레퍼런스 보강

- 작업자: Claude Code (Mythos 5.1, 리더 세션) + 서브에이전트 2개(Sonnet, 읽기 전용: 코드 감사·웹 조사), Codex astra 교차검토
- 코드 기준: main `cdef0bb`(v0.9.0 태그 `4edec39` 뒤 보고서 색인 커밋)의 클린 클론. **제품 코드 변경 없음.** 추가 파일은 `research/llm-wiki/analysis/refactor-proposal-1025/`(README·code-audit·references·tools 3개)와 이 보고서, 백로그 행 WIKI-09, 현황·분석 색인 한 줄씩.
- 시작 근거: 소유자 요청(10-25) 「main 기준으로 더 뛰어난 품질·성능을 위한 리팩토링·최적화 제안서. 위키의 개발 의도는 참고만 하고 메타 관점에서 다 뜯어고쳐도 좋다. 레퍼런스를 적극 찾아 위키에 보강. 설치·동작 편의성 극대화 포함」. 10-25 오후 제안서(`프로젝트/제안서_구조_권한_격리_20261025.md`)와 S4 실사용 보고([bugbash-pj1](2026-10-25-bugbash-pj1.md))가 선행 자료.
- 해결할 문제와 완료 조건: ① main의 구조·비용·시험·설치를 수치로 진단 ② 핵심 불변식을 지키는 재설계안 ③ 측정 기준이 있는 성능 최적화 순서 ④ 설치·연결 편의 극대화안 ⑤ 외부 레퍼런스를 원문 열람으로 보강해 위키에 남김 ⑥ astra 교차검토 반영.

## 결과

- **제안서** [analysis/refactor-proposal-1025/README.md](../../analysis/refactor-proposal-1025/README.md): 진단(규모·커밋 비율·실측 지연·구조 문제 10개) → 3평면(제어/데이터/엔드포인트)+정책 스냅숏 → 단계 파이프라인 → 패키지 경계·데이터 계층·시험 피라미드·콘솔·개발 흐름 → SLO와 최적화 13항목 → 서버 설치·운영·직원 PC 연결(키트 없는 OAuth 연결 신설)·관리자 흐름 → 레퍼런스 비교 → 3단계 로드맵·위험 → 지표 14개.
- **코드 감사** [code-audit.md](../../analysis/refactor-proposal-1025/code-audit.md): `tools/call` 한 건의 단계별 DB 체크아웃·문장·HTTP·락·디스크 비용(약 35회·49문장·OPA 2~4·폐기 목록 동기 검증 5회 이상), `tools/list` `5N+6`문장, 트랜잭션 안 두 번째 연결 5곳, import 강연결 성분 31모듈, `os.getenv` 207곳, 시험 189개 중 CI 연결 45개, CI 실측 15~18분, 배포 묶음·키트 중복, 리팩토링 후보 25건. 리더가 상위 주장 7건을 원본 코드(`disposal.py`·`tool_sunset.py`·`mcp_facade.py`·`main.py`·`local_jobs.py`·`core.py`·`privacy.py`)와 `gh run list`로 대조해 일치 확인.
- **외부 레퍼런스** [references.md](../../analysis/refactor-proposal-1025/references.md): MCP 규격 2026-07-28(세션·`initialize` 제거, `Mcp-Method`/`Mcp-Name` 헤더, DCR 폐기·CIMD, ID-JAG), OSS 게이트웨이 10종의 언어·정책 표현·설치, 정책 엔진 5종(OPA 45µs 샘플, Python 바인딩 현황), Python 비동기·psycopg_pool 기본값·Granian 벤치·free-threading·BRIN/파티션, 설치·등록·갱신 관행 12제품, 2026 연구(GatewayBench·ShieldMCP·Governed MCP)·OWASP·CISA. 110개 URL 열람, 그중 핵심 7개(OPA 성능 문서·psycopg_pool API·GatewayBench 초록·MCP 변경 기록·Claude Code 관리형 MCP·Codex MCP·agentgateway 외부 인가)는 리더가 다시 열어 확인.
- 초안과 어긋났던 사실 7건(시험 「스택 필요 146」→ CI 미연결 144, 「CI 1시간」→ 15~18분, 「p50/p95 화면 없음」→ `/api/latency` 있음, 모듈 수, 키트 세 벌→두 벌, Rego 96→130, D-243 잔존 패턴)은 제안서에 정정 반영.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | 리더 PC(Windows)에서 `grep`/`sed`/`python -I -B -X utf8 tools/*.py`로 집계, 2026-10-25 20~21시 KST | 감사 수치 산출. 핵심 7건 원본 대조 일치 | `code-audit.md` 파일:행, `tools/` |
| CI 실행 기록 | `gh run list --workflow verify.yml --limit 8 --json`(읽기) | 성공 5건 14.9·15.8·17.1·17.5·17.5분 | GitHub Actions |
| 외부 문서 | WebFetch로 원문 열람(요약기 경유), 핵심 7개 재열람 | 수치·문장 일치 | `references.md` URL·확인일 |
| 위키 검사 | `python -B -X utf8 research/llm-wiki/tools/refresh_generated.py --skip-code-pointers`, 2026-10-25 21:3x KST | 보고서 색인·결정 색인 재생성, `check_wiki` 오류 0(경고 119, 기존), `check_trace` 오류 0, `check_enterprise_analysis` 오류 0 | 명령 출력 |
| 교차검토 | `codex exec -m gpt-6-astra -c model_reasoning_effort=medium -s read-only --skip-git-repo-check`(저장소 루트, 제안서·감사·레퍼런스·코드 읽기), 2026-10-25 21:4x KST | 지적 15건(상 10·중 4·하 1) 전부 반영 — 제안서 §9 표. 채택 판단 「계측·CI 연결·배포 점검부터, 스냅숏 전면화·TTL·체인 개편·다중 워커·단일 실행 파일 키트는 보류」를 로드맵 순서에 반영 | [astra-review.md](../../analysis/refactor-proposal-1025/astra-review.md) |
| 실제 모델·하네스 | 미실행 | 미실행 | 제안 문서라 해당 없음 |
| upstream 효과 | 미확인 | 미확인 | 해당 없음 |
| 배포·정책 해시 | 미확인 | 코드 변경 없음 | |

## 실패·미완료·한계

- 성능 수치 중 「호출당 체크아웃·문장」은 코드를 읽고 센 정적 집계이고 실제 왕복 시간·`count(*)` 소요·원장 행 수는 운영 DB에서 재지 않았다. 제안서 3.1의 질의로 0단계에 잰다.
- 웹 조사 본문은 요약기를 거쳐 읽었다. 리더가 다시 연 7개 외의 수치를 다른 문서에 옮길 때는 원문을 재확인한다. 원본 파일을 저장하지 않아 `sources.json`·SHA-256이 없다.
- GatewayBench의 평면형/계층형 비교 수치는 HTML 본문을 요약기로 읽은 값이라 「원문 재확인 필요」로 표시했다.
- 제안은 구현·승인·일정이 아니다. 로드맵의 기간은 안이며 소유자 결정이 필요하다.

## 다음 작업

- WIKI-09: 소유자가 제안서를 검토하고 0단계(측정·CI 연결·린트·폐기 목록 색인·목록 스냅숏) 착수 여부와 3평면 분리·키트 없는 OAuth 연결·Go 키트의 채택 범위를 정한다. 채택되면 각 항목을 DEV-번호로 쪼개 백로그에 넣고 D-번호 결정을 남긴다.
- 0단계 첫 산출물: 기기 원장에서 3.1 질의 4개를 읽기 전용으로 실행한 p50/p95 기준선 보고서.

## 사용자에게 필요한 입력

- 제안서 채택 범위와 우선순위 결정(특히 3평면 분리 시점, 키트 없는 연결 기본값 여부, 정책 엔진 인프로세스화 여부).
- 0단계 기준선 측정을 위해 솔루션 기기 DB 읽기 전용 질의 실행 허용(비밀번호 입력 없이 기존 키 경로).
