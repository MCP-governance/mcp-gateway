#!/usr/bin/env python3
"""One focused check for the approved-intake handoff to Git review."""
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException

if __file__ != "<stdin>":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from app import agent_service  # noqa: E402


async def check():
    request_id = uuid4()
    row = {
        "id": request_id, "status": "APPROVED", "display_name": "Example",
        "repository_url": "https://github.com/example/server",
        "requested_transport": "stdio", "risk_level": "LOW", "review_note": "검증 완료",
        "reviewed_by": "admin", "reviewed_at": datetime.now(UTC),
        "commit_sha": "a" * 40, "source_ref": "intake:example/server@aaaaaaaaaaaa",
        "validated_at": datetime.now(UTC), "evidence": {"critical": 0}, "exit_terms": {},
    }
    identity = AsyncMock(return_value={"roles": ["admin"]})
    fetch = AsyncMock(return_value=row)
    with patch.object(agent_service, "current_identity", identity), patch.object(agent_service.db, "fetch_one", fetch):
        draft = (await agent_service.registration_draft(request_id, "Bearer token"))["draft"]
        assert draft["validated_source"]["commit_sha"] == "a" * 40
        assert draft["catalog_candidate"] == {"display_name": "Example", "source_url": row["repository_url"]}
        assert "endpoint" not in draft["catalog_candidate"]  # never invent executable configuration

        row["status"] = "VALIDATED"
        try:
            await agent_service.registration_draft(request_id, "Bearer token")
        except HTTPException as error:
            assert error.status_code == 409
        else:
            raise AssertionError("unapproved intake exported")

        row["status"] = "APPROVED"
        row["commit_sha"] = None
        try:
            await agent_service.registration_draft(request_id, "Bearer token")
        except HTTPException as error:
            assert error.status_code == 409
        else:
            raise AssertionError("unpinned intake exported")

        identity.return_value = {"roles": ["employee"]}
        try:
            await agent_service.registration_draft(request_id, "Bearer token")
        except HTTPException as error:
            assert error.status_code == 403
        else:
            raise AssertionError("non-admin exported")


if __name__ == "__main__":
    asyncio.run(check())
    print("registration draft: ok")
