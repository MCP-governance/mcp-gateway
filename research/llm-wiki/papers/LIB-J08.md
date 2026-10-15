# LIB-J08 · open-telemetry/semantic-conventions-genai (OpenTelemetry generative AI semantic conventions repository)

생성형 AI 클라이언트의 스팬, 메트릭, 이벤트를 정의하는 OpenTelemetry 시맨틱 컨벤션 저장소이며, MCP와 OpenAI 같은 공급자별 컨벤션을 포함하고 core 규격을 확장한다고 설명한다. 용어 정의와 구현 참조 자료가 함께 들어 있다.

## 출처와 확인 수준

- 공식 출처: [open-telemetry/semantic-conventions-genai (OpenTelemetry generative AI semantic conventions repository)](https://github.com/open-telemetry/semantic-conventions-genai)
- 유형: 도구 문서 · 2026년 · OpenTelemetry 시맨틱 컨벤션 저장소 · `official_publication`
- 저자·발행: OpenTelemetry 프로젝트 (open-telemetry/semantic-conventions-genai 저장소)
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 저장소는 생성형 AI 스팬, 메트릭, 이벤트 정의와 MCP 컨벤션을 포함한다고 페이지가 밝힌다(페이지 확인).
- core 시맨틱 컨벤션을 확장하며, 저장소 생성 도구로 의존성을 관리한다고 설명한다(페이지 확인).

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이의 도구 호출 스팬과 메트릭 속성 이름을 이 저장소의 MCP 항목에 맞춰 두면 외부 관측 도구와 바로 연결된다.
- 메시지 본문 기록 여부를 스팬 속성과 분리해 설정하고, 본문은 PII 마스킹 파이프라인을 거친 뒤에만 내보내도록 설계한다.
- 에이전트 스팬 이름(invoke_agent, execute_tool 등)은 구현 전에 이 저장소의 정의 파일에서 직접 확인한 뒤 고정한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

저장소 README 수준만 확인했다. 안정성 상태(Development 또는 Stable)와 에이전트 스팬 이름은 페이지에서 확인하지 못했다. 공식 opentelemetry.io 명세 페이지는 이동 안내 또는 500 오류로 열리지 않았다. 페이지에 발행일이 없어 연도 2026은 조회 시점 기준 기입이다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
