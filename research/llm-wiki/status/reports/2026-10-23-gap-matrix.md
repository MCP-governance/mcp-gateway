# ACK RES-GAP — 2026-10-23 발표용 경쟁·갭 매트릭스

- 작업자: Codex · Agent Hub job `auto-3bb8bd922aa191fc4f43`.
- 코드 기준: `e30be961a9a00d7982dd8565e4412c7289e85f4d`.
- 브랜치: 리더가 만든 `10/23-gap-matrix`, 로컬 `origin/main`과 같은 시작 commit. 브랜치 생성·변경·커밋·push 없음. 커밋은 리더 담당.
- 시작 근거: 사용자 RES-GAP 지시, 기존 조사 7종, DEV-07의 비교 재현 과제.
- 완료 조건: 통제 10행×MINT·근거 있는 제품 열, 구현·배포·실측의 독립 판정, 미확인 보존, 근거 JSON, 위키 검사 통과.

## CHECKED

| 확인 | 실제 관측 |
| --- | --- |
| baseline·편집 직전 HEAD | `e30be961a9a00d7982dd8565e4412c7289e85f4d`; 최초 편집 전과 추가 편집 전 반복 조회에서 동일 |
| 실제 branch/diff | `10/23-gap-matrix...origin/main`; 시작 tracked diff 없음. 보호 지정 미추적 보고서 1개만 존재 |
| 관련 최근 commit | `e30be96` Windows 원클릭 병합, `10ffa83` 기업 분석 코드 해시 갱신, `d69044c` 실사용 보고와 `8aae0c9` 병합, `903f006` 동의·로컬 실행기 변경을 로그/파일/코드로 대조 |
| 원격 HEAD | `git ls-remote --symref origin HEAD` 실패(GitHub 443 연결 제한). 로컬 `origin/main` 일치는 확인; 로컬 `origin/HEAD`는 `feat/web-ui`를 가리켜 최신 기본 브랜치 근거로 사용하지 않음 |
| 제한 시간 | 사용자 제공 timeout `3600`초. 목표 자동 생성·상태 변경 도구는 사용하지 않음 |
| 관련 inbox ID | `8306` 동의, `8322` Windows 검토, `8330` 이전 갭 작업, `8336` 현재 갭 작업. snapshot 마지막 `8360` |
| inbox 대조 | 지정 recorder 파일의 해당 행을 읽어 제공 본문과 일치 확인. JSONL에 자체 id 필드가 없어 행 위치로 대조. 이전 job `auto-acd200fde9db369fab28`의 완료·브랜치 권한 거부 결과도 확인 |
| 중복·소유권 | 이전 갭 작업은 편집 전 중단했고 산출물 없음. 현재 checkout에는 갭 산출물/타인 tracked 변경 없음. 동의·Windows·macOS 구현/검토는 이번 문서와 직접 파일 중복 없음; 기존 결과만 근거로 사용. inbox를 추가 구현·실사용 권한으로 해석하지 않음 |
| 보존 파일 | 미추적 `2026-10-21-pglast-license.md` 내용·경로 유지. 시작 SHA-256 `0fd983f7e9a0f18b47986cf4276ba927ecbeea40b55e4fb49cbce03204439c26` |
| quota | 제공된 Codex 관측값 45%, reset epoch `1792706934` = **2026-10-23 07:08:54 KST**. 현재 잔량을 새로 조회한 값은 아님. 다른 제공자/현재 reset의 미확인 값은 추정하지 않음 |

## 결과

- [발표용 매트릭스](../../analysis/gap-matrix-1023/README.md): 10행×9열(90칸)을 읽기 편하게 2개 표로 나눴다. MINT 열만 반복하며, 기능 수 점수나 순위는 계산하지 않는다.
- [근거 JSON](../../analysis/gap-matrix-1023/evidence.json): 각 칸의 구현·배포·실측 3축(270개 단계), 범위·한계·출처, 코드 commit·행·해시, 기존 manifest의 공식 URL·확보 시각·읽기 범위를 연결했다.
- [재생성 도구](../../analysis/gap-matrix-1023/build.py): 표준 라이브러리만 사용하며 HEAD·브랜치가 달라지면 생성 전 중단한다. MINT 코드·결정·실사용 보고를 baseline Git blob과 LF 정규화 해시로 대조한다. `--check`는 출처 변경·산출물 불일치와 MINT 증거 제한을 검사한다.
- [실제 검사 결과](../../analysis/gap-matrix-1023/checks.json): 실행 명령·종료 코드·위키 오류/경고를 그대로 보존했다. ignored 원문 부재 경고를 기능 부재·실험 실패로 바꾸지 않았다.
- 행별 정상·음성·경계·실패·경쟁·복구 조건 60개를 JSON에 남겼다. 후속 검증 조건이며 이번 실행/통과 기록으로 만들지 않았다.
- 기존 조사 7종의 역할·제외 근거를 연결했고 `status/current.md`·기존 DEV-07·분석 목차를 갱신했다. 별도 중복 백로그나 제품 정책·UI·DECISIONS 변경은 없다.

