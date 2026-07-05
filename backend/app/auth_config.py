from __future__ import annotations

from typing import Any

from .config import settings
from .db import fetch

# Effective auth configuration = settings table value if present, else the
# environment default below. Editing in Settings -> Authentication therefore
# overrides .env without a restart, while fresh installs keep working from env.
SECRET_FIELDS = {("oidc", "client_secret"), ("ldap", "bind_password")}


def _defaults() -> dict[str, dict[str, Any]]:
    return {
        "local": {
            "enabled": True,
            "password_min_length": 8,
            "password_require_uppercase": False,
            "password_require_lowercase": False,
            "password_require_digit": False,
            "password_require_special": False,
        },
        "oidc": {
            "enabled": settings.oidc_enabled,
            "issuer": settings.oidc_issuer,
            "client_id": settings.oidc_client_id,
            "client_secret": settings.oidc_client_secret,
            "scopes": settings.oidc_scopes,
            "provider_name": settings.oidc_provider_name,
            "default_role": settings.oidc_default_role,
            "auto_create_users": settings.oidc_auto_create_users,
        },
        "ldap": {
            "enabled": settings.ldap_enabled,
            "server_url": settings.ldap_server_url,
            "user_dn_template": settings.ldap_user_dn_template,
            "bind_dn": settings.ldap_bind_dn,
            "bind_password": settings.ldap_bind_password,
            "search_base": settings.ldap_search_base,
            "user_filter": settings.ldap_user_filter,
            "email_attribute": settings.ldap_email_attribute,
            "name_attribute": settings.ldap_name_attribute,
            "default_role": settings.ldap_default_role,
        },
    }


def _coerce(raw: str, default: Any) -> Any:
    if isinstance(default, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        try:
            return int(raw)
        except ValueError:
            return default
    return raw


async def get_auth_config() -> dict[str, dict[str, Any]]:
    rows = await fetch("SELECT key, value FROM settings WHERE key LIKE 'auth.%'")
    stored = {row["key"]: row["value"] for row in rows}
    config: dict[str, dict[str, Any]] = {}
    for section, fields in _defaults().items():
        config[section] = {}
        for field, default in fields.items():
            key = f"auth.{section}.{field}"
            config[section][field] = _coerce(stored[key], default) if key in stored else default
    return config


def mask_auth_config(config: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Copy with secrets blanked; *_set flags say whether a secret exists."""
    masked = {section: dict(fields) for section, fields in config.items()}
    for section, field in SECRET_FIELDS:
        masked[section][f"{field}_set"] = bool(masked[section].get(field))
        masked[section][field] = ""
    return masked


def validate_password(password: str, local_rules: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    min_length = int(local_rules.get("password_min_length", 8))
    if len(password) < min_length:
        problems.append(f"be at least {min_length} characters")
    if local_rules.get("password_require_uppercase") and not any(c.isupper() for c in password):
        problems.append("contain an uppercase letter")
    if local_rules.get("password_require_lowercase") and not any(c.islower() for c in password):
        problems.append("contain a lowercase letter")
    if local_rules.get("password_require_digit") and not any(c.isdigit() for c in password):
        problems.append("contain a digit")
    if local_rules.get("password_require_special") and not any(not c.isalnum() for c in password):
        problems.append("contain a special character")
    return problems
