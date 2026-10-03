"""The upstream Gitleaks rule catalog, with no secret values in returned evidence."""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from .privacy import InspectionUnavailable

_slots = asyncio.Semaphore(4)


async def labels(text: str) -> list[str]:
    if len(text) < 6:
        return []
    async with _slots:
        with tempfile.TemporaryDirectory(prefix="mcpgw-secret-") as folder:
            report = Path(folder)/"report.json"
            process = None
            try:
                # Gitleaks token boundaries do not include URL query delimiters.
                # Inspect decoded query values as separate lines as well as the raw input.
                query_values = [value for url in re.findall(r"https?://[^\s<>\"']+", text)
                                for _, value in parse_qsl(urlsplit(url).query, keep_blank_values=True)]
                scan_text = "\n".join([text, *query_values])
                process = await asyncio.create_subprocess_exec(
                    os.getenv("GITLEAKS_BINARY", "/usr/local/bin/gitleaks"), "stdin", "--no-banner",
                    "--redact=100", "--exit-code=0", "--report-format=json", f"--report-path={report}",
                    "--ignore-gitleaks-allow",
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                    env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": folder})
                await asyncio.wait_for(process.communicate(scan_text.encode()), timeout=5)
                if process.returncode != 0:
                    raise ValueError("scanner failed")
                found = json.loads(report.read_text())
                if not isinstance(found, list) or any(not isinstance(f, dict) or not isinstance(f.get("RuleID"), str) for f in found):
                    raise ValueError("invalid scanner output")
                return sorted({"gitleaks:"+f["RuleID"] for f in found})
            except (OSError, ValueError, asyncio.TimeoutError) as exc:
                raise InspectionUnavailable("Gitleaks Secret 검사를 완료하지 못했습니다.") from exc
            finally:
                if process is not None and process.returncode is None:
                    process.kill()
                    await process.wait()
