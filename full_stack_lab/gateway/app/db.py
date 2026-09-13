from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Iterable

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://mcp:demo-only-change-me@db:5432/mcp_governance"
)


def _fetch_all(query: str, params: Iterable | None = None) -> list[dict]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        return list(connection.execute(query, params or ()).fetchall())


def _fetch_one(query: str, params: Iterable | None = None) -> dict | None:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        return connection.execute(query, params or ()).fetchone()


def _execute(query: str, params: Iterable | None = None) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(query, params or ())


async def fetch_all(query: str, params: Iterable | None = None) -> list[dict]:
    return await asyncio.to_thread(_fetch_all, query, params)


async def fetch_one(query: str, params: Iterable | None = None) -> dict | None:
    return await asyncio.to_thread(_fetch_one, query, params)


async def execute(query: str, params: Iterable | None = None) -> None:
    await asyncio.to_thread(_execute, query, params)


async def wait_until_ready(timeout: int = 45) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            await fetch_one("SELECT 1 AS ready")
            return
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(1)
    raise RuntimeError(f"PostgreSQL did not become ready: {last_error}")


def _fetch_one(query: str, params: Iterable | None = None) -> dict | None:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        return connection.execute(query, params or ()).fetchone()


def _execute(query: str, params: Iterable | None = None) -> int:
    with psycopg.connect(DATABASE_URL) as connection:
        cursor = connection.execute(query, params or ())
        return cursor.rowcount


async def fetch_all(query: str, params: Iterable | None = None) -> list[dict]:
    return await asyncio.to_thread(_fetch_all, query, params)


async def fetch_one(query: str, params: Iterable | None = None) -> dict | None:
    return await asyncio.to_thread(_fetch_one, query, params)


async def execute(query: str, params: Iterable | None = None) -> int:
    return await asyncio.to_thread(_execute, query, params)


async def wait_until_ready(timeout: int = 45) -> None:
    started = time.monotonic()
    while True:
        try:
            row = await fetch_one("SELECT 1 AS ok")
            if row and row["ok"] == 1:
                return
        except psycopg.Error:
            pass
        if time.monotonic() - started >= timeout:
            raise RuntimeError("PostgreSQL did not become ready")
        await asyncio.sleep(1)
