---
date: 2026-10-15
scope: MINT 의존성 Presidio(HTTP/REST), Gitleaks(C 라이브러리 바인딩)의 사용 경계와 장애 안전성
---

# Presidio + Gitleaks 의존성 심층 분석

## 요약

MINT는 도구 결과의 민감 정보 마스킹에 두 개의 검사기를 연쇄한다:
- **Presidio Analyzer/Anonymizer**: HTTP REST로 PII(한국어 주민번호, 휴대전화, 계좌, 자격증, 비밀번호 라벨) 감지·마스킹.
- **Gitleaks**: C 라이브러리(`libmcpgw_gitleaks.so`)로 발급자 접두 토큰(AWS, GitHub, API key 등) 감지.

분석 결과: 우리 호출 방식에서 놓칠 수 있는 입력은 *인코딩 + 분할* 조합이고, 오류 시 fail-closed(거부)를 보장하며, 오프셋 불일치 위험은 낮지만 특정 조건에서는 검증 필요하다. Gitleaks 단독은 한국어 비밀번호 3/27 (11%)만 잡으므로 Presidio 의존성이 높다.

**판정**: L2~L3 (소스 확인·경로 추적 완료, L4 재현 설계 제시).

## 고정 정보

| 항목 | 값 |
| --- | --- |
| 저장소 | `/mnt/c/Users/bobysg/bob/프로젝트/ref-src/presidio` (태그 2.2.364) |
| Presidio commit | `779dbd286d5ef4d1fbe2514275fb1bce358f2417` (태그 2.2.364, 메인 검토에서 정정) |
| 라이선스 | MIT (LICENSE 경로: `presidio/LICENSE`) |
| 주요 파일(Presidio) | `presidio-analyzer/app.py:67-110` (analyze 엔드포인트 요청 검증), `analyzer_engine.py:35-100` (엔진 초기화), `batch_analyzer_engine.py` (배치 처리) |
| 저장소 | `/mnt/c/Users/bobysg/bob/프로젝트/ref-src/gitleaks` (v8.30.1) |
| Gitleaks commit | `83d9cd684c87d95d656c1458ef04895a7f1cbd8e` (태그 v8.30.1, 메인 검토에서 정정) |
| 라이선스 | MIT (LICENSE 경로: `gitleaks/LICENSE`) |
| 주요 파일(Gitleaks) | `detect/detect.go:114-150` (NewDetector, NewDetectorContext), `cmd/detect.go:43-100` (DetectSource 호출), main.go는 MINT 내부(gateway/native/gitleaks/main.go) |
| MINT 호출자 | `full_stack_lab/gateway/app/privacy.py:117-171` (mask_text, mask_payload), `secret_scan.py:73-86` (labels, timeout) |
| MINT Go 바인딩 | `full_stack_lab/gateway/native/gitleaks/main.go:68-125` (mcpgw_gitleaks_scan, mcpgw_gitleaks_free) |

## 경로 추적

### Presidio Analyzer HTTP 호출

