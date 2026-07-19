"""Test videos and dummy data for exercising the AI pipeline without real CCTV.

Test cameras are ordinary camera rows with ``source = 'test'`` whose stream URL
is a local video file (``file:///data/test-videos/...``); the ai-service plays
the file in a loop at native FPS so it behaves like a live walk-in feed.
Bundled sample clips ship inside the backend image (test_assets/) together with
matching dummy staff/customer photos, so recognition, greetings, and attendance
alerts can all be demonstrated end to end from Settings > Demo.
"""
from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path
from uuid import uuid4

import aiofiles
import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..audit import write_audit
from ..config import settings
from ..db import execute, fetch, fetchrow
from ..schemas import DummyClearRequest, TestVideoCameraRequest
from ..security import require_roles
from ..utils import to_jsonable, vector_literal
from .cameras import _set_ai_mode, _start_live_camera, _stop_live_camera
from .detections import _remove_snapshot_files
from .persons import safe_filename

router = APIRouter(prefix="/testing", tags=["testing"])

BUNDLE_DIR = Path(__file__).resolve().parents[2] / "test_assets"
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".avi", ".mov", ".mkv", ".webm"}
MAX_UPLOAD_BYTES = 300 * 1024 * 1024


def _videos_root() -> Path:
    return Path(settings.storage_dir) / "test-videos"


def _dir_for(kind: str) -> Path:
    return _videos_root() / ("bundled" if kind == "bundled" else "uploads")


def _thumbs_dir() -> Path:
    return _videos_root() / "thumbs"


def _file_url(kind: str, name: str) -> str:
    return f"file://{_dir_for(kind) / name}"


def load_manifest() -> dict:
    try:
        return json.loads((BUNDLE_DIR / "manifest.json").read_text())
    except (OSError, ValueError):
        return {"persons": [], "videos": []}


def sync_bundled_assets() -> int:
    """Copy bundled sample clips into the shared storage volume so the
    ai-service container can play them. Runs at startup; idempotent."""
    source_dir = BUNDLE_DIR / "videos"
    if not source_dir.is_dir():
        return 0
    target_dir = _dir_for("bundled")
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    bundled_names = set()
    for video in source_dir.iterdir():
        if video.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        bundled_names.add(video.name)
        target = target_dir / video.name
        if not target.is_file() or target.stat().st_size != video.stat().st_size:
            shutil.copy2(video, target)
            copied += 1
    # The bundled dir mirrors the image's assets exactly - drop clips that were
    # removed or renamed in a newer release so they don't linger in the picker.
    for stale in target_dir.iterdir():
        if stale.suffix.lower() in VIDEO_EXTENSIONS and stale.name not in bundled_names:
            stale.unlink(missing_ok=True)
    return copied


def _safe_video_name(kind: str, name: str) -> Path:
    """Resolve a video filename inside its kind directory, rejecting traversal."""
    if kind not in ("bundled", "uploaded"):
        raise HTTPException(status_code=400, detail="kind must be 'bundled' or 'uploaded'")
    base = _dir_for(kind).resolve()
    path = (base / name).resolve()
    if path.parent != base or path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid video file name")
    return path


async def _test_camera_map() -> dict[str, dict]:
    rows = await fetch("SELECT id, name, rtsp_url, status FROM cameras WHERE source = 'test'")
    return {row["rtsp_url"]: dict(row) for row in rows}


@router.get("/videos")
async def list_test_videos(user=Depends(require_roles("Admin", "Manager"))):
    sync_bundled_assets()
    manifest = load_manifest()
    by_file = {entry["file"]: entry for entry in manifest.get("videos", [])}
    cameras = await _test_camera_map()

    videos = []
    for kind in ("bundled", "uploaded"):
        directory = _dir_for(kind)
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            meta = by_file.get(path.name, {}) if kind == "bundled" else {}
            camera = cameras.get(_file_url(kind, path.name))
            videos.append(
                {
                    "file": path.name,
                    "kind": kind,
                    "label": meta.get("label") or path.stem.replace("-", " ").replace("_", " ").title(),
                    "description": meta.get("description"),
                    "camera_name": meta.get("camera_name") or f"TEST - {path.stem}",
                    "attendance_role": meta.get("attendance_role", "none"),
                    "person": meta.get("person"),
                    "size_bytes": path.stat().st_size,
                    "camera_id": str(camera["id"]) if camera else None,
                    "camera_status": camera["status"] if camera else None,
                }
            )
    return {"videos": videos, "license": manifest.get("license")}


