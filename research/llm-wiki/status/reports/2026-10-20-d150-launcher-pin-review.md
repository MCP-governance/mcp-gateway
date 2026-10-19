# 2026-10-20 D-150 관리 하네스 런처 고정 적대 검토

- 작업자: Codex sol.
- 코드 기준: `10/20-launcher-pin-review`, 시작 `07708a2caadf6df17ba4212c88adfd716d0374e4`, 시작 dirty 없음. 커밋·푸시 없음.
- 실제 변경: 새 적대 시험·검토 Markdown·실행 원본 JSON·D-150 후속·명령 표면 후속·DEV-42 상태 칸·본 보고. 제품 코드/기존 시험/status/current.md는 변경하지 않음.
- 시작 근거: DEV-42, D-150, D-147/D-148, S6-03, 사용자 지정 반박 목표.
- 해결할 문제와 완료 조건: 설정 주입·정상 인자·Windows 대기/중단·PATH·원본 직접 실행을 근거별로 검토하고 확정 결함을 최소 수정한다. 기존 시험 기대값과 충돌하면 수정하지 않고 이유를 남겨 멈춘다.

## 결과

[검토 정본](../../analysis/review-1020/d150-launcher-pin.md)에 LP-01~07의 심각도·재현·수정안과 모든 요청 표면의 근거/추정/미실행을 분리했다. 새 `full_stack_lab/tests/launcher_pin_adversarial_check.py`는 정상 프롬프트·차단 인자·대기/코드 반환을 대조하며, 값 붙임 옵션/리터럴·미등록 홈·Ctrl+C kill·PATH 손실을 실패로 남긴다. 실패를 승인하거나 expectedFailure로 바꾸지 않았다.

판정은 **병합 보류**다. 원본 실행 권한과 런처 인자를 통한 프로필 재선택은 코드상 공백이며, 실제 헬퍼 실행/토큰/외부 효과 우회 성공은 확인하지 않았다. Windows CLAUDE_CONFIG_DIR는 설정이 아니라 제거라는 문서 정정을 후속 기록으로 남겼다. 새 의존성·정책·DB·mock MCP는 없다.

## 검증

실행 시각: 2026-10-20 06:38 KST, Windows Python 3.10.5. 명령 argv·각 종료 코드·원문 stdout/stderr·관련 소스 해시는 [실행 원본 JSON](../../analysis/review-1020/d150-launcher-pin-evidence.json)에 보존했다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 기존 launcher 시험 | `python -B -X utf8 -m unittest full_stack_lab.tests.launcher_pin_check -v` | 4통과, Linux 1건너뜀 | 실행 원본 checks[0] |
| 새 적대 시험 | `python -B -X utf8 -m unittest full_stack_lab.tests.launcher_pin_adversarial_check -v` | 12개 메서드: 5통과/5실패/2건너뜀, 실패 assertion 8개, exit 1 | checks[1] |
| 기존 CA 시험 | `python -B -X utf8 -m unittest discover -s endpoint-agent/tests-windows -p test_windows_kit.py -k managed_ca -v` | TypeError 오류 1, exit 1 | checks[2] |
| Python 구문 | `python -X utf8 -m py_compile endpoint-agent/enforce-linux.py endpoint-agent/managed-windows.py full_stack_lab/tests/launcher_pin_adversarial_check.py` | 통과 | checks[3] |
| 위키 검사 | `python -B -X utf8 research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 실패: 이번 작업에서 바꾸지 않은 코드와 기존 위협 매핑의 불일치 23개, ignored 원본 누락 경고 119개 | 실행 원본 wiki_check |
| 변경 범위·문서 정합성 | `git diff --check`, Python으로 변경 7파일 UTF-8/BOM/LF·로컬 링크·백로그 전후 행·소스 해시 대조 | 통과. DEV-42 마지막 칸만 변경, 제품/기존 시험/current.md 불변 | 로컬 검사 출력 |
| Linux 생성 C 실행 | WSL 진입 시도 | 미실행: Wsl/Service/E_ACCESSDENIED, 호스트 gcc 없음 | 도구 오류, Linux 시험 건너뜀 |
| 원격 HEAD | `git ls-remote --symref origin HEAD` | 실패: GitHub:443 연결 불가 | 도구 오류 |
| 프로토콜 | 실제 MCP 호출 | 미실행 | 없음 |
| 실제 모델·하네스 | PJ1·Windows 관리 대상 | 미실행 | 없음 |
| upstream 효과 | 실제 서버 효과 | 미확인 | 없음 |
| 배포·정책 해시 | 솔루션 field 배포 | 미실행 | 없음 |

## 기존 시험 변경 필요

**필요. 사용자 규칙에 따라 제품 수정 중단.** `test_windows_kit.py:171-175`의 3인자 API/profile 없는 fixture/CA 스크립트 형식, `launcher_pin_check.py:35,98`의 값 소비를 구분하지 않는 `-pcnotify=[]` 거부 기대값, 55행의 `subprocess.call` 호출 자체 검증을 사람이 적대 검토해야 한다. 기대값이나 기존 파일은 바꾸지 않았다. 자세한 대조는 검토 정본의 같은 제목 절을 따른다.

## 실패·미완료·한계

- 수정 완료가 아니다. 확정 결함의 최소 수정안만 남겼고 새 회귀 시험은 현재 실패한다.
- Linux 생성 C, Windows 실제 Ctrl+C·Ctrl+Break·로그오프·현재 디렉터리/시스템 PATH·실제 ACL 효과·프로필 로딩은 미실행이다.
- 공식 문서와 고정 Codex/파서 소스는 웹에서 확인했으며 원문 바이트 SHA-256은 확보하지 않았다. Claude 배포판의 실제 Commander 판본과 Codex의 정확한 clap lock 판본은 미확인이다. 외부 스킬은 탐색만 했고 실행/채택하지 않았다.
- status/current.md 및 생성 스냅샷은 사용자 범위 규칙에 따라 갱신하지 않는다. 검수 점수를 올리지 않는다.
- 위키 전체 검사는 실패했다. 기존 위협 매핑을 새 소스로 덮어써 과거 실행 근거를 갱신하지 않는다. 이번 문서의 로컬 링크·UTF-8/LF·백로그 상태 칸 범위는 별도 검사한다.

## 다음 작업

DEV-42: 기존 시험 변경을 사람이 검토한 뒤 LP-01~07 수정, 이미지·Linux gcc 환경 회귀, PJ1 실제 CLI/정상 MCP·헬퍼 음성·복구를 검수한다. Windows는 별도 관리 테스트 계정에서 원본 직접 실행과 런처 프로필 선택/콘솔 중단을 확인해야 한다.

기기 명령(솔루션 기기 저장소 루트, Linux gcc 필요):

```bash
python3 -B -X utf8 -m unittest full_stack_lab.tests.launcher_pin_check full_stack_lab.tests.launcher_pin_adversarial_check -v
```

이미지 명령은 검토 정본의 「기기 확인 순서」를 따른다. gcc가 없는 이미지의 Linux 건너뜀을 통과로 세지 않는다. 현재 실패는 예상된 미수정 결함이며 이를 제거하기 전 배포하지 않는다.

## 사용자에게 필요한 입력

없음. 기존 시험 승인·기기 실행은 메인 검토 단계로 남기며 이 작업에서는 질문하지 않는다.