| 단계 | 함수/경로:행 | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| **입구** | `privacy.py:117-126` `analyze()` | 호출: `text` 길이(MIN_CHARS 6), 언어 고정 "en" | <6 문자 → 빈 목록 반환(통과) |
| **HTTP 요청** | `privacy.py:122-127` `_client().post(ANALYZER + "/analyze", json={...})` | 세마포(2 동시), TIMEOUT 20s | HTTPError/timeout → `InspectionUnavailable` (거부) |
| **요청 필드 검증** | 요청 JSON: `text`, `language`, `score_threshold: 0.6`, `entities: ENTITIES`, `ad_hoc_recognizers: RECOGNIZERS` | 분석기:app.py:71-83 `AnalyzerRequest(request.get_json())`, 언어 검증 | 언어 미지원 → HTTP 400 |
| **응답 검증** | `privacy.py:128-141` 응답 JSON 스키마 검증 | `list[dict]`, 각 항목: `entity_type(str)`, `start/end(int, 범위 확인)`, `score(0~1)` | 응답 형식 오류 → `InspectionUnavailable` (거부) |
| **Luhn 필터** | `privacy.py:145-147` 카드 번호만 Luhn 체크 | 정규식 `\D` 제거 후 Luhn 검증 | 실패 → 결과에서 제외 |
| **무시 훅** | `privacy.py:148-149` `ignore(entity_type, matched_value)` | 호출자 제공 함수 | true → 결과 제외 |
| **익명화** | `privacy.py:158-164` `anonymizer POST /anonymize` | 분석 결과·원본 텍스트 전송, 타임아웃 동일 | HTTPError/JSON 오류 → `InspectionUnavailable` (거부) |
| **익명화 검증** | `privacy.py:165-167` 마스킹 결과 검증 | `isinstance(masked, str)`, 각 감지값이 여전히 원본에 있는지 확인 | 검증 실패 → `InspectionUnavailable` (거부) |

### Gitleaks C 라이브러리 호출

| 단계 | 함수/경로:행 | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| **입구** | `secret_scan.py:73-87` `labels(text)` | 길이 <6 → 빈 목록 | 통과 |
| **전처리** | `secret_scan.py:59-64` `scan_text(text)` | URL 쿼리 값 분리(`parse_qsl`), 개행으로 연결 | 정규식 오류 → 예외 → `InspectionUnavailable` (거부) |
| **바이트 변환** | `secret_scan.py:77` `encode()` | UTF-8 인코딩, 크기 검증(1GB 초과 거부) | OS 오류 → 예외 (거부) |
| **세마포 획득** | `secret_scan.py:78` `_slots.acquire()` | Semaphore(4), 동시 4개 스캔 | 미사용(대기만 함) |
| **스레드 생성** | `secret_scan.py:81-82` `asyncio.ensure_future(asyncio.to_thread(rule_ids, data))` | ctypes 호출, GIL 해제 | 스레드 생성 실패 → 예외 (거부) |
| **타임아웃** | `secret_scan.py:83` `asyncio.wait_for(..., timeout=5)` | 5초 제한, `shield()` 로 취소 방지 | 초과 → `TimeoutError` (거부) |
| **Go 함수 호출** | `main.go:108-118` `mcpgw_gitleaks_scan(data *C.char, size C.longlong)` | C 메모리 안전 검증(크기 1GB 초과 거부) | 입력 오류 → `{"rules":[],"error":"invalid input"}` |
| **규칙 로드** | `main.go:74-76` `setup.Do(load)` 한 번만 실행 | 기본 설정 로드, viper 파싱 | 오류 → `{"error": "..."}` JSON 응답 |
| **스캔 실행** | `main.go:78-90` `detector.DetectSource(ctx, &sources.File{...})` | 컨텍스트 타임아웃 5s(Go 레벨), 결과 누적 | 타임아웃 → `context.DeadlineExceeded()` → `{"error": "..."}` |
| **JSON 응답 검증** | `secret_scan.py:85-87` 응답 파싱 | ctypes로 C 메모리 읽고 해제, JSON 디코딩 | 오류 → 예외 (거부) |
| **규칙 ID 목록** | `secret_scan.py:86` 정렬된 규칙 목록 | `gitleaks:` 접두 추가 | 미실패 |

## 실패·경합·복구 결정표

