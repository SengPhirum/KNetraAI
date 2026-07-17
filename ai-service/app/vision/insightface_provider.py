from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path

os.environ.setdefault("ORT_LOG_SEVERITY_LEVEL", "3")

import cv2
import numpy as np

from ..config import settings
from .base import EmbeddingResult, FaceResult, dedupe_faces, is_valid_face_bbox, normalize_vector
from .hw import apply_thread_settings, resolve_onnx_providers


class InsightFaceProvider:
    """InsightFace provider for production-style deep-learning embeddings.

    Requires optional packages:
        insightface
        onnxruntime or onnxruntime-gpu

    ``det_size`` and ``enable_tiling`` can be overridden per instance so callers
    (e.g. the YOLO person cascade) can run a second, cheaper-tuned instance for
    face detection on already-cropped person regions.
    """

    model_version = "insightface_arcface_512"

    def __init__(self, det_size: int | None = None, enable_tiling: bool | None = None) -> None:
        with self._quiet_native_startup_output():
            self._configure_onnxruntime_logging()

            from insightface.app import FaceAnalysis

            self._configure_model_downloader()
            providers, auto_ctx_id = resolve_onnx_providers(settings.insightface_providers)
            ctx_id = auto_ctx_id if int(settings.insightface_ctx_id) == -2 else int(settings.insightface_ctx_id)
            self._enable_tiling = (
                settings.insightface_enable_tiled_detection if enable_tiling is None else enable_tiling
            )
            resolved_det_size = max(320, int(det_size if det_size is not None else settings.insightface_det_size))
            self.model_version = f"insightface_{settings.insightface_model}_{resolved_det_size}"

            self._configure_thread_settings()
            self.app = FaceAnalysis(
                name=settings.insightface_model,
                root=settings.insightface_model_root,
                providers=providers,
            )
            self.app.prepare(
                ctx_id=ctx_id,
                det_thresh=float(settings.face_min_confidence),
                det_size=(resolved_det_size, resolved_det_size),
            )

    @staticmethod
    @contextmanager
    def _quiet_native_startup_output():
        try:
            stdout_fd = sys.stdout.fileno()
            stderr_fd = sys.stderr.fileno()
        except (AttributeError, OSError, ValueError):
            yield
            return

        saved_stdout = os.dup(stdout_fd)
        saved_stderr = os.dup(stderr_fd)
        try:
            with open(os.devnull, "w") as sink:
                os.dup2(sink.fileno(), stdout_fd)
                os.dup2(sink.fileno(), stderr_fd)
                yield
        finally:
            os.dup2(saved_stdout, stdout_fd)
            os.dup2(saved_stderr, stderr_fd)
            os.close(saved_stdout)
            os.close(saved_stderr)

    @staticmethod
    def _configure_thread_settings() -> None:
        """FaceAnalysis loads each sub-model (detector, recognizer, genderage, ...)
        through insightface.model_zoo.get_model(), which only ever forwards
        ``providers``/``provider_options`` on to onnxruntime - any other kwarg
        (including ``sess_options``) is silently dropped, so there's no supported
        way to hand it a tuned SessionOptions directly. Patch the InferenceSession
        subclass it instantiates internally instead, so every sub-model it loads
        picks up our thread-count cap without needing insightface to support it.
        Only patches anything if onnx_intra/inter_op_threads are actually set
        (default "high" profile leaves ONNX Runtime's own defaults untouched).
        """
        if int(settings.onnx_intra_op_threads) <= 0 and int(settings.onnx_inter_op_threads) <= 0:
            return

        from insightface.model_zoo import model_zoo as _model_zoo

        session_cls = _model_zoo.PickableInferenceSession
        if getattr(session_cls, "_knetraai_thread_patched", False):
            return

        import onnxruntime as ort

        original_init = session_cls.__init__

        def patched_init(self, model_path, **kwargs):
            if "sess_options" not in kwargs:
                opts = ort.SessionOptions()
                apply_thread_settings(opts)
                kwargs["sess_options"] = opts
            original_init(self, model_path, **kwargs)

        session_cls.__init__ = patched_init
        session_cls._knetraai_thread_patched = True

    @staticmethod
    def _configure_onnxruntime_logging() -> None:
        try:
            import onnxruntime as ort

            ort.set_default_logger_severity(3)  # ERROR: hide harmless CPU-only device discovery warnings.
        except Exception:
            pass

    @staticmethod
    def _configure_model_downloader() -> None:
        Path(settings.insightface_model_root).mkdir(parents=True, exist_ok=True)
        if not settings.insightface_insecure_model_download:
            return

        import requests
        from insightface.utils import download as download_module
        from insightface.utils import storage as storage_module

        def download_file(url, path=None, overwrite=False, sha1_hash=None, **kwargs):
            target = Path(path or url.rsplit("/", 1)[-1])
            if target.exists() and not overwrite:
                return str(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            with requests.get(url, stream=True, verify=False, timeout=120) as response:
                response.raise_for_status()
                with target.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            handle.write(chunk)
            return str(target)

        download_module.download_file = download_file
        storage_module.download_file = download_file

    def _face_to_result(self, face, frame_shape, offset: tuple[int, int] = (0, 0)) -> FaceResult:
        embedding = normalize_vector(np.asarray(face.normed_embedding, dtype="float32"), size=512)
        gender = None
        gender_confidence = None
        if hasattr(face, "gender"):
            # InsightFace commonly returns 1 for male and 0 for female.
            gender = "male" if int(face.gender) == 1 else "female"
            gender_confidence = 0.80
        frame_h, frame_w = frame_shape[:2]
        offset_x, offset_y = offset
        x1, y1, x2, y2 = [int(round(float(v))) for v in face.bbox.tolist()]
        x1 += offset_x
        x2 += offset_x
        y1 += offset_y
        y2 += offset_y
        bbox = [
            max(0, min(frame_w - 1, x1)),
            max(0, min(frame_h - 1, y1)),
            max(0, min(frame_w - 1, x2)),
            max(0, min(frame_h - 1, y2)),
        ]
        return FaceResult(
            bbox=bbox,
            confidence=float(getattr(face, "det_score", 0.0)),
            embedding=embedding,
            gender=gender,
            gender_confidence=gender_confidence,
            metadata={"provider": self.model_version, "detection_kind": "face"},
        )

    def _is_valid_bbox(self, bbox: list[int], score: float, frame_shape) -> bool:
        return is_valid_face_bbox(
            bbox,
            score,
            frame_shape,
            min_confidence=settings.face_min_confidence,
            min_area_ratio=settings.face_min_area_ratio,
            max_area_ratio=settings.face_max_area_ratio,
        )

    def _is_valid_face(self, face, frame_shape, offset: tuple[int, int] = (0, 0)) -> bool:
        result = self._face_to_result(face, frame_shape, offset)
        return self._is_valid_bbox(result.bbox, result.confidence, frame_shape)

    def _dedupe_faces(self, faces: list[FaceResult]) -> list[FaceResult]:
        return dedupe_faces(faces, max_detections=settings.face_max_detections)

    def _tile_regions(self, frame: np.ndarray) -> list[tuple[int, int, np.ndarray]]:
        frame_h, frame_w = frame.shape[:2]
        if (
            not self._enable_tiling
            or frame_w < settings.insightface_tile_min_width
            or frame_h < 480
        ):
            return []

        overlap = min(0.45, max(0.0, float(settings.insightface_tile_overlap)))
        tile_w = int(frame_w * (0.5 + overlap / 2.0))
        tile_h = int(frame_h * (0.5 + overlap / 2.0))
        x_positions = [0, max(0, frame_w - tile_w)]
        y_positions = [0, max(0, frame_h - tile_h)]
        regions: list[tuple[int, int, np.ndarray]] = []
        for y in y_positions:
            for x in x_positions:
                tile = frame[y : y + tile_h, x : x + tile_w]
                if tile.size:
                    regions.append((x, y, tile))
        return regions

    def _detect_faces(self, frame: np.ndarray) -> list[FaceResult]:
        detected: list[FaceResult] = []
        for face in self.app.get(frame):
            result = self._face_to_result(face, frame.shape)
            if self._is_valid_bbox(result.bbox, result.confidence, frame.shape):
                detected.append(result)

        for offset_x, offset_y, tile in self._tile_regions(frame):
            for face in self.app.get(tile):
                result = self._face_to_result(face, frame.shape, (offset_x, offset_y))
                if self._is_valid_bbox(result.bbox, result.confidence, frame.shape):
                    result.metadata["source"] = "tile"
                    detected.append(result)
        return self._dedupe_faces(detected)

    def detect_faces_in_region(
        self,
        region: np.ndarray,
        full_frame_shape: tuple[int, int] | tuple[int, int, int],
        offset: tuple[int, int] = (0, 0),
    ) -> list[FaceResult]:
        """Run face detection on a sub-image (e.g. a YOLO person crop).

        Bounding boxes are translated by ``offset`` and validated against
        ``full_frame_shape`` so area-ratio thresholds stay meaningful relative
        to the whole scene rather than the crop.
        """
        detected: list[FaceResult] = []
        for face in self.app.get(region):
            result = self._face_to_result(face, full_frame_shape, offset)
            if self._is_valid_bbox(result.bbox, result.confidence, full_frame_shape):
                detected.append(result)
        return detected

    def embed_image(self, path: str) -> EmbeddingResult:
        image = cv2.imread(path)
        if image is None:
            raise ValueError(f"Could not read image: {path}")
        faces = self._detect_faces(image)
        if not faces:
            raise ValueError("No face found in image")
        face_result = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        h, w = image.shape[:2]
        bx = face_result.bbox
        area = max(0.0, float((bx[2] - bx[0]) * (bx[3] - bx[1])))
        quality = min(1.0, area / max(1.0, float(w * h)) * 4.0)
        return EmbeddingResult(
            embedding=face_result.embedding,
            model_version=self.model_version,
            quality_score=quality,
            metadata={"faces_found": len(faces), "provider": self.model_version},
        )

    def detect_and_embed(self, frame: np.ndarray) -> list[FaceResult]:
        return self._detect_faces(frame)
