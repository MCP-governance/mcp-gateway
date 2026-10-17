# DEV-64 하네스–게이트웨이 TLS / D-124

기준: `10/18-field-tls`, 시작 commit `6ce607035271b00949ee075313635a9e6f3a8d82`, 시작 워킹 트리 clean.
WBS G08.05·POL-16의 현장 연결을 HTTPS로 전환한다. **구현·로컬 단위 증거**이며 배포·PJ1 통과는 아니다.
원자 요구사항·코드 SHA-256·심볼·시험 연결은 [requirements.json](requirements.json),
실행 결과는 [validation.json](validation.json), 메인 인계 명령은 [작업 보고](../../status/reports/2026-10-18-field-tls-d124.md)에 있다.

| 요구사항 | 구현 | 검증·남은 조건 |
| --- | --- | --- |
| TLS-01 | Caddy `tls internal`, TLS 1.2/1.3, ECDHE/ECDSA AES-GCM·ChaCha20, 자동 리디렉션 중지 | 설정 불변식 검사 통과. Caddy 자체 adapt/validate는 실행기 부재로 미실행 |
| TLS-02 | Tailscale IP:443→8080 유지, IP 및 선택 공개 이름 인증서, IP 기본 SNI | 실제 SAN·빈 SNI·LAN 비게시·구버전 TLS 거부는 기기 확인 필요 |
| TLS-03 | 배치 볼륨 보존, `field ca` 공개 루트·DER SHA-256 내보내기 | 볼륨 재기동/경쟁 발급/복구 시험 미실행 |
| TLS-04 | Console ZIP의 루트·지문·등록 정보, 단일 인증서와 지문 검사 | 정상·불일치·누락·다중 인증서, 등록/파일 쓰기 이전 거부 단위 통과 |
| TLS-05 | Linux root 소유 CA, 하네스 실행기·직원 PC `harness` 명령의 프로세스 환경 | 환경 불변·하네스별 변수 단위 통과. 실제 Claude/Codex MCP 호출은 PJ1 대기 |
| TLS-06 | 관측/관리형 에이전트의 HTTPSHandler·호스트/체인 검사·리디렉션 거부 | 컨텍스트·평문 선차단 단위 통과. OS 관측기는 공통 `agent.call()` 사용 |
| TLS-07 | 레지스트리/렌더러 HTTPS, field 이미지 빌드 인자와 동적 관리형 정책 HTTPS | 4종 출력 검사 통과. 격리 기본 랩은 명시적 HTTP 인자 사용 |
| TLS-08 | Windows ZIP에 동일 CA 필드 전달 | 전용 파일 수정 금지에 따라 소비·실행 환경 연결은 별도 Windows 작업과 통합 필요 |

## 근거와 선택

- [RFC 9325](https://www.rfc-editor.org/info/rfc9325/) §3.1.1·§3.2·§4.2: 구버전 TLS를 끄고 TLS 전용 경로와 ECDHE/AEAD를 사용한다. TLS 1.3 암호군은 Go 기본값이다.
- [NIST SP 800-52r2](https://csrc.nist.gov/pubs/sp/800/52/r2/final): TLS 버전·인증서·암호 설정 검토의 근거로 사용한다. 이 설정만으로 FIPS 또는 NIST 전체 적합성을 주장하지 않는다.
- [Caddy 설정](https://caddyserver.com/docs/caddyfile/options): `disable_redirects`, `skip_install_trust`, `default_sni`를 선택했다. [TLS 지시어](https://caddyserver.com/docs/caddyfile/directives/tls)의 internal CA를 기존 Caddy에 적용한다.
- Caddy **2.11.4**, commit [`e2eee6a7fce366321294c9c2a79f3146891dcbdf`](https://github.com/caddyserver/caddy/commit/e2eee6a7fce366321294c9c2a79f3146891dcbdf), Apache-2.0. [고정 소스](https://github.com/caddyserver/caddy/blob/e2eee6a7fce366321294c9c2a79f3146891dcbdf/modules/caddytls/connpolicy.go#L180-L205)의 TLS 정책/기본 SNI를 확인했다. 기존 의존성만 사용하며 새 CA 서버는 만들지 않는다. 릴리스에서 유지보수 패치를 확인했으나 이미지 전체 취약점 감사를 수행한 것은 아니다.
- Codex **0.157.0**, commit [`00c972ed5d6ff6499317fd41b7f23605b8e6850d`](https://github.com/openai/codex/commit/00c972ed5d6ff6499317fd41b7f23605b8e6850d), Apache-2.0. [공식 문서](https://learn.chatgpt.com/docs/auth#custom-ca-bundles)와 [custom_ca.rs](https://github.com/openai/codex/blob/00c972ed5d6ff6499317fd41b7f23605b8e6850d/codex-rs/http-client/src/custom_ca.rs#L153-L171)에서 `CODEX_CA_CERTIFICATE`와 `SSL_CERT_FILE` 대체 순서를 확인했다. 실제 적용은 전자를 사용한다. [RMCP 소스](https://github.com/openai/codex/blob/00c972ed5d6ff6499317fd41b7f23605b8e6850d/codex-rs/rmcp-client/src/rmcp_client.rs#L1174-L1190)는 주입된 HTTP client를 사용하는 구조다. 이 확인을 실제 MCP TLS 성공으로 세지 않는다.
- [Claude Code 공식 문서](https://code.claude.com/docs/en/network-config), [Node 문서](https://nodejs.org/api/cli.html#node_extra_ca_certsfile): `NODE_EXTRA_CA_CERTS`를 프로세스 시작 전에 지정한다. 재실행이 필요하다. 별도 시스템 CA 설치나 검증 비활성화는 사용하지 않는다.
- GitHub 공개 스킬 탐색에서 [caddy-security configuration-authorization](https://github.com/greenpau/caddy-security/blob/main/.codex/skills/configuration-authorization/SKILL.md)을 발견했다. 인가 플러그인용으로 이번 기본 Caddy TLS 설정에 적용하지 않았다. 해당 스킬의 고정 commit·라이선스·최신 유지보수 상태는 미확인이고 외부 스크립트도 실행하지 않았다.

외부 자료는 2026-10-18 웹 본문·고정 태그/commit으로 읽었다. 원문 파일은 재배포하지 않는다.
셸 네트워크가 `WinError 10013`으로 차단되어 원문 바이트 SHA-256은 미확보다. 로컬 변경 파일의 해시는 JSON에 별도 기록한다.
원본 기준의 현황·점수는 [10-17 기능명세](../feature-spec-2026-10-17/README.md) 그대로 보존하며 이번 단위 검증으로 최종 검수 점수를 올리지 않는다.

## 실패·경쟁·복구 조건

CA·지문 중 하나만 있거나 루트가 바뀌면 요청 전에 실패한다. HTTP URL은 원격 자격을 보내기 전에 거부한다.
agent·관리형 서비스·직원 PC 요청은 HTTP 리디렉션을 따라가지 않는다. 지문 일치는 키트 무결성 검사이므로 최초 루트는 인증된 배포 경로와 별도 지문 대조가 필요하다.
재기동·인증서 갱신은 같은 CA 볼륨을 유지한다. 동시 연결/키트 발급 시 지문 동일성, Caddy 장애 시 토큰 미발급,
루트 교체 후 기존 CA 실패→재설치 복구는 PJ1에서 확인한다. Windows 이전 키트와 레거시 HTTP 실험 스크립트는 새 배치 검증 수단으로 쓰지 않는다.
