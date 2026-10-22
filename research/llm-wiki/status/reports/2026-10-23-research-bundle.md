# 2026-10-23 조사 묶음 — 최신 레퍼런스·기업 사례·업계 동향

- 작업자: Claude Code (Sonnet 5.5, 조사 레인)
- 코드 기준: `origin/main 8edcb95`에서 분기한 `10/23-research-gemini`(깨끗하지 않았다: 같은 경로에 미커밋 초안이 있었다, 아래 한계 참조). 제품 코드 변경 없음. 변경 파일은 위키 문서·카탈로그·출처 manifest뿐이다.
- 시작 근거: 소유자 지시(10-23) "최신 레퍼런스, 국내외 기관 규정, MCP 활용 기업 사례, 업계 동향, gap 조사" 중 규정 갭을 뺀 세 가지
- 해결할 문제와 완료 조건: 2026-08~10 레퍼런스 갱신, 국내외 기업 사례 15건 이상, 2026년 업계 동향과 MINT 갭을 근거와 함께 남긴다. 구현은 하지 않는다.

## 결과

| 산출물 | 위치 | 건수 | 핵심 발견 3가지 |
| --- | --- | --- | --- |
| 최신 레퍼런스 | [README](../../analysis/refs-update-1023/README.md), 카탈로그 `LIB-N01`~`N28`, [OSS 카드](../../solutions/oss-gateway-scanner-releases-1023.md) | preprint 27, 정부 가이드 1, 명세·표준 6행, OSS 릴리스·공시 11행. `catalogs/papers.json` +28, `solutions.json` +7 | ① 새 명세(2026-07-28)가 헤더 라우팅·다회전 사람 확인·무상태를 넣어 게이트웨이 책임이 늘었고 MINT는 헤더-본문 일치 검증과 다회전 응답을 아직 다루지 않는다 ② 게이트웨이 자체의 fail-open·기본 비밀·이름 충돌 권고가 2026-08~10에 ContextForge 15건·ToolHive 다수·Docker 2건·Microsoft 1건·MCP Inspector 9건 ③ 호출별 인가는 합성되지 않는다는 불가능 결과(`LIB-N09`)와 승인·권한 잔존 연구가 승인 UI·원장 설계의 근거 |
| 기업 사례 | [README](../../analysis/mcp-enterprise-cases-1023/README.md) | 20건(사용 15: 국내 7·해외 8, 사고 4, 설문 1) | ① 거의 모든 사례가 중앙 게이트웨이·레지스트리·기본 비활성·사용자 신원 유지를 택했다(Uber·Pinterest·Toss·에이블리·KB) ② 서버가 수백 개가 되면 도구 목록의 문맥·비용 문제가 먼저 터져 점진 노출·응답 투영·코드 모드가 등장했다(Uber·Cloudflare·PayPal) ③ 국내 금융은 신원 전파·읽기/쓰기 분리·승인 레지스트리를 요구하고 토스는 데이터 등급(L1~L4)을 프로젝트 승인에 묶었다 |
| 업계 동향 | [README](../../analysis/industry-trends-1023/README.md) | 시간순 22행, 가격 모델 7행, 포지셔닝 갭 6개 | ① 표준화가 AAIF로 모이는 중(회원 305, 프로젝트 10개, 게이트웨이 2개 포함, 10-22) ② 통제 위치가 클라우드·신원·데이터 플랫폼·개발자 노트북·어플라이언스로 분산되고 인수는 신원·접근 통제로 향함(SGNL·Natoma) ③ 가격은 사용자당(Microsoft $15)·소비(AWS)·OSS+지원이며 온프레미스 MCP 게이트웨이의 시장 가격 근거는 확인하지 못함 |

MINT 갭 상위 5(문서 기준 후보, 구현 아님): ① 업스트림 사용자 위임(RFC 8693) ② 공급자 다회전(`input_required`) 처리 ③ `Mcp-Method`·`Mcp-Name`와 본문 불일치 검증 ④ 게이트웨이 자체 fail-open·기본 비밀·이름 충돌 시험 ⑤ 도구 카탈로그 점진 노출·응답 투영.

