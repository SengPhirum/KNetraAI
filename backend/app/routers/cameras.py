import json

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..audit import write_audit
from ..config import settings
from ..db import execute, fetch, fetchrow
from ..schemas import CameraAiModeRequest, CameraCreate, CameraDiscoverRequest, CameraProbeRequest, CameraTestStreamRequest, CameraUpdate
from ..security import get_sse_user, require_roles
from ..utils import rows_to_dicts, to_jsonable

router = APIRouter(prefix="/cameras", tags=["cameras"])

ACTIVE_STATUSES = {"starting", "connecting", "running", "reconnecting"}


def _raise_for_status(response: httpx.Response) -> None:
    """Forward an ai-service error as a clean message instead of re-wrapping its raw JSON body."""
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    raise HTTPException(status_code=response.status_code, detail=detail)


def _ai_service_unavailable(exc: httpx.HTTPError, action: str) -> HTTPException:
    return HTTPException(status_code=502, detail=f"Could not reach the AI service while {action}: {exc}")


def _camera_payload(camera) -> dict:
    return {
        "id": str(camera["id"]),
        "name": camera["name"],
        "rtsp_url": camera["rtsp_url"],
        "branch": camera["branch"],
        "location": camera["location"],
        "ai_enabled": camera["ai_enabled"],
    }


async def _start_live_camera(camera) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{settings.ai_service_url}/cameras/start",
            json=_camera_payload(camera),
            headers={"x-internal-api-key": settings.internal_api_key},
        )
    if response.status_code >= 400:
        _raise_for_status(response)
    return response.json()


async def _stop_live_camera(camera_id: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{settings.ai_service_url}/cameras/{camera_id}/stop",
                headers={"x-internal-api-key": settings.internal_api_key},
            )
    except httpx.HTTPError:
        pass


async def _set_ai_mode(camera_id: str, enabled: bool) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{settings.ai_service_url}/cameras/{camera_id}/ai",
                json={"enabled": enabled},
                headers={"x-internal-api-key": settings.internal_api_key},
            )
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            _raise_for_status(response)
        return response.json()
    except httpx.HTTPError:
        return None


async def _ai_worker_map() -> dict[str, dict]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{settings.ai_service_url}/cameras",
                headers={"x-internal-api-key": settings.internal_api_key},
            )
        if response.status_code >= 400:
            return {}
        return {str(worker.get("id")): worker for worker in response.json() if worker.get("id")}
    except httpx.HTTPError:
        return {}


