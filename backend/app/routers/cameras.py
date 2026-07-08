import json

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..audit import write_audit
from ..config import settings
from ..db import execute, fetch, fetchrow
from ..schemas import CameraCreate, CameraDiscoverRequest, CameraProbeRequest, CameraTestStreamRequest, CameraUpdate
from ..security import get_sse_user, require_roles
from ..utils import rows_to_dicts, to_jsonable

router = APIRouter(prefix="/cameras", tags=["cameras"])


def _raise_for_status(response: httpx.Response) -> None:
    """Forward an ai-service error as a clean message instead of re-wrapping its raw JSON body."""
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    raise HTTPException(status_code=response.status_code, detail=detail)


def _camera_payload(camera) -> dict:
    return {
        "id": str(camera["id"]),
        "name": camera["name"],
        "rtsp_url": camera["rtsp_url"],
        "branch": camera["branch"],
        "location": camera["location"],
    }


async def _start_ai_camera(camera) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{settings.ai_service_url}/cameras/start",
            json=_camera_payload(camera),
            headers={"x-internal-api-key": settings.internal_api_key},
        )
    if response.status_code >= 400:
        _raise_for_status(response)
    return response.json()


async def _stop_ai_camera(camera_id: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{settings.ai_service_url}/cameras/{camera_id}/stop",
                headers={"x-internal-api-key": settings.internal_api_key},
            )
    except httpx.HTTPError:
        pass


@router.get("")
async def list_cameras(user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer"))):
    rows = await fetch("SELECT * FROM cameras ORDER BY created_at DESC")
    return rows_to_dicts(rows)


@router.post("")
async def create_camera(payload: CameraCreate, user=Depends(require_roles("Admin", "Manager"))):
    row = await fetchrow(
        """
        INSERT INTO cameras (name, branch, location, rtsp_url, enabled, source, onvif_host, onvif_profile_token)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING *
        """,
        payload.name,
        payload.branch,
        payload.location,
        payload.rtsp_url,
        payload.enabled,
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
    restart_worker = existing["status"] == "running"
    if restart_worker:
        await _stop_ai_camera(camera_id)
    row = await fetchrow(
        """
        UPDATE cameras
        SET name = $1, branch = $2, location = $3, rtsp_url = $4, enabled = $5, updated_at = now()
        WHERE id = $6
        RETURNING *
        """,
        merged["name"],
        merged["branch"],
        merged["location"],
        merged["rtsp_url"],
        merged["enabled"],
        camera_id,
    )
    if restart_worker and row["enabled"]:
        try:
            await _start_ai_camera(row)
            row = await fetchrow(
                "UPDATE cameras SET status = 'running', updated_at = now() WHERE id = $1::uuid RETURNING *",
                camera_id,
            )
        except HTTPException:
            await execute("UPDATE cameras SET status = 'stopped', updated_at = now() WHERE id = $1::uuid", camera_id)
            raise
    await write_audit(user, "camera.update", "camera", camera_id)
    return to_jsonable(row)


@router.delete("/{camera_id}")
async def delete_camera(camera_id: str, user=Depends(require_roles("Admin"))):
    await _stop_ai_camera(camera_id)
    await execute("DELETE FROM cameras WHERE id = $1::uuid", camera_id)
    await write_audit(user, "camera.delete", "camera", camera_id)
    return {"ok": True}


@router.post("/{camera_id}/start")
async def start_camera(camera_id: str, user=Depends(require_roles("Admin", "Manager", "Operator"))):
    camera = await fetchrow("SELECT * FROM cameras WHERE id = $1::uuid", camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    result = await _start_ai_camera(camera)
    await execute("UPDATE cameras SET status = 'running', updated_at = now() WHERE id = $1::uuid", camera_id)
    await write_audit(user, "camera.start", "camera", camera_id)
    return result


@router.post("/{camera_id}/stop")
async def stop_camera(camera_id: str, user=Depends(require_roles("Admin", "Manager", "Operator"))):
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{settings.ai_service_url}/cameras/{camera_id}/stop",
            headers={"x-internal-api-key": settings.internal_api_key},
        )
    if response.status_code >= 400:
        _raise_for_status(response)
    await execute("UPDATE cameras SET status = 'stopped', updated_at = now() WHERE id = $1::uuid", camera_id)
    await write_audit(user, "camera.stop", "camera", camera_id)
    return response.json()


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


@router.post("/discover")
async def discover_cameras(payload: CameraDiscoverRequest, user=Depends(require_roles("Admin", "Manager"))):
    async with httpx.AsyncClient(timeout=max(15.0, (payload.timeout_seconds or 0) + 5)) as client:
        response = await client.post(
            f"{settings.ai_service_url}/discovery/scan",
            json=payload.model_dump(),
            headers={"x-internal-api-key": settings.internal_api_key},
        )
    if response.status_code >= 400:
        _raise_for_status(response)
    return response.json()


@router.post("/probe")
async def probe_camera(payload: CameraProbeRequest, user=Depends(require_roles("Admin", "Manager"))):
    # A single unreachable-host connect attempt can legitimately take ~30s (the ONVIF client library's
    # own connect timeout) before failing, so this must stay comfortably above that.
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            f"{settings.ai_service_url}/discovery/probe",
            json=payload.model_dump(),
            headers={"x-internal-api-key": settings.internal_api_key},
        )
    if response.status_code >= 400:
        _raise_for_status(response)
    return response.json()


@router.post("/test-stream")
async def test_camera_stream(payload: CameraTestStreamRequest, user=Depends(require_roles("Admin", "Manager"))):
    async with httpx.AsyncClient(timeout=(payload.timeout_ms / 1000) + 5) as client:
        response = await client.post(
            f"{settings.ai_service_url}/discovery/test-stream",
            json=payload.model_dump(),
            headers={"x-internal-api-key": settings.internal_api_key},
        )
    if response.status_code >= 400:
        _raise_for_status(response)
    return response.json()
