"""Build-time acquisition only; never fetch an interpreter in the serving process."""
import hashlib
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path


def prepare(manifest: Path, destination: Path) -> None:
    pin = json.loads(manifest.read_text(encoding="utf-8"))
    destination.mkdir(parents=True, exist_ok=True)
    temporary = destination / "python.download"
    try:
        with urllib.request.urlopen(pin["url"], timeout=120) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != pin["sha256"]:
            raise ValueError("Windows Python SHA-256 mismatch")
        with zipfile.ZipFile(temporary) as archive:
            for name in ("python.exe", "pythonw.exe", "python313.zip", pin["pth"], "LICENSE.txt"):
                archive.getinfo(name)
        temporary.replace(destination / "python.zip")
        shutil.copyfile(manifest, destination / "windows-python.json")
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    prepare(Path(sys.argv[1]), Path(sys.argv[2]))
