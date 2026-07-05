from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import close_db, connect_db
from .routers import audit_logs, auth, cameras, detections, persons, settings as settings_router, users
from .seed import seed_data

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
    await connect_db()
    await seed_data()


@app.on_event("shutdown")
async def shutdown() -> None:
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
