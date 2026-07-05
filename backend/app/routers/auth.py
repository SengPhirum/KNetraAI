from fastapi import APIRouter, Depends, HTTPException, status

from ..db import fetchrow
from ..schemas import LoginRequest, TokenResponse
from ..security import create_access_token, get_current_user, verify_password
from ..utils import to_jsonable

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    row = await fetchrow(
        """
        SELECT u.id, u.email, u.full_name, u.password_hash, u.is_active, r.name AS role
        FROM users u
        LEFT JOIN roles r ON r.id = u.role_id
        WHERE lower(u.email) = lower($1)
        """,
        payload.email,
    )
    if row is None or not row["is_active"] or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token(str(row["id"]), row["email"], row["role"] or "Viewer")
    user = to_jsonable(row)
    user.pop("password_hash", None)
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user
