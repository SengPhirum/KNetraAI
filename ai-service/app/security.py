import secrets
from fastapi import Header, HTTPException

from .config import settings


async def verify_internal_key(x_internal_api_key: str = Header(default="")) -> None:
    if not secrets.compare_digest(x_internal_api_key, settings.internal_api_key):
        raise HTTPException(status_code=401, detail="Invalid internal API key")