@router.get("/videos/{kind}/{name}/thumbnail")
async def test_video_thumbnail(kind: str, name: str, user=Depends(require_roles("Admin", "Manager"))):
    path = _safe_video_name(kind, name)
    if kind == "bundled":
        thumb = BUNDLE_DIR / "thumbs" / f"{path.stem}.jpg"
        if thumb.is_file():
            data = base64.b64encode(thumb.read_bytes()).decode("ascii")
            return {"ok": True, "thumbnail": f"data:image/jpeg;base64,{data}"}
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")

    cache = _thumbs_dir() / f"{kind}-{path.stem}.jpg"
    if cache.is_file():
        data = base64.b64encode(cache.read_bytes()).decode("ascii")
        return {"ok": True, "thumbnail": f"data:image/jpeg;base64,{data}"}

    # Grab the first frame through the ai-service (same helper the RTSP
    # channel tester uses; it accepts local file paths too).
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{settings.ai_service_url}/discovery/test-stream",
                json={"rtsp_url": str(path), "timeout_ms": 8000},
                headers={"x-internal-api-key": settings.internal_api_key},
            )
        data = response.json() if response.status_code < 400 else {}
    except httpx.HTTPError:
        data = {}
    thumbnail = data.get("thumbnail")
    if not thumbnail:
        return {"ok": False, "thumbnail": None}
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(base64.b64decode(thumbnail.split(",", 1)[1]))
    except (OSError, ValueError, IndexError):
        pass
    return {"ok": True, "thumbnail": thumbnail}


@router.post("/videos/upload")
async def upload_test_video(file: UploadFile = File(...), user=Depends(require_roles("Admin", "Manager"))):
    original = safe_filename(file.filename or "test-video.mp4")
    if Path(original).suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported video type. Use mp4, m4v, mov, avi, mkv, or webm.")
    uploads = _dir_for("uploaded")
    uploads.mkdir(parents=True, exist_ok=True)
    target = uploads / original
    if target.exists():
        target = uploads / f"{uuid4().hex[:8]}_{original}"

    written = 0
    try:
        async with aiofiles.open(target, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Video is too large (300 MB max).")
                await out.write(chunk)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not store the video: {exc}") from exc

    await write_audit(user, "testing.video.upload", "test_video", target.name, {"size_bytes": written})
    return {"ok": True, "file": target.name, "kind": "uploaded", "size_bytes": written}


@router.delete("/videos/{name}")
async def delete_test_video(name: str, user=Depends(require_roles("Admin"))):
    path = _safe_video_name("uploaded", name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Uploaded video not found")

    # Remove any test cameras playing this file first (stopping their workers).
    cameras = await fetch("SELECT id FROM cameras WHERE source = 'test' AND rtsp_url = $1", _file_url("uploaded", name))
    for camera in cameras:
        await _stop_live_camera(str(camera["id"]))
    if cameras:
        ids = [camera["id"] for camera in cameras]
        events = await fetch("DELETE FROM detection_events WHERE camera_id = ANY($1::uuid[]) RETURNING snapshot_path", ids)
        _remove_snapshot_files([event["snapshot_path"] for event in events])
        await execute("DELETE FROM cameras WHERE id = ANY($1::uuid[])", ids)

    path.unlink(missing_ok=True)
    (_thumbs_dir() / f"uploaded-{path.stem}.jpg").unlink(missing_ok=True)
    await write_audit(user, "testing.video.delete", "test_video", name)
    return {"ok": True, "cameras_removed": len(cameras)}


@router.post("/videos/camera")
async def create_test_camera(payload: TestVideoCameraRequest, user=Depends(require_roles("Admin", "Manager"))):
    path = _safe_video_name(payload.kind, payload.file)
    if payload.kind == "bundled":
        sync_bundled_assets()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")

    url = _file_url(payload.kind, payload.file)
    existing = await fetchrow("SELECT * FROM cameras WHERE source = 'test' AND rtsp_url = $1", url)
    if existing is None:
        meta = {}
        if payload.kind == "bundled":
            meta = next((v for v in load_manifest().get("videos", []) if v["file"] == payload.file), {})
        name = payload.name or meta.get("camera_name") or f"TEST - {path.stem}"
        existing = await fetchrow(
            """
            INSERT INTO cameras (name, branch, location, rtsp_url, enabled, ai_enabled, source, attendance_role)
            VALUES ($1, 'Test', 'Test video', $2, TRUE, FALSE, 'test', $3)
            RETURNING *
            """,
            name,
            url,
            meta.get("attendance_role", "none"),
        )
        await write_audit(user, "testing.camera.create", "camera", str(existing["id"]), {"file": payload.file})

    started = False
    if payload.autostart:
        try:
            result = await _start_live_camera(existing)
            status_value = result.get("status") or ("running" if result.get("running") else "stopped")
            # Unlike a normal camera start (view first, AI as a second step), a test
            # camera exists to demo detection - switch AI on right away.
            ai_result = await _set_ai_mode(str(existing["id"]), True)
            await execute(
                "UPDATE cameras SET status = $2, ai_enabled = $3, updated_at = now() WHERE id = $1::uuid",
                str(existing["id"]),
                status_value,
                ai_result is not None,
            )
            started = True
        except HTTPException:
            pass
    return {"ok": True, "camera": to_jsonable(existing), "started": started}


async def _enroll_photo(person_id: str, photo: Path) -> dict:
    """Store a bundled face photo as the person's image and embed it - the same
    flow as a manual photo upload on the person page."""
    person_dir = Path(settings.storage_dir) / "persons" / person_id
    person_dir.mkdir(parents=True, exist_ok=True)
    target = person_dir / f"{uuid4().hex}_{photo.name}"
    shutil.copy2(photo, target)
    rel_path = str(target.relative_to(settings.storage_dir))
    image_row = await fetchrow(
        "INSERT INTO person_images (person_id, file_path, original_filename) VALUES ($1::uuid, $2, $3) RETURNING id",
        person_id,
        rel_path,
        photo.name,
    )
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.ai_service_url}/embeddings/from-path",
                json={"path": str(target)},
                headers={"x-internal-api-key": settings.internal_api_key},
            )
        response.raise_for_status()
        data = response.json()
        await execute(
            "INSERT INTO face_embeddings (person_id, person_image_id, embedding, model_version) VALUES ($1::uuid, $2::uuid, $3::vector, $4)",
            person_id,
            image_row["id"],
            vector_literal(data["embedding"]),
            data.get("model_version", "unknown"),
        )
        await execute(
            "UPDATE person_images SET quality_score = $1 WHERE id = $2::uuid", data.get("quality_score"), image_row["id"]
        )
        return {"embedding": "created", "quality": data.get("quality_score")}
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except ValueError:
            detail = str(exc)
        return {"embedding": "failed", "error": detail}
    except Exception as exc:  # noqa: BLE001 - init must report, not crash
        return {"embedding": "failed", "error": str(exc)}


