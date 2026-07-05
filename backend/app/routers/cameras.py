import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..audit import write_audit
from ..config import settings
from ..db import execute, fetch, fetchrow
from ..schemas import CameraCreate, CameraUpdate
from ..security import require_roles
from ..utils import rows_to_dicts, to_jsonable

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.get("")
async def list_cameras(user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer"))):
    rows = await fetch("SELECT * FROM cameras ORDER BY created_at DESC")
    return rows_to_dicts(rows)


@router.post("")
async def create_camera(payload: CameraCreate, user=Depends(require_roles("Admin", "Manager"))):
    row = await fetchrow(
        """
        INSERT INTO cameras (name, branch, location, rtsp_url, enabled)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        payload.name,
        payload.branch,
        payload.location,
        payload.rtsp_url,
        payload.enabled,
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
    await write_audit(user, "camera.update", "camera", camera_id)
    return to_jsonable(row)


@router.delete("/{camera_id}")
async def delete_camera(camera_id: str, user=Depends(require_roles("Admin"))):
    await execute("DELETE FROM cameras WHERE id = $1::uuid", camera_id)
    await write_audit(user, "camera.delete", "camera", camera_id)
    return {"ok": True}


@router.post("/{camera_id}/start")
async def start_camera(camera_id: str, user=Depends(require_roles("Admin", "Manager", "Operator"))):
    camera = await fetchrow("SELECT * FROM cameras WHERE id = $1::uuid", camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    payload = {
        "id": str(camera["id"]),
        "name": camera["name"],
        "rtsp_url": camera["rtsp_url"],
        "branch": camera["branch"],
        "location": camera["location"],
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{settings.ai_service_url}/cameras/start",
            json=payload,
            headers={"x-internal-api-key": settings.internal_api_key},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    await execute("UPDATE cameras SET status = 'running', updated_at = now() WHERE id = $1::uuid", camera_id)
    await write_audit(user, "camera.start", "camera", camera_id)
    return response.json()


@router.post("/{camera_id}/stop")
async def stop_camera(camera_id: str, user=Depends(require_roles("Admin", "Manager", "Operator"))):
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{settings.ai_service_url}/cameras/{camera_id}/stop",
            headers={"x-internal-api-key": settings.internal_api_key},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    await execute("UPDATE cameras SET status = 'stopped', updated_at = now() WHERE id = $1::uuid", camera_id)
    await write_audit(user, "camera.stop", "camera", camera_id)
    return response.json()
