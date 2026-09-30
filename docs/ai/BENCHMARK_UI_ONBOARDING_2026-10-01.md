# Microsoft · IBM · LiteLLM UI와 조직 등록 비교

분석일: 2026-10-01. 공개 소스를 다운로드해 읽은 결과다. 아래 세 제품을 실기기에서 실행하거나
유료 기업 기능을 검증했다는 뜻은 아니다. 기능의 존재, 정책의 집행, 우리 배포의 증거를 구분한다.

## 재현 가능한 소스

| 제품 | 분석 커밋 | 읽은 UI 소스 |
| --- | --- | --- |
| Microsoft MCP Gateway | `3594c4eee36308ac131aad1c946ea14140b4353d` | `portal/src/components/Layout.tsx`, `pages/AdaptersPage.tsx`, `auth/config.ts`, `auth/msal.ts` |
| IBM ContextForge | `0d269c38dc8b1d149c4aee78002431b0eaf63290` | `mcpgateway/templates/admin.html`, `users_partial.html`, `teams_partial.html`, `team_invitation_email.html` |
| LiteLLM | `72049427569f314a23d743dca05d735b611e60b5` | `ui/litellm-dashboard/src/app/(dashboard)/mcp-servers/_components/MCPSubmissionsTab.tsx`, `components/shared/Sidebar.tsx`, `components/Settings/AdminSettings/SSOSettings/RoleMappings.tsx` |

다운로드 위치는 `/home/kali/mcpgw-reference-20261001/{microsoft,ibm,litellm}`다. sparse checkout을 사용했다.
분석 중 공급자 코드를 수정하지 않았다. 이후 비교에는 위 커밋을 기준으로 삼고 최신 상태와 혼동하지 않는다.

## 가져올 설계와 가져오지 않을 주장

Microsoft UI는 고정 상단바, 접을 수 있는 메뉴, 검색 가능한 adapter 목록, 상태 badge와 상세 화면을 사용한다.
runtime 설정이 개발 신원과 Entra 인증을 구분한다. 이를 우리 Console의 상단 검색·접는 메뉴·실제 로그인 역할 표시에
적용한다. 개발용 신원 header를 기업 인증으로 제시하지 않는다.
[Layout 소스](https://github.com/microsoft/mcp-gateway/blob/3594c4eee36308ac131aad1c946ea14140b4353d/portal/src/components/Layout.tsx),
[인증 설정 소스](https://github.com/microsoft/mcp-gateway/blob/3594c4eee36308ac131aad1c946ea14140b4353d/portal/src/auth/config.ts).

IBM은 UI의 사용자·팀·초대와 API RBAC를 함께 제공한다. 메뉴를 감추는 것만으로 보안 경계가 생기지 않는다.
우리 초대 발급·회수·목록은 Console scope와 관리자 역할을 모두 요구한다. 초대받은 사람에게는 employee만 부여하고,
정해진 아이디·부서·기한을 서버에서 고정한다. 화면에서 role을 보내 관리자 권한을 얻을 수 없다.
[초대 템플릿](https://github.com/IBM/mcp-context-forge/blob/0d269c38dc8b1d149c4aee78002431b0eaf63290/mcpgateway/templates/team_invitation_email.html),
[공식 RBAC 문서](https://ibm.github.io/mcp-context-forge/latest/manage/rbac/).

LiteLLM의 MCP 심사 화면은 검색·상태 집계·검토 이력·거부 사유를 제공한다. 도구 접근은 key/team/organization 수준으로
제한한다. 우리 원격 도입도 endpoint·주체·선택한 도구·기한을 검토 기록에 묶고, 승인 후 다른 범위로 등록할 수 없게 한다.
LiteLLM의 해당 UI 승인은 runtime 활성화로 이어지지만, 우리는 검토 → 독립 승인 → 활성화를 각각 기록한다.
[심사 UI 소스](https://github.com/BerriAI/litellm/blob/72049427569f314a23d743dca05d735b611e60b5/ui/litellm-dashboard/src/app/%28dashboard%29/mcp-servers/_components/MCPSubmissionsTab.tsx),
[공식 MCP 문서](https://docs.litellm.ai/docs/mcp).

## 우리 UI 변경

- 고정 상단바, 활동 로그 검색, 접는 메뉴, 로그인한 사용자·역할 표시.
- 개요의 오늘 이벤트와 실제 upstream 실행, 미등록 연결 거부를 별도 집계.
- 활동 로그에서 `tools/call`과 `mcp-connection`을 구분하고 실행·미전송·미확인 필터 제공.
- 원격 서비스 계약 검토에는 실제 광고 도구의 설명·입력 스키마·해시, 사용 주체·기한을 표시.
  경고를 확인하지 않은 도구를 자동 승인하지 않는다. 구현 소스를 검사하지 않은 서비스는 코드 검사 결과로 포장하지 않는다.
- 조직 초대: 최대 50명, 48시간, 1회용. 관리자에게는 발급 때만 링크를 보여준다.
  DB에는 비밀 해시만 저장하며 목록에는 해시도 반환하지 않는다. 사용자 본인이 가입 화면에서 비밀번호를 설정한다.

## 단말·공급망·섀도 AI 경계

MS/IBM/LiteLLM의 위 Gateway UI 소스가 사용자 PC의 임의 `npm`, `pip`, `git clone`, `apt`를
차단한다는 근거는 없다. MCP 등록 관리와 OS 설치 통제는 다른 집행 지점이다.
Microsoft의 앱 허용 정책은 별도 App Control/Intune 계층이고, 섀도 앱 탐지·차단도 Defender for Cloud Apps와
Endpoint 또는 SWG 연동이 담당한다. 이를 오픈소스 MCP Gateway의 기능으로 옮겨 적지 않는다.
[App Control 공식 문서](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/appcontrol),
[Shadow IT 정책 공식 문서](https://learn.microsoft.com/en-us/defender-cloud-apps/policies-cloud-discovery).

우리 설치형 통제는 다음 증거가 모두 있어야 완료다: 비관리자 단말 계정, 관리자가 소유한 정책·서비스,
IPv4/IPv6 TCP/UDP 강제 경로, 실제 패키지 관리자 명령의 실패, 임의 주소·루프백 우회 실패,
등록된 실제 로컬 MCP의 정상 사용, 재시작 후 지속성. 관측 에이전트가 보고를 보냈다는 결과로 집행 성공을 대신하지 않는다.
root·Docker 그룹은 정책을 바꿀 수 있으므로 일반 사용자 범위에 포함하지 않는다.

## 검증 상태

별도 네트워크·빈 볼륨의 WSL2 테스트보드 `mcpgw-remaster-20261001`에서 원격 신청의
실제 fetch 계약 조회·승인·활성화, 범위 변경 거부, 자기 승인 금지, 사용 주체 제한, 만료 차단을 검증했다.
세 공급자 UI를 직접 기동한 비교 시험과 전체 단말 집행은 아직 완료하지 않았다.
최신 진행 상태는 [개편 관리표](REMASTER_2026-10-01.md)를 따른다.