제품 열은 MINT, LiteLLM, IBM ContextForge, ToolHive, Docker AI Governance, AWS AgentCore Policy·Gateway, Cloudflare MCP 포털·Gateway, Kong AI MCP Proxy, CrowdStrike Falcon Guardian이다. Docker 상용 거버넌스와 OSS MCP Gateway를 하나의 판본/라이선스로 합치지 않았다. 라이선스·commit·유지보수 관측·스킬 검토는 기존 고정 OSS 조사를 재사용했으며 공개 GitHub 후보 탐색만 추가했다. 외부 스킬이나 스크립트는 실행하지 않았다.

MINT의 긍정 근거는 실제 코드·DECISIONS·[지정된 실사용 보고](2026-10-23-real-usage-local-mcp.md)로 제한했다. 이전 연구 문서의 MINT 평가를 코드·배포·효과의 대용으로 사용하지 않았다.

## 핵심 발견과 미해결

1. LiteLLM은 도입 승인·도구 ACL·pin·출력 검사·세션 종료/자격 철회가 있다. 과거 고정 소스에서 못 본 기능을 최신 제품 전체의 부재로 표시하지 않았다. 일반 로그·철회 조치와 불변 원장·종료 판정은 구분했다.
2. MINT의 PJ1 정상 업무는 실사용 보고에 있지만, 그 결과만으로 계약 변경 공격·동의 철회 경합·격리 탈출 방지·OS 우회 차단·원장 무결성·종료 효과까지 실측됐다고 쓰지 않았다. `부분·보고` 칸에도 구체 관측 범위와 미확인 조건을 적었다.
3. MINT 출력 스키마 해시 NULL의 미고정 예외, 같은 UID/SID bearer 접근·Linux 경고 단계, Docker userns 위험 수용, 요청 미리보기와 관리 변경 기록·외부 앵커는 남은 한계다.
4. MINT AI 게이트웨이 연동은 A 업스트림/B 애드인 코드가 있지만 허용 근거 D-191과 10-23 보고만으로 해당 연동의 배포·실측은 확인할 수 없다. 기존 현황의 배포 설명을 근거 제한 밖에서 끌어오지 않았다. 승인·철회 동기화와 애드인 출력 통제도 갭이다.
5. 종료 모듈의 C1~C4/T1~T3 코드는 확인했다. 시험 서버 8개 철회 보고는 종료 판정·하류 자격 거부·외부 데이터 폐기 실측이 아니다.
6. 경쟁 제품의 실측은 전부 미확인이다. Cloudflare의 자사 운영 사례와 ContextForge 기업 포크 사례는 자기 보고·판본 제한을 유지했다. 문서 기능을 실제 고객 배포나 독립 효과 시험으로 승격하지 않았다.

원시 `tmp/w4/local3_final.log`·decisions 행은 이번 checkout에서 재수집하지 않았다. 기존 보고에 원장 ID·정책 해시·반복 조건별 결과가 없어 그 수준은 미확인이다. 오래된 OSS 분석 판본과 최신 릴리스/보안 권고를 분리했으며 배포 판본을 추천하지 않는다. 규제·연구 갭을 기능 충족·법적 준수·인증으로 바꾸지 않았다.

## 검증

Python 명령은 이 PC의 `python` 별칭 부재로 같은 Python 3 런처인 `py -3 -B -X utf8`을 사용했다. `rg`도 PATH에 없어 PowerShell 검색·Python을 사용했다. 아래 명령은 모두 로컬에서 실행했고 `checks.json`의 실제 실행 시각과 결과로 대조할 수 있다.

| 확인 종류 | 명령·환경 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 90칸·270축·60조건·62출처·MINT 증거 제한·생성물 일치 | `py -3 -B -X utf8 research/llm-wiki/analysis/gap-matrix-1023/build.py --check` | 통과, 종료 코드 0 | `checks.json` |
| 위키 출처·해시·로컬 링크·실험 상태 | `py -3 -B -X utf8 research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 통과, 오류 0·경고 119·문서 732, 종료 코드 0 | `checks.json`; 경고는 ignored 원문 부재 |
| 저장소 상태·Markdown 목록 | `capture_status.py`, `build_wiki.py` | 통과, HEAD/branch·로컬 상태 기록·Markdown 732개 | `status/repository-snapshot.json`, `checks.json` |
| 공백·패치 검사 | `git diff --check` | 통과, 종료 코드 0 | `checks.json` |
| 제품 배포·프로토콜·실제 MCP/모델·하네스·upstream 효과 | 이번 문서 종합에서는 미실행 | 미실행 | 제품 스택·기기 상태 변경 없음 |

## 다음 작업

리더가 이 산출물의 증거 수준·미확인 표시를 검토한 뒤 `10/23-gap-matrix`에서 커밋한다. 기능별 실환경 비교는 기존 DEV-07의 미실행 조건으로 남긴다. 이 보고와 관련 산출물은 커밋하지 않았다.

## 사용자에게 필요한 입력

없음. 이번 범위의 새 권한·계정·실사용 데이터·파괴적 변경은 요청하지 않는다.
