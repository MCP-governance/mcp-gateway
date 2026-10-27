# 2026-10-27 사내 저장소 직접 접근 차단·콘솔 HTTPS (D-262)

- 출처: 10-27 개발 온보딩 회의 3번(내부저장소 관리 / 소스코드 관리)
- 브랜치: `10/27-internal-repo-console-only`, 기준 `origin/main` 1d22361
- 결정: D-262 (D-48 권한 축소, D-129 평문 콘솔 대체)

## 변경

| 파일 | 내용 |
| --- | --- |
| `full_stack_lab/gateway/app/agent_service.py` | `/auth/gitea`가 관리자만 통과. 직원 브라우저 302 `/#/intake?t=approved`, 그 밖 403, Gitea 사용자 동기화 안 함 |
| `full_stack_lab/field/console/none.caddy` | `http://:8081`(호스트 `:8000`)은 콘솔 대신 `https://{$APPLIANCE_BIND}{uri}` 301 |
| `full_stack_lab/console.sh`, `compose.field.yaml` | 안내 콘솔 주소를 IP HTTPS로 |
| `tests/approved_mcp_download_check.py`, `tests/console_https_check.py` | 직원 302·403·동기화 없음·관리자 200, none 방식 리디렉트 |
| `docs/ai/FIELD.md`, `RUNBOOK.md`, `docs/API.md`, `CHANGELOG.md` | 동작 설명 갱신 |

## 검증

- 로컬: `approved_mcp_download_check.py` 22건 OK, `console_https_check` 14건 OK(도커 4건 생략), `field_kit_check.py` OK, `open_endpoints.py` PASS, `deploy/check.py` PASS, pyflakes 무경고.
- 개인 시험 솔루션(WSL kali, 별도 클론 `mint-ysg-1027`, Tailscale IP, `field init-disposal` 뒤 `field up`):
  - `http://<IP>:8000/login`·`/workspace`·`/git/mcp` → 301 `https://<IP>/…`
  - 새 직원 가입→승인→로그인: 브라우저 `/git/mcp` 302 `/#/intake?t=approved`, 쿠키 요청 403, Basic `info/refs` 403, `git ls-remote` 403
  - 관리자(root): 브라우저 200, Basic 웹 200, `info/refs` 인증 통과(없는 저장소 404)
  - 직원 `GET /api/approved-mcp` 200
  - 관리자 Basic으로 Gitea API `/api/v1/version` 403은 D-48의 기존 한계(API 역방향 프록시 인증 꺼짐)이며 이 변경과 무관.

## 남은 것

- 키트 설치 화면에서 승인된 소스를 Console 경로로 받아 자동 설치·설정(회의 3번의 「설치 GUI에서 다운」). 회의 2번(키트 설치 GUI) 작업과 같은 파일을 다뤄 그 작업과 맞춰 진행.
- 병합 직전 `refresh_generated.py`로 위키 생성물(코드 해시·결정 색인) 재생성 — 먼저 올라온 PR #65·#66 병합 뒤.
