from __future__ import annotations

import cv2
import numpy as np

from ..config import settings
from .base import EmbeddingResult, FaceResult, normalize_vector


class InsightFaceProvider:
    """InsightFace provider for production-style deep-learning embeddings.

    Requires optional packages:
        insightface
        onnxruntime or onnxruntime-gpu
    """

    model_version = "insightface_arcface_512"

    def __init__(self) -> None:
        from insightface.app import FaceAnalysis

        self.app = FaceAnalysis(name=settings.insightface_model, providers=["CPUExecutionProvider"])
        self.app.prepare(ctx_id=-1, det_size=(640, 640))

    def _face_to_result(self, face) -> FaceResult:
        embedding = normalize_vector(np.asarray(face.normed_embedding, dtype="float32"), size=512)
        gender = None
        gender_confidence = None
        if hasattr(face, "gender"):
            # InsightFace commonly returns 1 for male and 0 for female.
            gender = "male" if int(face.gender) == 1 else "female"
            gender_confidence = 0.80
        bbox = [int(v) for v in face.bbox.tolist()]
        return FaceResult(
            bbox=bbox,
            confidence=float(getattr(face, "det_score", 0.0)),
            embedding=embedding,
            gender=gender,
            gender_confidence=gender_confidence,
            metadata={"provider": self.model_version},
        )

    def _is_valid_face(self, face, frame_shape) -> bool:
        score = float(getattr(face, "det_score", 0.0))
        if score < settings.face_min_confidence:
            return False
        frame_h, frame_w = frame_shape[:2]
        bx = face.bbox
        width = max(0.0, float(bx[2] - bx[0]))
        height = max(0.0, float(bx[3] - bx[1]))
        if width <= 0 or height <= 0:
            return False
        area_ratio = (width * height) / max(1.0, float(frame_w * frame_h))
        if area_ratio < settings.face_min_area_ratio or area_ratio > settings.face_max_area_ratio:
            return False
        aspect_ratio = width / max(1.0, height)
        return 0.65 <= aspect_ratio <= 1.45

    def embed_image(self, path: str) -> EmbeddingResult:
        image = cv2.imread(path)
        if image is None:
            raise ValueError(f"Could not read image: {path}")
        faces = [face for face in self.app.get(image) if self._is_valid_face(face, image.shape)]
        if not faces:
            raise ValueError("No face found in image")
        largest = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        face_result = self._face_to_result(largest)
        h, w = image.shape[:2]
        bx = largest.bbox
        area = max(0.0, float((bx[2] - bx[0]) * (bx[3] - bx[1])))
        quality = min(1.0, area / max(1.0, float(w * h)) * 4.0)
        return EmbeddingResult(
            embedding=face_result.embedding,
            model_version=self.model_version,
            quality_score=quality,
            metadata={"faces_found": len(faces)},
        )

    def detect_and_embed(self, frame: np.ndarray) -> list[FaceResult]:
        return [self._face_to_result(face) for face in self.app.get(frame) if self._is_valid_face(face, frame.shape)]
