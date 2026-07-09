from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt

from ..audit import write_audit
from ..auth_config import get_auth_config
from ..config import settings
from ..db import fetchrow
from ..schemas import LdapLoginRequest, LoginRequest, TokenResponse
from ..security import create_access_token, get_current_user, hash_password, verify_password
from ..utils import to_jsonable

router = APIRouter(prefix="/auth", tags=["auth"])

USER_QUERY = """
    SELECT u.id, u.email, u.full_name, u.password_hash, u.is_active, r.name AS role
    FROM users u
    LEFT JOIN roles r ON r.id = u.role_id
    WHERE lower(u.email) = lower($1)
"""


def _token_response(row: dict[str, Any] | Any) -> dict[str, Any]:
    token = create_access_token(str(row["id"]), row["email"], row["role"] or "Viewer")
    user = to_jsonable(row)
    user.pop("password_hash", None)
    return {"access_token": token, "token_type": "bearer", "user": user}


async def _get_or_provision_user(email: str, full_name: str, default_role: str, provider: str):
    """Find a user by email, creating one just-in-time for external identity providers."""
    row = await fetchrow(USER_QUERY, email)
    if row is None:
        role = await fetchrow("SELECT id FROM roles WHERE name = $1", default_role)
        if role is None:
            raise HTTPException(status_code=500, detail=f"Default role '{default_role}' does not exist")
        # External users never log in with a local password; store an unguessable one.
        await fetchrow(
            """
            INSERT INTO users (email, full_name, password_hash, role_id)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            email,
            full_name or email,
            hash_password(secrets.token_urlsafe(32)),
            role["id"],
        )
        row = await fetchrow(USER_QUERY, email)
        await write_audit(to_jsonable(row), "user.provision", "user", str(row["id"]), {"provider": provider})
    if not row["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")
    return row


@router.get("/methods")
async def auth_methods():
    """Public: which login methods the frontend should offer."""
    cfg = await get_auth_config()
    return {
        "password": cfg["local"]["enabled"],
        "oidc": {"enabled": cfg["oidc"]["enabled"], "provider_name": cfg["oidc"]["provider_name"]},
        "ldap": {"enabled": cfg["ldap"]["enabled"]},
    }


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    cfg = await get_auth_config()
    if not cfg["local"]["enabled"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local password login is disabled")
    row = await fetchrow(USER_QUERY, payload.email)
    if row is None or not row["is_active"] or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return _token_response(row)


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user


# --------------------------------------------------------------------------
# OIDC (Keycloak, Authentik, or any OpenID Connect provider)
# --------------------------------------------------------------------------

_oidc_discovery_cache: dict[str, Any] = {}


async def _oidc_config(oidc: dict[str, Any]) -> dict[str, Any]:
    if not oidc["enabled"]:
        raise HTTPException(status_code=404, detail="OIDC is not enabled")
    if not oidc["issuer"] or not oidc["client_id"]:
        raise HTTPException(status_code=500, detail="OIDC issuer and client ID must be configured")
    cached = _oidc_discovery_cache.get(oidc["issuer"])
    if cached and cached["expires"] > time.time():
        return cached["config"]
    url = oidc["issuer"].rstrip("/") + "/.well-known/openid-configuration"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OIDC discovery failed: {exc}") from exc
    config = response.json()
    _oidc_discovery_cache[oidc["issuer"]] = {"config": config, "expires": time.time() + 3600}
    return config


def _oidc_redirect_uri() -> str:
    return settings.api_base_url.rstrip("/") + "/auth/oidc/callback"


def _safe_frontend_path(value: str = "") -> str:
    if not value or not value.startswith("/") or value.startswith("//") or value.startswith("/login"):
        return "/"
    return value


def _login_redirect(**params: str) -> RedirectResponse:
    return RedirectResponse(settings.frontend_base_url.rstrip("/") + "/login?" + urlencode(params))


@router.get("/oidc/login")
async def oidc_login(redirect: str = ""):
    oidc = (await get_auth_config())["oidc"]
    config = await _oidc_config(oidc)
    state = jwt.encode(
        {
            "purpose": "oidc_state",
            "nonce": secrets.token_urlsafe(16),
            "redirect": _safe_frontend_path(redirect),
            "exp": int(time.time()) + 600,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    params = {
        "response_type": "code",
        "client_id": oidc["client_id"],
        "redirect_uri": _oidc_redirect_uri(),
        "scope": oidc["scopes"],
        "state": state,
    }
    return RedirectResponse(config["authorization_endpoint"] + "?" + urlencode(params))


@router.get("/oidc/callback")
async def oidc_callback(code: str = "", state: str = "", error: str = "", error_description: str = ""):
    if error:
        return _login_redirect(sso_error=error_description or error)
    try:
        state_payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if state_payload.get("purpose") != "oidc_state":
            raise JWTError("wrong purpose")
    except JWTError:
        return _login_redirect(sso_error="Invalid or expired login state, try again")

    oidc = (await get_auth_config())["oidc"]
    config = await _oidc_config(oidc)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_res = await client.post(
                config["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _oidc_redirect_uri(),
                    "client_id": oidc["client_id"],
                    "client_secret": oidc["client_secret"],
                },
            )
            token_res.raise_for_status()
            access_token = token_res.json().get("access_token")
            userinfo_res = await client.get(
                config["userinfo_endpoint"], headers={"Authorization": f"Bearer {access_token}"}
            )
            userinfo_res.raise_for_status()
            userinfo = userinfo_res.json()
    except httpx.HTTPError:
        return _login_redirect(sso_error="Could not verify login with the identity provider")

    email = userinfo.get("email")
    if not email:
        return _login_redirect(sso_error="Identity provider returned no email claim (add the 'email' scope)")
    full_name = userinfo.get("name") or userinfo.get("preferred_username") or email

    if not oidc["auto_create_users"]:
        existing = await fetchrow(USER_QUERY, email)
        if existing is None:
            return _login_redirect(sso_error="No local account for this identity; ask an admin to create one")
    try:
        row = await _get_or_provision_user(email, full_name, oidc["default_role"], "oidc")
    except HTTPException as exc:
        return _login_redirect(sso_error=str(exc.detail))
    result = _token_response(row)
    return _login_redirect(sso_token=result["access_token"], redirect=_safe_frontend_path(state_payload.get("redirect", "")))


# --------------------------------------------------------------------------
# LDAP / Active Directory
# --------------------------------------------------------------------------


def _ldap_authenticate(ldap: dict[str, Any], username: str, password: str) -> tuple[str, str]:
    """Bind against LDAP; returns (email, full_name). Runs in a worker thread."""
    from ldap3 import ALL_ATTRIBUTES, BASE, SUBTREE, Connection, Server
    from ldap3.core.exceptions import LDAPException
    from ldap3.utils.conv import escape_filter_chars

    server = Server(ldap["server_url"])
    email_attr = ldap["email_attribute"]
    name_attr = ldap["name_attribute"]
    try:
        if ldap["user_dn_template"]:
            user_dn = ldap["user_dn_template"].format(username=username)
            conn = Connection(server, user=user_dn, password=password, auto_bind=True)
            conn.search(user_dn, "(objectClass=*)", search_scope=BASE, attributes=ALL_ATTRIBUTES)
            entry = conn.entries[0] if conn.entries else None
        else:
            if not ldap["search_base"]:
                raise HTTPException(status_code=500, detail="Set the LDAP user DN template or search base")
            lookup = Connection(
                server,
                user=ldap["bind_dn"] or None,
                password=ldap["bind_password"] or None,
                auto_bind=True,
            )
            lookup.search(
                ldap["search_base"],
                ldap["user_filter"].format(username=escape_filter_chars(username)),
                search_scope=SUBTREE,
                attributes=ALL_ATTRIBUTES,
            )
            if not lookup.entries:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid LDAP credentials")
            entry = lookup.entries[0]
            # Re-bind as the found user to verify the password.
            Connection(server, user=entry.entry_dn, password=password, auto_bind=True)
    except LDAPException as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid LDAP credentials") from exc

    def attr(entry: Any, name: str) -> str:
        try:
            value = entry[name].value
            return value[0] if isinstance(value, list) else (value or "")
        except Exception:
            return ""

    email = attr(entry, email_attr) if entry is not None else ""
    if not email:
        email = username if "@" in username else f"{username}@ldap.local"
    full_name = (attr(entry, name_attr) if entry is not None else "") or username
    return email, full_name


@router.post("/ldap/login", response_model=TokenResponse)
async def ldap_login(payload: LdapLoginRequest):
    ldap = (await get_auth_config())["ldap"]
    if not ldap["enabled"]:
        raise HTTPException(status_code=404, detail="LDAP is not enabled")
    if not ldap["server_url"]:
        raise HTTPException(status_code=500, detail="LDAP server URL must be configured")
    email, full_name = await asyncio.to_thread(_ldap_authenticate, ldap, payload.username, payload.password)
    row = await _get_or_provision_user(email, full_name, ldap["default_role"], "ldap")
    return _token_response(row)
