import asyncio
import logging
from typing import Any

import asyncpg

from .config import settings

logger = logging.getLogger(__name__)
_pool: asyncpg.Pool | None = None


async def connect_db(retries: int = 30, delay_seconds: float = 2.0) -> None:
    global _pool
    if _pool is not None:
        return

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            _pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=10)
            logger.info("Connected to PostgreSQL")
            return
        except Exception as exc:  # pragma: no cover - startup retry
            last_error = exc
            logger.warning("Database connection failed on attempt %s/%s: %s", attempt, retries, exc)
            await asyncio.sleep(delay_seconds)
    raise RuntimeError(f"Could not connect to database: {last_error}")


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized")
    return _pool


async def fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    async with pool().acquire() as conn:
        return list(await conn.fetch(query, *args))


async def fetchrow(query: str, *args: Any) -> asyncpg.Record | None:
    async with pool().acquire() as conn:
        return await conn.fetchrow(query, *args)


async def fetchval(query: str, *args: Any) -> Any:
    async with pool().acquire() as conn:
        return await conn.fetchval(query, *args)


async def execute(query: str, *args: Any) -> str:
    async with pool().acquire() as conn:
        return await conn.execute(query, *args)
