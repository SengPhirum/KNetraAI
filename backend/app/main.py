import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import close_db, connect_db
from .routers import audit_logs, auth, cameras, detections, persons, settings as settings_router, users
from .seed import seed_data

logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_retention_task: asyncio.Task | None = None


async def _retention_loop() -> None:
    """Applies the retention.days setting every 6 hours (0 = keep forever)."""
    while True:
        try:
            await detections.cleanup_expired_events()
        except Exception as exc:  # pragma: no cover - housekeeping must never crash the app
            logger.warning("Retention cleanup failed: %s", exc)
        await asyncio.sleep(6 * 3600)


@app.on_event("startup")
async def startup() -> None:
    global _retention_task
    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
    await connect_db()
    await seed_data()
    _retention_task = asyncio.create_task(_retention_loop(), name="retention-cleanup")


@app.on_event("shutdown")
async def shutdown() -> None:
    if _retention_task is not None:
        _retention_task.cancel()
    await close_db()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "backend"}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(cameras.router)
app.include_router(persons.router)
app.include_router(detections.router)
app.include_router(settings_router.router)
app.include_router(audit_logs.router)

# MVP local file serving. For production, place files behind private storage or signed URLs.
app.mount("/files", StaticFiles(directory=settings.storage_dir), name="files")
