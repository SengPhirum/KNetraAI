from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

import cv2
import numpy as np

from .backend_client import BackendClient
from .config import settings
from .schemas import CameraStartRequest
from .vision.base import FaceResult, VisionProvider

logger = logging.getLogger(__name__)

# Shared across every CameraWorker in this process. On a constrained device (e.g. a
# 4-core Raspberry Pi), letting every running camera try to run YOLO/InsightFace at the
# same instant thrashes the CPU far worse than making them take turns - each inference
# finishes faster with exclusive use of the core budget than all of them crawling
# forward in parallel. 0/unset means unlimited (desktop/server-class hosts).
_inference_semaphore: asyncio.Semaphore | None = (
    asyncio.Semaphore(settings.max_concurrent_inference) if settings.max_concurrent_inference > 0 else None
)


class _LatestFrameReader:
    """Reads an RTSP stream on a dedicated thread and keeps only the newest frame.

    A plain synchronous ``cap.read()`` loop backs up: if AI processing takes
    longer than the camera's frame interval, OpenCV's internal buffer (or the
    RTSP source itself) queues up unread frames, and the live view/detections
    drift further and further behind wall-clock time. Reading continuously on
    its own thread and always exposing only the latest frame keeps the worker
    loop free to process/publish at whatever rate it can sustain without ever
    falling behind.
    """

    def __init__(self, rtsp_url: str) -> None:
        self._cap = cv2.VideoCapture(rtsp_url)
        try:
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._frame_id = 0
        self._error: str | None = None
        self._running = self._cap.isOpened()
        self._thread: threading.Thread | None = None
        if self._running:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def isOpened(self) -> bool:
        return self._cap.isOpened()

    def _loop(self) -> None:
        while self._running:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                with self._lock:
                    self._error = "Camera frame read failed"
                    self._running = False
                return
            with self._lock:
                self._frame = frame
                self._frame_id += 1

    def latest(self) -> tuple[int, np.ndarray | None, str | None]:
        with self._lock:
            return self._frame_id, self._frame, self._error

    def release(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._cap.release()


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
        # Per-person presence sessions: tracks who is currently in this camera's
        # zone so a person is greeted once per visit instead of on a fixed timer.
        # key -> {"last_seen": t, "greeted_at": t, "announced": bool}
        self.presence: dict[str, dict[str, Any]] = {}
        self._presence_pruned_at = 0.0
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
            reader: _LatestFrameReader | None = None
            try:
                self.status = "connecting"
                reader = await asyncio.to_thread(_LatestFrameReader, self.camera.rtsp_url)
                if not reader.isOpened():
                    raise RuntimeError("Could not open camera stream")
                self.status = "running"
                last_processed = 0.0
                last_frame_id = -1
                motion_reference: np.ndarray | None = None
                # Rolling estimate of how long this device actually takes to run
                # inference, used to self-pace the target rate on slower hardware
                # instead of continuously trying (and failing) to hit process_fps.
                inference_time_ema: float | None = None
                while self.running:
                    frame_id, frame, error = reader.latest()
                    if error:
                        raise RuntimeError(error)
                    if frame is None or frame_id == last_frame_id:
                        await asyncio.sleep(0.01)
                        continue
                    last_frame_id = frame_id

                    now = monotonic()
                    effective_min_interval = min_interval
                    if settings.adaptive_frame_skip and inference_time_ema is not None:
                        effective_min_interval = max(min_interval, inference_time_ema * 1.1)
                    should_process = self.ai_enabled and now - last_processed >= effective_min_interval
                    if should_process and settings.motion_gating_enabled:
                        should_process, motion_reference = self._gate_on_motion(
                            frame, motion_reference, now, last_processed
                        )
                    if should_process:
                        last_processed = now
                        inference_started = monotonic()
                        faces = await self._detect(frame)
                        if settings.adaptive_frame_skip:
                            elapsed = monotonic() - inference_started
                            inference_time_ema = (
                                elapsed if inference_time_ema is None else (0.7 * inference_time_ema + 0.3 * elapsed)
                            )
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
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                self.status = "reconnecting"
                logger.warning("Camera %s error: %s", self.camera.id, exc)
                await asyncio.sleep(3)
            finally:
                if reader is not None:
                    await asyncio.to_thread(reader.release)
        self.status = "stopped"

    async def _detect(self, frame: np.ndarray) -> list[FaceResult]:
        if _inference_semaphore is not None:
            async with _inference_semaphore:
                return await asyncio.to_thread(self.provider.detect_and_embed, frame)
        return await asyncio.to_thread(self.provider.detect_and_embed, frame)

    @staticmethod
    def _gate_on_motion(
        frame: np.ndarray,
        reference: np.ndarray | None,
        now: float,
        last_processed: float,
    ) -> tuple[bool, np.ndarray]:
        """Cheap grayscale-diff motion gate for skipping AI inference on an
        unchanged scene, with a periodic idle poll as a safety net so a person
        who walks in and immediately holds still is still caught."""
        small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (160, 90))
        if reference is None:
            return True, small
        diff = cv2.absdiff(small, reference)
        changed_ratio = float(np.count_nonzero(diff > 25)) / diff.size
        motion_detected = changed_ratio >= settings.motion_gating_min_area_ratio
        idle_timeout = now - last_processed >= settings.motion_gating_idle_interval_seconds
        return (motion_detected or idle_timeout), small

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

    def _gender_min_confidence(self) -> float:
        return float(self.backend.cached_runtime_settings.get("gender_min_confidence", settings.gender_min_confidence))

    def _face_overlay(self, face: FaceResult, recognition: dict[str, Any]) -> dict[str, Any]:
        person_type = recognition.get("person_type") if recognition.get("known") else None
        detection_kind = face.metadata.get("detection_kind", "face")
        gender = (
            face.gender
            if face.gender in ("male", "female")
            and (face.gender_confidence or 0.0) >= self._gender_min_confidence()
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

    @staticmethod
    def _face_capture_score(face: FaceResult) -> float:
        """Estimated fraction of the face captured: bbox visibility inside the
        frame x detection quality (det score >= 0.8 counts as full quality)."""
        coverage = float(face.metadata.get("coverage", 1.0))
        quality = min(1.0, float(face.confidence or 0.0) / 0.8)
        return round(coverage * quality, 4)

    def _prune_presence(self, now: float, absence_seconds: float) -> None:
        if now - self._presence_pruned_at < 60:
            return
        self._presence_pruned_at = now
        expiry = max(3600.0, absence_seconds * 4)
        for key in [k for k, s in self.presence.items() if now - s["last_seen"] > expiry]:
            self.presence.pop(key, None)

    async def _handle_face(self, frame, face: FaceResult, recognition: dict[str, Any]) -> None:
        runtime = await self.backend.runtime_settings()
        known = bool(recognition.get("known"))
        person_id = recognition.get("person_id") if known else None
        person_type = recognition.get("person_type") if known else "unknown"
        similarity = recognition.get("similarity") if known else None
        gender_estimate = (
            face.gender
            if face.gender in ("male", "female")
            and (face.gender_confidence or 0.0) >= float(runtime["gender_min_confidence"])
            else None
        )
        presence_key = f"person:{person_id}" if person_id else f"unknown:{self.camera.id}:{gender_estimate or 'unknown'}"
        now = monotonic()
        absence_seconds = float(runtime["presence_absence_seconds"])
        cooldown_seconds = float(runtime["greeting_cooldown_seconds"])
        self._prune_presence(now, absence_seconds)

        state = self.presence.get(presence_key)
        if state is None or now - state["last_seen"] >= absence_seconds:
            # New visit: they just arrived, or left the zone and came back.
            state = {"greeted_at": state["greeted_at"] if state else None, "announced": False, "last_seen": now}
        else:
            state["last_seen"] = now
        self.presence[presence_key] = state

        if state["announced"]:
            return  # Already greeted this visit - stay quiet while they remain in the zone.
        if state["greeted_at"] is not None and now - state["greeted_at"] < cooldown_seconds:
            return  # They returned too soon after the last greeting.

        # Storage quality gate (the backend enforces the same rules; checking here
        # too avoids writing snapshots to disk for events the backend would reject).
        capture_score = self._face_capture_score(face)
        if capture_score < float(runtime["min_face_capture"]):
            return  # Leave announced=False so a better frame this visit can still greet.
        if bool(runtime["require_gender_or_person"]) and not known and gender_estimate is None:
            return

        state["announced"] = True
        state["greeted_at"] = now

        greeting = self._build_greeting(recognition, face, float(runtime["gender_min_confidence"]))
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
            "face_capture_score": capture_score,
            "raw": {
                "bbox": face.bbox,
                "recognition": recognition,
                "face_confidence": face.confidence,
                "face_coverage": face.metadata.get("coverage"),
                "provider": self.provider.model_version,
            },
        }
        await self.backend.create_detection_event(payload)

    def _build_greeting(self, recognition: dict[str, Any], face: FaceResult, gender_min_confidence: float) -> str:
        hour = datetime.now().hour
        if hour < 12:
            prefix = "Good morning"
        elif hour < 18:
            prefix = "Good afternoon"
        else:
            prefix = "Good evening"

        if recognition.get("known"):
            return f"{prefix}, {recognition.get('full_name')}"

        if face.gender and (face.gender_confidence or 0.0) >= gender_min_confidence:
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
