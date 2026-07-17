from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "KNetraAI Inference Service"
    backend_url: str = "http://localhost:8000"
    internal_api_key: str = "change-this-internal-key"
    storage_dir: str = "/data"
    ai_provider: str = "yolo_cascade"
    process_fps: float = 2.0
    greeting_cooldown_seconds: int = 300
    gender_min_confidence: float = 0.60
    face_min_confidence: float = 0.50
    face_min_area_ratio: float = 0.0002
    face_max_area_ratio: float = 0.35
    face_max_detections: int = 12
    opencv_face_scale_factor: float = 1.08
    opencv_face_min_neighbors: int = 7
    opencv_face_min_size: int = 44
    opencv_require_eye_validation: bool = True
    opencv_min_eyes: int = 1
    opencv_enable_mock_gender: bool = False
    opencv_enable_person_detector: bool = False
    opencv_person_hit_threshold: float = 0.0
    opencv_person_min_height: int = 80
    snapshot_jpeg_quality: int = 85
    insightface_model: str = "buffalo_l"
    insightface_model_root: str = "/data/insightface"
    insightface_det_size: int = 960
    # "auto" probes ONNX Runtime for the fastest available accelerator (CUDA/TensorRT/
    # CoreML/DirectML) and falls back to CPU; set explicitly (e.g. "CPUExecutionProvider")
    # to override.
    insightface_providers: str = "auto"
    # -2 = derive from insightface_providers (GPU provider chosen -> 0, else -1 for CPU).
    insightface_ctx_id: int = -2
    insightface_enable_tiled_detection: bool = True
    insightface_tile_min_width: int = 1100
    insightface_tile_overlap: float = 0.18
    insightface_insecure_model_download: bool = False
    allow_provider_fallback: bool = False

    # YOLO person-detection cascade (ai_provider=yolo_cascade): a fast YOLO12 pass finds
    # people first so the accurate (and heavier) InsightFace stage only has to look at
    # those crops instead of the whole frame - faster, and better small/far-face recall
    # since each crop effectively zooms in on the person.
    yolo_person_model_path: str = "/app/models/yolo12n.onnx"
    yolo_input_size: int = 640
    yolo_providers: str = "auto"
    yolo_person_conf: float = 0.35
    yolo_nms_threshold: float = 0.45
    yolo_person_min_height_ratio: float = 0.10
    yolo_crop_padding: float = 0.25
    yolo_max_persons: int = 8
    yolo_fallback_full_frame: bool = True
    yolo_emit_person_only_detections: bool = True
    # det_size for the InsightFace stage inside the cascade. Lower than the standalone
    # insightface_det_size default because the YOLO crop already zooms in on the face.
    yolo_face_det_size: int = 640

    stream_jpeg_quality: int = 80
    stream_max_width: int = 960
    onvif_discovery_timeout: float = 4.0
    onvif_probe_timeout: float = 8.0
    # Thumbnail captured from the same test frame already read while validating a
    # channel's stream during "Fetch Channels" - resized down to keep the response small.
    onvif_thumbnail_max_width: int = 320
    onvif_thumbnail_jpeg_quality: int = 70

    # Skip AI inference on frames with no meaningful change from the last processed
    # frame (cheap grayscale diff), except for a periodic idle poll so a person who
    # walks in and immediately holds still is still caught.
    motion_gating_enabled: bool = True
    motion_gating_min_area_ratio: float = 0.004
    motion_gating_idle_interval_seconds: float = 2.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
