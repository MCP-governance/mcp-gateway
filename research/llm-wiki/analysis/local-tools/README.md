# 로컬 도구·MCP 설치와 엔드포인트 검수

2026-10-14. Luna 3개가 설치·프로토콜·기능 수집을 분담했고 Codex가 실제 응답, 스키마, 소스와 권한 반례를 검수했다. 분석은 작업 브랜치 `10/14-local-mcp-endpoint`에 보존한다. 시작 commit은 `ab6936c64f3578de8360b840f1928681714fa7bb`이며 기존 다른 작업의 미커밋 파일132개를 격리 작업트리로 복사해 기준선으로 보존했다.

## 설치·실행 결과

| 유형 | 로컬 소프트웨어·실제 MCP | 도구 수 | 실제 확인 | 제한 |
| --- | --- | --- | --- | --- |
| 역공학·바이너리 분석 | Ghidra12.1.4 / GhidraMCP2.0.0 | 28 | 합성 ELF import·분석, initialize·목록·get_program_info | read20/write8 중 변경 도구는 미호출; 바이너리는 실행하지 않음 |
| 개발·저장소 | Git2.55 / cyanheads Git MCP2.15.3 | 28 | status, add/commit의 HEAD 변화·원복, 기준 경로 밖 setter/clone 반례 | 기준 경로가 모든 도구에 동일하게 적용되지 않음; 원격 push/fetch 미실행 |
| 데이터 | SQLite / DBHub1.5.0 | 2 | SELECT·INSERT 독립 관찰·DELETE 원복; readonly INSERT/ATTACH/extension 거부 | SQL gate와 OS 파일격리는 별도 |
| 3D·앱 자동화 | Blender5.2.2 LTS / mcp-for-blender2.1.9 | 9 | addon 상태·장면 읽기·합성 구 생성 후 mesh1→2 확인 | MCP safe mode가 인증 없는 raw TCP bridge를 제한하지 않음 |
| 브라우저 | Chromium155 / Playwright MCP0.0.83 | 25 | headless 격리 프로필·loopback 합성 한글 HTML navigate/snapshot | 호스트 unsafe JS·파일 업로드·외부 egress는 미호출 |

총92개는 **이 판본·설정에서 광고된 도구의 수**다. 92개를 전부 실행했다는 뜻이 아니다. 도구 이름별 보수적 권한 상한과 실제 선택 호출 여부는 [기능 유형표](tool-capabilities.md)와 [전체 스키마·hash JSON](tool-capabilities.json)에 있다. 조회·쓰기·실행·네트워크 태그는 겹칠 수 있다.

GhidraMCP·Git MCP·DBHub·Blender MCP·Playwright MCP는 실제 공개 OSS이며 자체/mock 서버를 만들지 않았다. MCP client/protocol driver와 합성 fixture는 시험 도구다. 설치 경로와 가상환경·lock·원본 응답은 저장소의 ignored `.task-local-20261014/` 아래에 있다. 사용자 하네스·브라우저 프로필·시스템 방화벽/PATH를 변경하지 않았고 운영 registry에 자동 등록하거나 계약 승인하지 않았다. Git은 기존 시스템 설치를 재사용했다.

DBeaver Community26.2.2는 공식 portable ZIP을 검증·설치했으나 GUI DB 연결·쿼리는 미완료다. Burp Community 공식 desktop MCP 확장과 유료 DAST MCP는 별개이며 최신 후보 상태는 [desktop 조사](desktop.md)를 따른다. radare2/rizin은 비교 후보로만 두었다.

## 근거와 검수

- [Ghidra 결과](reverse.md) · [정본 JSON](reverse.json)
- [Git·SQLite·DBeaver 결과](data.md) · [정본 JSON](data.json)
- [Blender·Playwright·Burp 결과](desktop.md) · [정본 JSON](desktop.json)
- [10개 위험 항목과 원본 정책의 연결](../../threats/local-tool-map.md) · [위험 정본](../../catalogs/local-tool-risks.json)
- [검수 manifest](review.json) · [키트 회귀 원본](../../status/reports/2026-10-14-endpoint-regressions.json)

