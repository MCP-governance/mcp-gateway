# 2026-10-25 릴리스 판본·기업 적용 패키징·위생·브랜치 정리

- 작업자: Claude Code (Opus 5.5), 세션 `release-packaging`(지시서 S2)
- 코드 기준: 시작 main `7687a9e`, 브랜치 `10/25-release-packaging`(로컬 `claude/release-packaging-154ea4`). 제품 코드(`gateway/app`·`endpoint-agent`) 변경 없음
- 변경 파일: `VERSION`, `CHANGELOG.md`, `deploy/**`(compose·.env.example·install.sh·mint.sh·check.py·README·.gitignore), `.gitleaks.toml`, `.github/workflows/verify.yml`, `README.md`, `README.en.md`, `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `docs/ai/RUNBOOK.md`·`TROUBLESHOOTING.md`·`FIELD.md`·`DECISIONS.md`(D-239~D-241 추가만), `full_stack_lab/README.md`(한 줄), `research/llm-wiki/history/readme-2026-10-25.md`(신규), 이 보고서
- 시작 근거: 소유자 지시(10-25) 「릴리즈 버전 관리·기업 적용 패키징, 토큰·작업용 주석 제거, README·브랜치 정리」, 지시서 S2
- 완료 조건: CI 통과(deploy 기동 단계 포함), CHANGELOG·VERSION·README 한/영, 위생 제거 표, 브랜치 삭제 로그·보존 태그, `check_wiki.py` 오류 0, 결정 기록

## 결과

### 1. 판본 체계 (D-239)

- `VERSION` = `0.9.0`, `CHANGELOG.md`(Keep a Changelog, 한국어). 0.9.0 항목은 D-131~D-237을 사용자 관점(추가·변경·수정·보안·업그레이드 주의)으로 묶었고 작업 번호·레인·D-번호는 넣지 않았다.
- **태그 제안**: `v0.9.0`을 이 브랜치의 main 병합 커밋에 붙인다. 지금 main `7687a9e`에는 `VERSION`이 없어 태그와 판본 표시가 어긋난다. 0.9.0인 이유: 기능은 한 기기에서 실사용 중이지만 최종 검수 0건·macOS 실기기 미검증·고객 서버 설치는 CI에서만 실증·이전 판본 이행 경로 없음 → 1.0.0(안정 약속)은 이르다. S1(간편 모드 기본)은 기본 동작이 바뀌므로 0.10.0.
- **같은 판본 표시 설계**: 빌드 인자 `MCP_BUILD_REVISION=<VERSION>+g<커밋>` — `deploy/mint.sh`가 이미 넣어 `/api/health`·`/api/readiness`의 `build.revision`에 판본이 보인다(코드 변경 없이). 후속 코드(S1·다음 세션): ① 게이트웨이 Dockerfile `ARG MINT_VERSION` → `release.build_info()['version']` ② 콘솔 하단은 `/api/readiness`의 `build.console.version`을 `v0.9.0`으로(라벨 없이) ③ 키트 ZIP에 `VERSION`을 넣고 `mcpgw-status`가 「키트 0.9.0 · 게이트웨이 0.9.0」과 불일치 경고. 비교는 문자열 일치, 해시(`pc_kit_sha256`)는 같은 판본 안 핫픽스 구분용으로 유지.
- CI 정적 검사 `deploy/check.py`: VERSION 형식, CHANGELOG 첫 판본 = VERSION.

### 2. 운영 배포 묶음 `deploy/` (D-240)

| 파일 | 내용 |
| --- | --- |
| `compose.yaml` | 서비스 11개(db·opa·presidio 2·gateway·agent-service·intake-worker·runtime-worker·corp-git·caddy·model-proxy, 선택 siem-worker). 랩 PC 4대·회사 시스템·MCP 10종·Jaeger·GreenMail·Ollama·LiteLLM·gateway-sse 제외. 외부 이미지 5종은 판본+digest, 자체 이미지는 `mcpgw/*:${MINT_VERSION}`. 게시는 `${MINT_BIND}:443`, `${MINT_BIND}:3128`만 |
| `.env.example` | 비밀 값 전부 빈 값 + 생성 명령 주석. `ROOT_SOLO_APPROVAL=0`, `OTEL_SDK_DISABLED=true` 기본 |
| `install.sh` | `./install.sh --bind <사내 IPv4> [--name <DNS>]` 한 줄 → `mint.sh install` |
| `mint.sh` | install·up·status·ca·backup·restore·upgrade·set-password·add-account·logs·down·compose |
| `check.py` | 판본·변경 기록·이미지 고정·게시 포트·.env.example 빈 비밀·제품 문서 위생 정적 검사 |
| `README.md` | 요구 사항·설치·직원 PC 연결·명령·구성 |

- 첫 관리자: HTTPS를 열기 전에 비밀번호가 아직 기본값인 `root`만 임의 값으로 바꿔 `initial-admin-password`(0600)에 쓰고 기본 비밀번호의 `user`를 중지. 업그레이드·복구한 서버는 건드리지 않음(DB에서 `password_hash = crypt(token, password_hash)`로 판정).
- 백업: DB 덤프 + 폐기 목록·내부 Git·CA·등록 목록·보고서 볼륨 tar + `.env` 사본(0700 디렉터리). 복구: 같은 서버에서는 폐기 목록·CA를 되돌리지 않고(D-123·D-124), 현재 `.env` 키가 백업과 다르면 멈춤. 새 서버에서만 백업 키·볼륨 사용.
- 업그레이드 = 자동 백업 → 새 판본 빌드·재기동. 롤백 = 현재 상태 백업 → 이전 태그 체크아웃 → 직전 백업 복구. 절차와 이유는 `docs/ai/RUNBOOK.md` 1부로 재정리(랩은 2부).
- CI `deploy` 작업(새 실행기 = 빈 서버): `install.sh` → health ok·판본·Jaeger 제외 → 게시 포트 2개뿐·콘솔 HTTP 닫힘 → `root` 초기 비밀번호 로그인 200, `root/root`·`user/user` 거절 → `mint.sh up` 재실행 뒤 비밀번호 파일 불변 → 백업·복구 왕복 뒤 health ok·로그인 유지.

### 3. 위생 (D-241)

**비밀(gitleaks v8.30.1, 저장소가 이미 쓰는 판본)**: 원격 브랜치 포함 전체 이력 763 커밋(병합 제외, 89 MB) → 70건, 모두 가짜·예시로 판정. 실제 자격 0건이라 이력 재작성이 필요 없다(결정은 소유자 몫으로 남김). 커밋 이력에 `.env`·개인 키·인증서 파일이 추가된 적 없음(`git log --all --diff-filter=A`).

| 파일(이력) | 건수 | 판정 |
| --- | --- | --- |
| `research/llm-wiki/sources/live/T10·T11·T12/rfc*.md·txt` | 30 | RFC 9700·8693·9396 본문 예시 토큰 |
| `research/llm-wiki/web/content.js` | 22 | 위키 생성물(위 원문·검사기 설명 포함) |
| `full_stack_lab/tests/*`(mcp_result_services·dest_pin·adversarial·solo_mode) | 8 | 검사기 시험용 가짜 키·JWT |
| `full_stack_lab/gateway/app/classify.py` | 2 | 자체 점검용 가짜 slack·JWT(`fake` 접미) |
| `research/llm-wiki/sources/policy/T20/*` | 2 | 정책 원문 예시 |
| `research/llm-wiki/analysis/**`, `sheet/tabs/36-integrations.csv` | 4 | 파일 해시값·커밋 해시·문서 속 예시 비밀번호 |
| `full_stack_lab/siem/compose.yaml` | 1 | curl 인증 인자의 환경 변수 참조 |
| `.github/workflows/verify.yml`(9월 이력) | 1 | CI 자리표시 값 |

CI 정적 검사에 같은 판본 gitleaks의 작업 트리 스캔을 넣고, 위 가짜 경로만 `.gitleaks.toml`로 뺐다(로컬 일회성 컨테이너에서 「no leaks found」 확인).

**직접 제거(자기 소유 파일)**

| 파일 | 제거한 것 | 옮긴 곳 |
| --- | --- | --- |
| `AGENTS.md` | 솔루션 기기·시험 PC 주소와 계정(`user@…`, `pj1@…`), 로컬 비밀번호, WSL 키 경로·배포판 이름, 낡은 원격 기본 브랜치 표기 | `.agents.local.md`(Git 제외) |
| `CLAUDE.md` | 로컬 비밀번호, 기기 콘솔 주소 | 같은 파일(`@.agents.local.md` 가져오기 추가) |
| `docs/ai/RUNBOOK.md` | 노트북 환경 표(WSL 경로·비밀번호·포트·하드웨어), WSL 유휴·Git Bash 요령, 랩 계정의 실명 열, 「이번 실험 자격」 서술, 「이 노트북」 서술 | `.agents.local.md` / 삭제 |
| `docs/ai/TROUBLESHOOTING.md` | WSL 배포판 이름, Git Bash→WSL 행 | 삭제·`<배포판>` |
| `docs/ai/FIELD.md` | 기기 IP 예시 2곳 | `<기기 IP>` |
| `README.md`·`README.en.md` | 「PJ1 완주」 링크, 작업 과정 서술 | `research/llm-wiki/history/readme-2026-10-25.md` |
| `full_stack_lab/README.md` | 「PJ1 검수」 | 「실기기 검수」 |

`.agents.local.md`의 내용은 공유 노트 `release-packaging-agents.local.md`에 두었다. **병합 뒤 리더가 메인 체크아웃 루트에 복사**해야 에이전트가 기기 주소를 계속 안다.

**인계(다른 소유자의 파일, 382건·104파일)**: 아래 「부록 A」. 요지:
- S1(키트·게이트웨이 장치 코드): 주석의 `PJ1`/`pj2`/`pj3`·날짜 실측 메모(예: `endpoint_plane.py:777·843·867·935`, `local_jobs.py:310·436·580·586`, `bootstrap.py:394·396·501`), 자체 점검 값의 기기 IP(`enforce-linux.py:373·377`, `managed-windows.py:811·816`, `tests-windows/test_windows_kit.py:223·246`), `tests-windows/README.md`의 pj3 계정명 14곳, 작업 번호 `DEV-xx` 주석(`agent_service.py`·`core.py`·`local_jobs.py` 등). 자체 점검 값은 `192.0.2.10`(RFC 5737 문서용) 같은 값으로 바꾸면 의미가 같다.
- 리더: `agent_service.py:348` 「팀원 저장소 … `miso` 브랜치」, `field/pc/mcpgw_pc.py:4` 사용 예시의 기기 IP, **`db/init.sql`의 랩 시드 계정 7명(실명) — 운영 배포 DB에도 중지 상태로 들어간다. 스키마와 랩 시드를 분리하는 것이 우선**, `opa/policy_ledger.json:3201` `PJ1-managed-install`, `docs/design/NETWORK.md:43`.
- S3: `docs/ai/README.md:26`의 RUNBOOK 설명(「비밀번호 1111」). RUNBOOK 구조가 바뀌어 설명도 「운영·실습 명령, 백업·복구·업그레이드·롤백」으로 고칠 것.
- S5: `integrations/litellm/preflight.py:5`, `llm/standalone/compose.yaml:80`, `llm/standalone/harness/Dockerfile:1`.
- 협업 도구(`research/collaboration-console`, `research/development-status-site`)는 개발용이라 제품 위생 대상에서 뺐고 건수만 적었다.

### 4. README 한/영

제품 저장소 형식으로 다시 썼다: 소개 한 문단 → 구성도(10-23 한/영판 `docs/ai/architecture/mint-architecture-{ko,en}.png`) → 지원 하네스·직원 PC OS·서버 표 → 5분 설치(`deploy/`) → 직원 PC 연결 → 운영(콘솔 메뉴 이름은 `console.js`·`i18n-en.mjs`와 대조) → 보안 경계 5줄 → 개발·기여 → 라이선스. 이전 판은 `research/llm-wiki/history/readme-2026-10-25.md` 한 파일로만 옮기고 상대 링크만 고쳤다(S3가 색인에 넣음).

### 5. 브랜치 정리

`git fetch --prune` 뒤 `git branch -r --merged origin/main`(main `7687a9e`). 보호: `main`·`feat/web-ui`·`10/25-*` 전부·마지막 커밋 2026-10-24 이후·세션 브랜치(`claude/wiki-structure-332d12`). 삭제 직전에 목록을 다시 뽑아 처음 목록과 같음을 확인했다. **원격 81개 → 18개**(삭제 63, 실패 0). 로컬 브랜치는 건드리지 않았다.


**삭제한 병합 완료 브랜치(63)** — 이름 · 마지막 커밋 · 끝점

| 브랜치 | 마지막 커밋 | 끝점 |
| --- | --- | --- |
| `10/18-console-http` | 2026-10-18 | `c9ce4a4809` |
| `10/18-remaining-features` | 2026-10-19 | `6c2eb33af8` |
| `10/20-control-review` | 2026-10-20 | `30be297aeb` |
| `10/21-dev03-review-refresh` | 2026-10-21 | `217b706bef` |
| `10/21-dev73-integrate` | 2026-10-21 | `f5a608e09d` |
| `10/21-dev73-rework` | 2026-10-21 | `cdba06f6ae` |
| `10/21-intake-d189` | 2026-10-21 | `eb71d51940` |
| `10/21-intake-one-click-main` | 2026-10-21 | `ff3d0f050d` |
| `10/21-sheet-runtime-completion` | 2026-10-22 | `b4c571b48e` |
| `10/22-ai-gateway-addon` | 2026-10-22 | `a41bbc1967` |
| `10/22-id-trace` | 2026-10-22 | `cbd49fa649` |
| `10/22-kit-e2e` | 2026-10-22 | `1e3100712e` |
| `10/22-kit-macos` | 2026-10-23 | `2b1ad47431` |
| `10/22-local-mcp-followup` | 2026-10-22 | `94a58a4445` |
| `10/22-local-mcp-oneclick` | 2026-10-22 | `4a57a154b8` |
| `10/22-main-ci-fix` | 2026-10-22 | `834e1fa253` |
| `10/22-signup-fixes` | 2026-10-22 | `d6cbafe3b0` |
| `10/22-w10-ux` | 2026-10-22 | `2d96b6d88a` |
| `10/22-w7-console-fixes` | 2026-10-22 | `e44f0898e9` |
| `10/23-agent-skip-local-runner` | 2026-10-23 | `656ec811dd` |
| `10/23-ast-harness` | 2026-10-23 | `8b157f30b5` |
| `10/23-cloud-control-benchmark` | 2026-10-23 | `29fc52623b` |
| `10/23-connector-control` | 2026-10-23 | `3bc4f53e4c` |
| `10/23-console-declutter` | 2026-10-23 | `afb35d43ac` |
| `10/23-console-i18n` | 2026-10-23 | `c6649b1d4b` |
| `10/23-enterprise-code-refresh` | 2026-10-23 | `10ffa83d5e` |
| `10/23-gap-matrix` | 2026-10-23 | `5126c67727` |
| `10/23-kit-install-upfront` | 2026-10-23 | `648f44c037` |
| `10/23-kit-reinstall-continuity` | 2026-10-23 | `973b8f1e87` |
| `10/23-litellm-intervention` | 2026-10-23 | `0743e0449b` |
| `10/23-litellm-sync` | 2026-10-23 | `eba2680692` |
| `10/23-local-call-one-container` | 2026-10-23 | `687540fe6d` |
| `10/23-local-control-race` | 2026-10-23 | `5a7f992d6c` |
| `10/23-local-health` | 2026-10-23 | `5a530cd7e6` |
| `10/23-local-jobs-policy-gap` | 2026-10-23 | `9ff1dbc8aa` |
| `10/23-local-run-presets` | 2026-10-23 | `092ab72af3` |
| `10/23-mcp-detect` | 2026-10-23 | `ae7535bea0` |
| `10/23-notion-bugs` | 2026-10-23 | `a4d83f9c2f` |
| `10/23-output-credential-span` | 2026-10-23 | `c2ec070727` |
| `10/23-output-overblock` | 2026-10-23 | `305b79dbbf` |
| `10/23-policy-refresh-gap` | 2026-10-23 | `41787a4fc8` |
| `10/23-policy-removal-gap` | 2026-10-23 | `e8028a6145` |
| `10/23-real-usage-report` | 2026-10-23 | `d69044cfea` |
| `10/23-reapply-after-deregister` | 2026-10-23 | `77492fc272` |
| `10/23-recipient-heuristic` | 2026-10-23 | `6bb21ceec9` |
| `10/23-references-3` | 2026-10-23 | `d89f083d3a` |
| `10/23-repo-subpath` | 2026-10-23 | `d7b0938548` |
| `10/23-research-codex` | 2026-10-23 | `8f1999f181` |
| `10/23-research-gemini` | 2026-10-23 | `159e6c709f` |
| `10/23-root-only-images` | 2026-10-23 | `8e01a18833` |
| `10/23-runner-consent` | 2026-10-23 | `903f006847` |
| `10/23-runner-failure-log` | 2026-10-23 | `53a7cdfc57` |
| `10/23-runner-http-detail` | 2026-10-23 | `41095eb88f` |
| `10/23-scan-url-parse` | 2026-10-23 | `da732e3153` |
| `10/23-served-policy-history` | 2026-10-23 | `67af62e0cc` |
| `10/23-server-id-path` | 2026-10-23 | `e7ca934ab3` |
| `10/23-sheet-refresh` | 2026-10-23 | `55bba3df42` |
| `10/23-tool-action-override` | 2026-10-23 | `6ef0d59e35` |
| `10/23-w7-acceptance-today` | 2026-10-23 | `49d224e783` |
| `10/23-w7-check` | 2026-10-23 | `1df3b65a1a` |
| `10/23-wbs-evidence` | 2026-10-23 | `9f3d67eeff` |
| `10/23-wiki-readability` | 2026-10-23 | `9026e226ff` |
| `10/23-windows-oneclick` | 2026-10-23 | `85c8f6d2a3` |

삭제 로그: `git push origin --delete …` 1회, 출력의 `[deleted]` 63줄, 종료 코드 0. 끝점은 모두 main에 포함돼 있어 커밋은 사라지지 않는다.

**보존 태그(미병합 10, push 완료)와 삭제 후보** — 삭제는 리더 승인 뒤

| 보존 태그 | 원격 브랜치(남김) | 끝점 |
| --- | --- | --- |
| `archive/2026-10-20-dev72-design` | `10/20-dev72-design` | `cac2fd4fa8` |
| `archive/2026-10-20-dev73-design` | `10/20-dev73-design` | `7112290044` |
| `archive/2026-10-20-dev73-impl` | `10/20-dev73-impl` | `217da74ed4` |
| `archive/2026-10-21-intake-one-click-preserved` | `10/20-intake-one-click-preserved` | `0717462fee` |
| `archive/2026-10-20-root-solo` | `10/20-root-solo` | `27fcea9f62` |
| `archive/2026-10-21-dev81-direct-helper` | `10/21-dev81-direct-helper` | `47a4977c25` |
| `archive/2026-10-23-hierarchical-agents` | `10/22-hierarchical-agents` | `2e72f3b543` |
| `archive/2026-10-22-runtime-recovery` | `10/22-runtime-recovery` | `22e6aaf4d1` |
| `archive/2026-10-22-w7-ci-probe` | `10/22-w7-ci-probe` | `7b6df32735` |
| `archive/2026-10-23-codex-output-fp-unmerged` | `10/23-codex-output-fp-unmerged` | `e906e50076` |

처음에 날짜가 겹친 이름(`archive/2026-10-20-20-…`)으로 10개를 잘못 만들어 push했다가, 올바른 이름으로 다시 만들어 push한 뒤 잘못된 원격 태그 10개를 지웠다(이 세션이 만든 것만).

**남은 원격 브랜치(18)**: `10/20-dev72-design`, `10/20-dev73-design`, `10/20-dev73-impl`, `10/20-intake-one-click-preserved`, `10/20-root-solo`, `10/21-dev81-direct-helper`, `10/22-hierarchical-agents`, `10/22-runtime-recovery`, `10/22-w7-ci-probe`, `10/23-codex-output-fp-unmerged`, `10/25-console-mcp-download`, `10/25-github-per-user`, `10/25-policy-sync-split`, `10/25-release-packaging`, `10/25-w7-today`, `claude/wiki-structure-332d12`, `feat/web-ui`, `main`

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사(로컬) | `python deploy/check.py`, `bash -n deploy/*.sh`, `pyflakes deploy/check.py`, 10-25 | 통과 | 이 세션 출력 |
| compose 렌더링(로컬, 기동 없음) | WSL `docker compose --env-file <가짜 값> -f deploy/compose.yaml config`, 10-25 | 서비스 11, 게시 2(443·3128, 지정 주소), 외부 이미지 digest 고정 | 이 세션 출력 |
| 비밀 스캔(로컬 일회성 컨테이너) | `zricethezav/gitleaks:v8.30.1 git --log-opts=--all`(이력 763 커밋) / `dir`(작업 트리, `.gitleaks.toml`), 10-25 | 이력 70건 전부 가짜·예시 / 작업 트리 no leaks | 위 표 |
| 위키 | `check_wiki.py --ci-ignored-local-sources`, `check_trace.py`, 10-25 | 오류 0(경고는 기존 참조 0 항목) | 이 세션 출력 |
| CI 정적 검사 | GitHub Actions `full_stack_lab 검증 / 정적 검사` | CI_STATIC | CI_LINK |
| CI 운영 배포 설치 | `full_stack_lab 검증 / 운영 배포 설치 검증`(새 ubuntu-latest 실행기) | CI_DEPLOY | CI_LINK |
| CI 실습 전체 회귀 | `full_stack_lab 검증 / 완료 조건 전체 검증` | CI_VERIFY | CI_LINK |
| 실제 모델·하네스 | — | 미실행(이 작업 범위 밖, 코드 변경 없음) | — |
| 기기 배포 | — | 미실행(리더 몫, 소유자 규칙상 이 세션은 기기를 쓰지 않음) | — |

## 실패·미완료·한계

- 운영 배포 CI는 설치·로그인·백업·복구까지다. 직원 PC 키트 설치와 실제 MCP 호출은 필드 카탈로그에 승인 서버가 없어 넣지 않았다(실습 스택 CI의 `field up` 단계가 같은 코드 경로를 본다). 고객 인증서, 이전 판본에서의 업그레이드, 실제 고객 서버 설치는 미실행.
- 판본 표시(게이트웨이 `version` 필드·콘솔 하단·`mcpgw-status`)는 설계만 했다. 지금은 `build.revision` 문자열로만 보인다.
- 서버용 `install.ps1`은 만들지 않았다(아래 방향 제안).
- 제품 코드의 위생 382건은 인계만 했다. 저장소가 공개(PUBLIC)이고 이력에 기기 주소·시험 PC 계정·로컬 비밀번호가 남아 있다. 비밀(토큰·키)은 0건이지만 이 내부 정보까지 이력에서 지울지는 소유자 결정이다(`git filter-repo` + 강제 push, 모든 클론 무효화).
- 라이선스 파일이 없다. README는 「라이선스 미지정, 저작권자 허락 없이 복제·배포 불가」로 사실만 적었다.
- 「현황·백로그」 갱신은 하지 않았다(`research/llm-wiki`는 S3 소유, 리더가 병합 뒤 갱신).

## 방향 제안(판단이 갈린 곳과 대안)

1. **구성도**: 지시서는 `docs/ai/architecture.png`(09-26판)를 지정했지만, 현재 서비스와 맞는 10-23 한/영판(`architecture/mint-architecture-{ko,en}.png`)을 썼다. 옛 그림을 원하면 경로만 바꾸면 된다.
2. **CI 위치**: 「기존 acceptance 작업에 deploy 단계 추가」 대신 같은 워크플로의 **별도 작업**으로 만들었다. 실습 스택이 이미 떠 있는 실행기는 「빈 서버」가 아니고 443·이름이 겹친다. 대안: `verify` 끝에 붙이면 실행기 1대로 끝나지만 실습 스택을 먼저 내려야 하고 75분 작업이 더 길어진다.
3. **서비스 이름**: `corp-git` 등 랩 이름을 그대로 뒀다(실행기·Caddyfile이 이름에 의존). 고객에게 보이는 이름을 `git`으로 바꾸려면 Caddyfile·`GITEA_ADMIN_URL`·실행기를 함께 고쳐야 한다.
4. **`deploy/`가 `../full_stack_lab`을 마운트**: 정본을 하나로 두려는 선택. 대안은 릴리스 때 필요한 파일만 `deploy/`로 복사한 묶음(tar)을 만드는 것 — 고객이 저장소 전체를 받지 않아도 되지만 생성 스크립트와 동기 검사가 하나 더 생긴다. 1.0 전에 결정 권고.
5. **콘솔 HTTP(8000) 미게시**: 고객 사내망에는 Tailscale 터널 암호화가 없어 콘솔도 HTTPS만 연다. 브라우저에 사설 루트를 넣어야 한다. 대안: 고객 공인·사내 인증서를 Caddy에 넣는 옵션(Caddyfile에 `tls <cert> <key>` 분기) — 다음 판본 후보.
6. **`ROOT_SOLO_APPROVAL=0` 기본**: README 원칙 4(신청자 ≠ 승인자)를 따랐다. 한 사람만 운영하는 고객은 `.env`에서 1로 바꾼다.
7. **`install.ps1`(서버용) 생략**: 서버는 Linux 컨테이너 호스트가 전제다. Windows Server + Docker는 지원 대상에서 빼는 것을 권고. 필요하면 WSL2 안에서 `install.sh`를 쓰는 절차만 문서화.
8. **브랜치 날짜 기준**: 「10-24 이후」를 커밋 시각(`%cI`, +09:00)으로 판정했다. 미병합 10개는 태그만 만들고 원격 브랜치는 남겼다(삭제 후보).

## 다음 작업

- 리더: 이 브랜치 diff·CI 확인 → main 병합 → `v0.9.0` 태그 push → `.agents.local.md`를 메인 체크아웃에 복사 → 미병합 10개 원격 브랜치 삭제 승인 여부 결정.
- S1·다음 세션: 판본 표시 코드(D-239 4항), 부록 A의 키트·게이트웨이 주석 정리, `db/init.sql` 스키마/랩 시드 분리.
- S3: `history/readme-2026-10-25.md` 색인, `docs/ai/README.md:26` 설명 수정.
- 소유자: 공개 저장소 이력 재작성 여부, 라이선스 선택.

## 사용자에게 필요한 입력

- 공개 저장소 이력에 남은 내부 정보(기기 주소·시험 PC 계정·로컬 비밀번호)를 이력에서까지 지울지 결정.
- 라이선스 선택(제3자 구성요소 라이선스: OPA·Caddy·Trivy Apache-2.0, Presidio·Gitea·gitleaks MIT, Semgrep CE LGPL-2.1).

## 부록 A. 위생 인계 표(다른 소유자의 파일)

생성: 이 세션 `handoff.py`(git 추적 파일을 Python으로 읽어 정규식 5분류: 기기 주소·시험 PC·계정·로컬 경로·팀원·작업 서술·작업 번호). 카드번호 자체 점검 값(`4111 1111…`)은 제외. 같은 표가 공유 노트 `release-packaging-hygiene-handoff.md`에 있다.

| 담당 | 파일 | 건수 |
| --- | --- | --- |
| S1(같은 파일 수정 중) | `docs/ai/SECURITY_BOUNDARIES.md` | 5 |
| S1(키트) | `endpoint-agent/README.md` | 5 |
| S1(키트) | `endpoint-agent/agent.py` | 1 |
| S1(키트) | `endpoint-agent/bootstrap.py` | 3 |
| S1(키트) | `endpoint-agent/enforce-linux.py` | 3 |
| S1(키트) | `endpoint-agent/local-runner.py` | 3 |
| S1(키트) | `endpoint-agent/managed-linux.py` | 3 |
| S1(키트) | `endpoint-agent/managed-windows.py` | 3 |
| S1(키트) | `endpoint-agent/os-observer.py` | 1 |
| S1(키트) | `endpoint-agent/tests-windows/README.md` | 12 |
| S1(키트) | `endpoint-agent/tests-windows/test_windows_kit.py` | 4 |
| S1(키트) | `endpoint-agent/tests-windows/test_windows_oneclick.py` | 1 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/agent_service.py` | 6 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/automatic_suspend.py` | 1 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/core.py` | 5 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/endpoint_plane.py` | 5 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/intake_proposal.py` | 1 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/integrations.py` | 2 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/lifecycle_tables.sql` | 1 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/local_jobs.py` | 5 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/main.py` | 1 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/mcp_facade.py` | 1 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/pac.py` | 2 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/privacy.py` | 2 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/review.py` | 1 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/risk_tier.py` | 1 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/tool_sunset.py` | 1 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/upstream.py` | 1 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/user_suspend.py` | 1 |
| S1·리더(게이트웨이 코드) | `full_stack_lab/gateway/app/v2_tables.sql` | 2 |
| S3 | `docs/ai/README.md` | 1 |
| S5(애드온) | `full_stack_lab/integrations/litellm/preflight.py` | 1 |
| S5(애드온) | `full_stack_lab/llm/standalone/compose.yaml` | 1 |
| S5(애드온) | `full_stack_lab/llm/standalone/harness/Dockerfile` | 1 |
| 리더 | `docs/design/NETWORK.md` | 1 |
| 리더(DB 시드) | `full_stack_lab/db/init.sql` | 1 |
| 리더(시험) | `full_stack_lab/tests/command_surfaces_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/connector_control_check.py` | 4 |
| 리더(시험) | `full_stack_lab/tests/console_copy_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/data_residency_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/dev73_integration_check.py` | 2 |
| 리더(시험) | `full_stack_lab/tests/dev73_review2_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/dev73_rework_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/dev73_rework_pg_check.py` | 2 |
| 리더(시험) | `full_stack_lab/tests/endpoint_offline_arrival_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/endpoint_snapshot_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/field_account_git_test.py` | 2 |
| 리더(시험) | `full_stack_lab/tests/field_kit_check.py` | 8 |
| 리더(시험) | `full_stack_lab/tests/field_release_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/field_tls_check.py` | 6 |
| 리더(시험) | `full_stack_lab/tests/flow_fingerprint_check.py` | 2 |
| 리더(시험) | `full_stack_lab/tests/harness_detect_check.py` | 2 |
| 리더(시험) | `full_stack_lab/tests/high_impact_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/intake_fixture.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/intake_register.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/ledger_retention_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/local_jobs_pg_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/local_run_manifest_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/local_run_presets_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/local_runner_usability_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/macos_kit_check.py` | 3 |
| 리더(시험) | `full_stack_lab/tests/managed_enrollment_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/managed_helper_unavailable_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/managed_kernel_proof.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/oauth_rotation_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/output_credential_span_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/plane_cases_field_other_identities.json` | 2 |
| 리더(시험) | `full_stack_lab/tests/plane_evidence.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/plane_sequence.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/provenance_gateway_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/provenance_referrer_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/provenance_verify_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/real_mcp_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/resource_residual_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/resource_residual_pg_check.py` | 2 |
| 리더(시험) | `full_stack_lab/tests/runtime_rollback_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/runtime_rollback_provenance_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/runtime_rollback_queue_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/runtime_rollback_reconcile_check.py` | 2 |
| 리더(시험) | `full_stack_lab/tests/runtime_worker_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/server_egress_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/termination_dispatch_lab.sh` | 1 |
| 리더(시험) | `full_stack_lab/tests/testbed_network_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/tool_sunset_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/user_auto_suspend_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/user_server_suspend_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/user_suspend_all_check.py` | 1 |
| 리더(시험) | `full_stack_lab/tests/windows_config_env_check.py` | 1 |
| 리더(실행기) | `full_stack_lab/runtime/Dockerfile` | 1 |
| 리더(실행기) | `full_stack_lab/runtime/worker.py` | 1 |
| 리더(정책) | `full_stack_lab/opa/policy.rego` | 1 |
| 리더(정책) | `full_stack_lab/opa/policy_ledger.json` | 2 |
| 리더(정책) | `full_stack_lab/opa/policy_test.rego` | 2 |
| 리더(필드 키트 코드) | `full_stack_lab/field/pc/mcpgw_pc.py` | 2 |
| 리더(협업 도구) | `research/collaboration-console/README.md` | 6 |
| 리더(협업 도구) | `research/collaboration-console/install-autostart.ps1` | 2 |
| 리더(협업 도구) | `research/collaboration-console/run-console.ps1` | 3 |
| 리더(협업 도구) | `research/collaboration-console/test_console.py` | 4 |
| 리더(협업 도구) | `research/development-status-site/README.md` | 1 |
| 리더(협업 도구) | `research/development-status-site/build_snapshot.py` | 31 |
| 리더(협업 도구) | `research/development-status-site/dist/data.json` | 122 |
| 리더(협업 도구) | `research/development-status-site/extend_1017.py` | 1 |
| 리더(협업 도구) | `research/development-status-site/owners.json` | 5 |
| 리더(협업 도구) | `research/development-status-site/rescore_1015.py` | 32 |

합계 382건(파일 104개). 시험·협업 도구는 건수만, 나머지는 아래에 행 단위로 적는다.

| 파일:행 | 분류 | 내용(앞 90자) |
| --- | --- | --- |
| `full_stack_lab/gateway/app/agent_service.py:274` | 작업 번호 | # Optional on the wire so older clients keep working; approval holds a request that has no |
| `full_stack_lab/gateway/app/agent_service.py:348` | 팀원·작업 서술 | "계정을 끈다"는 조치가 배포가 된다. 팀원 저장소 Agent-Service의 `miso` 브랜치가 |
| `full_stack_lab/gateway/app/agent_service.py:1262` | 작업 번호 | # approved again with the input it lacks (DEV-71). A registration taken back out (DISABLED |
| `full_stack_lab/gateway/app/agent_service.py:1381` | 작업 번호 | """Queues one build-and-run of the approved commit (DEV-38). The runtime worker does the r |
| `full_stack_lab/gateway/app/agent_service.py:1921` | 작업 번호 | # DEV-73: signed manifest for a run on employees' PCs. Excluded from model_dump so a revie |
| `full_stack_lab/gateway/app/agent_service.py:2351` | 작업 번호 | """저장소형 stdio 서버를 신청자 PC의 격리 컨테이너로 실행하도록 지정한다(DEV-73). 서명은 승인 화면에서.""" |
| `full_stack_lab/gateway/app/automatic_suspend.py:1` | 작업 번호 | """DEV-74 automation on the employee/server suspension state established by D-181.""" |
| `full_stack_lab/gateway/app/core.py:627` | 작업 번호 | # DEV-73: the server runs on each caller's own device under a signed manifest. |
| `full_stack_lab/gateway/app/core.py:712` | 작업 번호 | # registration names the image built from the approved commit (DEV-38). |
| `full_stack_lab/gateway/app/core.py:763` | 작업 번호 | # DEV-71: the tier is read again from the stated input the approval was made on, and the a |
| `full_stack_lab/gateway/app/core.py:2272` | 작업 번호 | # An administrator's stop (DEV-79) and a live automatic stop share the same state row. |
| `full_stack_lab/gateway/app/core.py:2359` | 시험 PC·계정 | # a 200 KB string reached an outside provider before it refused it (D-59, pj1). |
| `full_stack_lab/gateway/app/endpoint_plane.py:777` | 시험 PC·계정 | # cleanup; its record would stay "active" forever (10-23 PJ1: user's device beside aaaa's) |
| `full_stack_lab/gateway/app/endpoint_plane.py:843` | 시험 PC·계정 | # in the user's files or try to run the harness from its shell (10-23 PJ1). |
| `full_stack_lab/gateway/app/endpoint_plane.py:867` | 시험 PC·계정 | # (PJ1 10-23: productivity@synced loaded); only `false` is honoured, so this cannot be und |
| `full_stack_lab/gateway/app/endpoint_plane.py:875` | 작업 번호 | # header helper the harness profile may run (DEV-42). Only managed hooks load, and the |
| `full_stack_lab/gateway/app/endpoint_plane.py:935` | 시험 PC·계정 | # last confirmed list alone quarantined PJ1 and pj3 although every control check passed (1 |
| `full_stack_lab/gateway/app/intake_proposal.py:99` | 시험 PC·계정 | # git·time 이미지는 인터프리터가 /root(0700) 아래 uv 설치에 있어 관리 계정(UID)으로 exec가 거부된다(10-23 PJ1 docker 2 |
| `full_stack_lab/gateway/app/integrations.py:332` | 시험 PC·계정 | shared = device_state({**base, "detail": host(\[{"name": "pj1", "uid": 1000, "privileged_gr |
| `full_stack_lab/gateway/app/integrations.py:334` | 시험 PC·계정 | assert shared\["unmanaged_accounts"\] == \[{"name": "pj1", "uid": 1000, "privileged_groups":  |
| `full_stack_lab/gateway/app/lifecycle_tables.sql:393` | 작업 번호 | -- DEV-73 (D-175): one MCP message for an approved local server, run on the caller's own d |
| `full_stack_lab/gateway/app/local_jobs.py:1` | 작업 번호 | """Approved local MCP servers run on the caller's own device (DEV-73, D-175). |
| `full_stack_lab/gateway/app/local_jobs.py:310` | 시험 PC·계정 | # 관리 조치로 멈춘 실행을 시간 초과로 보이게 하면 직원이 이유를 모른 채 재시도한다(10-23 PJ1 철회 실측). |
| `full_stack_lab/gateway/app/local_jobs.py:436` | 시험 PC·계정 | # spend the call's time budget before the call itself ran (10-23 PJ1). Observation still a |
| `full_stack_lab/gateway/app/local_jobs.py:580` | 시험 PC·계정 | # pre-start row, fail its lease renewal against the started job and stop a healthy run (10 |
| `full_stack_lab/gateway/app/local_jobs.py:586` | 시험 PC·계정 | # servers added or removed elsewhere keeps the job; any control change stops it (D-198, 10 |
| `full_stack_lab/gateway/app/main.py:843` | 작업 번호 | """DEV-73: the manifest and the signature an approver produced offline.""" |
| `full_stack_lab/gateway/app/mcp_facade.py:197` | 시험 PC·계정 | # and the model then stops or reports a block (pj2 10-23 grep.app), so the employee sees a |
| `full_stack_lab/gateway/app/pac.py:181` | 시험 PC·계정 | from memory or with a built-in tool (pj2 10-23: 4 of 12 such requests never reached an MCP |
| `full_stack_lab/gateway/app/pac.py:282` | 시험 PC·계정 | # to the mail domain list (10-23 PJ1). An address, or a call the classifier read as mail,  |
| `full_stack_lab/gateway/app/privacy.py:31` | 시험 PC·계정 | # D-59 pj1). Queue here, where the wait is not the request's timeout, and give the |
| `full_stack_lab/gateway/app/privacy.py:227` | 시험 PC·계정 | # with the whole result (10-23 PJ1: five SDK documents withheld). |
| `full_stack_lab/gateway/app/review.py:339` | 작업 번호 | # Keep $defs so $ref inside the advertised contract still resolves (DEV-44). |
| `full_stack_lab/gateway/app/risk_tier.py:1` | 작업 번호 | """Risk tier of an intake request from what the applicant stated (DEV-71). |
| `full_stack_lab/gateway/app/tool_sunset.py:1` | 작업 번호 | """Time out unused, human-scoped tools using the append-only decision ledger (DEV-75).""" |
| `full_stack_lab/gateway/app/upstream.py:443` | 작업 번호 | put on later pages, and an enabled tool there blocked every call to the server (DEV-44)."" |
| `full_stack_lab/gateway/app/user_suspend.py:1` | 작업 번호 | """An administrator stops one employee's use of one MCP server and later lets it resume (D |
| `full_stack_lab/gateway/app/v2_tables.sql:298` | 작업 번호 | -- Approved source MCP servers the solution builds and runs itself (DEV-38, D-114). Approv |
| `full_stack_lab/gateway/app/v2_tables.sql:375` | 작업 번호 | -- DEV-71: what the applicant stated about data, transfer, permission and users. The risk  |
| `endpoint-agent/README.md:133` | 시험 PC·계정 | 실제 화면·UAC·재설치 검수는 \[pj3 시험 절차\] (tests-windows/README.md)를 따릅니다. |
| `endpoint-agent/README.md:154` | 시험 PC·계정 | - PJ1 재검증: root가 Console 직원·독립 관리자 신원을 stdin으로 제공하고 |
| `endpoint-agent/README.md:230` | 시험 PC·계정 | \[PJ1 Linux 실제 검증과 로그\] (../research/llm-wiki/status/reports/2026-10-14-endpoint-telemetry-fi |
| `endpoint-agent/README.md:236` | 팀원·작업 서술 | - **OS 거부 분류.** `os-observer.py`는 AppArmor 거부에서 실행 시도 프로세스(`comm`)·프로파일·대상 파일명을 보내고 `harne |
| `endpoint-agent/README.md:289` | 시험 PC·계정 | 공식 카탈로그 이미지도 일반 UID 실행을 보장하지 않는다. 10-23 PJ1 Docker 29.8.1 실측에서 `mcp/git`· |
| `endpoint-agent/agent.py:675` | 시험 PC·계정 | (10-23 PJ1). The runner's containers carry the label mcpgw.local=1; only root or the engin |
| `endpoint-agent/bootstrap.py:394` | 시험 PC·계정 | # header helper failed on PJ1. `cd /` keeps that out of the way; the login shell moves to  |
| `endpoint-agent/bootstrap.py:396` | 시험 PC·계정 | # PATH, and a harness installer that ran there at login (PJ1, 10-15) put an unapproved cop |
| `endpoint-agent/bootstrap.py:501` | 시험 PC·계정 | # (PJ1, 10-22) still reports "Logged in" and then fails every model call with 401. |
| `endpoint-agent/enforce-linux.py:135` | 작업 번호 | # the device token (DEV-31). Anything bash starts, sh included, stays in -tool. |
| `endpoint-agent/enforce-linux.py:373` | 기기 주소 | text = nft_rules(1234, \["100.83.175.111", "fd7a:115c:a1e0::1"\], 443) |
| `endpoint-agent/enforce-linux.py:377` | 기기 주소 | assert "tcp dport { 443, 3128 } accept" in nft_rules(1234, \["100.83.175.111"\], 443, 3128) |
| `endpoint-agent/local-runner.py:96` | 시험 PC·계정 | # 첫 설치 PC에는 승인된 폴더가 아직 없다(10-23 pj2). 관리 계정 홈 안의 승인 경로만, |
| `endpoint-agent/local-runner.py:177` | 시험 PC·계정 | # runc 1.2+는 다른 프로세스의 /proc/<pid>/fd 링크를 바인드 원천으로 받지 않는다(EINVAL, 10-22 PJ1 docker 29.8.1). |
| `endpoint-agent/local-runner.py:560` | 시험 PC·계정 | # Only to this PC's journal: a failure before the container starts left no cause anywhere  |
| `endpoint-agent/managed-linux.py:204` | 시험 PC·계정 | # `claude` there ran the unmanaged copy (10-23 pj2: the model sign-in went to the employee |
| `endpoint-agent/managed-linux.py:487` | 시험 PC·계정 | # Right after install the service has not written its first summary yet (10-23 pj2): not a |
| `endpoint-agent/managed-linux.py:893` | 시험 PC·계정 | # 헤더가 없으면 하네스가 OAuth 인증 대기로 표시·캐시해 복구 뒤에도 연결하지 않는다(D-148 PJ1). |
| `endpoint-agent/managed-windows.py:480` | 시험 PC·계정 | # 헤더가 없으면 하네스가 OAuth 인증 대기로 표시·캐시해 복구 뒤에도 연결하지 않는다(D-148 PJ1). |
| `endpoint-agent/managed-windows.py:811` | 기기 주소 | assert complement(\["100.83.175.111"\]) == \["0.0.0.0-100.83.175.110", "100.83.175.112-255.25 |
| `endpoint-agent/managed-windows.py:816` | 기기 주소 | rules = firewall_rules("kim", "S-1-5-21-1-2-3-1001", \["100.83.175.111"\], \[443, 3128\]) |
| `endpoint-agent/os-observer.py:70` | 작업 번호 | # listener the harness runs (Codex's login callback, DEV-35): not a connection attempt. |
| `endpoint-agent/tests-windows/README.md:1` | 시험 PC·계정 | # Windows 키트 검수 — pj3 |
| `endpoint-agent/tests-windows/README.md:3` | 시험 PC·계정 | 이 절차는 메인이 격리 pj3 VM에서 수행한다. 이번 작업에서는 원격 접속·설치·GUI 실행·실기기 캡처를 수행하지 않았다. |
| `endpoint-agent/tests-windows/README.md:16` | 시험 PC·계정 | - 관리자 `pj3`, 표준 사용자 `pj3user`의 프로필을 각각 만들고, 승인된 native 하네스와 같은 릴리스의 동반 실행파일을 준비한다. |
| `endpoint-agent/tests-windows/README.md:45` | 시험 PC·계정 | ## 관리자 계정 pj3 |
| `endpoint-agent/tests-windows/README.md:47` | 시험 PC·계정 | 1. `pj3user`를 로그아웃하고 pj3 콘솔에서 `install.cmd`를 연다. 시작 화면이 보이고 아직 UAC가 없어야 한다. |
| `endpoint-agent/tests-windows/README.md:48` | 시험 PC·계정 | 2. 대상 계정 `pj3user`를 입력한다. 시작 → 게이트웨이 연결 확인(TCP와 `/api/health`) → 설치 위치·관측 범위 확인 순서를 캡처한다. |
| `endpoint-agent/tests-windows/README.md:56` | 시험 PC·계정 | 7. 관리자 자신의 계정 pj3를 대상으로 하는 분기도 별도 VM 스냅샷에서 시험한다. `mcpgw-pj3` 프로필이 없으면 |
| `endpoint-agent/tests-windows/README.md:59` | 시험 PC·계정 | ## 표준 계정 pj3user |
| `endpoint-agent/tests-windows/README.md:61` | 시험 PC·계정 | 1. 아직 관리되지 않는 초기 VM에서 `pj3user`로 마법사를 열고 연결·위치·범위 확인까지 UAC 없이 진행한다. |
| `endpoint-agent/tests-windows/README.md:63` | 시험 PC·계정 | 3. 다시 시도에서 pj3 자격으로 UAC를 승인한다. 현재 pj3user 세션이 열려 있으면 `대상 계정 로그아웃 필요`로 실패해야 한다. |
| `endpoint-agent/tests-windows/README.md:64` | 시험 PC·계정 | 해당 경계를 완화하지 않는다. pj3user 로그아웃 후 pj3 세션에서 그 계정을 대상으로 설치를 완료한다. |
| `endpoint-agent/tests-windows/README.md:127` | 시험 PC·계정 | 작업은 콘솔 세션 1의 실제 로그인 계정(`pj3` 또는 `pj3user`)을 UserId로 지정하고 `LogonType Interactive`·`RunLevel |
| `endpoint-agent/tests-windows/test_windows_kit.py:223` | 기기 주소 | $failed=$false; try { $null=New-EndpointGatewayRequest 'http://100.83.175.111/api/health'  |
| `endpoint-agent/tests-windows/test_windows_kit.py:246` | 기기 주소 | policy = {'tailscale_node_id': 'approved', 'gateway_ips': \['100.83.175.111'\], 'gateway_por |
| `endpoint-agent/tests-windows/test_windows_kit.py:534` | 시험 PC·계정 | # pj3: CRLF translation made three of four managed configs mismatch, so activation was ref |
| `endpoint-agent/tests-windows/test_windows_kit.py:542` | 시험 PC·계정 | # pj3: icacls /T left existing files with empty DACLs, so the elevated installer could not |
| `endpoint-agent/tests-windows/test_windows_oneclick.py:178` | 기기 주소 | policy = {'tailscale_node_id': 'approved', 'gateway_ips': \['100.83.175.111'\], 'gateway_por |
| `full_stack_lab/field/pc/mcpgw_pc.py:4` | 기기 주소 | python mcpgw_pc.py setup --url https://100.83.175.111 --ca root.crt --ca-sha256 SHA256 --s |
| `full_stack_lab/field/pc/mcpgw_pc.py:609` | 팀원·작업 서술 | """Codex가 실제로 쓰는 웹 검색 모드: 계층 설정을 관리형 requirements가 제한한 값. 기본은 cached이고, |
| `full_stack_lab/db/init.sql:3` | 팀원·작업 서술 | -- 끄는 방법이 없었고 (2) 한 계정의 비밀번호만 바꾸는 것이 불가능했다. 팀원 저장소 |
| `full_stack_lab/integrations/litellm/preflight.py:5` | 시험 PC·계정 | Run on the designated managed PJ1 account after provisioning; --validate-only |
| `full_stack_lab/llm/standalone/compose.yaml:80` | 기기 주소 | GATEWAY_ADDR: ${GATEWAY_ADDR:?제품 게이트웨이 주소(예 100.83.175.111:443)} |
| `full_stack_lab/llm/standalone/harness/Dockerfile:1` | 시험 PC·계정 | # 하네스 시험용 클라이언트: 직원 PC의 Claude Code·Codex와 같은 판본(PJ1 실측 2.1.288 / 0.160.0)을 공식 npm 패키지 그대로 |
| `full_stack_lab/opa/policy.rego:18` | 작업 번호 | # DEV-69: facts are made from the reviewed registry, never tool arguments or IP geography. |
| `full_stack_lab/opa/policy_ledger.json:3201` | 시험 PC·계정 | "PJ1-managed-install" |
| `full_stack_lab/opa/policy_ledger.json:3477` | 작업 번호 | "purpose": "미확인 위치 또는 금지 국가로의 전송을 차단한다(DEV-69, POL-26·10·40).", |
| `full_stack_lab/opa/policy_test.rego:751` | 팀원·작업 서술 | # 팀원의 실행 전 정책 PAC-01~15 중 이 정책이 무엇을 집행하는지(docs/ai/PAC_MAPPING.md). |
| `full_stack_lab/opa/policy_test.rego:1233` | 작업 번호 | # DEV-69: independent of the PAC fixture's resource scope; grade/location facts are regist |
| `full_stack_lab/runtime/Dockerfile:1` | 작업 번호 | # The runtime worker: the only container that talks to the container engine (DEV-38). It c |
| `full_stack_lab/runtime/worker.py:1` | 작업 번호 | """Builds and runs approved source MCP servers from fixed recipes (DEV-38, D-114). |
| `docs/ai/SECURITY_BOUNDARIES.md:7` | 시험 PC·계정 | **현재 기본은 경고 단계이며 같은 UID 노출은 남아 있다.** 기존 하네스의 `sh -c` 헤더 명령도 엄격한 자식 분리에 걸리므로, 정상 경로를 확보하고 P |
| `docs/ai/SECURITY_BOUNDARIES.md:20` | 시험 PC·계정 | PJ1 일반 UID에서 실제 AppArmor/nft 집행, 185초 heartbeat 만료, 보호 파일 변조·격리·독립 복구, |
| `docs/ai/SECURITY_BOUNDARIES.md:26` | 시험 PC·계정 | `unknown_not_enrolled`·`bypass_possible`로 나눠 Console·API에 표시한다. PJ1처럼 관리 계정(`managed-pj1`) |
| `docs/ai/SECURITY_BOUNDARIES.md:27` | 시험 PC·계정 | 같은 단말에 sudo·docker 계정(`pj1`)이 있으면 단말은 `bypass_possible`이다. 응답은 text만 반환하고, 그 밖의 형식·마스킹 |
| `docs/ai/SECURITY_BOUNDARIES.md:116` | 작업 번호 | 주장은 DEV-73 완료 조건에 포함하지 않는다. 장치 자격 복제와 호스트 root 침해도 하드웨어 증명으로 해결했다고 주장하지 않는다. |
| `docs/ai/README.md:14` | 시험 PC·계정 | \| \[PJ1_SIGNALS_2026-10-01.md\] (PJ1_SIGNALS_2026-10-01.md) \| D-59 뒤 실제 PC(pj1)의 신호 81건·하네스 1 |
| `docs/design/NETWORK.md:43` | 기기 주소·시험 PC·계정 | `PJ1_SSH=pj1@192.168.85.129`, `PJ2_SSH=pj2@192.168.85.130`처럼 하이퍼바이저 NAT |
