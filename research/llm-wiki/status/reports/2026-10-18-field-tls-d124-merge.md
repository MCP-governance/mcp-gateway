# 2026-10-18 field-tls-d124 병합 후 보강

- 작업자: Codex. 시작 HEAD `b7b348849376a9edc5c5d66b8f0c9250ee28a1fc`, main 병합 중 워킹 트리. 커밋·원격 접속·스택 기동 없음.
- 근거: D-118과 D-120~123을 보존하는 D-124 후속 리뷰. [이전 보고](2026-10-18-field-tls-d124.md)의 Windows 통합 대기를 이번 코드·단위 증거로 대체한다.
- 해결 범위: 충돌 7파일의 텍스트, Windows 관리형 CA 연결과 승인 키트, CLI/브라우저 안내, 잘못된 내부 TLS 기본값.

## 변경

| 파일 | 결과 |
| --- | --- |
| `full_stack_lab/compose.field.yaml` | CA·폐기 원장·Trivy 등 양쪽 볼륨 유지 |
| `full_stack_lab/gateway/app/agent_service.py` | main의 `payload.items()` ZIP 구조 유지. CA 파일·지문·직원 PC 도구도 payload로 넣고 Windows 매니페스트 해시 계산에 포함. Python ZIP/manifest 보존 |
| `docs/ai/DECISIONS.md` | D-118·119·120~123·124 번호 순 유지, D-124 후속 정정 추가 |
| `research/llm-wiki/status/backlog.md` | DEV-62·63은 main, DEV-64는 TLS 작업 내용 유지·후속 검증 반영 |
| `research/llm-wiki/catalogs/threats.json`, `status/repository-snapshot.*` | 기존 TLS 쪽 선택, 마커 제거. **메인이 map_threats.py·capture_status.py로 재생성** |
| `endpoint-agent/managed-windows.py` | 계정/파일 변경 전 번들 지문 검사, 요청별 Python HTTPS context, CA 설정 보존, 서비스·OS 관측 전달. 보호된 SID별 `.cmd` 실행기에서 CA 환경값만 프로세스에 지정. 계정 CA 환경값·시스템 저장소는 변경하지 않음 |
| `endpoint-agent/windows-common.ps1` | 요청별 C# 검증 콜백으로 구성 CA에 연결되는 체인·이름·유효기간/용도를 검증. Framework 호환 `ExtraStore` 사용, 전역 인증서 콜백/인증서 저장소 변경 없음. 프로세스의 TLS 프로토콜은 1.2로 제한 |
| `endpoint-agent/setup.ps1`, `windows-worker.ps1`, `windows-trust.ps1`, `tray.ps1` | 초기/설치/트레이 연결 확인에 CA 전달. 관리자 작업자는 외부 승인된 파일 해시로 검증한 루트로 요청과 번들의 CA를 덮어씀. 사용자 제공 CA가 승격된 목적지의 신뢰를 결정하지 못함 |
| `full_stack_lab/console.sh`, `docs/ai/FIELD.md`, `docs/ai/ARCHITECTURE.md`, `endpoint-agent/README.md`, `tests-windows/README.md` | 지문·별도 Firefox 프로필 신뢰 안내, 실제 실행기 경로·승인 매니페스트 갱신 안내 |
| `full_stack_lab/registry/catalog.toml`, `registry/field/catalog.toml` | `https://gateway/mcp` 기본값 제거. 기본값은 비어 있으며 `render.py --gateway-url https://실제게이트웨이/mcp`가 없으면 파일 쓰기 전 실패. 기본 격리 랩 Dockerfile의 명시적 내부 HTTP 인자와 field의 HTTPS 인자는 유지 |
| `full_stack_lab/tests/field_tls_check.py`, `endpoint-agent/tests-windows/test_windows_kit.py` | 새 payload 구조 회귀, Windows 등록/서비스/관측 CA 전달, 승인 루트 고정, 프로세스 실행기·전역 환경 미변경, 실제 .NET 체인/지문/이름/만료 음성 시험 |

