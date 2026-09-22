"""Configure the real A.I.G model without printing its API key."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib import error, request
from urllib.parse import urlsplit


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
MODEL_ID = "mcp-gateway-live"
KEYS = ("MCP_SCAN_BASE_URL", "MCP_SCAN_MODEL", "MCP_SCAN_API_KEY")
AIG_URL = "http://127.0.0.1:8088"


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip("\"'")
    return values


def validate(values: dict[str, str]) -> None:
    base, model, key = (values.get(name, "").strip() for name in KEYS)
    parsed = urlsplit(base)
    # 평문 http는 이 호스트를 벗어나지 않는 주소에만 허용한다. 저장소가 "코드
    # 반출이 불가한 조직은 로컬 모델만 연결하라"고 적어 두고 정작 로컬 주소를
    # 막으면, 그 권고를 따르는 방법이 없다.
    local_http = {"host.docker.internal", "localhost", "127.0.0.1", "::1", "ollama"}
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or (parsed.scheme == "http" and parsed.hostname not in local_http)
            or parsed.hostname in {"aig-lab-model", "llm-stub"}):
        raise ValueError(
            "모델 URL은 HTTPS 주소이거나 이 호스트를 벗어나지 않는 http 주소여야 합니다 "
            "(host.docker.internal, localhost, 127.0.0.1).")
    if any(char.isspace() or char in "#$'\"\\" for char in base + model + key):
        raise ValueError("모델 설정에 공백, 제어문자 또는 .env 특수문자가 있습니다.")
    if not model or not key or key in {"replace-me", "wire-stub-key", "lab-only-test-double"}:
        raise ValueError("실제 모델 이름과 API 키를 입력하세요.")


def save_env(path: Path, values: dict[str, str]) -> None:
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept = [line for line in existing if line.split("=", 1)[0].strip() not in KEYS]
    content = "\n".join(kept + [f"{name}={values[name]}" for name in KEYS]) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=".env-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def init(path: Path, rotate: bool = False) -> None:
    values = read_env(path)
    needs_prompt = rotate or not all(values.get(name) for name in KEYS)
    if not needs_prompt:
        try:
            validate(values)
        except ValueError:
            needs_prompt = True
            values.update({name: "" for name in KEYS})
    if needs_prompt:
        if not sys.stdin.isatty():
            raise RuntimeError("터미널에서 실행하거나 full_stack_lab/.env에 모델 URL·이름·키를 먼저 입력하세요.")
        values["MCP_SCAN_BASE_URL"] = (input("OpenAI 호환 Base URL: ").strip()
                                        or values.get("MCP_SCAN_BASE_URL", ""))
        values["MCP_SCAN_MODEL"] = (input("모델 이름: ").strip()
                                    or values.get("MCP_SCAN_MODEL", ""))
        values["MCP_SCAN_API_KEY"] = (getpass.getpass("API 키 (입력 내용 숨김): ").strip()
                                      or ("" if rotate else values.get("MCP_SCAN_API_KEY", "")))
    validate(values)
    save_env(path, values)
    print("실모델 설정을 저장했습니다. 키는 출력하지 않습니다.")


def api(method: str, path: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(AIG_URL + path, data=body, method=method,
                          headers={"Content-Type": "application/json"})
    try:
        with request.build_opener(request.ProxyHandler({})).open(req, timeout=15) as response:
            raw = response.read(1_000_001)
    except error.HTTPError as exc:
        raise RuntimeError(f"A.I.G 모델 API가 HTTP {exc.code}을 반환했습니다.") from None
    except error.URLError as exc:
        raise RuntimeError("A.I.G Web UI에 연결하지 못했습니다. 8088 포트를 확인하세요.") from exc
    if len(raw) > 1_000_000:
        raise RuntimeError("A.I.G 모델 API 응답이 너무 큽니다.")
    result = json.loads(raw)
    if not isinstance(result, dict) or result.get("status") != 0:
        raise RuntimeError("A.I.G 모델 API가 요청을 거부했습니다.")
    return result


def register(path: Path) -> None:
    values = read_env(path)
    validate(values)
    rows = api("GET", "/api/v1/app/models").get("data") or []
    if not isinstance(rows, list):
        raise RuntimeError("A.I.G 모델 목록의 형식이 다릅니다.")
    model = {"model": values["MCP_SCAN_MODEL"], "token": values["MCP_SCAN_API_KEY"],
             "base_url": values["MCP_SCAN_BASE_URL"].rstrip("/"),
             "note": "MCP Gateway live lab", "limit": 1000}
    if any(isinstance(row, dict) and row.get("model_id") == MODEL_ID for row in rows):
        api("PUT", f"/api/v1/app/models/{MODEL_ID}", {"model": model})
    else:
        api("POST", "/api/v1/app/models", {"model_id": MODEL_ID, "model": model})
    saved = api("GET", f"/api/v1/app/models/{MODEL_ID}").get("data") or {}
    if (saved.get("model_id") != MODEL_ID or saved.get("model", {}).get("model") != model["model"]
            or saved.get("model", {}).get("base_url") != model["base_url"]):
        raise RuntimeError("A.I.G에 저장된 모델 설정이 요청한 값과 다릅니다.")
    print(f"A.I.G Web 모델 등록 완료: {MODEL_ID} ({model['model']})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "register"))
    parser.add_argument("--env-file", type=Path, default=ENV_FILE)
    parser.add_argument("--rotate", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "init":
            init(args.env_file, args.rotate)
        else:
            register(args.env_file)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"실모델 설정 실패: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
