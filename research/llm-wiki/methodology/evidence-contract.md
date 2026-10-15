# 시험 실행과 근거의 연결 규칙

2026-10-15 위키 보강안이다. 현재 product API나 수집기의 필수 필드가 추가됐다는 뜻은 아니다. 기존 [검증 방법](evidence-methodology.md)을 실행 기록과 최신성 관리로 구체화한다. 관련 구현 작업은 DEV-45다.

## 실행 한 건의 최소 필드

| 구분 | 필요한 값 |
| --- | --- |
| 실행 | 고유 run_id, 시작·종료·시간대, 명령 종류, 종료 코드, 검사/성공/실패/미확인 수 |
| 판본 | source commit, image digest, 정책·데이터·계약 hash, SDK/MCP/하네스 판본 |
| 범위 | 요구/정책/DEV ID, 정상·음성·경계·장애·경쟁·복구, 실제/격리 환경, managed 활성 여부 |
| 예상 | 정확한 decision/policy ID, 시도/실행/업무 결과, 외부 효과 수·원복 조건 |
| 관측 | MCP request ID, decision ID, dispatch intent, endpoint event ID, 독립 효과와 시각 |
| 증거 | 저장 경로, 원본 byte SHA-256, 비밀 제거 projection SHA-256와 변환 규칙, 읽기/실행 수준 |

시험 이름은 실행 ID가 아니다. 재실행은 새 run_id로 남기고 채점 항목이 어떤 실행을 선택했는지 명시한다. 실패 원인·환경 수정을 보존하며 마지막 rc=0을 모든 판본에 적용하지 않는다. 일회성 평가에서 사용한 기능과 미지원 항목도 기록한다.

## 성공을 구분하는 기준

1. 연결/health 정상: 프로토콜·서비스 응답이 온 것.
2. 정책 허용: 요청이 정책을 통과한 것.
3. 도구 업무 성공: quota·인증·업무 오류 없이 원하는 작업이 끝난 것.
4. 독립 효과 확인: 공급자/수신처의 상태·효과와 호출을 대조한 것.

Context7의 할당량 오류는 정책 허용과 제공자 업무 실패를 함께 기록한다. 모델 턴의 `is_error=false`를 도구 성공으로 바꾸지 않는다. 응답 보류는 이미 실행된 작업을 취소하지 않는다. 답을 잃은 쓰기는 불확실로 남기며 자동 재시도하지 않는다.

## 원본과 정규화 해시

원본은 byte SHA로 보존하고 다른 바이트로 덮어쓰지 않는다. Git의 text/eol 정규화 대상인 분석 Markdown/JSON에는 canonical LF SHA와 기준 commit을 별도로 기록한다. 원본 SHA와 정규화 SHA의 종류·대상·변환을 명시한다. 해시 불일치는 먼저 줄바꿈·판본·경로·변환을 조사하며 곧바로 변조라고 부르지 않는다.

코드 근거가 바뀌면 과거 실행은 역사적 증거로 남기고 현재 판본의 유효성을 `재검수`로 표시한다. 과거 실행 파일의 hash를 새 소스로 덮어쓴 뒤 옛 통과 결과를 재사용하지 않는다. 구조·행 번호 갱신은 실행 검증과 분리한다.

## 모델·MCP·개인정보

응답이 보고한 모델과 요청 모델을 구분한다. 자체 신고 하네스 이름·clientInfo·trace 정보는 인증 신원이 아니다. trace를 인증이나 권한 확대에 사용하지 않는다. [OpenTelemetry MCP 관례](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/mcp.md)는 Development 상태이므로 적용 판본을 고정한다. 원시 인자·응답·토큰·로그인 코드·OAuth state는 기본 수집 대상으로 삼지 않는다. 합성 식별자·hash·비밀 제거 projection과 제한된 원본 보관을 사용한다.

run_id·소스·빌더·산출물의 연결에는 [SLSA provenance](https://slsa.dev/spec/v1.2/build-provenance)를 참고한다. 이는 프로젝트 증거 형식 제안이며 인증·표준 준수 판정이 아니다.
