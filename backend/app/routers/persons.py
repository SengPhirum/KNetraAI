from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiofiles
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from ..audit import write_audit
from ..config import settings
from ..db import execute, fetch, fetchrow
from ..schemas import PersonApiConfig, PersonApiSyncRequest, PersonCreate, PersonImportRequest, PersonUpdate
from ..security import require_roles
from ..utils import rows_to_dicts, to_jsonable, vector_literal

router = APIRouter(prefix="/persons", tags=["persons"])

PERSON_API_CONFIG_KEY = "person_api.config"

# Aggregated per-person enrollment info returned with every listing row.
_PERSON_LIST_SELECT = """
    SELECT p.*,
           (SELECT COUNT(*) FROM person_images pi WHERE pi.person_id = p.id) AS image_count,
           (SELECT COUNT(*) FROM face_embeddings fe WHERE fe.person_id = p.id) AS embedding_count,
           (SELECT MAX(de.detected_at) FROM detection_events de WHERE de.person_id = p.id) AS last_seen_at
    FROM persons p
"""


def _with_biometric_status(person: dict) -> dict:
    embeddings = int(person.get("embedding_count") or 0)
    images = int(person.get("image_count") or 0)
    if embeddings > 0:
        person["biometric_status"] = "registered"
    elif images > 0 or person.get("consent_at"):
        person["biometric_status"] = "pending"
    else:
        person["biometric_status"] = "na"
    return person


