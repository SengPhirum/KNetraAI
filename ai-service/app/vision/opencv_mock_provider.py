from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .base import EmbeddingResult, FaceResult, normalize_vector


class OpenCVMvpProvider:
    """Lightweight development provider.

    This provider is not production face recognition. It keeps the full app runnable
    without downloading large deep-learning models. Use InsightFace provider for real
    face detection, embeddings, and gender estimation.
    """

    model_version = "opencv_mock_embedding_512_v1"

    def __init__(self) -> None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

    def _embedding_from_crop(self, crop: np.ndarray) -> list[float]:
        if crop.size == 0:
            crop = np.zeros((64, 64, 3), dtype="uint8")
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        resized = cv2.resize(gray, (32, 16), interpolation=cv2.INTER_AREA).astype("float32") / 255.0
        resized = resized - float(resized.mean())
        return normalize_vector(resized, size=512)

    def _estimate_gender_for_dev(self, embedding: list[float]) -> tuple[str, float]:
        # Deterministic low-confidence development heuristic only.
        score = int(abs(sum(embedding[:32])) * 100000) % 2
        return ("male" if score == 0 else "female", 0.52)

    def _detect_faces(self, image: np.ndarray) -> list[tuple[int, int, int, int]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]

    def embed_image(self, path: str) -> EmbeddingResult:
        image = cv2.imread(path)
        if image is None:
            raise ValueError(f"Could not read image: {path}")
        faces = self._detect_faces(image)
        h, w = image.shape[:2]
        if faces:
            x, y, fw, fh = max(faces, key=lambda item: item[2] * item[3])
            crop = image[y : y + fh, x : x + fw]
            quality = min(1.0, float((fw * fh) / max(1, w * h)) * 4.0)
        else:
            crop = image
            quality = 0.25
        return EmbeddingResult(
            embedding=self._embedding_from_crop(crop),
            model_version=self.model_version,
            quality_score=quality,
            metadata={"faces_found": len(faces), "source": str(Path(path).name)},
        )

    def detect_and_embed(self, frame: np.ndarray) -> list[FaceResult]:
        faces = self._detect_faces(frame)
        results: list[FaceResult] = []
        for x, y, w, h in faces:
            crop = frame[y : y + h, x : x + w]
            embedding = self._embedding_from_crop(crop)
            gender, gender_conf = self._estimate_gender_for_dev(embedding)
            results.append(
                FaceResult(
                    bbox=[x, y, x + w, y + h],
                    confidence=0.70,
                    embedding=embedding,
                    gender=gender,
                    gender_confidence=gender_conf,
                    metadata={"provider": self.model_version},
                )
            )
        return results
