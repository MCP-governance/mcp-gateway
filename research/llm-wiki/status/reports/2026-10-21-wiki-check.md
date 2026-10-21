# 위키 검사 실행 결과와 경고 분류 (10-21)

- 기준: `origin/main` a52d661, 브랜치 `10/21-wiki-check`, 실행 2026-10-21 12:46 KST
- 범위: 도구 4개를 실행하고 결과를 분류했다. 제품 코드와 위키 본문은 고치지 않았다.
- 원시 출력은 세션 scratchpad `wikicheck/`에 보관했다(`capture_status.out`, `build_wiki.out`, `check_wiki.out`, `check_wiki_ci.out`).

## 1. 실행 명령

| # | 명령 | 시작 | 종료 | 종료 코드 | 결과 |
|---|------|------|------|-----------|------|
| 1 | `python research/llm-wiki/tools/capture_status.py` | 12:46:12 | 12:46:12 | 0 | 스냅샷 기록, `scope: local-code-only` |
| 2 | `python research/llm-wiki/tools/build_wiki.py` | 12:46:13 | 12:46:13 | 0 | 마크다운 607쪽 생성 |
| 3 | `python research/llm-wiki/tools/check_wiki.py` | 12:46:13 | 12:46:19 | **1** | `ok: false`, 오류 32, 경고 0 |
| 4 | `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 12:46:19 | 12:46:20 | **1** | `ok: false`, 오류 3, 경고 119 |

오류가 0건이 아니다. 두 검사 모두 종료 코드 1로 실패했다. 실패를 통과로 적지 않는다.

## 2. 오류·경고 분류

| 분류 | 기본 실행 오류 (32) | CI 옵션 오류 (3) | CI 옵션 경고 (119) |
|------|---------------------|------------------|--------------------|
| (A) 로컬 원본 경로 (Git 제외) | 29 | 0 | 119 |
| (B) 끊어진 내부 링크 | 1 | 1 | 0 |
| (C) 해시·출처 메타 불일치 | 0 | 0 | 0 |
| (D) 분류 불가 | 2 | 2 | 0 |

**(A) 로컬 원본.** 오류 29건은 전부 `local-sources/compliance/LIB-*/provenance.json`이다(LIB-L05 등 29개 항목). CI 옵션 경고 119건은 `provenance.json` 29, `extracts/` 45, `originals/` 45이며 전부 `research/llm-wiki/local-sources/` 아래다. 작업 트리에 `local-sources/` 디렉터리가 없다(`ls` 확인). 재배포 조건상 의도적으로 제외된 원본이다.

**(B) 끊어진 내부 링크 (전체 목록).**
- `research/llm-wiki/analysis/direction-1020/shadow-and-declaration-limits.md:23`의 `[설계 9장](dev73-local-isolated-run.md)`.
- 대상 파일은 main에 없다. `origin/10/20-dev73-design` 브랜치에만 있다(`git cat-file -e` 확인).
- 고치지 않았다.

**(C).** 해당 없음.

**(D) 분류 불가 2건.**
- `research/llm-wiki/status/reports/2026-10-20-pj1-real-mcp.md:40` `../../analysis/real-env-20261020/install/`
- `research/llm-wiki/status/reports/2026-10-20-pj1-real-mcp.md:84` `../../analysis/real-env-20261020/e13/`
- 두 대상은 디렉터리이고 존재하며 추적 파일이 있다(`git ls-files` 확인). 검사기가 `check_wiki.py` 24행 `path.is_file()`로만 검사해 디렉터리 링크를 오류로 낸 것으로 보인다. 끊어진 링크가 아니므로 (B)로 넣지 않았다. 검사기 오탐 가능성이 높다.

## 3. 최근 main 커밋 신규 문서의 내부 링크

| 커밋 | 신규 문서 | 내부 상대 링크 | 존재 여부 |
|------|-----------|----------------|-----------|
| 8809787 | `research/llm-wiki/status/reports/2026-10-20-litellm-compat.md` | 0 | 해당 없음 (같은 커밋의 설정·코드 파일은 문서가 아님) |
| d3238dc | `research/llm-wiki/status/reports/2026-10-20-pj1-real-mcp.md` | 9 (파일 7, 디렉터리 2) | 9/9 존재 |
| a52d661 (병합, 원본 395c878) | `docs/ai/DECISIONS.md` 1744행 D-157 항목 | 3 | 3/3 존재 |

- D-157 항목의 링크 3개는 `research/llm-wiki/analysis/siem-dedup/README.md`, `full_stack_lab/tests/siem_queue_pg_check.py`, `research/llm-wiki/status/reports/2026-10-20-siem-dedup.md`이다.
- 같은 항목의 외부 https 링크 2개(OCSF, Psycopg)는 범위 밖이라 확인하지 않았다.
- 깨진 내부 링크는 없다. 위 (D) 디렉터리 2건도 실제로는 존재한다.

## 4. 도구가 만든 파일 변경

`git status` 결과 두 파일이 바뀌었다. 둘 다 `capture_status.py`가 만든 스냅샷이다.
- `research/llm-wiki/status/repository-snapshot.json`
- `research/llm-wiki/status/repository-snapshot.md`

내용: `captured_at` 2026-10-21T12:46:12+09:00, `head` a52d661, `branch` 10/21-wiki-check, `status` 빈 목록(작업 트리가 깨끗했음). 이전 스냅샷(10-18, 10/18-remaining-features)을 대체했다.

`build_wiki.py`는 추적 파일을 바꾸지 않았다. `git status --ignored`로도 `research/llm-wiki`에 새 무시 파일이 없음을 확인했다.

## 5. 고치지 않고 남긴 것

- **(B) dev73 링크.** 대상이 미머지 브랜치에 있다. 링크를 고칠지, 설계를 main에 올릴지는 소유자가 정할 일이다.
- **(D) 디렉터리 링크 2건.** 문서는 정상이다. 검사기가 디렉터리를 허용하도록 고쳐야 하지만 도구 수정은 이번 범위 밖이다.
- **(A) 기본 실행 오류 29건.** 원본이 저장소에 없어 `--ci-ignored-local-sources` 없이 실행하면 clean checkout에서 항상 실패한다. CI가 이 옵션을 쓰는지는 확인하지 못했다.

## 6. 실행하지 못한 도구

없음. 네 명령 모두 실행했다.

## 7. 검사기 오탐 수정 (10-21)

- 기준: `origin/main` fd2655f, 브랜치 `10/21-wiki-check-tool`. 위 5절의 (D) 오탐 2건을 고친 기록이다.
- 변경: `tools/check_wiki.py`의 `local_path`에 `link` 인자를 더했다. 본문 링크 검사에서만 켜지며, 대상이 디렉터리이고 `git ls-files`로 추적 파일이 하나 이상 잡히면 존재로 인정한다. 빈 디렉터리와 없는 경로는 계속 오류다. 카탈로그 경로·코드 근거·실험 증거 검사는 그대로 두었다.
- 자체 검사: `tools/check_wiki_link_check.py`. 임시 위키와 임시 Git 저장소에서 `check()`를 돌려 세 경우를 확인한다(존재하는 파일 링크 통과, 추적 파일이 있는 디렉터리 링크 통과, 없는 경로 링크 실패). 수정 전 `check_wiki.py`에 대고 돌리면 디렉터리 경우에서 실패한다. 빈 디렉터리 링크는 수정 후에도 오류로 남는 것을 따로 확인했다.

| 실행 | 명령 | 수정 전 | 수정 후 |
|------|------|---------|---------|
| 기본 | `python research/llm-wiki/tools/check_wiki.py` | 종료 1, 오류 32, 경고 0 | 종료 1, 오류 30, 경고 0 |
| CI 옵션 | `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 종료 1, 오류 3, 경고 119 | 종료 1, 오류 1, 경고 119 |
| 자체 검사 | `python research/llm-wiki/tools/check_wiki_link_check.py` | 해당 없음 | 종료 0, `check_wiki link rule: ok` |

