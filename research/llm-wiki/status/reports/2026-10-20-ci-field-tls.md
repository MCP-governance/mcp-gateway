# 2026-10-20 CI field TLS 및 위키 검사

- 작업자: Codex luna
- 코드 기준: `10/20-ci-field-tls`, 시작 `c002fbd5fcf5f928e5ad68c57fa05edb1f76b1a6`, 시작 clean.
- 시작 근거: DEV-10, D-124 사설 CA, D-129 브라우저 콘솔과 하네스 경로 분리.
- 해결할 문제와 완료 조건: 현장 CI의 TLS·CA 전달과 직접 Compose 정리 환경을 맞추고, Git에 넣지 않는 `local-sources/` 누락은 CI에서만 경고 처리한다.

## 결과

`verify.yml`에서 `field ca`로 공개 루트와 지문을 가져와 키트 setup, Claude/Codex 환경, curl, Git HTTPS 검증에 전달했다. 하네스·키트는 `https://127.0.0.1`(호스트 443)을 사용하고 Caddy TLS 주소는 컨테이너 포트 8080으로 설정했다. 직접 실행하는 정리 명령에도 `FIELD_TLS_ADDRESSES`를 넣었다.

`check_wiki.py` 기본 모드는 엄격하게 유지했다. GitHub Actions에서만 `--ci-ignored-local-sources`를 전달해 `research/llm-wiki/local-sources/`의 없는 경로를 경고로 기록한다. 존재하는 파일의 SHA-256 검사와 그 밖의 누락·불일치 검사는 계속 오류다. `local-sources/`가 위키 전용 `.gitignore` 대상임을 `git check-ignore`로 확인했다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| Python 구문 | `python -m py_compile research/llm-wiki/tools/check_wiki.py` | 통과 | 로컬 실행 |
| 셸 구문 | 수정한 세 YAML run 블록과 정리 명령에 `bash -n` | 통과 | 로컬 실행 |
| 위키 기본 검사 | `python research/llm-wiki/tools/check_wiki.py` | 실패: 무시 대상 누락 파일 29건 | 로컬 재현 |
| 위키 CI 모드 | `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 종료 코드 0, 오류 0, 경고 119건 | 누락 local-sources 경로 경고 |
| 패치 공백 | `git diff --check` | 통과 | 로컬 실행 |
| YAML 파싱 | PyYAML, Ruby YAML, Node YAML 모듈 확인 | 미실행: 사용 가능한 파서 없음 | 환경 제약 |
| GitHub Actions / 스택·실제 하네스 | 실제 워크플로 실행 | 미실행 | GitHub 재실행 필요 |

## 실패·미완료·한계

원격 HEAD 조회는 현재 네트워크에서 `github.com:443` 연결 실패로 확인하지 못했다. 현재 브랜치의 upstream 표시는 `origin/main`이다. YAML 파서는 설치되어 있지 않아 파싱을 수행하지 못했다. GitHub Actions에서 전체 두 워크플로가 실제로 통과하는지는 아직 확인하지 않았다. 기본 위키 검사는 로컬 전용 원본 29개가 없어 계속 실패하며, CI 모드는 이를 숨기지 않고 경고로 남긴다. `git add`는 `.git/index.lock` 생성 권한 거부로 실패해 커밋하지 못했다. 현재 실행 환경에서 `.git`은 읽기 전용이다.

## 다음 작업

DEV-10: GitHub에서 `full_stack_lab 검증`과 `Research Markdown and collaboration console`을 재실행하고, TLS 키트·하네스·Git 로그인과 위키 검사 결과를 확인한다.

## 사용자에게 필요한 입력

없음
