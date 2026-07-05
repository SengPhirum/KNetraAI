from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import aiofiles
import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..audit import write_audit
from ..config import settings
from ..db import execute, fetch, fetchrow
from ..schemas import PersonCreate, PersonUpdate
from ..security import require_roles
from ..utils import rows_to_dicts, to_jsonable, vector_literal

router = APIRouter(prefix="/persons", tags=["persons"])


def safe_filename(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return clean or "face.jpg"


@router.get("")
async def list_persons(person_type: str | None = None, user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer"))):
    if person_type:
        rows = await fetch("SELECT * FROM persons WHERE person_type = $1 ORDER BY created_at DESC", person_type)
    else:
        rows = await fetch("SELECT * FROM persons ORDER BY created_at DESC")
    return rows_to_dicts(rows)


@router.post("")
async def create_person(payload: PersonCreate, user=Depends(require_roles("Admin", "Manager", "Operator"))):
    consent_at_expr = "now()" if payload.consent_confirmed else "NULL"
    row = await fetchrow(
        f"""
        INSERT INTO persons (
            person_type, full_name, gender, branch, status, staff_id, department, position,
            customer_id, customer_type, vip_flag, consent_at, notes
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, {consent_at_expr}, $12)
        RETURNING *
        """,
        payload.person_type,
        payload.full_name,
        payload.gender,
        payload.branch,
        payload.status,
        payload.staff_id,
        payload.department,
        payload.position,
        payload.customer_id,
        payload.customer_type,
        payload.vip_flag,
        payload.notes,
    )
    await write_audit(user, "person.create", "person", str(row["id"]), {"person_type": payload.person_type})
    return to_jsonable(row)


@router.get("/{person_id}")
async def get_person(person_id: str, user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer"))):
    row = await fetchrow("SELECT * FROM persons WHERE id = $1::uuid", person_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Person not found")
    images = await fetch("SELECT * FROM person_images WHERE person_id = $1::uuid ORDER BY created_at DESC", person_id)
    result = to_jsonable(row)
    result["images"] = rows_to_dicts(images)
    return result


@router.put("/{person_id}")
async def update_person(person_id: str, payload: PersonUpdate, user=Depends(require_roles("Admin", "Manager", "Operator"))):
    existing = await fetchrow("SELECT * FROM persons WHERE id = $1::uuid", person_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Person not found")
    data = payload.model_dump(exclude_unset=True)
    merged = {**dict(existing), **data}
    row = await fetchrow(
        """
        UPDATE persons
        SET full_name = $1, gender = $2, branch = $3, status = $4, staff_id = $5,
            department = $6, position = $7, customer_id = $8, customer_type = $9,
            vip_flag = $10, notes = $11, updated_at = now()
        WHERE id = $12::uuid
        RETURNING *
        """,
        merged["full_name"],
        merged["gender"],
        merged["branch"],
        merged["status"],
        merged["staff_id"],
        merged["department"],
        merged["position"],
        merged["customer_id"],
        merged["customer_type"],
        merged["vip_flag"],
        merged["notes"],
        person_id,
    )
    await write_audit(user, "person.update", "person", person_id)
    return to_jsonable(row)


@router.delete("/{person_id}")
async def delete_person(person_id: str, user=Depends(require_roles("Admin", "Manager"))):
    await execute("DELETE FROM persons WHERE id = $1::uuid", person_id)
    await write_audit(user, "person.delete", "person", person_id)
    return {"ok": True}


@router.post("/{person_id}/images")
async def upload_person_image(
    person_id: str,
    file: UploadFile = File(...),
    user=Depends(require_roles("Admin", "Manager", "Operator")),
):
    person = await fetchrow("SELECT * FROM persons WHERE id = $1::uuid", person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")

    person_dir = Path(settings.storage_dir) / "persons" / person_id
    person_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}_{safe_filename(file.filename or 'face.jpg')}"
    path = person_dir / filename
    async with aiofiles.open(path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            await out.write(chunk)

    rel_path = str(path.relative_to(settings.storage_dir))
    image_row = await fetchrow(
        """
        INSERT INTO person_images (person_id, file_path, original_filename)
        VALUES ($1::uuid, $2, $3)
        RETURNING *
        """,
        person_id,
        rel_path,
        file.filename,
    )

    embedding_status = "created"
    embedding_error = None
    model_version = None
    quality_score = None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.ai_service_url}/embeddings/from-path",
                json={"path": str(path)},
                headers={"x-internal-api-key": settings.internal_api_key},
            )
        response.raise_for_status()
        data = response.json()
        embedding = data["embedding"]
        model_version = data.get("model_version", "unknown")
        quality_score = data.get("quality_score")
        await execute(
            """
            INSERT INTO face_embeddings (person_id, person_image_id, embedding, model_version)
            VALUES ($1::uuid, $2::uuid, $3::vector, $4)
            """,
            person_id,
            image_row["id"],
            vector_literal(embedding),
            model_version,
        )
        await execute("UPDATE person_images SET quality_score = $1 WHERE id = $2::uuid", quality_score, image_row["id"])
    except Exception as exc:
        embedding_status = "failed"
        embedding_error = str(exc)

    await write_audit(
        user,
        "person.image.upload",
        "person",
        person_id,
        {"image_id": str(image_row["id"]), "embedding_status": embedding_status},
    )
    result = to_jsonable(image_row)
    result.update(
        {
            "embedding_status": embedding_status,
            "embedding_error": embedding_error,
            "model_version": model_version,
            "quality_score": quality_score,
        }
    )
    return result
