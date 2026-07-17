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


def bbox_iou(box_a: list[int], box_b: list[int]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    return inter / max(1, area_a + area_b - inter)


def is_valid_face_bbox(
    bbox: list[int],
    score: float,
    frame_shape: tuple[int, int] | tuple[int, int, int],
    min_confidence: float,
    min_area_ratio: float,
    max_area_ratio: float,
    min_aspect: float = 0.65,
    max_aspect: float = 1.45,
) -> bool:
    if score < min_confidence:
        return False
    frame_h, frame_w = frame_shape[:2]
    width = max(0.0, float(bbox[2] - bbox[0]))
    height = max(0.0, float(bbox[3] - bbox[1]))
    if width <= 0 or height <= 0:
        return False
    area_ratio = (width * height) / max(1.0, float(frame_w * frame_h))
    if area_ratio < min_area_ratio or area_ratio > max_area_ratio:
        return False
    aspect_ratio = width / max(1.0, height)
    return min_aspect <= aspect_ratio <= max_aspect


def bbox_center_inside(inner: list[int], outer: list[int]) -> bool:
    """True if the center point of ``inner`` falls within ``outer``.

    Unlike IoU, this is meaningful when the two boxes are very different sizes
    (e.g. a face box versus the person box it was found in) where IoU is
    always small even when one box is fully contained in the other.
    """
    cx = (inner[0] + inner[2]) / 2.0
    cy = (inner[1] + inner[3]) / 2.0
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def dedupe_faces(faces: list[FaceResult], max_detections: int, iou_threshold: float = 0.35) -> list[FaceResult]:
    ordered = sorted(
        faces,
        key=lambda item: (
            item.confidence,
            max(0, item.bbox[2] - item.bbox[0]) * max(0, item.bbox[3] - item.bbox[1]),
        ),
        reverse=True,
    )
    kept: list[FaceResult] = []
    for face in ordered:
        if all(bbox_iou(face.bbox, existing.bbox) < iou_threshold for existing in kept):
            kept.append(face)
        if len(kept) >= max_detections:
            break
    return kept
