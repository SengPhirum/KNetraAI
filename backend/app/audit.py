from __future__ import annotations

import json
from typing import Any

from .db import execute


async def write_audit(
    user: dict[str, Any] | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    actor_user_id = user.get("id") if user else None
    await execute(
        """
        INSERT INTO audit_logs (actor_user_id, action, entity_type, entity_id, metadata)
        VALUES ($1::uuid, $2, $3, $4, $5::jsonb)
        """,
        actor_user_id,
        action,
        entity_type,
        entity_id,
        json.dumps(metadata or {}),
    )
