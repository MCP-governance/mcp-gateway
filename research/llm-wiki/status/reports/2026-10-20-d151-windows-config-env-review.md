# 2026-10-20 D-151 Windows 설정 환경 적대 검증

- 작업자: Codex sol.
- 코드 기준: `10/20-windows-config-env-review`, HEAD `3d9e58ab24377f9829a0f8002929cfc5d398df5c`(Claude Sonnet), 시작 시 깨끗함. 원격 HEAD 조회는 GitHub 연결 실패. 커밋·푸시 없음.
- 실제 변경: 새 `full_stack_lab/tests/windows_config_env_review_check.py`, 분석 정본·실행 증거 JSON, `docs/ai/DECISIONS.md` 끝의 D-151 정정, 이 보고서, 백로그 DEV-42 행의 마지막 상태 칸.
- 시작 근거: DEV-42, D-148/D-151, [S6 적대 검토](../../analysis/review-1020/s6-user-command-settings.md).
- 해결할 문제와 완료 조건: HEAD의 레지스트리 의미·오류·비누출·전환 경계를 반박하고, 기존 시험 대역 7줄을 A/B/C로 판정한다. 확실한 결함 수정에 기존 시험 변경이 필요하면 기대값을 바꾸지 않고 중단한다.

## 결과

**B: 수정 후 채택**으로 판정했다. [정본 검토](../../analysis/review-1020/d151-windows-config-env.md)에 12개 조건·코드 위치·공식 근거·수정 후보를 연결했다. 기존 대역은 파일 검사의 기대값을 약화하지 않았지만, Windows에서 표준 `platform.system()` 경로를 깨뜨린다. 하이브 미탑재를 정상 처리하는 제품 결함도 재현했다.

새 시험은 14건 중 12통과·1실패·1오류다. 실패를 생략하거나 예상 실패로 처리하지 않는다. REG_EXPAND_SZ·대소문자 비구별 조회·빈 값·import/권한 오류·고정 표기·발견 항목 우선 실패·사건 INSERT·단계 전환은 대역으로 확인했다. 휘발성/시스템/프로세스 환경 미조회 시험은 범위 관찰이며 차단 성공이 아니다.

기존 시험의 보안 기대값과 충돌하므로 제품과 기존 시험은 수정하지 않았다. 결정 기록에 로그인 직후 공백, 값은 QueryValueEx가 메모리에 읽는다는 사실, D-148만 설치된 장치도 D-151을 증명하지 않는다는 전환 한계를 정정했다. 구현·배포·실제 MCP 효과의 완료를 주장하지 않는다. `status/current.md`는 사용자 지시대로 보존했다.

## 검증

