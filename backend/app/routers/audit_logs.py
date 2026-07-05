from fastapi import APIRouter, Depends, Query

from ..db import fetch
from ..security import require_roles
from ..utils import rows_to_dicts

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("")
async def list_audit_logs(limit: int = Query(default=100, ge=1, le=500), user=Depends(require_roles("Admin"))):
    rows = await fetch(
        """
        SELECT al.*, u.email AS actor_email, u.full_name AS actor_name
        FROM audit_logs al
        LEFT JOIN users u ON u.id = al.actor_user_id
        ORDER BY al.created_at DESC
        LIMIT $1
        """,
        limit,
    )
    return rows_to_dicts(rows)
