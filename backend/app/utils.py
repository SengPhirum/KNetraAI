from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg


def to_jsonable(value: Any) -> Any:
    if isinstance(value, asyncpg.Record):
        return {k: to_jsonable(v) for k, v in dict(value).items()}
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def rows_to_dicts(rows: list[asyncpg.Record]) -> list[dict[str, Any]]:
    return [to_jsonable(row) for row in rows]


def vector_literal(vector: list[float]) -> str:
    if len(vector) != 512:
        raise ValueError("Expected a 512-dimensional vector")
    return "[" + ",".join(f"{float(v):.8f}" for v in vector) + "]"