## 이전 초안 대체와 정정

같은 경로(`analysis/refs-update-1023/README.md`)에 Gemini가 만든 미커밋 초안이 있었다. 이 작업의 산출 경로와 같아 새 내용으로 대체했다. 대체 근거와 정정 8건은 README §1에 있다(요약: 이미 등록된 논문을 신규로 적음, 이미 `T15`가 v2.0, ToolHive CVE 연결 오류, OpenCode RCE·초지능 사고 대응·OWASP 개정은 1차 출처 미확인).
`status/reports/2026-10-23-latest-refs.md`(Gemini 작성, 미커밋)는 위 정정 항목을 그대로 담고 있어 사실과 다르다. 건드리지 않았고 커밋하지 않았다. 리더가 폐기 여부를 정한다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 출처 확보 | curl 및 브라우저 창, 2026-10-23(KST), manifest 3개 | manifest 124행(세 문서 간 중복 포함, 고유 119): 저장 108, 자동 요청 차단 후 브라우저 해시만 4(NSA 보도자료·NSA PDF·Pinterest·Uber), 실패 7(NSA 2·Pinterest·Uber 자동 요청, Cato 블로그, Obot·Runlayer 가격 404) | `*.sources.json` |
| 위키 검사 | `check_wiki.py --ci-ignored-local-sources` | 오류 0. 경고는 기존 policy 원본의 ignored local-sources 부재뿐 | 콘솔 출력 |
| 추적 검사 | `check_trace.py` | 오류 0, 경고 6(기존) | 콘솔 출력 |
| 링크 규칙 | `check_wiki_link_check.py` | ok | 콘솔 출력 |
| 논문 본문·실험 재현 | — | 미실행. arXiv API의 서지·초록만 | — |
| OSS 코드 읽기·설치·실행 | — | 미실행. 릴리스 노트·권고·저장소 메타데이터만 | — |
| MINT 코드·기기·PJ1 | — | 미실행. `docs/ai` 문서 읽기만 | — |
| upstream 효과 | — | 미확인 | — |

## 실패·미완료·한계

- NSA CSI PDF 본문을 읽지 못했다(자동 요청 403, 브라우저에서는 다운로드 처리). 보도자료 전문과 PDF 바이트 해시만 있다. 대응표는 PDF를 확보한 뒤에 한다.
- Pinterest·Uber는 자동 요청이 막혀 브라우저 창에서 읽었다. 원본 HTML을 보관하지 못하고 같은 URL 응답의 해시만 기록했다.
- 논문 27건은 초록 수준이다. 수치는 저자 보고이며 정식 학회지 게재는 확인하지 못했다.
- 국내 사례는 기술 블로그 RSS 최근 항목과 검색으로 찾았다. 삼성SDS·네이버·카카오뱅크·SK텔레콤 등의 구체 도입 구조와 은행·보험사 사례는 찾지 못했다.
- 가격: Kong·Cloudflare·Docker·Okta의 MCP 가격과 AWS AgentCore Gateway 단가, 인수 금액은 확인하지 못했다.
- Palo Alto Networks·Cisco·Zscaler·Okta의 MCP 신제품은 1차 출처를 얻지 못해 제외했다.
- RU·CU·PG 번호는 각 문서 안의 임시 표기이며 백로그 번호가 아니다. 백로그·`status/current.md`는 수정하지 않았다(다른 브랜치와의 번호 충돌 방지, 리더가 반영).

## 다음 작업

소유자 결정 후 백로그에 등록할 후보: 헤더-본문 일치 검증 시험(RU-3), 다회전 응답 설계(RU-2), 게이트웨이 fail-open·기본 비밀 시험 목록(RU-4), 업스트림 위임 대상 목록(RU-1). NSA CSI PDF를 확보하면 `LIB-N28` 대응표를 만든다.

## 사용자에게 필요한 입력

- NSA CSI PDF를 사람이 내려받아 전달할 수 있는지(자동 요청이 막힘). 다른 입력은 없음.
