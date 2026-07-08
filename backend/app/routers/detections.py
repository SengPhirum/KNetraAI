from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..db import execute, fetch, fetchrow
from ..schemas import DetectionEventCreate, RecognitionRequest
from ..security import get_sse_user, require_roles, verify_internal_key
from ..utils import rows_to_dicts, to_jsonable, vector_literal

router = APIRouter(tags=["detections"])


class EventBus:
    def __init__(self) -> None:
        self.queues: set[asyncio.Queue] = set()

    def add(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.queues.add(queue)
        return queue

    def remove(self, queue: asyncio.Queue) -> None:
        self.queues.discard(queue)

    async def publish(self, event: dict) -> None:
        stale: list[asyncio.Queue] = []
        for queue in list(self.queues):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self.remove(queue)


event_bus = EventBus()


async def get_setting_float(key: str, default: float) -> float:
    row = await fetchrow("SELECT value FROM settings WHERE key = $1", key)
    if not row:
        return default
    try:
        return float(row["value"])
    except ValueError:
        return default


async def get_event(event_id: str) -> dict:
    row = await fetchrow(
        """
        SELECT de.*, c.name AS camera_name, c.branch AS camera_branch,
               p.full_name AS person_name, p.person_type AS matched_person_type
        FROM detection_events de
        LEFT JOIN cameras c ON c.id = de.camera_id
        LEFT JOIN persons p ON p.id = de.person_id
        WHERE de.id = $1::uuid
        """,
        event_id,
    )
    return to_jsonable(row)


@router.get("/detection-events")
async def list_detection_events(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    person_type: str | None = None,
    camera_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    has_snapshot: bool | None = None,
    user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer")),
):
    values: list = []
    clauses: list[str] = []

    def add_clause(sql: str, value) -> None:
        values.append(value)
        clauses.append(sql.format(f"${len(values)}"))

    if person_type:
        add_clause("de.person_type = {}", person_type)
    if camera_id:
        add_clause("de.camera_id = {}::uuid", camera_id)
    if date_from:
        add_clause("de.detected_at >= {}::date", date_from)
    if date_to:
        add_clause("de.detected_at < ({}::date + interval '1 day')", date_to)
    if has_snapshot is True:
        clauses.append("de.snapshot_path IS NOT NULL")
    elif has_snapshot is False:
        clauses.append("de.snapshot_path IS NULL")
    if q:
        values.append(f"%{q}%")
        clauses.append(
            f"""
            (
                c.name ILIKE ${len(values)}
                OR p.full_name ILIKE ${len(values)}
                OR de.greeting ILIKE ${len(values)}
                OR de.person_type ILIKE ${len(values)}
                OR de.gender_estimate ILIKE ${len(values)}
            )
            """
        )

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    values.extend([limit, offset])
    rows = await fetch(
        f"""
        SELECT de.*, c.name AS camera_name, p.full_name AS person_name
        FROM detection_events de
        LEFT JOIN cameras c ON c.id = de.camera_id
        LEFT JOIN persons p ON p.id = de.person_id
        {where}
        ORDER BY de.detected_at DESC
        LIMIT ${len(values) - 1} OFFSET ${len(values)}
        """,
        *values,
    )
    return rows_to_dicts(rows)


@router.get("/dashboard/stats")
async def dashboard_stats(user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer"))):
    row = await fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE detected_at >= date_trunc('day', now())) AS events_today,
            COUNT(*) FILTER (WHERE detected_at >= date_trunc('day', now()) AND person_type = 'staff') AS staff_today,
            COUNT(*) FILTER (WHERE detected_at >= date_trunc('day', now()) AND person_type = 'customer') AS customer_today,
            COUNT(*) FILTER (WHERE detected_at >= date_trunc('day', now()) AND person_type = 'unknown') AS unknown_today
        FROM detection_events
        """
    )
    cameras = await fetchrow(
        """
        SELECT
            COUNT(*) AS camera_total,
            COUNT(*) FILTER (WHERE status = 'running') AS camera_running
        FROM cameras
        """
    )
    result = to_jsonable(row)
    result.update(to_jsonable(cameras))
    return result


@router.get("/events/stream")
async def stream_events(user=Depends(get_sse_user)):
    queue = event_bus.add()

    async def generator():
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: detection\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield f": ping {datetime.now(timezone.utc).isoformat()}\n\n"
        finally:
            event_bus.remove(queue)

    return StreamingResponse(generator(), media_type="text/event-stream")


@router.post("/internal/recognize", dependencies=[Depends(verify_internal_key)])
async def recognize(payload: RecognitionRequest):
    try:
        embedding = vector_literal(payload.embedding)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = await fetchrow(
        """
        SELECT fe.person_id, fe.model_version, p.full_name, p.person_type, p.gender,
               1 - (fe.embedding <=> $1::vector) AS similarity
        FROM face_embeddings fe
        JOIN persons p ON p.id = fe.person_id
        WHERE p.status = 'active'
        ORDER BY fe.embedding <=> $1::vector
        LIMIT 1
        """,
        embedding,
    )
    threshold = await get_setting_float("recognition_threshold", 0.45)
    if row and float(row["similarity"]) >= threshold:
        data = to_jsonable(row)
        data.update({"known": True, "threshold": threshold})
        return data
    return {"known": False, "threshold": threshold, "similarity": float(row["similarity"]) if row else None}


async def get_setting_str(key: str, default: str) -> str:
    row = await fetchrow("SELECT value FROM settings WHERE key = $1", key)
    return row["value"] if row else default


async def within_detection_schedule() -> bool:
    """False only when scheduling is enabled and the current server time is outside it."""
    if (await get_setting_str("schedule.enabled", "false")).lower() not in ("1", "true", "yes"):
        return True
    now = datetime.now()
    days = [d.strip().lower() for d in (await get_setting_str("schedule.days", "")).split(",") if d.strip()]
    if days and now.strftime("%a").lower()[:3] not in days:
        return False
    try:
        start = datetime.strptime(await get_setting_str("schedule.start_time", "00:00"), "%H:%M").time()
        end = datetime.strptime(await get_setting_str("schedule.end_time", "23:59"), "%H:%M").time()
    except ValueError:
        return True
    current = now.time()
    if start <= end:
        return start <= current <= end
    # Overnight window, e.g. 20:00 -> 06:00.
    return current >= start or current <= end


@router.post("/internal/detection-events", dependencies=[Depends(verify_internal_key)])
async def create_detection_event(payload: DetectionEventCreate):
    if not await within_detection_schedule():
        return {"skipped": "outside_schedule"}
    if payload.camera_id:
        camera = await fetchrow("SELECT id FROM cameras WHERE id = $1::uuid", payload.camera_id)
        if camera is None:
            return {"skipped": "camera_not_found"}
    row = await fetchrow(
        """
        INSERT INTO detection_events (
            camera_id, person_id, person_type, confidence, gender_estimate, gender_confidence,
            greeting, snapshot_path, raw
        ) VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9::jsonb)
        RETURNING id
        """,
        payload.camera_id,
        payload.person_id,
        payload.person_type,
        payload.confidence,
        payload.gender_estimate,
        payload.gender_confidence,
        payload.greeting,
        payload.snapshot_path,
        json.dumps(payload.raw or {}),
    )
    event = await get_event(str(row["id"]))
    await event_bus.publish(event)
    return event