아래는 Windows Python 3.10.5, 2026-10-20의 실제 실행이다. [명령·종료 코드·원본 stdout/stderr](../../analysis/review-1020/d151-windows-config-env-evidence.json).

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 새 적대 시험 | `python -B -X utf8 full_stack_lab/tests/windows_config_env_review_check.py` | 14건: 12통과·1실패·1오류, 종료 1 | 증거 JSON `review` |
| 기존 D-151 | `python -B -X utf8 full_stack_lab/tests/windows_config_env_check.py` | 8건 실행, 하위 사례 포함 오류 11·1생략. `OpenKeyEx` 대역 부재, 종료 1 | `original_d151` |
| 기존 D-148 | `python -B -X utf8 full_stack_lab/tests/user_command_settings_check.py` | 15건: 10통과·1오류·4생략, 종료 1. Pydantic·tomllib 부재/링크 권한 생략 | `original_d148` |
| Python 구문 | `python -m py_compile endpoint-agent/managed-windows.py full_stack_lab/gateway/app/main.py full_stack_lab/tests/windows_config_env_review_check.py` | 통과 | `compile` |
| JavaScript 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과, JS 변경 없음 | `javascript` |
| 위키 목록 | `python -B -X utf8 research/llm-wiki/tools/build_wiki.py` | 통과 | `wiki_inventory` |
| 위키 전체 | `python -B -X utf8 research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 기존 코드 매핑 해시 등 오류 22·경고 119로 실패. 문서 추가 전 실행 | `wiki_check` |
| 최종 범위·문서 검사 | UTF-8/BOM 없음/LF·로컬 링크 존재·HEAD 바이트 대조·`git diff --check` | 통과. 제품 2파일·기존 시험 2파일·`current.md`는 HEAD와 동일, 백로그는 DEV-42 마지막 칸만 변경 | `final_scope_check` |

## 기존 시험 변경 필요

1. `user_command_settings_check.py:190-201`: 하이브 전체를 항상 없는 것으로 만드는 대역을 「SID는 존재 + 환경 변수 없음」으로 구분하고, observer import의 호스트 조회와 격리해야 한다. 기존 파일/키 목록 기대값은 유지한다.
2. `windows_config_env_check.py:103-104`: 하이브 없음과 환경 키/값 없음을 분리하고, 확인 불가의 정상 기대값은 false + `env`로 보안 강화해야 한다. 현재 사용자 규칙상 사람의 채택 결정 전에는 바꿀 수 없다.
3. 같은 파일의 대역은 대소문자 비구별·REG_EXPAND_SZ·경로별 핸들을 표현해야 한다. 기존 전체 시험을 생략하거나 platform 캐시 예열로 오류를 숨겨서는 안 된다.

위 이유로 제품 수정은 중단했다. 변경 제안은 정본에 있으며 기존 시험 파일과 기대값은 모두 HEAD 그대로다.

## 실패·미완료·한계

- 하이브 미탑재의 정상 인증 결함과 기존 대역 오류는 미수정이다. 제품/시험 전체 통과가 아니다.
- 로그인 직후 하네스 시작·자격 캐시 이용은 코드 순서상 공백이며, 실제 토큰 획득·명령 헬퍼 실행 성공은 미확인이다.
- 휘발성 환경의 임의 값이 Windows 로그인/세션에서 실제 상속되는지, 시스템 변수/실행 중 환경이 하네스에 미치는 효과는 미검증이다.
- D-148 미보고 전환 유예뿐 아니라 D-148 전용 장치의 D-151 검사 부재도 남는다.
- 실제 레지스트리/ACL·게이트웨이 이미지/Pydantic 입력 모델·실제 DB·배포·PJ1/OSS MCP·독립 효과는 미실행이다.
- 전체 위키 매핑 해시 정리는 다른 변경까지 포함하므로 하지 않았다. `capture_status.py`는 공통 상태 산출물을 덮어쓰므로 이 레인의 문서 범위 밖으로 두었다.

## 다음 작업

DEV-42: 사람이 위 기존 시험 변경을 채택한 뒤 하이브 확인 불능 실패 처리를 최소 수정하고, 세 시험 파일을 게이트웨이 이미지에서 실행한다. Windows 3.13.16의 깨끗한 프로세스로도 대역 import를 검증한다. 새 적대 시험의 Windows 전용 사례는 Linux 이미지에서 생략된다.

솔루션 기기에서 기존 실행 중 스택을 사용해 저장소를 `/repo:ro`로 마운트한 게이트웨이 이미지 내 명령:

```bash
python -B -X utf8 /repo/full_stack_lab/tests/windows_config_env_review_check.py
python -B -X utf8 /repo/full_stack_lab/tests/windows_config_env_check.py
python -B -X utf8 /repo/full_stack_lab/tests/user_command_settings_check.py
```

현재 코드로는 새 적대 시험의 하이브 부재 사례가 Linux 이미지에서도 실패해야 한다. 정상 회귀 성공으로 해석하지 않는다. 이후 PJ1 Windows 대상에서 로그인 전 설정→로그인 직후 실행→다음 검사 격리→원복→관리자 복귀를 확인한다. PJ1의 Windows 실행 환경 확보 여부는 이번에 확인하지 않았다. 로컬 스택은 띄우지 않았다.

## 사용자에게 필요한 입력

없음. 기존 시험 변경의 채택 판단은 정본의 B 판정과 변경 목록으로 넘기며 질문은 하지 않는다.
