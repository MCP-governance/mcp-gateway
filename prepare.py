"""Render Keycloak realm import/Dashboard config from .env before Compose starts.

기본(loopback) 모드는 기존과 동일하게 동작한다. .env에 APPLIANCE_HOST가 있거나
--field가 주어지면 실기기(솔루션 기기) 모드로 렌더링한다: 리다이렉트 URI·웹 오리진·issuer가
전부 https://${APPLIANCE_HOST} 기준이 된다.

렌더링 결과물은 추적하지 않는 outputs/ 아래에 쓴다(.gitignore). deploy/realm.template.json이 커밋되는 원본이며
비밀번호를 담지 않는다(이전에는 추적 중인 deploy/realm.json을 .env의 비밀번호로 덮어썼다). compose.yaml은 outputs/의
realm.json과 config.js를 마운트한다. dashboard/config.js는 그 마운트 지점을 위한 loopback 기본값이다 — 읽기 전용
./dashboard 마운트 안에 파일이 없으면 Docker가 겹쳐 마운트할 자리를 만들지 못한다.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).parent


def load_env(path: Path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def render(root: Path, values: dict, field_host: str = "") -> str:
    """Write outputs/deploy/realm.json and outputs/dashboard/config.js. Returns the issuer used."""
    realm = json.loads((root / "deploy/realm.template.json").read_text(encoding="utf-8"))
    for user in realm["users"]:
        user["credentials"][0]["value"] = values[user["username"].upper() + "_PASSWORD"]

    if field_host:
        origin = "https://" + field_host
        issuer = origin + "/realms/mcp"
    else:
        origin = "http://127.0.0.1:" + values.get("DASHBOARD_PORT", "18083")
        issuer = "http://127.0.0.1:" + values.get("KEYCLOAK_PORT", "18081") + "/realms/mcp"

    for client in realm["clients"]:
        if client["clientId"] == "mcp-gateway":
            client["redirectUris"] = [origin + "/*"]
            client["webOrigins"] = [origin]

    out_deploy = root / "outputs/deploy"
    out_dashboard = root / "outputs/dashboard"
    out_deploy.mkdir(parents=True, exist_ok=True)
    out_dashboard.mkdir(parents=True, exist_ok=True)
    (out_deploy / "realm.json").write_text(json.dumps(realm, indent=2) + "\n", encoding="utf-8")
    (out_dashboard / "config.js").write_text("export const issuer=" + json.dumps(issuer) + ";\n", encoding="utf-8")
    return issuer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field", action="store_true",
                         help="APPLIANCE_HOST 기준(https://)으로 렌더링을 강제한다(.env의 APPLIANCE_HOST가 비어 있으면 오류)")
    args = parser.parse_args()

    values = load_env(ROOT / ".env")
    field_host = values.get("APPLIANCE_HOST", "").strip()
    if args.field and not field_host:
        raise SystemExit("실기기 모드(--field)를 쓰려면 .env의 APPLIANCE_HOST를 먼저 채워야 합니다.")

    issuer = render(ROOT, values, field_host=field_host)
    mode = "field(실기기)" if field_host else "loopback(기본)"
    print(f"prepare.py: {mode} 모드로 렌더링했습니다. issuer={issuer}")


if __name__ == "__main__":
    main()
