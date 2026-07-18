from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..audit import write_audit
from ..config import settings as app_settings
from ..db import execute, fetch, fetchrow
from ..schemas import DetectionClearRequest, DetectionEventCreate, RecognitionRequest
from ..security import get_sse_user, require_roles, verify_internal_key
from ..utils import rows_to_dicts, to_jsonable, vector_literal

logger = logging.getLogger(__name__)

router = APIRouter(tags=["detections"])

_TRUTHY = ("1", "true", "yes")


def _remove_snapshot_files(paths: list[str | None]) -> int:
    """Best-effort deletion of snapshot files under the storage dir."""
    storage_root = Path(app_settings.storage_dir).resolve()
    removed = 0
    for rel_path in paths:
        if not rel_path:
            continue
        try:
            path = (storage_root / rel_path).resolve()
            if path.is_relative_to(storage_root) and path.is_file():
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


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


@router.delete("/detection-events/{event_id}")
async def delete_detection_event(event_id: str, user=Depends(require_roles("Admin"))):
    row = await fetchrow("DELETE FROM detection_events WHERE id = $1::uuid RETURNING snapshot_path", event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Detection event not found")
    _remove_snapshot_files([row["snapshot_path"]])
    await write_audit(user, "detection_event.delete", "detection_event", event_id)
    return {"ok": True}


@router.post("/detection-events/clear")
async def clear_detection_events(payload: DetectionClearRequest, user=Depends(require_roles("Admin"))):
    """Admin-only bulk delete of detection history (rows + snapshot files)."""
    values: list = []
    clauses: list[str] = []

    def add_clause(sql: str, value) -> None:
        values.append(value)
        clauses.append(sql.format(f"${len(values)}"))

    if payload.event_ids:
        add_clause("id = ANY({}::uuid[])", payload.event_ids)
    if payload.camera_id:
        add_clause("camera_id = {}::uuid", payload.camera_id)
    if payload.person_type:
        add_clause("person_type = {}", payload.person_type)
    if payload.date_from:
        add_clause("detected_at >= {}::date", payload.date_from)
    if payload.date_to:
        add_clause("detected_at < ({}::date + interval '1 day')", payload.date_to)

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = await fetch(f"DELETE FROM detection_events {where} RETURNING snapshot_path", *values)
    removed_files = _remove_snapshot_files([row["snapshot_path"] for row in rows])
    await write_audit(
        user,
        "detection_event.clear",
        "detection_event",
        None,
        {"deleted": len(rows), "snapshots_removed": removed_files, "filters": payload.model_dump(exclude_none=True)},
    )
    return {"ok": True, "deleted": len(rows), "snapshots_removed": removed_files}


async def cleanup_expired_events() -> dict:
    """Delete detection events older than the retention.days setting (0 = keep forever)."""
    retention_days = int(await get_setting_float("retention.days", 0))
    if retention_days <= 0:
        return {"deleted": 0}
    rows = await fetch(
        "DELETE FROM detection_events WHERE detected_at < now() - make_interval(days => $1) RETURNING snapshot_path",
        retention_days,
    )
    removed = _remove_snapshot_files([row["snapshot_path"] for row in rows])
    if rows:
        logger.info("Retention cleanup removed %s events (%s snapshots) older than %s days", len(rows), removed, retention_days)
    return {"deleted": len(rows), "snapshots_removed": removed}


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


async def meets_storage_criteria(payload: DetectionEventCreate) -> str | None:
    """Minimum quality gate for persisting detection history.

    Returns a skip reason, or None when the event qualifies:
      - the face capture score (visibility x detection quality) must reach
        detection.min_face_capture (default 0.75), and
      - when detection.require_gender_or_person is on, either the person was
        recognized or a gender was estimated with sufficient confidence.
    """
    min_capture = await get_setting_float("detection.min_face_capture", 0.75)
    if payload.face_capture_score is not None and payload.face_capture_score < min_capture:
        return "below_min_face_capture"
    require_flag = (await get_setting_str("detection.require_gender_or_person", "true")).lower() in _TRUTHY
    if require_flag:
        person_recognized = payload.person_id is not None
        gender_recognized = (payload.gender_estimate or "").lower() in ("male", "female")
        if not person_recognized and not gender_recognized:
            return "no_gender_or_person"
    return None


@router.post("/internal/detection-events", dependencies=[Depends(verify_internal_key)])
async def create_detection_event(payload: DetectionEventCreate):
    if not await within_detection_schedule():
        return {"skipped": "outside_schedule"}
    skip_reason = await meets_storage_criteria(payload)
    if skip_reason:
        return {"skipped": skip_reason}
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
        json.dumps((payload.raw or {}) | ({"face_capture_score": payload.face_capture_score} if payload.face_capture_score is not None else {})),
    )
    event = await get_event(str(row["id"]))
    await event_bus.publish(event)
    return event


@router.get("/internal/runtime-settings", dependencies=[Depends(verify_internal_key)])
async def runtime_settings():
    """Live tunables the AI service polls so Settings changes apply without restarts."""
    return {
        "greeting_cooldown_seconds": await get_setting_float("greeting_cooldown_seconds", 300),
        "presence_absence_seconds": await get_setting_float("presence.absence_seconds", 30),
        "gender_min_confidence": await get_setting_float("gender_min_confidence", 0.60),
        "min_face_capture": await get_setting_float("detection.min_face_capture", 0.75),
        "require_gender_or_person": (await get_setting_str("detection.require_gender_or_person", "true")).lower() in _TRUTHY,
    }
