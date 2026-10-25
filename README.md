<div align="center">

<img src="docs/assets/mint-logo.svg" width="84" alt="MINT">

# MINT

**MCP 거버넌스 게이트웨이**

**한국어** · [English](README.en.md)

[![검증](https://github.com/MCP-governance/mcp-gateway/actions/workflows/verify.yml/badge.svg?branch=main)](https://github.com/MCP-governance/mcp-gateway/actions/workflows/verify.yml)
[![CodeQL](https://github.com/MCP-governance/mcp-gateway/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/MCP-governance/mcp-gateway/actions/workflows/codeql.yml)
![판본](https://img.shields.io/badge/판본-0.9.0-1f4287)
![MCP](https://img.shields.io/badge/MCP-2025--11--25-1f4287)
![Docker](https://img.shields.io/badge/배포-Docker%20Compose-2496ED?logo=docker&logoColor=white)

</div>

MINT는 직원 PC의 AI 코딩 에이전트(Claude Code·Codex CLI)가 쓰는 MCP 서버를 회사가 승인한 것으로 한정하고, 모든 도구 호출을 게이트웨이 한 곳에서
**실행 전에** 판정합니다. MCP를 쓰려면 직원이 신청하고 공급망 검사를 거쳐 다른 관리자가 승인합니다. 호출마다 신원·도구 분류·입력 검사·정책·동의를 확인하고,
응답의 개인정보와 비밀 정보를 가린 뒤 모든 판정을 덧붙이기만 하는 감사 원장에 남깁니다. 직원 PC 키트는 하네스의 관리형 설정을 배포해
승인된 경로만 쓰게 하고, 이용 관계를 끝내면 즉시 차단한 뒤 회수 여부를 증거로 판정합니다.

<p align="center">
  <img src="docs/ai/architecture/mint-architecture-ko.png" alt="MINT 구성도" width="100%">
</p>

<p align="center"><sub>역할 설명이 붙은 판: <a href="docs/ai/architecture/mint-architecture-roles-ko.png">구성도(역할)</a> · 편집 원본: <a href="docs/ai/architecture/mint-architecture-ko.drawio">draw.io</a></sub></p>

## 지원 범위

| 하네스 | 상태 |
| --- | --- |
| Claude Code | 지원 |
| Codex CLI | 지원 |
| Gemini CLI · OpenCode | 실습 스택에서 시험 |

| 직원 PC | 설치 | 상태 |
| --- | --- | --- |
| Linux (Ubuntu 20.04~26.04) | 명령 한 줄, sudo 1회 | 지원 |
| Windows 11 | 파일 하나, UAC 1회 | 지원 |
| macOS | 명령 한 줄 | 시험 |

| 서버 | 요구 사항 |
| --- | --- |
| 게이트웨이 서버 | Linux x86_64, Docker Engine 24+, Docker Compose v2 |

## 5분 설치

```bash
git clone --branch v0.9.0 https://github.com/MCP-governance/mcp-gateway.git
cd mcp-gateway/deploy
./install.sh --bind <사내 IPv4>
```

설치가 끝나면 `https://<사내 IPv4>/`에서 관리자 `root`로 로그인합니다. 초기 비밀번호는 `deploy/initial-admin-password`에 있고,
`./mint.sh set-password root`로 바꿉니다. 요구 사항·구성·옵션은 [deploy/README.md](deploy/README.md)를 봅니다.

## 직원 PC 연결

1. 직원이 콘솔에 로그인 → **내 PC 연결**에서 자기 OS의 키트를 받습니다.
2. 키트를 실행합니다(Linux·macOS는 명령 한 줄, Windows는 파일 하나). 키트에 게이트웨이 주소·루트 인증서·지문이 들어 있습니다.
3. 관리자가 콘솔 **사용자·엔드포인트**에서 엔드포인트를 활성화하면 하네스에 승인된 MCP가 나타납니다. 처음 쓸 때 서버 단위로 이용 동의를 합니다.

키트의 설치 내용·제거·문제 해결은 [엔드포인트 키트](endpoint-agent/README.md)에 있습니다.

## 운영

| 일 | 어디서 |
| --- | --- |
| MCP 도입 신청·승인 | 콘솔 **도입 신청**, **승인 대기** |
| 승인한 서버의 사용 대상·중지·철회 | 콘솔 **MCP 서버** |
| 엔드포인트 활성화·통제 상태 | 콘솔 **사용자·엔드포인트**, **통제 범위** |
| 판정·동의·감사 조회 | 콘솔 **도구 호출 로그**, **이용 동의**, **감사 기록** |
| 계정·비밀번호 | `./mint.sh add-account`, `./mint.sh set-password` |
| 백업·복구·업그레이드·롤백 | `./mint.sh backup`·`restore`·`upgrade` — [운영 런북](docs/ai/RUNBOOK.md) |
| 판본별 변경 | [CHANGELOG.md](CHANGELOG.md) |

## 보안 경계

- **신원은 전송 계층의 토큰에서만** 정합니다. 인자·헤더·클라이언트가 보고한 값은 기록만 하고 판정에 쓰지 않습니다.
- **직원 토큰을 업스트림 MCP로 넘기지 않습니다.** 서버별 자격은 게이트웨이가 따로 보관하고, 직원이 연결한 자격은 조직 키로 암호화합니다.
- **판정할 수 없으면 막습니다.** 정책 엔진·검사기·계약 확인이 실패하거나 분류를 모르면 차단합니다.
- **게이트웨이는 자기 경로를 지나는 호출만 통제합니다.** 관리되지 않는 계정·키트가 없는 PC·벤더 기본 커넥터는 엔드포인트·네트워크·벤더 관리 설정의 몫이며, 콘솔에 통제 상태로 표시합니다.
- **종료 판정은 공개된 증거로 내린 판단입니다.** 제공자의 실제 회수를 검증하는 것은 아닙니다.

세부 위협 모델과 한계는 [보안 경계](docs/ai/SECURITY_BOUNDARIES.md)에 있습니다.

## 개발·기여

- 설계: [docs/ai/ARCHITECTURE.md](docs/ai/ARCHITECTURE.md) · 결정 기록: [docs/ai/DECISIONS.md](docs/ai/DECISIONS.md) · 문서 지도: [docs/ai/README.md](docs/ai/README.md)
- 실습·검증 스택(합성 회사·직원 PC 4대·MCP 서버 10종): [full_stack_lab/](full_stack_lab/README.md)
- 개발 현황·작업 보고·실험 증거: [research/llm-wiki/](research/llm-wiki/README.md)
- 기여 규칙과 깨면 안 되는 불변식: [AGENTS.md](AGENTS.md). 변경은 작업별 브랜치에서 하고, 사용자에게 보이는 변경은 `CHANGELOG.md`의 「미배포」에 적습니다.
- 모든 커밋은 CI(정적 검사·비밀 스캔·실습 스택 전체 검증·운영 배포 설치 검증)를 통과해야 합니다.

## 라이선스

이 저장소에는 아직 오픈소스 라이선스가 지정되어 있지 않습니다. 저작권자의 허락 없이 복제·배포·수정할 수 없습니다.
포함된 제3자 구성요소(OPA, Presidio, Caddy, Gitea, PostgreSQL 등)는 각자의 라이선스를 따릅니다.