| 조건 | 코드 동작(근거) | fail-open/closed | 미확인 |
| --- | --- | --- | --- |
| **Presidio timeout** | `privacy.py:142` `httpx.HTTPError` → `InspectionUnavailable` 예외 발생, 호출자가 거부 | **closed** | 실제 10s 초과 응답은 미재현 |
| **Presidio 악형식 응답** | `privacy.py:140-141` 스키마 검증 실패 → `InspectionUnavailable` | **closed** | 정의되지 않은 필드는 무시(forward-compat) |
| **익명화 오프셋 불일치** | `privacy.py:166` 감지값이 마스킹 결과에 여전히 있으면 → `InspectionUnavailable` | **closed** | 오프셋 계산 오류 시나리오(아래 참조) |
| **Gitleaks 타임아웃** | `secret_scan.py:84` `asyncio.TimeoutError` → `InspectionUnavailable` | **closed** | 5초는 고정, 확장 입력 미재현 |
| **Gitleaks 타임아웃 후 진행 호출** | `secret_scan.py:68-71` callback `_finished`가 세마포 반환, 스캔은 백그라운드에서 계속 실행 | **불확실** | 스캔 결과가 다음 호출 결과에 섞일 가능성(아래 참조) |
| **Gitleaks 규칙 로드 실패** | `main.go:75-76` `setupFail != nil` → `{"error": "..."}` JSON, Python에서 파싱 오류 → `InspectionUnavailable` | **closed** | 첫 호출 직후 보장(once 패턴) |
| **Go 메모리 할당 실패** | `main.go:117` `C.CString` 실패 → nil 반환, Python `ctypes.string_at(None)` → 세그먼트 폴트 | **open** ⚠️ | C 수준 오류 처리 부재 |
| **Gitleaks Go 패닉** | `main.go:70-72` recover 문으로 포착, `{"error": "panic: ..."}` JSON 응답 | **closed** | Go 런타임 오류(메모리 소진)는 커버하지 않음 |
| **다중 worker 동시 세마포** | `secret_scan.py:81-82` `ensure_future` + `shield` → 취소 방지, 슬롯은 완료 시 반환 | **불확실** | 4개 동시 스캔 중 1개 timeout 시 나머지 3개와의 순서 보장 미확인 |
| **직원 토큰 회수 후 진행 호출** | Presidio/Gitleaks는 토큰을 사용하지 않음(HTTP 기본/무인증) | N/A | 구조상 불가능 |
| **Presidio HTTP 연결 재사용** | `privacy.py:114` `connections.shared("presidio", ...)` httpx AsyncClient 재사용 | **open** | 연결 풀 고갈·keep-alive timeout 미처리 |

**중대 미확인**: Gitleaks 타임아웃 후 백그라운드 스캔이 계속 실행되면서 ctypes 호출의 메모리 레이아웃이 변할 경우 oob 읽기 위험(Go GC와 Python 메모리 관리의 경쟁).

## Upstream 시험

### Presidio 공식 시험

- `presidio-analyzer/e2e-tests/tests/test_api_analyzer.py`: analyze 엔드포인트 요청·응답, 언어 검증, 점수 임계값, 인식기 로드.
- `test_api_anonymizer.py`: 익명화 API, 겹치는 구간 처리(범위 정렬 후 순차 처리).
- 누락: 대용량 입력(>1MB), 타임아웃 재현, 악형식 JSON 응답.

### Gitleaks 공식 시험

- `detect/detect_test.go`: 검사기 생성, 규칙 로드, 여러 encoding(base64, hex), archive 탐색, timeout(Go 컨텍스트).
- MINT 추가 확인: `tests/secret_engine_parity_check.py` 는 stdin 바이너리와 C 라이브러리를 비교(31/31 규칙 일치).
- 누락: C 라이브러리의 메모리 누수, 다중 worker 경쟁, 매우 큰 입력(>100MB).

## MINT 대조