@router.get("")
async def list_cameras(user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer"))):
    rows = await fetch("SELECT * FROM cameras ORDER BY created_at DESC")
    cameras = rows_to_dicts(rows)
    workers = await _ai_worker_map()
    stale_running_ids: list[str] = []
    for camera in cameras:
        worker = workers.get(camera["id"])
        camera["worker_running"] = bool(worker and worker.get("running"))
        camera["last_error"] = worker.get("last_error") if worker else None
        if worker and "ai_enabled" in worker:
            camera["ai_enabled"] = worker["ai_enabled"]
        if worker:
            camera["status"] = worker.get("status") or camera["status"]
        elif camera["status"] in ACTIVE_STATUSES:
            camera["status"] = "stopped"
            stale_running_ids.append(camera["id"])

    for camera_id in stale_running_ids:
        await execute("UPDATE cameras SET status = 'stopped', updated_at = now() WHERE id = $1::uuid", camera_id)

    return cameras


@router.post("")
async def create_camera(payload: CameraCreate, user=Depends(require_roles("Admin", "Manager"))):
    row = await fetchrow(
        """
        INSERT INTO cameras (name, branch, location, rtsp_url, enabled, ai_enabled, source, onvif_host, onvif_profile_token)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING *
        """,
        payload.name,
        payload.branch,
        payload.location,
        payload.rtsp_url,
        payload.enabled,
        payload.ai_enabled,
        payload.source,
        payload.onvif_host,
        payload.onvif_profile_token,
    )
    await write_audit(user, "camera.create", "camera", str(row["id"]))
    return to_jsonable(row)


@router.get("/{camera_id}")
async def get_camera(camera_id: str, user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer"))):
    row = await fetchrow("SELECT * FROM cameras WHERE id = $1::uuid", camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return to_jsonable(row)


@router.put("/{camera_id}")
async def update_camera(camera_id: str, payload: CameraUpdate, user=Depends(require_roles("Admin", "Manager"))):
    existing = await fetchrow("SELECT * FROM cameras WHERE id = $1::uuid", camera_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    data = payload.model_dump(exclude_unset=True)
    merged = {**dict(existing), **data}
    restart_worker = existing["status"] in ACTIVE_STATUSES
    if restart_worker:
        await _stop_live_camera(camera_id)
    row = await fetchrow(
        """
        UPDATE cameras
        SET name = $1, branch = $2, location = $3, rtsp_url = $4, enabled = $5, ai_enabled = $6, updated_at = now()
        WHERE id = $7
        RETURNING *
        """,
        merged["name"],
        merged["branch"],
        merged["location"],
        merged["rtsp_url"],
        merged["enabled"],
        merged["ai_enabled"],
        camera_id,
    )
    if restart_worker and row["enabled"]:
        try:
            result = await _start_live_camera(row)
            status_value = result.get("status") or ("running" if result.get("running") else "stopped")
            row = await fetchrow(
                "UPDATE cameras SET status = $2, updated_at = now() WHERE id = $1::uuid RETURNING *",
                camera_id,
                status_value,
            )
        except HTTPException:
            await execute("UPDATE cameras SET status = 'stopped', updated_at = now() WHERE id = $1::uuid", camera_id)
            raise
    elif restart_worker and not row["enabled"]:
        row = await fetchrow(
            "UPDATE cameras SET status = 'stopped', updated_at = now() WHERE id = $1::uuid RETURNING *",
            camera_id,
        )
    await write_audit(user, "camera.update", "camera", camera_id)
    return to_jsonable(row)


@router.delete("/{camera_id}")
async def delete_camera(camera_id: str, user=Depends(require_roles("Admin"))):
    await _stop_live_camera(camera_id)
    await execute("DELETE FROM cameras WHERE id = $1::uuid", camera_id)
    await write_audit(user, "camera.delete", "camera", camera_id)
    return {"ok": True}


@router.post("/{camera_id}/start")
async def start_camera(camera_id: str, user=Depends(require_roles("Admin", "Manager", "Operator"))):
    camera = await fetchrow("SELECT * FROM cameras WHERE id = $1::uuid", camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    if not camera["enabled"]:
        raise HTTPException(status_code=400, detail="Camera is disabled. Enable it before starting live view.")

    camera = await fetchrow(
        "UPDATE cameras SET ai_enabled = FALSE, updated_at = now() WHERE id = $1::uuid RETURNING *",
        camera_id,
    )
    result = await _start_live_camera(camera)
    status_value = result.get("status") or ("running" if result.get("running") else "stopped")
    await execute("UPDATE cameras SET status = $2, updated_at = now() WHERE id = $1::uuid", camera_id, status_value)
    await write_audit(user, "camera.live.start", "camera", camera_id)
    return result


@router.post("/{camera_id}/stop")
async def stop_camera(camera_id: str, user=Depends(require_roles("Admin", "Manager", "Operator"))):
    camera = await fetchrow("SELECT * FROM cameras WHERE id = $1::uuid", camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    await _stop_live_camera(camera_id)
    await execute(
        "UPDATE cameras SET status = 'stopped', ai_enabled = FALSE, updated_at = now() WHERE id = $1::uuid",
        camera_id,
    )
    await write_audit(user, "camera.live.stop", "camera", camera_id)
    return {"id": camera_id, "status": "stopped", "running": False, "ai_enabled": False}


@router.post("/{camera_id}/ai")
async def set_camera_ai(camera_id: str, payload: CameraAiModeRequest, user=Depends(require_roles("Admin", "Manager", "Operator"))):
    enabled = payload.enabled
    camera = await fetchrow("SELECT * FROM cameras WHERE id = $1::uuid", camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    if not camera["enabled"]:
        raise HTTPException(status_code=400, detail="Camera is disabled.")

    result = await _set_ai_mode(camera_id, enabled)
    if result is None and enabled:
        raise HTTPException(status_code=400, detail="Start live view from Camera Management before enabling AI detection.")

    status_value = (result or {}).get("status") or ("stopped" if not enabled and camera["status"] in ACTIVE_STATUSES else camera["status"])
    await execute(
        "UPDATE cameras SET ai_enabled = $2, status = $3, updated_at = now() WHERE id = $1::uuid",
        camera_id,
        enabled,
        status_value,
    )
    await write_audit(user, "camera.ai.enable" if enabled else "camera.ai.disable", "camera", camera_id)
    return result or {"id": camera_id, "status": status_value, "running": False, "ai_enabled": enabled}


@router.get("/{camera_id}/stream")
async def stream_camera(camera_id: str, user=Depends(get_sse_user)):
    """Live MJPEG relay from the ai-service worker. Auth is via query token (like /events/stream)
    because an <img> tag cannot send an Authorization header."""
    client = httpx.AsyncClient(timeout=None)
    try:
        upstream = client.stream(
            "GET",
            f"{settings.ai_service_url}/cameras/{camera_id}/stream.mjpg",
            headers={"x-internal-api-key": settings.internal_api_key},
        )
        response = await upstream.__aenter__()
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail="Could not reach the camera stream service") from exc

    if response.status_code >= 400:
        raw = await response.aread()
        await upstream.__aexit__(None, None, None)
        await client.aclose()
        try:
            detail = json.loads(raw.decode(errors="ignore")).get("detail") or "Camera stream unavailable"
        except ValueError:
            detail = raw.decode(errors="ignore") or "Camera stream unavailable"
        raise HTTPException(status_code=response.status_code, detail=detail)

    async def relay():
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await upstream.__aexit__(None, None, None)
            await client.aclose()

    return StreamingResponse(relay(), media_type=response.headers.get("content-type", "multipart/x-mixed-replace; boundary=frame"))


@router.get("/{camera_id}/snapshot")
async def camera_snapshot(
    camera_id: str,
    probe: bool = False,
    user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer")),
):
    """Thumbnail for the camera list. Cheap path first: re-serves the live worker's
    already-encoded latest frame if the camera is running. ``probe=true`` (the
    "force refresh" button) additionally falls back to a fresh one-shot RTSP grab
    when the cheap path isn't available - e.g. the camera is currently stopped -
    which is deliberately opt-in so loading/refreshing the whole camera list never
    fans out a live RTSP connection per stopped camera on its own."""
    camera = await fetchrow("SELECT * FROM cameras WHERE id = $1::uuid", camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{settings.ai_service_url}/cameras/{camera_id}/snapshot",
                headers={"x-internal-api-key": settings.internal_api_key},
            )
        if response.status_code == 200:
            return {**response.json(), "source": "live"}
    except httpx.HTTPError:
        pass

    if not probe:
        return {"ok": False, "error": "Camera is not running", "source": "live"}

    timeout = httpx.Timeout(15.0, connect=5.0, read=15.0, write=5.0, pool=15.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{settings.ai_service_url}/discovery/test-stream",
                json={"rtsp_url": camera["rtsp_url"], "timeout_ms": 7000},
                headers={"x-internal-api-key": settings.internal_api_key},
            )
        if response.status_code >= 400:
            _raise_for_status(response)
        return {**response.json(), "source": "probe"}
    except httpx.TimeoutException:
        return {"ok": False, "error": "Snapshot timed out. The camera may be offline or unreachable.", "source": "probe"}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"Could not reach the AI service: {exc}", "source": "probe"}


@router.post("/discover")
async def discover_cameras(payload: CameraDiscoverRequest, user=Depends(require_roles("Admin", "Manager"))):
    try:
        async with httpx.AsyncClient(timeout=max(15.0, (payload.timeout_seconds or 0) + 5)) as client:
            response = await client.post(
                f"{settings.ai_service_url}/discovery/scan",
                json=payload.model_dump(),
                headers={"x-internal-api-key": settings.internal_api_key},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="ONVIF discovery timed out. Try entering the camera or NVR IP directly.") from exc
    except httpx.HTTPError as exc:
        raise _ai_service_unavailable(exc, "scanning for cameras") from exc
    if response.status_code >= 400:
        _raise_for_status(response)
    return response.json()


@router.post("/probe")
async def probe_camera(payload: CameraProbeRequest, user=Depends(require_roles("Admin", "Manager"))):
    # A single unreachable-host connect attempt can legitimately take ~30s (the ONVIF client library's
    # own connect timeout) before failing, so this must stay comfortably above that.
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{settings.ai_service_url}/discovery/probe",
                json=payload.model_dump(),
                headers={"x-internal-api-key": settings.internal_api_key},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Fetching channels timed out. Check the ONVIF port, credentials, and camera network reachability.",
        ) from exc
    except httpx.HTTPError as exc:
        raise _ai_service_unavailable(exc, "fetching camera channels") from exc
    if response.status_code >= 400:
        _raise_for_status(response)
    return response.json()


@router.post("/test-stream")
async def test_camera_stream(payload: CameraTestStreamRequest, user=Depends(require_roles("Admin", "Manager"))):
    timeout_seconds = max(8.0, (payload.timeout_ms / 1000) + 8)
    timeout = httpx.Timeout(timeout_seconds, connect=5.0, read=timeout_seconds, write=5.0, pool=timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{settings.ai_service_url}/discovery/test-stream",
                json=payload.model_dump(),
                headers={"x-internal-api-key": settings.internal_api_key},
            )
    except httpx.TimeoutException:
        return {
            "ok": False,
            "error": "Stream test timed out. The channel may be offline, unreachable, or not returning RTSP video.",
        }
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"Could not reach the stream tester: {exc}"}
    if response.status_code >= 400:
        _raise_for_status(response)
    return response.json()
