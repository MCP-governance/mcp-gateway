# Microsoft Wassette — Wasm/WASI 실행 자원 경계

확인일: 2026-10-13 · 확인 수준: 고정 커밋 Rust 코드 검토 · 라이선스: MIT.

[검토 커밋](https://github.com/microsoft/wassette/tree/742ebb7236273dad2d88c415eabe872d3b95dff9): `742ebb7236273dad2d88c415eabe872d3b95dff9`.

## 코드로 확인한 사실

| 관찰 | 코드 근거 | 활용 방향 |
| --- | --- | --- |
| Wasmtime component model을 켜고 WASI·HTTP·config linker를 조립한다 | [runtime_context.rs:26–49](https://github.com/microsoft/wassette/blob/742ebb7236273dad2d88c415eabe872d3b95dff9/crates/wassette/src/runtime_context.rs#L26-L49) | MCP Gateway 바깥의 실행 런타임 경계와 비교한다 |
| 요청 URI의 host·scheme을 허용 목록과 대조하고 없으면 `HttpRequestDenied`를 반환한다 | [http.rs:99–138](https://github.com/microsoft/wassette/blob/742ebb7236273dad2d88c415eabe872d3b95dff9/crates/wassette/src/http.rs#L99-L138) | 도구 내부의 외부 호출을 정책 입력으로 어떻게 잡는지 참고한다 |
| network inherit을 제거하고 TCP 설정·preopened 디렉터리의 파일 권한을 적용한다 | [wasistate.rs:122–146](https://github.com/microsoft/wassette/blob/742ebb7236273dad2d88c415eabe872d3b95dff9/crates/wassette/src/wasistate.rs#L122-L146) | 도구에 파일시스템 전체를 주지 않는 실행 설정을 비교한다 |

## 채택 판단

공급망 실험에서 임의 실행 파일 대신 Wasm component를 후보로 삼을 수 있다. 기존 Python/Node MCP 전체를 Wassette로 바꾸는 결정은 하지 않는다. 포팅 비용, 지원 interface, tool schema, 자격 전달, 결과 형식이 달라진다.

이 런타임의 자원 제한과 우리 Gateway의 자원 분류·계약 재검증은 별도 층이다. 또한 이 소스의 host 허용 대조만으로 DNS rebinding·redirect·IP 범주·URL 경로 제한까지 보장된다고 말하지 않는다. 일반 사용자 프로세스의 모든 직접 인터넷 연결이 막혔다는 증거도 아니다.

## 확보 증거와 한계

[HTTP 제한 발췌](evidence/ms-wassette/crates__wassette__src__http.rs.excerpt.txt), [WASI 설정 발췌](evidence/ms-wassette/crates__wassette__src__wasistate.rs.excerpt.txt), [runtime 발췌](evidence/ms-wassette/crates__wassette__src__runtime_context.rs.excerpt.txt), [라이선스](evidence/ms-wassette/LICENSE.txt), [NOTICE](evidence/ms-wassette/NOTICE.txt), [해시 목록](evidence/manifest.json).

실제 component 실행·권한 회수·장시간 실행 중 중단·컨테이너 탈출·네트워크 우회는 시험하지 않았다. 향후에는 허용 host 요청 성공과 거부 host 요청 미발생을 서버 수신 로그로 함께 확인한다.
