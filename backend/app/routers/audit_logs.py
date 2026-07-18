from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ..db import fetch
from ..security import require_roles
from ..utils import rows_to_dicts

router = APIRouter(prefix="/audit-logs", tags=["audit"])

_SELECT = """
    SELECT al.*, u.email AS actor_email, u.full_name AS actor_name
    FROM audit_logs al
    LEFT JOIN users u ON u.id = al.actor_user_id
"""


def _build_filters(
    action: str | None,
    entity_type: str | None,
    q: str | None,
    date_from: str | None,
    date_to: str | None,
) -> tuple[str, list]:
    values: list = []
    clauses: list[str] = []

    def add_clause(sql: str, value) -> None:
        values.append(value)
        clauses.append(sql.format(f"${len(values)}"))

    if action:
        add_clause("al.action = {}", action)
    if entity_type:
        add_clause("al.entity_type = {}", entity_type)
    if date_from:
        add_clause("al.created_at >= {}::date", date_from)
    if date_to:
        add_clause("al.created_at < ({}::date + interval '1 day')", date_to)
    if q:
        values.append(f"%{q}%")
        n = len(values)
        clauses.append(
            f"(al.action ILIKE ${n} OR al.entity_type ILIKE ${n} OR al.entity_id ILIKE ${n}"
            f" OR u.email ILIKE ${n} OR u.full_name ILIKE ${n} OR al.metadata::text ILIKE ${n})"
        )

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where, values


@router.get("")
async def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    action: str | None = None,
    entity_type: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    user=Depends(require_roles("Admin", "Manager")),
):
    where, values = _build_filters(action, entity_type, q, date_from, date_to)
    values.extend([limit, offset])
    rows = await fetch(
        f"{_SELECT} {where} ORDER BY al.created_at DESC LIMIT ${len(values) - 1} OFFSET ${len(values)}",
        *values,
    )
    return rows_to_dicts(rows)


@router.get("/actions")
async def list_audit_actions(user=Depends(require_roles("Admin", "Manager"))):
    """Distinct action names, for the filter dropdown."""
    rows = await fetch("SELECT DISTINCT action FROM audit_logs ORDER BY action")
    return [row["action"] for row in rows]


@router.get("/export")
async def export_audit_logs(
    action: str | None = None,
    entity_type: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    user=Depends(require_roles("Admin", "Manager")),
):
    """CSV export of everything matching the current filters (capped at 50k rows)."""
    where, values = _build_filters(action, entity_type, q, date_from, date_to)
    rows = await fetch(f"{_SELECT} {where} ORDER BY al.created_at DESC LIMIT 50000", *values)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["time", "actor_email", "actor_name", "action", "entity_type", "entity_id", "metadata"])
    for row in rows:
        metadata = row["metadata"]
        if not isinstance(metadata, str):
            metadata = json.dumps(metadata)
        writer.writerow(
            [
                row["created_at"].isoformat(),
                row["actor_email"] or "",
                row["actor_name"] or "",
                row["action"],
                row["entity_type"] or "",
                row["entity_id"] or "",
                metadata,
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-logs.csv"'},
    )