def safe_filename(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return clean or "face.jpg"


@router.get("")
async def list_persons(
    person_type: str | None = None,
    status: str | None = None,
    biometric: str | None = None,
    q: str | None = None,
    user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer")),
):
    values: list = []
    clauses: list[str] = []

    def add_clause(sql: str, value) -> None:
        values.append(value)
        clauses.append(sql.format(f"${len(values)}"))

    if person_type:
        add_clause("p.person_type = {}", person_type)
    if status:
        add_clause("p.status = {}", status)
    if q:
        values.append(f"%{q}%")
        n = len(values)
        clauses.append(
            f"(p.full_name ILIKE ${n} OR p.staff_id ILIKE ${n} OR p.customer_id ILIKE ${n}"
            f" OR p.email ILIKE ${n} OR p.phone ILIKE ${n} OR p.branch ILIKE ${n})"
        )

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = await fetch(f"{_PERSON_LIST_SELECT} {where} ORDER BY p.created_at DESC", *values)
    persons = [_with_biometric_status(p) for p in rows_to_dicts(rows)]
    if biometric in ("registered", "pending", "na"):
        persons = [p for p in persons if p["biometric_status"] == biometric]
    return persons


async def _insert_person(payload: PersonCreate):
    consent_at_expr = "now()" if payload.consent_confirmed else "NULL"
    return await fetchrow(
        f"""
        INSERT INTO persons (
            person_type, full_name, gender, branch, status, staff_id, department, position,
            customer_id, customer_type, vip_flag, email, phone, fp_user_id, shift_start, shift_end,
            consent_at, notes
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, {consent_at_expr}, $17)
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
        payload.email,
        payload.phone,
        payload.fp_user_id,
        payload.shift_start,
        payload.shift_end,
        payload.notes,
    )


async def _adopt_orphan_punches(row) -> None:
    """Claim any earlier-synced fingerprint punches that match this staff member."""
    if row["person_type"] != "staff":
        return
    from .attendance import remap_person_punches

    try:
        await remap_person_punches(str(row["id"]), row["fp_user_id"], row["staff_id"])
    except Exception:
        pass


@router.post("")
async def create_person(payload: PersonCreate, user=Depends(require_roles("Admin", "Manager", "Operator"))):
    row = await _insert_person(payload)
    await _adopt_orphan_punches(row)
    await write_audit(user, "person.create", "person", str(row["id"]), {"person_type": payload.person_type})
    return to_jsonable(row)


CSV_COLUMNS = [
    "person_type", "full_name", "gender", "branch", "status", "staff_id",
    "department", "position", "customer_id", "customer_type", "vip_flag",
    "email", "phone", "fp_user_id", "shift_start", "shift_end", "notes", "consent_confirmed",
]

_TRUTHY = {"1", "true", "yes", "y"}


async def _find_existing(payload: PersonCreate):
    """Match on the external identifier so re-imports sync instead of duplicating."""
    if payload.person_type == "staff" and payload.staff_id:
        return await fetchrow(
            "SELECT * FROM persons WHERE person_type = 'staff' AND staff_id = $1", payload.staff_id
        )
    if payload.person_type == "customer" and payload.customer_id:
        return await fetchrow(
            "SELECT * FROM persons WHERE person_type = 'customer' AND customer_id = $1", payload.customer_id
        )
    return None


async def _import_persons(items: list[dict], mode: str, user, source: str = "csv") -> dict:
    created = updated = skipped = 0
    errors: list[dict] = []
    for index, item in enumerate(items, start=1):
        try:
            payload = PersonCreate(**item)
        except ValidationError as exc:
            first = exc.errors()[0]
            errors.append({"row": index, "error": f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}"})
            continue
        existing = await _find_existing(payload)
        if existing is None:
            await _insert_person(payload)
            created += 1
        elif mode == "upsert":
            await execute(
                """
                UPDATE persons
                SET full_name = $1, gender = $2, branch = $3, status = $4, department = $5,
                    position = $6, customer_type = $7, vip_flag = $8, email = $9, phone = $10,
                    fp_user_id = COALESCE($11, fp_user_id), shift_start = COALESCE($12, shift_start),
                    shift_end = COALESCE($13, shift_end), notes = $14, updated_at = now()
                WHERE id = $15
                """,
                payload.full_name,
                payload.gender,
                payload.branch,
                payload.status,
                payload.department,
                payload.position,
                payload.customer_type,
                payload.vip_flag,
                payload.email,
                payload.phone,
                payload.fp_user_id,
                payload.shift_start,
                payload.shift_end,
                payload.notes,
                existing["id"],
            )
            updated += 1
        else:
            skipped += 1
            errors.append({"row": index, "error": "Duplicate staff_id/customer_id (use sync mode to update)"})
    summary = {"created": created, "updated": updated, "skipped": skipped, "errors": errors}
    await write_audit(user, "person.import", "person", None, summary | {"mode": mode, "source": source})
    return summary


def _rows_from_csv(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file is empty")
    unknown = [c for c in reader.fieldnames if c.strip() and c.strip() not in CSV_COLUMNS]
    if "full_name" not in [c.strip() for c in reader.fieldnames]:
        raise HTTPException(status_code=400, detail="CSV must have a full_name column")
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown CSV columns: {', '.join(unknown)}")
    items = []
    for row in reader:
        item = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
        item = {k: v for k, v in item.items() if v not in (None, "")}
        for flag in ("vip_flag", "consent_confirmed"):
            if flag in item:
                item[flag] = str(item[flag]).lower() in _TRUTHY
        items.append(item)
    if not items:
        raise HTTPException(status_code=400, detail="CSV contains no data rows")
    return items


@router.post("/import")
async def import_persons_csv(
    file: UploadFile = File(...),
    mode: str = Form("create"),
    user=Depends(require_roles("Admin", "Manager")),
):
    if mode not in ("create", "upsert"):
        raise HTTPException(status_code=400, detail="mode must be 'create' or 'upsert'")
    items = _rows_from_csv(await file.read())
    return await _import_persons(items, mode, user, source="csv")


@router.post("/import-json")
async def import_persons_json(payload: PersonImportRequest, user=Depends(require_roles("Admin", "Manager"))):
    return await _import_persons([p.model_dump() for p in payload.persons], payload.mode, user, source="json")


# --------------------------------------------------------------------------
# External HR/CRM API import: stored config with field mapping + pull-sync.
# --------------------------------------------------------------------------

async def _load_api_config() -> PersonApiConfig:
    row = await fetchrow("SELECT value FROM settings WHERE key = $1", PERSON_API_CONFIG_KEY)
    if not row or not row["value"]:
        return PersonApiConfig()
    try:
        return PersonApiConfig(**json.loads(row["value"]))
    except (ValueError, ValidationError):
        return PersonApiConfig()


def _mask_api_config(config: PersonApiConfig) -> dict:
    data = config.model_dump()
    data["headers"] = {name: ("********" if value else "") for name, value in config.headers.items()}
    return data


@router.get("/api-config")
async def get_person_api_config(user=Depends(require_roles("Admin", "Manager"))):
    return _mask_api_config(await _load_api_config())


@router.put("/api-config")
async def update_person_api_config(payload: PersonApiConfig, user=Depends(require_roles("Admin"))):
    current = await _load_api_config()
    merged_headers: dict[str, str] = {}
    for name, value in payload.headers.items():
        # Blank/masked value means "keep the stored secret for this header".
        if value in ("", "********") and name in current.headers:
            merged_headers[name] = current.headers[name]
        else:
            merged_headers[name] = value
    payload.headers = merged_headers
    await execute(
        """
        INSERT INTO settings (key, value, description)
        VALUES ($1, $2, 'External HR/CRM person API import configuration (JSON)')
        ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now()
        """,
        PERSON_API_CONFIG_KEY,
        json.dumps(payload.model_dump()),
    )
    await write_audit(user, "person_api_config.update", "setting", PERSON_API_CONFIG_KEY, {"url": payload.url})
    return _mask_api_config(payload)


def _dig(obj: Any, path: str) -> Any:
    """Resolve a dot path like "data.profile.name" (list indexes allowed: "items.0.id")."""
    if not path:
        return obj
    current = obj
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


_GENDER_MAP = {
    "m": "male", "male": "male", "man": "male", "1": "male",
    "f": "female", "female": "female", "woman": "female", "2": "female",
}


def _map_api_record(record: dict, config: PersonApiConfig) -> dict:
    item: dict[str, Any] = {}
    for local_field, source_path in config.mapping.items():
        if not source_path:
            continue
        value = _dig(record, source_path)
        if value is None or value == "":
            continue
        item[local_field] = value

    item.setdefault("person_type", config.default_person_type)
    if str(item.get("person_type", "")).lower() not in ("staff", "customer"):
        item["person_type"] = config.default_person_type
    else:
        item["person_type"] = str(item["person_type"]).lower()

    if "gender" in item:
        item["gender"] = _GENDER_MAP.get(str(item["gender"]).strip().lower(), "unknown")
    if "status" in item:
        item["status"] = "inactive" if str(item["status"]).strip().lower() in ("inactive", "disabled", "0", "false") else "active"
    for flag in ("vip_flag", "consent_confirmed"):
        if flag in item:
            item[flag] = str(item[flag]).strip().lower() in _TRUTHY
    for key, value in list(item.items()):
        if key not in ("vip_flag", "consent_confirmed") and not isinstance(value, str):
            item[key] = str(value)
    return item


@router.post("/api-sync")
async def sync_persons_from_api(payload: PersonApiSyncRequest, user=Depends(require_roles("Admin", "Manager"))):
    config = await _load_api_config()
    if not config.url:
        raise HTTPException(status_code=400, detail="Configure the person API URL first (Import / Sync panel)")
    if not config.mapping.get("full_name"):
        raise HTTPException(status_code=400, detail="Map the full_name field before syncing")

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            if config.method == "POST":
                body = json.loads(config.body) if config.body.strip() else None
                response = await client.post(config.url, json=body, headers=config.headers)
            else:
                response = await client.get(config.url, headers=config.headers)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Person API returned HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach the person API: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Person API did not return valid JSON") from exc

    records = _dig(data, config.data_path)
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        raise HTTPException(
            status_code=422,
            detail=f"No record list found at data path '{config.data_path or '(root)'}' - check the Data path setting",
        )

    items = [_map_api_record(r, config) for r in records if isinstance(r, dict)]
    if payload.limit:
        items = items[: payload.limit]

    if payload.preview:
        return {"preview": True, "total": len(items), "items": items[:10]}
    result = await _import_persons(items, config.mode, user, source="api")
    return {"preview": False, "total": len(items), **result}


@router.get("/{person_id}")
async def get_person(person_id: str, user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer"))):
    row = await fetchrow(f"{_PERSON_LIST_SELECT} WHERE p.id = $1::uuid", person_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Person not found")
    images = await fetch(
        """
        SELECT pi.*,
               (SELECT COUNT(*) FROM face_embeddings fe WHERE fe.person_image_id = pi.id) AS embedding_count
        FROM person_images pi
        WHERE pi.person_id = $1::uuid
        ORDER BY pi.created_at DESC
        """,
        person_id,
    )
    result = _with_biometric_status(to_jsonable(row))
    result["images"] = rows_to_dicts(images)
    return result


@router.put("/{person_id}")
async def update_person(person_id: str, payload: PersonUpdate, user=Depends(require_roles("Admin", "Manager", "Operator"))):
    existing = await fetchrow("SELECT * FROM persons WHERE id = $1::uuid", person_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Person not found")
    data = payload.model_dump(exclude_unset=True)
    consent_confirmed = data.pop("consent_confirmed", None)
    merged = {**dict(existing), **data}
    consent_value = existing["consent_at"]
    if consent_confirmed is True and consent_value is None:
        consent_value = datetime.now(timezone.utc)
    elif consent_confirmed is False:
        consent_value = None
    row = await fetchrow(
        """
        UPDATE persons
        SET full_name = $1, gender = $2, branch = $3, status = $4, staff_id = $5,
            department = $6, position = $7, customer_id = $8, customer_type = $9,
            vip_flag = $10, email = $11, phone = $12, fp_user_id = $13, shift_start = $14,
            shift_end = $15, consent_at = $16, notes = $17, updated_at = now()
        WHERE id = $18::uuid
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
        merged["email"],
        merged["phone"],
        merged["fp_user_id"],
        merged["shift_start"],
        merged["shift_end"],
        consent_value,
        merged["notes"],
        person_id,
    )
    await _adopt_orphan_punches(row)
    await write_audit(user, "person.update", "person", person_id)
    return to_jsonable(row)


@router.delete("/{person_id}")
async def delete_person(person_id: str, user=Depends(require_roles("Admin", "Manager"))):
    images = await fetch("SELECT file_path FROM person_images WHERE person_id = $1::uuid", person_id)
    await execute("DELETE FROM persons WHERE id = $1::uuid", person_id)
    storage_root = Path(settings.storage_dir).resolve()
    for image in images:
        try:
            path = (storage_root / image["file_path"]).resolve()
            if path.is_relative_to(storage_root) and path.is_file():
                path.unlink()
        except OSError:
            pass
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
    faces_found = None
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
        faces_found = (data.get("metadata") or {}).get("faces_found")
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
    except httpx.HTTPStatusError as exc:
        embedding_status = "failed"
        try:
            embedding_error = exc.response.json().get("detail", str(exc))
        except ValueError:
            embedding_error = str(exc)
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
            "faces_found": faces_found,
        }
    )
    return result


@router.delete("/{person_id}/images/{image_id}")
async def delete_person_image(
    person_id: str,
    image_id: str,
    user=Depends(require_roles("Admin", "Manager", "Operator")),
):
    image = await fetchrow(
        "SELECT * FROM person_images WHERE id = $1::uuid AND person_id = $2::uuid", image_id, person_id
    )
    if image is None:
        raise HTTPException(status_code=404, detail="Face image not found")
    await execute("DELETE FROM face_embeddings WHERE person_image_id = $1::uuid", image_id)
    await execute("DELETE FROM person_images WHERE id = $1::uuid", image_id)
    storage_root = Path(settings.storage_dir).resolve()
    try:
        path = (storage_root / image["file_path"]).resolve()
        if path.is_relative_to(storage_root) and path.is_file():
            path.unlink()
    except OSError:
        pass
    await write_audit(user, "person.image.delete", "person", person_id, {"image_id": image_id})
    return {"ok": True}
