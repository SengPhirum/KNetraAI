from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from .hw import resolve_onnx_providers

logger = logging.getLogger(__name__)

COCO_PERSON_CLASS_ID = 0


class YoloOnnxPersonDetector:
    """Ultra-light YOLO12 person detector running purely on ONNX Runtime.

    Loads a standard Ultralytics YOLO ONNX export (output shape
    ``(1, 4 + num_classes, num_boxes)``, no objectness column) and returns
    only COCO class 0 ("person") boxes. No torch/ultralytics dependency is
    required at runtime; the ONNX file is produced ahead of time (see
    ``scripts/export_yolo_person_model.py`` or the Docker build's export stage).
    """

    def __init__(
        self,
        model_path: str,
        input_size: int = 640,
        providers_setting: str | None = "auto",
    ) -> None:
        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"YOLO person model not found at {model_path}. Run "
                "scripts/export_yolo_person_model.py or rebuild the ai-service image."
            )

        import onnxruntime as ort

        providers, _ctx_id = resolve_onnx_providers(providers_setting)
        session_options = ort.SessionOptions()
        session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(path), sess_options=session_options, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.input_size = int(input_size)
        logger.info("YOLO person detector ready (%s, providers=%s)", path.name, providers)

    @staticmethod
    def _letterbox(image: np.ndarray, new_size: int, color: tuple[int, int, int] = (114, 114, 114)):
        h, w = image.shape[:2]
        scale = min(new_size / h, new_size / w)
        new_w, new_h = int(round(w * scale)), int(round(h * scale))
        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        pad_w, pad_h = new_size - new_w, new_size - new_h
        left, top = pad_w // 2, pad_h // 2
        right, bottom = pad_w - left, pad_h - top
        padded = cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
        return padded, scale, left, top

    def detect(self, frame: np.ndarray, conf_threshold: float, nms_threshold: float = 0.45) -> list[tuple[list[int], float]]:
        """Returns a list of (xyxy bbox in original frame coords, confidence) for detected persons."""
        padded, scale, pad_left, pad_top = self._letterbox(frame, self.input_size)
        blob = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))[np.newaxis, ...]

        outputs = self.session.run(None, {self.input_name: blob})[0]
        # Ultralytics ONNX export: (1, 4 + num_classes, num_boxes) -> (num_boxes, 4 + num_classes)
        predictions = np.squeeze(outputs, axis=0).T

        person_scores = predictions[:, 4 + COCO_PERSON_CLASS_ID]
        keep = person_scores >= conf_threshold
        if not np.any(keep):
            return []

        boxes_cxcywh = predictions[keep, :4]
        scores = person_scores[keep]

        cx, cy, w, h = boxes_cxcywh[:, 0], boxes_cxcywh[:, 1], boxes_cxcywh[:, 2], boxes_cxcywh[:, 3]
        x1 = cx - w / 2
        y1 = cy - h / 2
        boxes_xywh = np.stack([x1, y1, w, h], axis=1)

        indices = cv2.dnn.NMSBoxes(
            boxes_xywh.tolist(),
            scores.tolist(),
            score_threshold=conf_threshold,
            nms_threshold=nms_threshold,
        )
        if len(indices) == 0:
            return []
        indices = np.array(indices).reshape(-1)

        frame_h, frame_w = frame.shape[:2]
        results: list[tuple[list[int], float]] = []
        for i in indices:
            bx1, by1, bw, bh = boxes_xywh[i]
            bx2, by2 = bx1 + bw, by1 + bh
            # Undo letterbox: remove padding, then rescale to original frame size.
            ox1 = (bx1 - pad_left) / scale
            oy1 = (by1 - pad_top) / scale
            ox2 = (bx2 - pad_left) / scale
            oy2 = (by2 - pad_top) / scale
            bbox = [
                max(0, min(frame_w - 1, int(round(ox1)))),
                max(0, min(frame_h - 1, int(round(oy1)))),
                max(0, min(frame_w - 1, int(round(ox2)))),
                max(0, min(frame_h - 1, int(round(oy2)))),
            ]
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                continue
            results.append((bbox, float(scores[i])))
        return results