@router.get("/dummy/status")
async def dummy_data_status(user=Depends(require_roles("Admin"))):
    persons = await fetchrow("SELECT COUNT(*) AS n FROM persons WHERE is_dummy")
    cameras = await fetchrow("SELECT COUNT(*) AS n FROM cameras WHERE source = 'test'")
    uploads_dir = _dir_for("uploaded")
    uploads = sum(1 for p in uploads_dir.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS) if uploads_dir.is_dir() else 0
    return {
        "dummy_persons": persons["n"],
        "test_cameras": cameras["n"],
        "bundled_videos": len(load_manifest().get("videos", [])),
        "uploaded_videos": uploads,
    }


@router.post("/dummy/init")
async def init_dummy_data(user=Depends(require_roles("Admin"))):
    """Create the bundled demo world: dummy staff/customers with enrolled face
    photos plus one looping test camera per sample clip. Idempotent - existing
    dummy rows are kept and only missing pieces are added."""
    sync_bundled_assets()
    manifest = load_manifest()
    results: list[dict] = []
    persons_created = 0

    for spec in manifest.get("persons", []):
        existing = await fetchrow("SELECT id FROM persons WHERE is_dummy AND full_name = $1", spec["full_name"])
        if existing is None:
            row = await fetchrow(
                """
                INSERT INTO persons (person_type, full_name, gender, status, staff_id, department, position,
                                     customer_id, customer_type, vip_flag, fp_user_id, shift_start, shift_end,
                                     notes, consent_at, is_dummy)
                VALUES ($1, $2, $3, 'active', $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, now(), TRUE)
                RETURNING id
                """,
                spec["person_type"],
                spec["full_name"],
                spec.get("gender", "unknown"),
                spec.get("staff_id"),
                spec.get("department"),
                spec.get("position"),
                spec.get("customer_id"),
                spec.get("customer_type"),
                spec.get("vip_flag", False),
                spec.get("fp_user_id"),
                spec.get("shift_start"),
                spec.get("shift_end"),
                spec.get("notes"),
            )
            person_id = str(row["id"])
            persons_created += 1
            created = True
        else:
            person_id = str(existing["id"])
            created = False

        entry = {"person": spec["full_name"], "type": spec["person_type"], "created": created}
        has_embedding = await fetchrow("SELECT 1 FROM face_embeddings WHERE person_id = $1::uuid LIMIT 1", person_id)
        if has_embedding is None:
            photo = BUNDLE_DIR / spec["photo"]
            if photo.is_file():
                entry.update(await _enroll_photo(person_id, photo))
            else:
                entry.update({"embedding": "failed", "error": f"Bundled photo missing: {spec['photo']}"})
        else:
            entry["embedding"] = "exists"
        if spec.get("fp_user_id") or spec.get("staff_id"):
            from .attendance import remap_person_punches

            await remap_person_punches(person_id, spec.get("fp_user_id"), spec.get("staff_id"))
        results.append(entry)

    cameras_created = 0
    for video in manifest.get("videos", []):
        url = _file_url("bundled", video["file"])
        if not (_dir_for("bundled") / video["file"]).is_file():
            results.append({"camera": video["camera_name"], "created": False, "error": "video file missing"})
            continue
        existing = await fetchrow("SELECT id FROM cameras WHERE source = 'test' AND rtsp_url = $1", url)
        if existing is None:
            await execute(
                """
                INSERT INTO cameras (name, branch, location, rtsp_url, enabled, ai_enabled, source, attendance_role)
                VALUES ($1, 'Test', 'Test video', $2, TRUE, FALSE, 'test', $3)
                """,
                video["camera_name"],
                url,
                video.get("attendance_role", "none"),
            )
            cameras_created += 1
        results.append({"camera": video["camera_name"], "created": existing is None})

    await write_audit(user, "testing.dummy.init", "maintenance", None, {"persons_created": persons_created, "cameras_created": cameras_created})
    return {
        "ok": True,
        "persons_created": persons_created,
        "cameras_created": cameras_created,
        "details": results,
    }