현재 main의 승인 매니페스트 조회는 보호된 `approved-windows-kit.json`의 로컬 읽기다. 새 네트워크 조회 라우트를 만들지 않았다.
기존 인증된 키트 응답의 매니페스트/응답 헤더를 조직 배포 경로가 전달한다. 그 HTTPS 다운로드에도 검증된 CA를 사용해야 한다.
Windows 승인 목록은 기존 목록을 그대로 쓰면 CA 파일 누락으로 실패하므로 새 payload의 목록으로 갱신한다.
설치기가 계정 PATH에 더한 `.cmd` 대신 다른 설치의 native exe를 먼저 찾는 PC는 명시적 실행기 경로를 사용한다.

## 검증

정본 결과·명령·파일 해시는 [merge-validation.json](../../analysis/field-tls-d124/merge-validation.json)에 기록한다.

- `field_tls_check.py`: 9개 통과.
- `field_kit_check.py`: 17개 중 16개 통과, Docker CLI가 필요한 compose 검사 1개 생략. Python 3.10 검사 프로세스에 기존 pip vendored TOML 파서를 주입했으며 제품 의존성 추가 없음.
- Windows 키트: 14개 통과. Windows PowerShell 컴파일·체인/이름/만료 검사와 ACL/입력 경계 단위를 포함한다. 실제 설치·MCP·방화벽 집행·GUI 증거는 아니다.
- `open_endpoints.py`, `bash -n console.sh`, Python 정적 검사, 작업 트리의 `git diff --check`: 결과는 JSON 참조. 실제 충돌 마커 0을 별도 확인한다.
- `git diff --cached --check`는 main이 이미 스테이징한 운영 대응 시험 로그의 기존 CRLF를 공백으로 지적한다. 원본 증거 바이트는 수정하지 않았다.

## 인덱스 권한 제한과 메인 후속

파일 안 충돌은 제거했지만, `git add`가 다음 경로에서 거부됐다.

```text
C:/Users/bobysg/bob/프로젝트/mcp-gateway-pdf-integration/.git/worktrees/mcp-gateway-codex-g/index.lock: Permission denied
```

샌드박스 쓰기 범위 밖의 연결된 Git 메타데이터여서 이 작업에서 인덱스를 갱신할 수 없다.
따라서 `git diff --name-only --diff-filter=U`에는 7파일이 남는다. 메인이 파일 검토 후 아래를 실행해야 병합 충돌 상태가 해제된다.

```bash
git add -- docs/ai/DECISIONS.md full_stack_lab/compose.field.yaml full_stack_lab/gateway/app/agent_service.py research/llm-wiki/catalogs/threats.json research/llm-wiki/status/backlog.md research/llm-wiki/status/repository-snapshot.json research/llm-wiki/status/repository-snapshot.md
python research/llm-wiki/tools/map_threats.py
python research/llm-wiki/tools/capture_status.py
```

나머지 변경 파일도 메인이 검토·스테이징한다. 이 작업은 커밋하지 않는다. 솔루션 기기 배포와 PJ1/pj3의 실제 TLS·설치·모델 MCP 호출·복구 검수는 메인이 수행한다.

## 근거·한계

기존 Caddy·Python·Windows Framework API와 설치기 구조를 재사용했다. 신규 의존성·시스템 CA 등록·전역 인증서 검증 우회는 없다.
브라우저 안내는 [Firefox 공식 자료](https://support.mozilla.org/en-US/kb/setting-certificate-authorities-firefox)의 프로필 인증서 DB 범위로 한정한다.
개인 CA는 폐기 조회 서비스가 없어 .NET 체인에서는 revocation 조회만 끄며 서명·체인·이름·용도·만료는 계속 검사한다.
원자 요구사항/코드 바이트/시험 연결은 JSON에 남기고 이전 분석의 미실행 표시는 과거 이력으로 보존한다.