| 우리 코드 | 참고한 상위 프로젝트 | 가져올 것 / 보류 / 이유 |
| --- | --- | --- |
| `privacy.py:128-141` 응답 검증 | Presidio 응답은 RecognizerResult 타입(관련 문서에서 확인 미비) | **가져올 것**: Presidio는 정의되지 않은 필드를 반환할 수 있으므로 화이트리스트 필드만 추출(현재 doing) |
| `secret_scan.py:81-83` 타임아웃 구조 | Gitleaks detect.go:80 `context.WithTimeout`은 동일하지만 Python asyncio.shield 추가 | **이미 있음**: 우리가 shield로 스캔 취소 방지(upstream은 ctx 취소로 스캔 중단) |
| `privacy.py:114` 클라이언트 풀 | Presidio 측은 FastAPI(uvicorn)로 여러 워커 실행, 연결 재사용 가정 | **보류**: 우리 세마포는 동시성을 제한하지만 연결 풀 고갈(64+ 동시 요청) 미처리, 모니터링 필요 |
| `main.go:117` C 메모리 할당 | Gitleaks는 malloc이 실패하면 nil 반환, 우리가 검증하지 않음 | **가져올 것**: C.CString 실패 검증 추가, 또는 Go에서 에러 처리 추가 |
| `privacy.py:165-167` 익명화 검증 | Presidio anonymizer는 offset 계산을 자체적으로 수행, 중첩 구간 정렬 후 순차 처리 | **이미 있음**: 우리가 "원본 값이 여전히 있는가" 검증 + 점수 필터로 이중 검증 |

### 백로그 연결

- **DEV-41** (Presidio 신뢰 경계): 요청 타임아웃 모니터링, 응답 스키마 비교.
- **DEV-43** (Gitleaks 신뢰 경계): C 메모리 할당 오류, 다중 worker 백그라운드 스캔 경쟁.
- **DEV-46** (마스킹 효과 검증): 오프셋 불일치 시나리오 재현.

## 목표 기능 재설계 시사점

### (1) 놓칠 수 있는 입력

우리 호출에서 감지 누락의 원인 3가지:

1. **인코딩 후 분할**: Presidio는 plain UTF-8만 받음. URL(`?api_key=...`) 내의 인코딩된 토큰은 `secret_scan.py:62-64`에서 `parse_qsl` 분해만 함. base64나 hex는 Gitleaks `MaxDecodeDepth: 5`에서 최대 5단계 복호화하므로 다중 레이어는 누락.
   - 예: `base64(base64(token))` → Gitleaks는 1단계만 복호화.
   - 우리 정책: 입력 단계(MCP SDK 자체 또는 gateway 인자)에서 제한, 또는 Gitleaks decode depth 늘림(성능 트레이드).

2. **분할된 비밀**: Presidio 인식기는 "비밀번호는 ..." 패턴을 찾지만, 비밀이 여러 줄에 분산되면 누락.
   - 예: `password = \n "abc" + \n "def"` → Gitleaks는 조합을 보지 않음.
   - 우리 정책: 사전 인코딩/서식 정규화(현재 미시행).

3. **한국어 PII + 특수 문자**: `privacy.py:45-94`의 한국어 인식기는 정규식 기반(경계 `(?<![0-9A-Za-z])` 사용). 문자 변환(유니코드 정규화 미실행)에 따라 누락.
   - 예: 전각 숫자 "０１２３" (U+FF10–19) vs 반각 "0123" (U+0030–39).
   - 우리 정책: 입력 정규화(NFC), 또는 정규식에 동등 문자 클래스 추가.

**결론**: 현 설계는 "plain, 단일 인코딩, 라틴 경계" 가정. 명령형 사용자 경고 또는 정책 엔진에서 높은 위험 입력 차단 필요.

### (2) 오류·timeout 시 fail-closed 검증

모든 경로에서 오류 → `InspectionUnavailable` 예외 → 상위에서 결과 거부:

- `gateway/app/core.py` (미확인, 호출자 관찰 필요): `mask_payload` 또는 `mask_text` 예외 → 결과를 보류하거나 거부.
- `secret_scan.py:85` timeout → `InspectionUnavailable` → 호출자 책임.

**확인 필요**: 호출자가 예외를 처리하지 않으면 예외 전파 → 요청 500 오류 → 결과 폐기(API 응답). 이것이 fail-closed인지 호출자 코드 확인 필수.

