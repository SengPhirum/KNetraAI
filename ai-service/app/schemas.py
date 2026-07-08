from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class CameraStartRequest(BaseModel):
    id: str
    name: str
    rtsp_url: str
    branch: str | None = None
    location: str | None = None


class EmbeddingFromPathRequest(BaseModel):
    path: str


class EmbeddingResponse(BaseModel):
    embedding: list[float]
    model_version: str
    quality_score: float | None = None
    metadata: dict[str, Any] = {}


class DiscoveryScanRequest(BaseModel):
    timeout_seconds: float | None = None


class DiscoveryProbeRequest(BaseModel):
    host: str
    port: int = 80
    username: str = ""
    password: str = ""


class TestStreamRequest(BaseModel):
    rtsp_url: str
    timeout_ms: int = 6000
