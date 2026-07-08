from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..config import settings
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
        eye_cascade_path = cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml"
        self.face_cascade = cv2.CascadeClassifier(cascade_path)
        self.eye_cascade = cv2.CascadeClassifier(eye_cascade_path)
        self.person_detector = cv2.HOGDescriptor()
        self.person_detector.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

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

    def _valid_eye_count(self, gray: np.ndarray, x: int, y: int, w: int, h: int) -> int:
        if not settings.opencv_require_eye_validation or self.eye_cascade.empty():
            return settings.opencv_min_eyes
        upper_face = gray[y : y + max(1, int(h * 0.68)), x : x + w]
        min_eye = max(8, int(min(w, h) * 0.10))
        eyes = self.eye_cascade.detectMultiScale(
            upper_face,
            scaleFactor=1.08,
            minNeighbors=4,
            minSize=(min_eye, min_eye),
        )
        return len(eyes)

    def _is_plausible_face(self, gray: np.ndarray, x: int, y: int, w: int, h: int) -> bool:
        frame_h, frame_w = gray.shape[:2]
        if w <= 0 or h <= 0:
            return False
        area_ratio = (w * h) / max(1, frame_w * frame_h)
        if area_ratio < settings.face_min_area_ratio or area_ratio > settings.face_max_area_ratio:
            return False
        aspect_ratio = w / max(1, h)
        if aspect_ratio < 0.72 or aspect_ratio > 1.35:
            return False
        if settings.opencv_require_eye_validation:
            return self._valid_eye_count(gray, x, y, w, h) >= settings.opencv_min_eyes
        return True

    def _detect_faces(self, image: np.ndarray) -> list[tuple[int, int, int, int]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        gray = cv2.equalizeHist(gray)
        min_size = max(24, int(settings.opencv_face_min_size))
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=float(settings.opencv_face_scale_factor),
            minNeighbors=int(settings.opencv_face_min_neighbors),
            minSize=(min_size, min_size),
        )
        results: list[tuple[int, int, int, int]] = []
        for x, y, w, h in faces:
            x, y, w, h = int(x), int(y), int(w), int(h)
            if self._is_plausible_face(gray, x, y, w, h):
                results.append((x, y, w, h))
        return results

    @staticmethod
    def _iou(box_a: tuple[int, int, int, int], box_b: tuple[int, int, int, int]) -> float:
        ax, ay, aw, ah = box_a
        bx, by, bw, bh = box_b
        ax2, ay2 = ax + aw, ay + ah
        bx2, by2 = bx + bw, by + bh
        ix1, iy1 = max(ax, bx), max(ay, by)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        if inter <= 0:
            return 0.0
        union = aw * ah + bw * bh - inter
        return inter / max(1, union)

    def _detect_people(self, image: np.ndarray, face_boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int, float]]:
        if not settings.opencv_enable_person_detector:
            return []
        frame_h, frame_w = image.shape[:2]
        detector_image = image
        scale_back = 1.0
        if frame_w > 720:
            scale_back = frame_w / 720.0
            detector_image = cv2.resize(image, (720, int(frame_h / scale_back)), interpolation=cv2.INTER_AREA)
        rects, weights = self.person_detector.detectMultiScale(
            detector_image,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
            hitThreshold=float(settings.opencv_person_hit_threshold),
        )
        people: list[tuple[int, int, int, int, float]] = []
        for index, rect in enumerate(rects):
            x, y, w, h = [int(round(float(v) * scale_back)) for v in rect]
            if h < settings.opencv_person_min_height:
                continue
            aspect_ratio = w / max(1, h)
            if aspect_ratio < 0.20 or aspect_ratio > 0.90:
                continue
            area_ratio = (w * h) / max(1, frame_w * frame_h)
            if area_ratio < settings.face_min_area_ratio or area_ratio > 0.75:
                continue
            if any(self._iou((x, y, w, h), face_box) > 0.15 for face_box in face_boxes):
                continue
            raw_weight = weights[index] if index < len(weights) else 0.0
            try:
                weight = float(raw_weight[0])
            except (TypeError, IndexError):
                weight = float(raw_weight)
            people.append((x, y, w, h, weight))
        return people

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
            gender = None
            gender_conf = None
            if settings.opencv_enable_mock_gender:
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
        for x, y, w, h, weight in self._detect_people(frame, faces):
            results.append(
                FaceResult(
                    bbox=[x, y, x + w, y + h],
                    confidence=max(0.50, min(0.99, 0.50 + weight / 2.0)),
                    embedding=[],
                    gender=None,
                    gender_confidence=None,
                    metadata={"provider": self.model_version, "detection_kind": "person"},
                )
            )
        return results
