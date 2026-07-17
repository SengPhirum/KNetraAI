from __future__ import annotations

import logging

import numpy as np

from ..config import settings
from .base import FaceResult, bbox_center_inside, dedupe_faces
from .insightface_provider import InsightFaceProvider
from .yolo_onnx import YoloOnnxPersonDetector

logger = logging.getLogger(__name__)


class YoloCascadeProvider:
    """Two-stage "smart" detector: fast YOLO12 person localization first, then
    accurate InsightFace (SCRFD + ArcFace) face detection/embedding only inside
    the person crops.

    Why this is faster *and* more accurate than scanning the whole frame:
      - A CCTV frame is mostly background. Scanning it whole (optionally sliced
        into overlapping tiles) burns most of its compute on empty space.
        YOLO12n on ONNX Runtime finds the people in a few milliseconds, so the
        expensive face model only ever looks at the (usually small) regions
        that can actually contain a face.
      - Cropping to a person zooms in on faces that would otherwise be a few
        dozen pixels wide in a wide-angle shot, which is exactly the case
        SCRFD (and any detector) struggles with. This recovers small/far-face
        recall more cheaply than brute-force tiling the whole frame.

    A person right against the camera (e.g. a greeting kiosk) can fill the
    frame with a face but little/no visible body, which YOLO's person class
    may not fire on. To keep recall, a single full-frame InsightFace pass is
    used as a fallback whenever the crop pass finds zero faces.
    """

    def __init__(self) -> None:
        self._person_detector = YoloOnnxPersonDetector(
            model_path=settings.yolo_person_model_path,
            input_size=settings.yolo_input_size,
            providers_setting=settings.yolo_providers,
        )
        self._face_provider = InsightFaceProvider(
            det_size=settings.yolo_face_det_size,
            enable_tiling=False,
        )
        self.model_version = f"yolo_person_cascade+{self._face_provider.model_version}"

    def _person_boxes(self, frame: np.ndarray) -> list[tuple[list[int], float]]:
        frame_h = frame.shape[0]
        min_height = frame_h * settings.yolo_person_min_height_ratio
        detections = self._person_detector.detect(
            frame,
            conf_threshold=settings.yolo_person_conf,
            nms_threshold=settings.yolo_nms_threshold,
        )
        sized = [(box, score) for box, score in detections if (box[3] - box[1]) >= min_height]
        sized.sort(key=lambda item: item[1], reverse=True)
        return sized[: max(1, settings.yolo_max_persons)]

    @staticmethod
    def _padded_crop(frame: np.ndarray, box: list[int], padding_ratio: float) -> tuple[np.ndarray, tuple[int, int]]:
        frame_h, frame_w = frame.shape[:2]
        x1, y1, x2, y2 = box
        pad_x = int((x2 - x1) * padding_ratio)
        pad_y = int((y2 - y1) * padding_ratio)
        cx1 = max(0, x1 - pad_x)
        cy1 = max(0, y1 - pad_y)
        cx2 = min(frame_w, x2 + pad_x)
        cy2 = min(frame_h, y2 + pad_y)
        return frame[cy1:cy2, cx1:cx2], (cx1, cy1)

    def _detect_faces(self, frame: np.ndarray) -> list[FaceResult]:
        persons = self._person_boxes(frame)
        faces: list[FaceResult] = []
        person_only: list[FaceResult] = []

        for box, score in persons:
            crop, offset = self._padded_crop(frame, box, settings.yolo_crop_padding)
            if crop.size == 0:
                continue
            crop_faces = self._face_provider.detect_faces_in_region(crop, frame.shape, offset=offset)
            if crop_faces:
                faces.extend(crop_faces)
            elif settings.yolo_emit_person_only_detections:
                person_only.append(
                    FaceResult(
                        bbox=box,
                        confidence=score,
                        embedding=[],
                        gender=None,
                        gender_confidence=None,
                        metadata={"provider": self.model_version, "detection_kind": "person"},
                    )
                )

        if not faces and settings.yolo_fallback_full_frame:
            faces.extend(self._face_provider.detect_faces_in_region(frame, frame.shape, offset=(0, 0)))

        faces = dedupe_faces(faces, max_detections=settings.face_max_detections)
        # Drop person-only boxes whose region already contains a detected face
        # (avoids a redundant second overlay for the same person).
        person_only = [
            p for p in person_only if not any(bbox_center_inside(f.bbox, p.bbox) for f in faces)
        ]
        return faces + person_only

    def embed_image(self, path: str):
        # Registration photos are already face-centric; the cascade's win is on
        # wide-angle live camera frames, so delegate straight to InsightFace.
        return self._face_provider.embed_image(path)

    def detect_and_embed(self, frame: np.ndarray) -> list[FaceResult]:
        return self._detect_faces(frame)
