"""Copy the reviewed capabilities with the two CI capacity ceilings adjusted."""
import json
import sys
from pathlib import Path


def main():
    source, target = map(Path, sys.argv[1:])
    document = json.loads(source.read_text(encoding="utf-8"))
    document["execution_profile"]["limits"].update(max_calls=10000, max_concurrency=500)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
