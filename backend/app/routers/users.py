from fastapi import APIRouter, Depends, HTTPException

from ..audit import write_audit
from ..db import execute, fetch, fetchrow
from ..schemas import UserCreate, UserUpdate
from ..security import hash_password, require_roles
from ..utils import rows_to_dicts, to_jsonable

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(user=Depends(require_roles("Admin"))):
    rows = await fetch(
        """
        SELECT u.id, u.email, u.full_name, u.is_active, r.name AS role, u.created_at, u.updated_at
        FROM users u
        LEFT JOIN roles r ON r.id = u.role_id
        ORDER BY u.created_at DESC
        """
    )
    return rows_to_dicts(rows)


@router.post("")
async def create_user(payload: UserCreate, user=Depends(require_roles("Admin"))):
    role = await fetchrow("SELECT id FROM roles WHERE name = $1", payload.role)
    if role is None:
        raise HTTPException(status_code=400, detail="Role not found")
    row = await fetchrow(
        """
        INSERT INTO users (email, full_name, password_hash, role_id, is_active)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, email, full_name, is_active, created_at, updated_at
        """,
        payload.email.lower(),
        payload.full_name,
        hash_password(payload.password),
        role["id"],
        payload.is_active,
    )
    await write_audit(user, "user.create", "user", str(row["id"]))
    result = to_jsonable(row)
    result["role"] = payload.role
    return result


@router.put("/{user_id}")
async def update_user(user_id: str, payload: UserUpdate, user=Depends(require_roles("Admin"))):
    existing = await fetchrow("SELECT id FROM users WHERE id = $1::uuid", user_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.full_name is not None:
        await execute("UPDATE users SET full_name = $1, updated_at = now() WHERE id = $2::uuid", payload.full_name, user_id)
    if payload.is_active is not None:
        await execute("UPDATE users SET is_active = $1, updated_at = now() WHERE id = $2::uuid", payload.is_active, user_id)
    if payload.password:
        await execute("UPDATE users SET password_hash = $1, updated_at = now() WHERE id = $2::uuid", hash_password(payload.password), user_id)
    if payload.role:
        role = await fetchrow("SELECT id FROM roles WHERE name = $1", payload.role)
        if role is None:
            raise HTTPException(status_code=400, detail="Role not found")
        await execute("UPDATE users SET role_id = $1, updated_at = now() WHERE id = $2::uuid", role["id"], user_id)

    row = await fetchrow(
        """
        SELECT u.id, u.email, u.full_name, u.is_active, r.name AS role, u.created_at, u.updated_at
        FROM users u
        LEFT JOIN roles r ON r.id = u.role_id
        WHERE u.id = $1::uuid
        """,
        user_id,
    )
    await write_audit(user, "user.update", "user", user_id)
    return to_jsonable(row)
