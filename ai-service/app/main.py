from __future__ import annotations

from pathlib import Path
import asyncio

from fastapi import Depends, FastAPI, HTTPException

from .backend_client import BackendClient
from .camera_worker import CameraWorker
from .config import settings
from .schemas import CameraStartRequest, EmbeddingFromPathRequest, EmbeddingResponse
from .security import verify_internal_key
from .vision.provider import build_provider

app = FastAPI(title=settings.service_name)
provider = build_provider()
backend_client = BackendClient()
workers: dict[str, CameraWorker] = {}


@app.on_event("startup")
async def startup() -> None:
    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-service", "provider": provider.model_version}


@app.post("/embeddings/from-path", response_model=EmbeddingResponse, dependencies=[Depends(verify_internal_key)])
async def embedding_from_path(payload: EmbeddingFromPathRequest):
    result = await asyncio.to_thread(provider.embed_image, payload.path)
    return {
        "embedding": result.embedding,
        "model_version": result.model_version,
        "quality_score": result.quality_score,
        "metadata": result.metadata,
    }


@app.post("/cameras/start", dependencies=[Depends(verify_internal_key)])
async def start_camera(payload: CameraStartRequest):
    existing = workers.get(payload.id)
    if existing and existing.running:
        return existing.info()
    worker = CameraWorker(payload, provider, backend_client)
    workers[payload.id] = worker
    await worker.start()
    return worker.info()


@app.post("/cameras/{camera_id}/stop", dependencies=[Depends(verify_internal_key)])
async def stop_camera(camera_id: str):
    worker = workers.get(camera_id)
    if not worker:
        return {"id": camera_id, "status": "stopped", "running": False}
    await worker.stop()
    return worker.info()


@app.get("/cameras", dependencies=[Depends(verify_internal_key)])
async def list_workers():
    return [worker.info() for worker in workers.values()]


@app.get("/cameras/{camera_id}", dependencies=[Depends(verify_internal_key)])
async def get_worker(camera_id: str):
    worker = workers.get(camera_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Camera worker not found")
    return worker.info()
