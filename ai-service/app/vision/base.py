from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np


@dataclass
class FaceResult:
    bbox: list[int]
    confidence: float
    embedding: list[float]
    gender: str | None = None
    gender_confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingResult:
    embedding: list[float]
    model_version: str
    quality_score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class VisionProvider(Protocol):
    model_version: str

    def embed_image(self, path: str) -> EmbeddingResult:
        ...

    def detect_and_embed(self, frame: np.ndarray) -> list[FaceResult]:
        ...


def normalize_vector(vector: np.ndarray, size: int = 512) -> list[float]:
    flat = vector.astype("float32").reshape(-1)
    if flat.size < size:
        flat = np.pad(flat, (0, size - flat.size), mode="constant")
    if flat.size > size:
        flat = flat[:size]
    norm = float(np.linalg.norm(flat))
    if norm < 1e-8:
        flat = np.ones(size, dtype="float32") / np.sqrt(size)
    else:
        flat = flat / norm
    return [float(x) for x in flat]
