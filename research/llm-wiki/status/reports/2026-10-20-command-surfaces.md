# 2026-10-20 하네스 명령 표면 잠금 (DEV-49·DEV-42, D-147)

## 요약

- 목적: 하네스가 셸로 시작하는 명령 표면을 판본별로 정리하고, 공식 관리 키로 잠글 수 있는 것은 잠근다.
- 기준: main 8983311, 브랜치 `10/20-command-surfaces`. 첫 구현 Codex luna, 검토·정정 Claude.

## 바꾼 것

- `gateway/app/endpoint_plane.py`: 엔드포인트 정책의 Codex `requirements.toml`에 `allow_managed_hooks_only = true`.
- `field/pc/mcpgw_pc.py managed`: Claude `allowManagedHooksOnly`, Codex `allow_managed_hooks_only`.
- `workstation/managed/render.py`: 같은 두 키. luna의 `null` 다섯 키와 `notify = []`는 효과가 없어 제거.
- `tests/command_surfaces_check.py`(새 파일): 세 관리 경로의 출력 파일을 만들어 키·헤더 헬퍼 유지·`null` 키 부재를 확인.
- 정본: [명령 표면 목록](../../analysis/command-surfaces/README.md), D-147.

## 검증

| 항목 | 결과 |
| --- | --- |
| `python tests/command_surfaces_check.py`(로컬) | 3/3 통과 |
| 변이 확인: 엔드포인트 정책에서 키 줄 삭제 | 시험 실패(KeyError) 확인 후 원복 |
| `python tests/field_kit_check.py`(로컬) | 통과(1건 건너뜀, 기존) |
| PJ1 배포 전 기준선 | Codex 사용자 훅 발견·실행, bash가 `-codex-tool` 프로필에서 `touch` 거부 |
| 기기 cc_test·배포 후 PJ1 재시험 | 병합 뒤 기록 |

## 남은 것

- Claude 자격/관측 헬퍼·Codex `notify`는 설정 잠금이 없다. 사용자 설정에 이 키가 있으면 엔드포인트 준수 검사로 보고하는 작업이 다음이다.
- statusLine 잠금의 대화형 실기기 확인은 미실행.
