"""Official-server local run defaults: selection by repository path, and that every default passes the existing manifest rules."""
import ast
import sys
import unittest
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dev73_rework_check import APP, G, load_functions

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "gateway"))
from app import intake_proposal  # noqa: E402

SERVICE = (LAB / "gateway/app/agent_service.py").read_text(encoding="utf-8")
CONSOLE = (LAB / "gateway/app/agent_static/console.js").read_text(encoding="utf-8")
_JOBS = ast.parse((APP / "local_jobs.py").read_text(encoding="utf-8"))
REASONS = ast.literal_eval(next(n.value for n in _JOBS.body if isinstance(n, ast.Assign) and n.targets[0].id == "REASONS"))
# dev73 하네스의 사유 표는 일부만 담고 있어, 실제 local_jobs의 표를 써서 manifest_errors를 실행한다.
jobs = load_functions(APP / "local_jobs.py", {"manifest_errors"}, {**G, "REASONS": REASONS})
DIGEST = "@sha256:" + "a" * 64
OFFICIAL = "https://github.com/modelcontextprotocol/servers"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def local_run_spec():
    """The production request model, executed without importing the whole service."""
    node = next(n for n in ast.parse(SERVICE).body if isinstance(n, ast.ClassDef) and n.name == "LocalRunSpec")
    scope = {"StrictModel": Strict, "Field": Field, "Literal": Literal}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "agent_service.py", "exec"), scope)
    return scope["LocalRunSpec"]


def row(path, url=OFFICIAL):
    return {"repository_url": url, "repository_path": path}


class Presets(unittest.TestCase):
    def test_known_official_paths_have_expected_defaults(self):
        fs = intake_proposal.local_run_preset(row("src/filesystem"))
        self.assertEqual((fs["image"], fs["command"], fs["mounts"], fs["env"]),
                         ("mcp/filesystem", ["/workspace/mcp-docs"], [{"path": "mcp-docs", "mode": "ro"}], {}))
        mem = intake_proposal.local_run_preset(row("src/memory"))
        self.assertEqual(mem["mounts"], [{"path": "mcp-memory", "mode": "rw"}])
        self.assertEqual(mem["env"], {"MEMORY_FILE_PATH": "/workspace/mcp-memory/memory.json"})
        git = intake_proposal.local_run_preset(row("src/git/"))
        self.assertEqual((git["command"], git["mounts"]), (["--repository", "/workspace/mcp-repo"], [{"path": "mcp-repo", "mode": "ro"}]))
        for name in ("sequentialthinking", "time"):
            plain = intake_proposal.local_run_preset(row(f"src/{name}"))
            self.assertEqual((plain["image"], plain["command"], plain["mounts"], plain["env"]), (f"mcp/{name}", [], [], {}))
        self.assertEqual({p for p, v in intake_proposal.LOCAL_RUN_PRESETS.items() if any(m["mode"] == "rw" for m in v["mounts"])},
                         {"src/memory"}, "only the storing server may default to a writable folder")

    def test_unknown_path_or_other_repository_gets_no_suggestion(self):
        for value in (row("src/everything"), row(""), {}, row("src/filesystem", "https://github.com/someone/servers"),
                      row("src/filesystem", ""), row("../src/filesystem")):
            self.assertEqual(intake_proposal.local_run_preset(value), {}, value)
        self.assertEqual(intake_proposal.local_run_preset(row("src/time", OFFICIAL + ".git"))["image"], "mcp/time")

    def test_a_suggestion_is_a_copy(self):
        intake_proposal.local_run_preset(row("src/memory"))["mounts"].clear()
        self.assertTrue(intake_proposal.LOCAL_RUN_PRESETS["src/memory"]["mounts"])

    def test_every_default_passes_the_existing_request_and_manifest_checks(self):
        spec = local_run_spec()
        for path, preset in intake_proposal.LOCAL_RUN_PRESETS.items():
            with self.subTest(path):
                request = spec(**preset)
                manifest = {"server_id": "x", "image": request.image + DIGEST, "command": request.command, "mounts": request.mounts,
                            "env": request.env, "reason": {"kind": request.reason_kind, "text": request.reason_text}}
                self.assertEqual(jobs.manifest_errors(manifest, "x"), [])

    def test_the_server_still_rejects_what_an_administrator_could_type(self):
        # 제안값을 고쳐 넣어도 기존 검사가 그대로 막는다: 홈 밖 경로, 로더 환경 변수.
        base = {"server_id": "x", "image": "mcp/memory" + DIGEST, "command": [], "mounts": [{"path": "mcp-memory", "mode": "rw"}],
                "env": {}, "reason": {"kind": "local_file", "text": "PC 폴더에 지식 그래프 영구 저장"}}
        for change in ({"mounts": [{"path": "../x", "mode": "rw"}]}, {"mounts": [{"path": "/etc", "mode": "rw"}]},
                       {"env": {"LD_PRELOAD": "/workspace/x.so"}}):
            self.assertTrue(jobs.manifest_errors({**base, **change}, "x"), change)
        with self.assertRaises(ValidationError):
            local_run_spec()(**{**intake_proposal.LOCAL_RUN_PRESETS["src/time"], "reason_text": "짧음"})

    def test_preview_returns_the_suggestion_and_the_dialog_prefills_only_when_nothing_is_stored(self):
        self.assertIn('"local_run_preset": intake_proposal.local_run_preset(row)', SERVICE)
        self.assertIn("askLocalRun(id, out.request, out.local_run_preset)", CONSOLE)
        self.assertIn("const cur = request.evidence?.local_run || preset;", CONSOLE)
        self.assertIn("mounts, env, reason_kind", CONSOLE, "환경 변수는 입력란의 값을 보낸다")


if __name__ == "__main__":
    unittest.main()
