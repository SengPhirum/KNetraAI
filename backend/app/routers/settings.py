from pathlib import Path
from uuid import uuid4

import aiofiles
import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..audit import write_audit
from ..auth_config import SECRET_FIELDS, get_auth_config, mask_auth_config
from ..config import settings as app_settings
from ..db import execute, fetch, fetchrow
from ..schemas import AuthConfigUpdate, GreetingTemplateUpdate, SettingUpdate
from ..security import require_roles
from ..utils import rows_to_dicts, to_jsonable

router = APIRouter(tags=["settings"])

APPEARANCE_DEFAULTS = {
    "appearance.app_name": "KNetraAI",
    "appearance.logo_url": "",
    "appearance.primary_color": "#1E90FF",
    "appearance.secondary_color": "#0f172a",
}


@router.get("/public/appearance")
async def public_appearance():
    """Public: branding used by the frontend before login."""
    rows = await fetch("SELECT key, value FROM settings WHERE key LIKE 'appearance.%'")
    values = {row["key"]: row["value"] for row in rows}
    return {key.split(".", 1)[1]: (values.get(key) or default) for key, default in APPEARANCE_DEFAULTS.items()}


@router.post("/settings/appearance/logo")
async def upload_logo(file: UploadFile = File(...), user=Depends(require_roles("Admin"))):
    suffix = Path(file.filename or "logo.png").suffix.lower()
    if suffix not in (".png", ".svg", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(status_code=400, detail="Logo must be png, svg, jpg, or webp")
    branding_dir = Path(app_settings.storage_dir) / "branding"
    branding_dir.mkdir(parents=True, exist_ok=True)
    filename = f"logo_{uuid4().hex[:8]}{suffix}"
    path = branding_dir / filename
    async with aiofiles.open(path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            await out.write(chunk)
    rel_path = f"branding/{filename}"
    await execute(
        """
        INSERT INTO settings (key, value, description)
        VALUES ('appearance.logo_url', $1, 'Custom logo file path')
        ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now()
        """,
        rel_path,
    )
    await write_audit(user, "setting.update", "setting", "appearance.logo_url", {"value": rel_path})
    return {"logo_url": rel_path}


@router.get("/settings/ai-provider")
async def ai_provider_info(user=Depends(require_roles("Admin", "Manager"))):
    """Current deep-learning provider reported live by the AI service."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{app_settings.ai_service_url}/health")
        response.raise_for_status()
        data = response.json()
        return {"reachable": True, "provider": data.get("provider", "unknown")}
    except httpx.HTTPError as exc:
        return {"reachable": False, "provider": None, "error": str(exc)}


def _is_secret_key(key: str) -> bool:
    return "secret" in key or "password" in key


@router.get("/settings")
async def list_settings(user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer"))):
    rows = await fetch("SELECT * FROM settings ORDER BY key")
    result = rows_to_dicts(rows)
    for item in result:
        if _is_secret_key(item["key"]) and item["value"]:
            item["value"] = "********"
    return result


@router.get("/settings/auth-config")
async def get_auth_configuration(user=Depends(require_roles("Admin"))):
    """Effective auth configuration (settings table overriding env), secrets masked."""
    return mask_auth_config(await get_auth_config())


@router.put("/settings/auth-config")
async def update_auth_configuration(payload: AuthConfigUpdate, user=Depends(require_roles("Admin"))):
    current = await get_auth_config()
    merged = {section: dict(fields) for section, fields in current.items()}
    for section in ("local", "oidc", "ldap"):
        update = getattr(payload, section)
        if update is None:
            continue
        for field, value in update.model_dump().items():
            if (section, field) in SECRET_FIELDS and value == "":
                continue  # blank secret input means keep the stored one
            merged[section][field] = value

    if not (merged["local"]["enabled"] or merged["oidc"]["enabled"] or merged["ldap"]["enabled"]):
        raise HTTPException(status_code=400, detail="At least one login method must remain enabled")
    if merged["local"]["enabled"] and not 4 <= int(merged["local"]["password_min_length"]) <= 128:
        raise HTTPException(status_code=400, detail="Password minimum length must be between 4 and 128")
    if merged["oidc"]["enabled"] and (not merged["oidc"]["issuer"] or not merged["oidc"]["client_id"]):
        raise HTTPException(status_code=400, detail="OIDC requires an issuer URL and client ID")
    if merged["ldap"]["enabled"] and not merged["ldap"]["server_url"]:
        raise HTTPException(status_code=400, detail="LDAP requires a server URL")
    if merged["ldap"]["enabled"] and not merged["ldap"]["user_dn_template"] and not merged["ldap"]["search_base"]:
        raise HTTPException(status_code=400, detail="LDAP requires a user DN template or a search base")

    for section, fields in merged.items():
        for field, value in fields.items():
            await execute(
                """
                INSERT INTO settings (key, value)
                VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now()
                """,
                f"auth.{section}.{field}",
                str(value),
            )
    await write_audit(
        user,
        "auth_config.update",
        "setting",
        "auth",
        {
            "local_enabled": merged["local"]["enabled"],
            "oidc_enabled": merged["oidc"]["enabled"],
            "ldap_enabled": merged["ldap"]["enabled"],
        },
    )
    return mask_auth_config(merged)


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
    await write_audit(user, "setting.update", "setting", key, {"value": "********" if _is_secret_key(key) else payload.value})
    result = to_jsonable(row)
    if _is_secret_key(key) and result.get("value"):
        result["value"] = "********"
    return result


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