**근거**: 
- `privacy.py:142-143`: `raise InspectionUnavailable(...) from exc`
- `secret_scan.py:84-85`: `raise InspectionUnavailable(...) from exc`

### (3) 오프셋 불일치로 마스킹 오류

Presidio anonymizer의 offset 계산:

- **입력**: 분석 결과 list `[{start: 10, end: 20}, {start: 25, end: 35}]` (정렬 가정).
- **익명화**: 각 구간을 `[REDACTED]` 9글자로 치환.
- **위험**: 
  1. 겹치는 구간 미정렬 → 뒤쪽 offset이 틀림.
  2. UTF-8 멀티바이트: "한글"(2글자, 6바이트)의 offset이 바이트 위치가 아닌 문자 위치 가정 → 치환 후 길이 변화.
  3. Presidio 응답 offset의 정의 불명 → 확인 필수.

**현재 우리 방어**: `privacy.py:165-167` 마스킹 후 원본 값이 여전히 있으면 거부(보수적, false positive 주의).

**미확인**: Presidio 소스에서 offset 정의 명시 필요(바이트 vs 문자 vs UTF-16 code unit).

**재현 제안**:
```python
# 테스트: 한글 + 겹치는 구간
text = "이메일 a@b.c와 010-0000-1234 계좌 110-123456789입니다"
# analyzer 응답: 이메일과 휴대전화 오프셋을 잘못 정렬하면
# anonymizer가 "이메일 [REDACTED]과 010" 같은 결과 반환
```

## 오프셋 검증 로직 분석

`privacy.py:165-167`:
```python
if not isinstance(masked, str) or any(text[f["start"]:f["end"]] in masked for f in findings):
    raise ValueError("anonymizer left a detected value in its output")
```

이 로직은:
- **장점**: 모든 감지값이 출력에서 완전히 제거되었는지 확인.
- **한계**: 
  1. 부분 문자열 일치(false positive): "010"이 "연락처010-1234" 정상 텍스트에도 있으면 오탐.
  2. 인코딩 변환: UTF-8 정규화 후 비교하지 않음(현재 UTF-8).
  3. 정확한 offset 검증 아님: 원본 offset이 정확한지 판단 불가.

**제안**: offset 검증 강화.
```python
# 정확한 비교: (start, end, entity_type) 조합 검증
for f in findings:
    original_span = text[f["start"]:f["end"]]
    if original_span in masked:  # 현재 방식
        # 추가: 같은 위치에 같은 길이의 문자가 남아있는지 확인
        # 또는 offset을 익명화 함수에 전달받아 역검증
        raise ValueError(...)
```

## 남은 미독 범위와 L4 재현 제안

### Presidio 미확인 구간

1. **app.py:100–150**: 배치 처리 로직(반복 호출 시 상태 누적 여부).
2. **anonymizer/anonymizer_engine.py**: offset 정렬·병합 알고리즘.
3. **네트워크 장애**: 분석기 컨테이너 다운·재시작 후 결과 캐시 미무효화.

### Gitleaks 미확인 구간

1. **detect/codec**: base64, hex, gzip 복호화 깊이와 순서.
2. **sources/reader.go**: 아카이브 탐색(tar.gz 내 tar.gz 중첩).
3. **Go GC와 ctypes 메모리**: 백그라운드 스캔 중 메모리 레이아웃 변화.

### L4 재현 테스트 계획

#### (1) 오프셋 불일치 재현

```python
# 입력
text = "Korean RRN: 990101-3123456 and password=abc123def456"
# 기대: 두 값 모두 마스킹
# 위험: offset 정렬 미흡 시 일부만 마스킹

from full_stack_lab.gateway.app import privacy
result, entities = await privacy.mask_text(text)
assert "990101-3123456" not in result
assert "abc123def456" not in result
```

#### (2) 다중 인코딩 + Gitleaks 타임아웃

