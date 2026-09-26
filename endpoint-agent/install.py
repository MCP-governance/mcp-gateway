"""Install the read-only endpoint observer for the current OS user."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def gateway_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise argparse.ArgumentTypeError("Gateway 기본 주소만 지정하세요. 경로·인증정보는 넣지 않습니다.")
    if parsed.scheme == "https" and parsed.hostname:
        return value.rstrip("/")
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return value.rstrip("/")
    raise argparse.ArgumentTypeError("원격 Gateway는 HTTPS가 필요합니다. HTTP는 로컬 터널만 허용합니다.")


def install_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "MCPGatewayEndpoint"
    return Path.home() / ".local" / "share" / "mcp-gateway-endpoint"


def config_dir() -> Path:
    if os.name == "nt":
        return install_dir()
    return Path.home() / ".config" / "mcp-gateway-endpoint"


def write_private_json(path: Path, document: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".config-", suffix=".json", delete=False) as output:
        temporary = Path(output.name)
        json.dump(document, output, ensure_ascii=False, indent=2)
        output.write("\n")
    try:
        if os.name != "nt":
            temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP Gateway endpoint observer installation")
    parser.add_argument("--gateway-url", required=True, type=gateway_url)
    parser.add_argument("--endpoint-id", required=True)
    parser.add_argument("--scan-path", action="append", required=True,
                        help="승인한 MCP 설정 파일 또는 디렉터리. 반복 지정 가능")
    parser.add_argument("--key-file", type=Path, help="발급된 장치 키만 담은 파일")
    parser.add_argument("--no-verify", action="store_true", help="설치 뒤 1회 보고를 생략")
    parser.add_argument("--windows-wrapper", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.name == "nt" and not args.windows_wrapper:
        parser.error("Windows에서는 ACL을 먼저 적용하는 install-windows.ps1을 사용하세요.")
    if not 3 <= len(args.endpoint_id) <= 120 or not all(c.isalnum() or c in "-_" for c in args.endpoint_id):
        parser.error("endpoint-id는 영숫자, '-'와 '_'로 된 3~120자여야 합니다.")
    paths = []
    for raw in args.scan_path:
        try:
            path = Path(raw).expanduser().resolve(strict=True)
        except OSError:
            parser.error(f"관측 경로를 찾을 수 없습니다: {raw}")
        if not path.is_file() and not path.is_dir():
            parser.error(f"관측 경로가 파일이나 디렉터리가 아닙니다: {path}")
        paths.append(str(path))
    if args.key_file:
        try:
            key_path = args.key_file.expanduser().resolve(strict=True)
        except OSError:
            parser.error(f"장치 키 파일을 찾을 수 없습니다: {args.key_file}")
        if os.name != "nt" and key_path.stat().st_mode & 0o077:
            parser.error("키 파일은 현재 사용자만 읽을 수 있어야 합니다 (chmod 600).")
        key = key_path.read_text(encoding="utf-8").strip()
    else:
        key = getpass.getpass("장치 키 (화면에 표시되지 않음): ").strip()
    if len(key) < 20:
        parser.error("장치 키가 비어 있거나 너무 짧습니다.")
    target = install_dir()
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        target.chmod(0o700)
    agent = target / "agent.py"
    shutil.copy2(Path(__file__).with_name("agent.py"), agent)
    if os.name != "nt":
        agent.chmod(0o700)
    config = config_dir() / "config.json"
    write_private_json(config, {
        "ENDPOINT_GATEWAY_URL": args.gateway_url,
        "ENDPOINT_DEVICE_KEY": key,
        "ENDPOINT_ID": args.endpoint_id,
        "ENDPOINT_CONFIG_PATHS": os.pathsep.join(paths),
        "ENDPOINT_NETSCAN": "1",
        "ENDPOINT_REPORT_SECONDS": "60",
    })
    print(f"에이전트: {agent}\n설정 파일: {config}")
    if not args.no_verify:
        result = subprocess.run([sys.executable, str(agent), "--config", str(config), "--once"], check=False)
        if result.returncode:
            print("1회 보고에 실패했습니다. Gateway 경로·장치 키·관측 경로를 확인하세요.", file=sys.stderr)
            return result.returncode
    print("설치 및 1회 보고가 완료됐습니다." if not args.no_verify else "설치 파일을 준비했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