@router.post("/dummy/clear")
async def clear_dummy_data(payload: DummyClearRequest, user=Depends(require_roles("Admin"))):
    """Remove everything Init created (plus any user-made test cameras): test
    cameras with their detection history, dummy persons with their photos,
    embeddings, attendance records/alerts, and optionally uploaded videos."""
    cameras = await fetch("SELECT id FROM cameras WHERE source = 'test'")
    camera_ids = [camera["id"] for camera in cameras]
    for camera_id in camera_ids:
        await _stop_live_camera(str(camera_id))
    events_removed = 0
    if camera_ids:
        events = await fetch(
            "DELETE FROM detection_events WHERE camera_id = ANY($1::uuid[]) RETURNING snapshot_path", camera_ids
        )
        _remove_snapshot_files([event["snapshot_path"] for event in events])
        events_removed += len(events)
        await execute("DELETE FROM cameras WHERE id = ANY($1::uuid[])", camera_ids)

    persons = await fetch("SELECT id FROM persons WHERE is_dummy")
    person_ids = [person["id"] for person in persons]
    images_removed = 0
    if person_ids:
        events = await fetch(
            "DELETE FROM detection_events WHERE person_id = ANY($1::uuid[]) RETURNING snapshot_path", person_ids
        )
        _remove_snapshot_files([event["snapshot_path"] for event in events])
        events_removed += len(events)
        await execute("DELETE FROM attendance_records WHERE person_id = ANY($1::uuid[])", person_ids)
        images = await fetch("SELECT file_path FROM person_images WHERE person_id = ANY($1::uuid[])", person_ids)
        storage_root = Path(settings.storage_dir).resolve()
        for image in images:
            try:
                path = (storage_root / image["file_path"]).resolve()
                if path.is_relative_to(storage_root) and path.is_file():
                    path.unlink()
                    images_removed += 1
            except OSError:
                pass
        # attendance_alerts, person_images, and face_embeddings cascade with the person rows.
        await execute("DELETE FROM persons WHERE id = ANY($1::uuid[])", person_ids)

    uploads_removed = 0
    if payload.include_uploads:
        uploads_dir = _dir_for("uploaded")
        if uploads_dir.is_dir():
            for path in uploads_dir.iterdir():
                if path.suffix.lower() in VIDEO_EXTENSIONS:
                    path.unlink(missing_ok=True)
                    (_thumbs_dir() / f"uploaded-{path.stem}.jpg").unlink(missing_ok=True)
                    uploads_removed += 1

    await write_audit(
        user,
        "testing.dummy.clear",
        "maintenance",
        None,
        {"cameras": len(camera_ids), "persons": len(person_ids), "events": events_removed, "uploads": uploads_removed},
    )
    return {
        "ok": True,
        "cameras_removed": len(camera_ids),
        "persons_removed": len(person_ids),
        "events_removed": events_removed,
        "images_removed": images_removed,
        "uploads_removed": uploads_removed,
    }
