from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

import cv2

from .backend_client import BackendClient
from .config import settings
from .schemas import CameraStartRequest
from .vision.base import FaceResult, VisionProvider

logger = logging.getLogger(__name__)


class CameraWorker:
    def __init__(self, camera: CameraStartRequest, provider: VisionProvider, backend: BackendClient) -> None:
        self.camera = camera
        self.provider = provider
        self.backend = backend
        self.task: asyncio.Task | None = None
        self.running = False
        self.ai_enabled = camera.ai_enabled
        self.status = "stopped"
        self.last_error: str | None = None
        self.last_greeting_at: dict[str, float] = {}
        self.latest_jpeg: bytes | None = None
        self.latest_faces: list[dict[str, Any]] = []
        self.frame_version = 0
        self._frame_condition = asyncio.Condition()

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.status = "starting"
        self.task = asyncio.create_task(self._run(), name=f"camera-worker-{self.camera.id}")

    async def stop(self) -> None:
        self.running = False
        self.status = "stopped"
        async with self._frame_condition:
            self._frame_condition.notify_all()
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def info(self) -> dict[str, Any]:
        return {
            "id": self.camera.id,
            "name": self.camera.name,
            "status": self.status,
            "last_error": self.last_error,
            "running": self.running,
            "ai_enabled": self.ai_enabled,
            "faces": self.latest_faces,
        }

    def set_ai_enabled(self, enabled: bool) -> None:
        self.ai_enabled = enabled
        self.camera.ai_enabled = enabled
        if not enabled:
            self.latest_faces = []

    async def _run(self) -> None:
        min_interval = 1.0 / max(0.1, float(settings.process_fps))
        while self.running:
            cap = None
            try:
                self.status = "connecting"
                cap = cv2.VideoCapture(self.camera.rtsp_url)
                if not cap.isOpened():
                    raise RuntimeError("Could not open camera stream")
                self.status = "running"
                last_processed = 0.0
                while self.running:
                    ok, frame = await asyncio.to_thread(cap.read)
                    if not ok or frame is None:
                        raise RuntimeError("Camera frame read failed")
                    now = monotonic()
                    if self.ai_enabled and now - last_processed >= min_interval:
                        last_processed = now
                        faces = await asyncio.to_thread(self.provider.detect_and_embed, frame)
                        overlays: list[dict[str, Any]] = []
                        for face in faces:
                            if face.metadata.get("detection_kind") == "person" or not face.embedding:
                                recognition = {"known": False}
                                overlays.append(self._face_overlay(face, recognition))
                                continue
                            recognition = await self.backend.recognize(face.embedding)
                            overlays.append(self._face_overlay(face, recognition))
                            await self._handle_face(frame, face, recognition)
                        self.latest_faces = overlays
                    elif not self.ai_enabled and self.latest_faces:
                        self.latest_faces = []

                    await self._publish_frame(frame)
                    if self.ai_enabled and now - last_processed < min_interval:
                        await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                self.status = "reconnecting"
                logger.warning("Camera %s error: %s", self.camera.id, exc)
                await asyncio.sleep(3)
            finally:
                if cap is not None:
                    cap.release()
        self.status = "stopped"

    async def _publish_frame(self, frame) -> None:
        overlays = list(self.latest_faces) if self.ai_enabled else []
        jpeg = await asyncio.to_thread(self._encode_frame, frame, overlays)
        if jpeg is None:
            return
        async with self._frame_condition:
            self.latest_jpeg = jpeg
            self.frame_version += 1
            self._frame_condition.notify_all()

    @staticmethod
    def _encode_frame(frame, overlays: list[dict[str, Any]] | None = None) -> bytes | None:
        if overlays:
            frame = frame.copy()
            for overlay in overlays:
                CameraWorker._draw_face_overlay(frame, overlay)
        height, width = frame.shape[:2]
        if width > settings.stream_max_width > 0:
            scale = settings.stream_max_width / width
            frame = cv2.resize(frame, (settings.stream_max_width, int(height * scale)))
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(settings.stream_jpeg_quality)])
        return buf.tobytes() if ok else None

    @staticmethod
    def _draw_face_overlay(frame, overlay: dict[str, Any]) -> None:
        bbox = overlay.get("bbox") or []
        if len(bbox) != 4:
            return
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1 = max(0, min(width - 1, x1))
        x2 = max(0, min(width - 1, x2))
        y1 = max(0, min(height - 1, y1))
        y2 = max(0, min(height - 1, y2))
        if x2 <= x1 or y2 <= y1:
            return

        green = (34, 197, 94)
        cv2.rectangle(frame, (x1, y1), (x2, y2), green, 2)
        label = f"Type: {overlay.get('type_label', 'N/A')} | Gender: {overlay.get('gender_label', 'N/A')}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.52
        thickness = 1
        (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)
        label_y = max(text_height + 8, y1 - 6)
        label_x = min(x1, max(0, width - text_width - 10))
        label_x2 = min(width - 1, label_x + text_width + 10)
        cv2.rectangle(frame, (label_x, label_y - text_height - 8), (label_x2, label_y + baseline), green, -1)
        cv2.putText(frame, label, (label_x + 5, label_y - 5), font, font_scale, (2, 6, 23), thickness, cv2.LINE_AA)

    async def stream_frames(self):
        """Async generator of multipart/x-mixed-replace JPEG chunks for the live view."""
        last_seen = -1
        while self.running:
            async with self._frame_condition:
                try:
                    await asyncio.wait_for(
                        self._frame_condition.wait_for(
                            lambda: self.frame_version != last_seen or not self.running
                        ),
                        timeout=10,
                    )
                except asyncio.TimeoutError:
                    continue
                if not self.running:
                    break
                last_seen = self.frame_version
                jpeg = self.latest_jpeg
            if not jpeg:
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"
            )

    def _face_overlay(self, face: FaceResult, recognition: dict[str, Any]) -> dict[str, Any]:
        person_type = recognition.get("person_type") if recognition.get("known") else None
        detection_kind = face.metadata.get("detection_kind", "face")
        gender = (
            face.gender
            if face.gender in ("male", "female")
            and (face.gender_confidence or 0.0) >= settings.gender_min_confidence
            else None
        )
        return {
            "bbox": face.bbox,
            "type": person_type or "unknown",
            "type_label": person_type.title() if person_type else "N/A",
            "gender": gender or "unknown",
            "gender_label": "M" if gender == "male" else "F" if gender == "female" else "N/A",
            "confidence": recognition.get("similarity") if recognition.get("known") else face.confidence,
            "detection_kind": detection_kind,
        }

    async def _handle_face(self, frame, face: FaceResult, recognition: dict[str, Any]) -> None:
        known = bool(recognition.get("known"))
        person_id = recognition.get("person_id") if known else None
        person_type = recognition.get("person_type") if known else "unknown"
        similarity = recognition.get("similarity") if known else None
        gender_estimate = (
            face.gender
            if face.gender in ("male", "female")
            and (face.gender_confidence or 0.0) >= settings.gender_min_confidence
            else None
        )
        cooldown_key = f"person:{person_id}" if person_id else f"unknown:{self.camera.id}:{gender_estimate or 'unknown'}"
        now = monotonic()
        last = self.last_greeting_at.get(cooldown_key, 0.0)
        if now - last < settings.greeting_cooldown_seconds:
            return
        self.last_greeting_at[cooldown_key] = now

        greeting = self._build_greeting(recognition, face)
        snapshot_rel = self._save_snapshot(frame)
        payload = {
            "camera_id": self.camera.id,
            "person_id": person_id,
            "person_type": person_type or "unknown",
            "confidence": similarity if known else face.confidence,
            "gender_estimate": gender_estimate,
            "gender_confidence": face.gender_confidence if gender_estimate else None,
            "greeting": greeting,
            "snapshot_path": snapshot_rel,
            "raw": {
                "bbox": face.bbox,
                "recognition": recognition,
                "face_confidence": face.confidence,
                "provider": self.provider.model_version,
            },
        }
        await self.backend.create_detection_event(payload)

    def _build_greeting(self, recognition: dict[str, Any], face: FaceResult) -> str:
        hour = datetime.now().hour
        if hour < 12:
            prefix = "Good morning"
        elif hour < 18:
            prefix = "Good afternoon"
        else:
            prefix = "Good evening"

        if recognition.get("known"):
            return f"{prefix}, {recognition.get('full_name')}"

        if face.gender and (face.gender_confidence or 0.0) >= settings.gender_min_confidence:
            if face.gender == "male":
                return "Hello sir"
            if face.gender == "female":
                return "Hello madam"
        return "Hello, welcome"

    def _save_snapshot(self, frame) -> str:
        today = datetime.now().strftime("%Y/%m/%d")
        rel_dir = Path("snapshots") / today
        abs_dir = Path(settings.storage_dir) / rel_dir
        abs_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid4().hex}.jpg"
        abs_path = abs_dir / filename
        cv2.imwrite(str(abs_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(settings.snapshot_jpeg_quality)])
        return str(rel_dir / filename)
