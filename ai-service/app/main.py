from __future__ import annotations

from pathlib import Path
import asyncio

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from . import onvif_discovery
from .backend_client import BackendClient
from .camera_worker import CameraWorker
from .config import settings
from .onvif_discovery import OnvifError
from .schemas import (
    CameraStartRequest,
    DiscoveryProbeRequest,
    DiscoveryScanRequest,
    EmbeddingFromPathRequest,
    EmbeddingResponse,
    TestStreamRequest,
)
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
    if existing and existing.running and existing.camera.model_dump() == payload.model_dump():
        return existing.info()
    if existing:
        await existing.stop()
        workers.pop(payload.id, None)
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
    info = worker.info()
    workers.pop(camera_id, None)
    return info


@app.get("/cameras", dependencies=[Depends(verify_internal_key)])
async def list_workers():
    return [worker.info() for worker in workers.values()]


@app.get("/cameras/{camera_id}", dependencies=[Depends(verify_internal_key)])
async def get_worker(camera_id: str):
    worker = workers.get(camera_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Camera worker not found")
    return worker.info()


@app.get("/cameras/{camera_id}/stream.mjpg", dependencies=[Depends(verify_internal_key)])
async def stream_camera(camera_id: str):
    worker = workers.get(camera_id)
    if not worker or not worker.running:
        raise HTTPException(status_code=404, detail="Camera is not running - start it before viewing the live feed")
    return StreamingResponse(worker.stream_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/discovery/scan", dependencies=[Depends(verify_internal_key)])
async def discovery_scan(payload: DiscoveryScanRequest):
    devices = await onvif_discovery.scan_network(payload.timeout_seconds)
    return {"devices": devices}


@app.post("/discovery/probe", dependencies=[Depends(verify_internal_key)])
async def discovery_probe(payload: DiscoveryProbeRequest):
    try:
        return await onvif_discovery.probe_device(payload.host, payload.port, payload.username, payload.password)
    except OnvifError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/discovery/test-stream", dependencies=[Depends(verify_internal_key)])
async def discovery_test_stream(payload: TestStreamRequest):
    return await onvif_discovery.test_stream(payload.rtsp_url, payload.timeout_ms)
