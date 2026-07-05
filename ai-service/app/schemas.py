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