- 줄어든 오류는 정확히 두 건이다: `../../analysis/real-env-20261020/install/`, `../../analysis/real-env-20261020/e13/` (`status/reports/2026-10-20-pj1-real-mcp.md`의 40행, 84행).
- 새로 생긴 오류는 없다. 두 실행의 `counts`와 `warnings` 목록은 수정 전후 같다.
- 남은 오류: 기본 실행은 (A) 로컬 원본 29건과 (B) dev73 링크 1건이다. CI 옵션 실행은 (B) 1건이다.

**CI 옵션 확인 (코드 변경 없음).** `.github/workflows/research-wiki.yml`의 `check` 잡 17행이 `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources`를 실행한다. 옵션을 쓰고 있으므로 Git 밖 로컬 원본 29건은 CI에서 오류가 아니라 경고로 처리된다. 앞선 추정("CI가 항상 29건으로 실패한다")은 틀렸다. 최근 main 실행(run 39540718296)의 실패 원인은 `Missing local file` 3건, 즉 dev73 링크 1건과 디렉터리 오탐 2건이었다. 이번 수정 후에는 dev73 링크 1건만 남으므로 CI는 여전히 실패한다. 워크플로 파일은 고치지 않았다. 자체 검사도 CI에 연결되어 있지 않다.

**남긴 것.**
- (B) dev73 링크(`analysis/direction-1020/shadow-and-declaration-limits.md:23`): 고치지 않았다. 대상이 미머지 브랜치에만 있어 CI 실패의 남은 원인이다. 링크를 고칠지 설계를 main에 올릴지는 소유자 결정이다.
- 자체 검사의 CI 연결: 워크플로 수정이 필요해 보류했다.
- 옵션 사용 시 로컬 원본 경고 119건: 의도된 경고로 유지했다.
