"""Capture local code facts only; never infer activation, live deployment or test success."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
FILES = ["full_stack_lab/gateway/app/core.py", "full_stack_lab/gateway/app/pac.py",
         "full_stack_lab/gateway/app/poisoning.py", "full_stack_lab/gateway/app/idp.py",
         "full_stack_lab/gateway/app/privacy.py", "full_stack_lab/gateway/app/secret_scan.py",
         "full_stack_lab/opa/pac15.rego", "full_stack_lab/opa/decision.rego",
         "endpoint-agent/bootstrap.py", "endpoint-agent/managed-linux.py", "endpoint-agent/enforce-linux.py"]


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


def capture():
    result = {"captured_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
              "head": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
              "status": git("-c", "core.quotePath=false", "status", "--short").splitlines(),
              "scope": "local-code-only", "deployment_verified": False, "experiments_run": False,
              "files": [{"path": p, "sha256": hashlib.sha256((REPO / p).read_bytes()).hexdigest()}
                        for p in FILES]}
    folder = ROOT / "status"
    folder.mkdir(exist_ok=True)
    (folder / "repository-snapshot.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = ["# 저장소 코드 스냅샷", "", f"확인 시각: {result['captured_at']}", "",
          f"HEAD: `{result['head']}` · 로컬 브랜치: `{result['branch']}`", "",
          "로컬 코드 상태입니다. 배포·활성화·실기기 검증과 실험 성공을 증명하지 않습니다.", "",
          "## 워킹 트리", "", "```text", *result["status"], "```", "",
          "## 주요 파일 바이트", "", "| 파일 | SHA-256 |", "| --- | --- |"]
    md += [f"| `{f['path']}` | `{f['sha256']}` |" for f in result["files"]]
    (folder / "repository-snapshot.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"head": result["head"], "dirty_paths": len(result["status"]), "scope": result["scope"]}))


if __name__ == "__main__":
    capture()