부모 검수에서 Git setter의 metadata 접근과 status 거부를 분리했고, clone의 바깥 경로 실제 쓰기·독립 HEAD 일치도 추가 확인했다. Burp는 DAST 문서만으로 Community 연동 불가라고 했던 초기 해석을 공식 BApp Store·desktop extension으로 정정했다. 제품 기능·설정의 권한과 OS 경계를 구분한다.

## 엔드포인트 개선과 남은 경계

Linux AppArmor는 실제 프로필의 정확한 행을 확인하며 다른 계정의 유사 이름을 인정하지 않는다. Windows는 Domain/Private/Public3개 프로필의 boolean true, 예상 규칙3개·활성 상태·Outbound/Block/Any·계정 SID와 설치 기준선 일치를 요구한다. 불완전한 snapshot의 일치만으로 정상으로 판정하지 않는다.

인벤토리에서는 이름을 복사해 Gateway 경유로 위장하지 못하게 실제 URL만 인정한다. URL userinfo/query/fragment와 이전 수집기의 stdio 원문 인자는 수집·수신·raw 저장에 SHA-256을 사용한다. Playwright/DBHub/Blender 직접 실행 표지를 수집기에 추가했지만 결과는 `suspected`로 유지한다.

이 수정은 로컬 회귀 이후 **솔루션과 PJ1 Linux에도 적용**했다. 처음 SSH 시간 초과가 났지만 재접속했고, 현재 PJ1 활성/준수·설정 hash 일치·fresh shell의 실제 AppArmor label·승인 Codex/Claude 실행·비승인 Node 거부·IPv4/IPv6 loopback 거부·승인 Gateway TCP 통과를 확인했다. [PJ1 원본](../../status/reports/2026-10-14-pj1-endpoint-update.json)과 [솔루션 배포·readiness/hash](../../status/reports/2026-10-14-solution-deployment.json)를 분리 보존한다. 이것은 새 모델의 자연어 MCP 호출·92개 도구 전부의 관리 엔드포인트 집행을 의미하지 않는다.

Windows loopback과 실행·스크립트 통제, AppArmor 로드 정책 본문·승인 binary 무결성, 이름을 바꾼 프로세스·앱 내부 플러그인, 다른 계정/root는 후속 경계다. Windows 사용자 범위 PC 키트의 background report/uninstall 파일 경합도 별도로 남아 있다.

2차 공식 권한 자료는 [Linux](permissions-reverse.md), [Windows](permissions-data.md), [앱 bridge·브라우저·MCP](permissions-desktop.md)에 각각4개 주제로 정리했다. 새 권한을 자동 설치하지 않고 적용조건·공백·정상/음성/독립 효과 시험 기준을 연결했다. root 서비스 격리를 위해 주소 family를 제한한다면 현재 nft 조회에 필요한 AF_NETLINK와 정책 파일 쓰기·저널 접근을 먼저 검토해야 한다.

DBeaver 확인 중 사용자 `%APPDATA%/DBeaverData/.../EBWebView` 캐시가 생성된 정황이 있다. 기존 파일의 변경 여부는 사전 hash가 없어 미확인이고 이 경로는 보존했다. [정확한 경로·시각·한계](data.md)에 기록했다.

## 재생성

```powershell
python -X utf8 research/llm-wiki/tools/build_local_tool_analysis.py
python -X utf8 research/llm-wiki/tools/map_threats.py
python -X utf8 research/llm-wiki/tools/capture_status.py
python -X utf8 research/llm-wiki/tools/build_wiki.py
python -X utf8 research/llm-wiki/tools/check_wiki.py
```

분석 재생성은 검증 당시 task-local raw 응답이 필요하며, 설치 없이 보고서를 읽는 것은 실행 검증이 아니다. 정책번호 PAC01~24와 런타임 PAC-01~15는 기존처럼 의미로 연결한다.

최종 재현 보강: Blender launcher는 `--disable-autoexec`와 호출자의 APPDATA/PROFILE 원복을 적용했다. 새 프로필 시작·bridge 준비·종료를 확인했고 MCP child에는 자격정보 환경을 전달하지 않는다. 마지막 raw 응답은 내용 hash가 붙은 immutable task-local 사본으로 고정했으며 Git/SQLite 최종 replay와 script hash는 data.json을 따른다.
