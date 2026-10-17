# LIB-K03 · Open Policy Agent — Decision Logs (OPA v1.21.2 문서)

OPA가 정책 질의 결과를 결정 로그 이벤트로 원격 서비스·사용자 플러그인·콘솔에 내보내는 방식을 설명한다. 이벤트 필드, 민감 데이터 마스킹(`data.system.log.mask`), 업로드 크기 제한과 재시도, 규칙 레이블 기록을 다룬다.

## 출처와 확인 수준

- 공식 출처: [Open Policy Agent — Decision Logs (OPA v1.21.2 문서)](https://www.openpolicyagent.org/docs/management-decision-logs)
- 관련 출처: <https://www.openpolicyagent.org/docs/policy-language>
- 유형: 공식 문서 · 2026년 · OPA 공식 문서 (OPA v1.21.2, 릴리스 2026-10-12) · `official_publication`
- 저자·발행: Open Policy Agent 프로젝트
- 판본: 문서 시점 OPA v1.21.2. 저장소 full_stack_lab/compose.yaml:67은 OPA 1.20.2를 `--set=decision_logs.console=true`로 실행한다. 같은 1.20.2 이미지로 일회성 시험을 했다(`analysis/drive-curation/opa-labels-probe/README.md`)
- 확인일: 2026-10-17 / `page_text_read` — 공식 페이지 본문을 읽었다(절 단위 정독 아님). 읽은 범위: Decision Logs 페이지 본문(필드 표, 업로드, 로컬 로그, 마스킹), Policy Language 페이지의 Metadata labels 절, 저장소 compose 파일 67행.
- 요약 검토: 출처 페이지 본문과 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 이벤트에는 decision_id, bundles의 revision, path, input, result, requested_by, timestamp와 W3C trace-context 형식의 trace_id·span_id가 있어 호출과 정책 판단을 상관시킬 수 있다.
- `data.system.log.mask`가 JSON Pointer 집합을 반환하면 해당 필드를 이벤트에서 지우고 `erased`·`masked`에 경로를 남긴다. 포인터는 /input, /result, /nd_builtin_cache로 시작해야 한다.
- 필드 표에 따르면 평가된 규칙의 annotation id는 `ids`에, 병합된 레이블은 `rule_labels`에 기록되고, 메타데이터 문서는 `labels` 주석이 결정 로그에 기록된다고 설명한다. 서버가 2xx가 아닌 응답을 주면 마지막 묶음을 큐에 되돌려 지수 백오프로 다시 올린다.
- 저장소와 같은 OPA 1.20.2에서 일회성 서버로 확인한 결과, 규칙 `labels`는 평가된(발화한) 규칙의 레이블로 `rule_labels`에 남고 `id` 주석 키는 오류 없이 받아들여지지만 `ids`로는 남지 않았다(우리 시험이며 문서의 서술이 아니다).

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-38 | 경보 검증·자동 대응 |
| POL-42 | 경보 검증·자동 대응 |
| POL-01~POL-50 | 정책 번호 체계 표류 |

## 우리 솔루션 개발에 사용할 곳

- **POL-38**: 호출·권한 변경 이력에서 비밀과 개인정보를 제외하는 마스킹을 정책(mask 규칙)으로 선언하고, 지워진 경로가 `erased`로 남는지 시험한다.
- **POL-42**: 경보 검증 시나리오에서 '설정 변경 뒤에도 신규 도구·미승인 연결 시도가 결정 이벤트로 남는가'를 decision_id·path 기준으로 관찰한다.
- **정책 번호 체계 표류**: 규칙에 `labels`(예: 엑셀 POL 번호, 런타임 PAC 번호)를 달면 어느 번호의 규칙이 평가됐는지 결정 로그의 `rule_labels`로 볼 수 있다(설계 제안). OPA 1.20.2에서 `rule_labels`가 동작함을 일회성 시험으로 확인했다. 레이블은 규칙이 발화할 때만 남으므로 차단 사유의 정책 번호 기록에는 쓸 수 있으나 '검사했고 통과했다'는 증거는 아니다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

결정 로그 문서 본문(필드 표·마스킹·업로드 규칙)을 읽었다. `ids` 필드가 도입된 OPA 판본과 annotation `id` 키의 정의는 확인하지 못했다(필드 표 설명에만 근거, 1.20.2에서는 `id`가 `ids`로 남지 않았고 1.21.x는 시험하지 않았다). 저장소는 콘솔 결정 로그를 켜지만 로그 내용·보관·마스킹 정책은 읽지 않았다.

OPA 저장소 LICENSE는 Apache License 2.0이다. 문서 페이지 자체의 별도 이용 조건은 확인하지 않았다. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
