# 실제 MCP 스키마의 기능 유형

2026-10-14 검수. 태그는 해당 기능의 보수적 권한 상한이며 인자/상태에 따라 달라집니다. readOnlyHint 등 annotation은 권한 보장이 아닙니다.
실제 호출을 확인한 도구와 목록만 확인한 도구를 분리합니다. 정상 read 한 건을 서버의 모든 도구 실행 완료로 집계하지 않습니다.

| MCP | 실제 도구 | 기능 유형 | 선택 호출 관측 |
| --- | --- | --- | --- |
| ghidra | `get_program_info` | read | 확인 |
| ghidra | `list_functions` | read | 목록만 |
| ghidra | `list_methods` | read | 목록만 |
| ghidra | `search_functions_by_name` | read | 목록만 |
| ghidra | `list_classes` | read | 목록만 |
| ghidra | `list_namespaces` | read | 목록만 |
| ghidra | `list_segments` | read | 목록만 |
| ghidra | `list_imports` | read | 목록만 |
| ghidra | `list_exports` | read | 목록만 |
| ghidra | `list_data_items` | read | 목록만 |
| ghidra | `list_strings` | read | 목록만 |
| ghidra | `get_function_by_address` | read | 목록만 |
| ghidra | `decompile_function` | read | 목록만 |
| ghidra | `decompile_function_by_address` | read | 목록만 |
| ghidra | `disassemble_function` | read | 목록만 |
| ghidra | `get_xrefs_to` | read | 목록만 |
| ghidra | `get_xrefs_from` | read | 목록만 |
| ghidra | `get_function_xrefs` | read | 목록만 |
| ghidra | `get_function_calls` | read | 목록만 |
| ghidra | `read_memory` | read | 목록만 |
| ghidra | `rename_function_by_address` | project-write | 목록만 |
| ghidra | `rename_function` | project-write | 목록만 |
| ghidra | `rename_data` | project-write | 목록만 |
| ghidra | `rename_variable` | project-write | 목록만 |
| ghidra | `set_function_prototype` | project-write | 목록만 |
| ghidra | `set_local_variable_type` | project-write | 목록만 |
| ghidra | `set_decompiler_comment` | project-write | 목록만 |
| ghidra | `set_disassembly_comment` | project-write | 목록만 |
| git | `git_add` | read, repository-write, git-subprocess | 확인 |
| git | `git_blame` | read, git-subprocess | 목록만 |
| git | `git_branch` | read, repository-write, git-subprocess | 목록만 |
| git | `git_changelog_analyze` | read, git-subprocess | 목록만 |
| git | `git_checkout` | read, repository-write, git-subprocess | 목록만 |
| git | `git_cherry_pick` | read, repository-write, git-subprocess | 목록만 |
| git | `git_clean` | read, repository-write, git-subprocess | 목록만 |
| git | `git_clear_working_dir` | read, session-write | 목록만 |
| git | `git_clone` | read, repository-write, git-subprocess, network | 확인 |
| git | `git_commit` | read, repository-write, git-subprocess | 확인 |
| git | `git_diff` | read, git-subprocess | 목록만 |
| git | `git_fetch` | read, repository-write, git-subprocess, network | 목록만 |
| git | `git_init` | read, repository-write, git-subprocess | 목록만 |
| git | `git_log` | read, git-subprocess | 목록만 |
| git | `git_merge` | read, repository-write, git-subprocess | 목록만 |
| git | `git_pull` | read, repository-write, git-subprocess, network | 목록만 |
| git | `git_push` | read, repository-write, git-subprocess, network | 목록만 |
| git | `git_rebase` | read, repository-write, git-subprocess | 목록만 |
| git | `git_reflog` | read, git-subprocess | 목록만 |
| git | `git_remote` | read, repository-write, git-subprocess | 목록만 |
| git | `git_reset` | read, repository-write, git-subprocess | 목록만 |
| git | `git_set_working_dir` | read, session-write | 확인 |
| git | `git_show` | read, git-subprocess | 목록만 |
| git | `git_stash` | read, repository-write, git-subprocess | 목록만 |
| git | `git_status` | read, git-subprocess | 확인 |
| git | `git_tag` | read, repository-write, git-subprocess | 목록만 |
| git | `git_worktree` | read, repository-write, git-subprocess | 목록만 |
| git | `git_wrapup_instructions` | read, repository-write, git-subprocess | 목록만 |
| sqlite | `execute_sql` | read, database-write, sql-execution | 확인 |
| sqlite | `search_objects` | read | 목록만 |
| blender | `get_addon_status` | read | 확인 |
| blender | `disable_telemetry` | settings-write | 목록만 |
| blender | `get_scene_info` | read | 확인 |
| blender | `execute_blender_code` | read, project-write, python-execution | 확인 |
| blender | `record_trajectory_feedback` | read, network | 목록만 |
| blender | `look` | read, host-file-read, view-write | 목록만 |
| blender | `generate_3d` | project-write, network | 목록만 |
| blender | `search_assets` | read, network | 목록만 |
| blender | `import_asset` | project-write, network | 목록만 |
| playwright | `browser_close` | read, browser-write | 목록만 |
| playwright | `browser_resize` | read, browser-write | 목록만 |
| playwright | `browser_console_messages` | read, host-write | 목록만 |
| playwright | `browser_handle_dialog` | read, browser-write | 목록만 |
| playwright | `browser_emulate_media` | read, browser-write | 목록만 |
| playwright | `browser_evaluate` | read, browser-write, page-javascript | 목록만 |
| playwright | `browser_file_upload` | host-file-read, browser-write, network | 목록만 |
| playwright | `browser_drop` | host-file-read, browser-write, network | 목록만 |
| playwright | `browser_find` | read, host-write | 목록만 |
| playwright | `browser_fill_form` | read, browser-write | 목록만 |
| playwright | `browser_press_key` | read, browser-write | 목록만 |
| playwright | `browser_type` | read, browser-write | 목록만 |
| playwright | `browser_navigate` | read, browser-write, network | 확인 |
| playwright | `browser_navigate_back` | read, browser-write | 목록만 |
| playwright | `browser_network_requests` | read, host-write | 목록만 |
| playwright | `browser_network_request` | read, host-write | 목록만 |
| playwright | `browser_run_code_unsafe` | read, host-write, server-javascript, network | 목록만 |
| playwright | `browser_take_screenshot` | read, host-write | 목록만 |
| playwright | `browser_snapshot` | read, host-write | 확인 |
| playwright | `browser_click` | read, browser-write | 목록만 |
| playwright | `browser_drag` | read, browser-write | 목록만 |
| playwright | `browser_hover` | read, browser-write | 목록만 |
| playwright | `browser_select_option` | read, browser-write | 목록만 |
| playwright | `browser_tabs` | read, browser-write, network | 목록만 |
| playwright | `browser_wait_for` | read | 목록만 |
