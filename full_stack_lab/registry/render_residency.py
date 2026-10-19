"""Render registry-owned location policy to OPA; --check verifies without writing."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gateway"))
from app.residency import validate_pack  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = json.loads((ROOT / "registry/data_residency.json").read_text(encoding="utf-8"))
    validate_pack(source["residency"])
    rendered = json.dumps(source, ensure_ascii=False, indent=2) + "\n"
    target = ROOT / "opa/residency.json"
    if args.check:
        if target.read_text(encoding="utf-8") != rendered:
            raise SystemExit("위치 규칙 재생성이 필요합니다.")
    else:
        target.write_text(rendered, encoding="utf-8")
    print("위치 규칙 확인 완료")


if __name__ == "__main__":
    main()
