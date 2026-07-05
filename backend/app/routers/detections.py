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
    user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer")),
):
    if person_type:
        rows = await fetch(
            """
            SELECT de.*, c.name AS camera_name, p.full_name AS person_name
            FROM detection_events de
            LEFT JOIN cameras c ON c.id = de.camera_id
            LEFT JOIN persons p ON p.id = de.person_id
            WHERE de.person_type = $1
            ORDER BY de.detected_at DESC
            LIMIT $2 OFFSET $3
            """,
            person_type,
            limit,
            offset,
        )
    else:
        rows = await fetch(
            """
            SELECT de.*, c.name AS camera_name, p.full_name AS person_name
            FROM detection_events de
            LEFT JOIN cameras c ON c.id = de.camera_id
            LEFT JOIN persons p ON p.id = de.person_id
            ORDER BY de.detected_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
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


@router.post("/internal/detection-events", dependencies=[Depends(verify_internal_key)])
async def create_detection_event(payload: DetectionEventCreate):
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
