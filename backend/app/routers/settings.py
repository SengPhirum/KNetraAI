from fastapi import APIRouter, Depends, HTTPException

from ..audit import write_audit
from ..db import execute, fetch, fetchrow
from ..schemas import GreetingTemplateUpdate, SettingUpdate
from ..security import require_roles
from ..utils import rows_to_dicts, to_jsonable

router = APIRouter(tags=["settings"])


@router.get("/settings")
async def list_settings(user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer"))):
    rows = await fetch("SELECT * FROM settings ORDER BY key")
    return rows_to_dicts(rows)


@router.put("/settings/{key}")
async def update_setting(key: str, payload: SettingUpdate, user=Depends(require_roles("Admin"))):
    row = await fetchrow(
        """
        INSERT INTO settings (key, value)
        VALUES ($1, $2)
        ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now()
        RETURNING *
        """,
        key,
        payload.value,
    )
    await write_audit(user, "setting.update", "setting", key, {"value": payload.value})
    return to_jsonable(row)


@router.get("/greeting-templates")
async def list_greeting_templates(user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer"))):
    rows = await fetch("SELECT * FROM greeting_templates ORDER BY language")
    return rows_to_dicts(rows)


@router.put("/greeting-templates/{language}")
async def update_greeting_template(language: str, payload: GreetingTemplateUpdate, user=Depends(require_roles("Admin", "Manager"))):
    existing = await fetchrow("SELECT * FROM greeting_templates WHERE language = $1", language)
    if existing is None:
        raise HTTPException(status_code=404, detail="Template not found")
    data = {**dict(existing), **payload.model_dump(exclude_unset=True)}
    row = await fetchrow(
        """
        UPDATE greeting_templates
        SET known_template = $1, male_template = $2, female_template = $3,
            neutral_template = $4, updated_at = now()
        WHERE language = $5
        RETURNING *
        """,
        data["known_template"],
        data["male_template"],
        data["female_template"],
        data["neutral_template"],
        language,
    )
    await write_audit(user, "greeting_template.update", "greeting_template", language)
    return to_jsonable(row)