```python
# 입력: base64로 여러 번 인코딩된 토큰
import base64
secret = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # GitHub token
encoded = secret
for _ in range(6):
    encoded = base64.b64encode(encoded.encode()).decode()
text = f"backup={encoded}"

# 기대: Gitleaks decode depth 5 제한으로 누락
from full_stack_lab.gateway.app import secret_scan
labels = await secret_scan.labels(text)
# depth 6은 못 잡음, 또는 타임아웃 위험
```

#### (3) 한국어 PII + 유니코드 정규화

```python
# 입력: 전각 vs 반각 혼합
text = "주민번호：９９０１０１－３１２３４５６입니다"  # 전각 숫자 + 한글 음절
# 기대: 마스킹 성공
from full_stack_lab.gateway.app import privacy
result, entities = await privacy.mask_text(text)
assert "마스킹" in str(result)  # 현재: 실패할 수 있음 (경계 문제)
```

#### (4) Presidio HTTP 타임아웃 + 동시 요청

```python
# 환경: Presidio 컨테이너 느림(네트워크 지연 >20s)
# 입력: 100개 동시 요청, 세마포 2개 제한
import asyncio
texts = [f"Text {i}: email@example.com" for i in range(100)]
results = []
try:
    results = await asyncio.gather(*[privacy.mask_text(t) for t in texts])
except privacy.InspectionUnavailable:
    print("일부 요청 timeout → 모두 거부됨(fail-closed 확인)")
```

#### (5) Gitleaks 세마포 경쟁 + 백그라운드 스캔

```python
# 입력: 4개 동시 스캔 + 5번째 스캔의 타임아웃
import asyncio
from full_stack_lab.gateway.app import secret_scan

async def timeout_test():
    futures = []
    for i in range(5):
        # 처음 4개: 정상 입력, 5번째: 초대형 입력(timeout 유도)
        data = "a" * (1000 if i < 4 else 100_000_000)
        futures.append(secret_scan.labels(data))
    
    try:
        results = await asyncio.gather(*futures, return_exceptions=True)
        # 5번째가 timeout 후, 백그라운드 스캔이 여전히 실행되는가?
        # 세마포가 올바르게 반환되는가? (다음 호출이 대기하지 않는가?)
    except Exception as e:
        print(f"예외: {e}")
```

### 재현 환경

- **Presidio**: 공식 Docker 이미지 + 의도적 지연(tc/iptables로 네트워크 latency 추가).
- **Gitleaks**: 공식 v8.30.1 바이너리 + C 라이브러리 컴파일(MINT 기존 빌드).
- **검증 도구**: `tests/secret_engine_parity_check.py` 확장, 새 unittest 추가.
- **모니터링**: 메모리 프로필(tracemalloc), 동시성 로그(asyncio debug mode).

## 정정

기존 `docs/ai/BENCHMARK_presidio.md`의 이전 결론:
- "Presidio는 언어별 전용 NLP 모델 로드" → **정정**: v2.2.364에서는 configurable이며 기본값이 영어 + 정규식. 우리는 정규식만 로드(`nlp-small.yaml`).
- "토큰은 Presidio로 마스킹 불가" → **정정**: 우리가 `CREDENTIAL` 인식기 추가해 마스킹 가능(privacy.py:87-94).

기존 `2026-10-15-inspection-corpus.md`:
- 한국어 비밀번호 재현율 27/27 (100%) → **근거**: Presidio 인식기(정규식) + 우리 커스텀 라벨(한국어), Gitleaks 단독 3/27 (11%)은 정책 우회 규칙만 해당.

## 미확인·미검증

- Presidio anonymizer의 정확한 offset 정의(바이트? 문자? UTF-16 code unit?).
- Gitleaks Go GC와 ctypes 메모리 레이아웃 동시성(Linux malloc arena 단편화).
- Presidio 분석기 다중 워커·Redis 캐시 시나리오(현재 단일 인스턴스만 테스트).
- 실제 하네스·PJ1에서의 오류율·지연(로컬 이미지만 확인).
