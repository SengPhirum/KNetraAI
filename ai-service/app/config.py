import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    service_name: str = "KNetraAI Inference Service"
    backend_url: str = "http://localhost:8000"
    internal_api_key: str = "change-this-internal-key"
    storage_dir: str = "/data"
    ai_provider: str = "yolo_cascade"
    # "auto" detects Raspberry-Pi-class ARM boards / low-core hosts and lowers model
    # input sizes, thread counts, and target FPS to defaults that stay smooth on them;
    # "high"/"balanced"/"low" force a tier explicitly. Only applies to settings the
    # user hasn't already set themselves (via env/.env) - see resolve_device_profile().
    device_profile: str = "auto"
    resolved_device_profile: str = ""
    # 0 = let ONNX Runtime pick its own default thread count. Set explicitly on
    # constrained devices (e.g. a 4-core Raspberry Pi running several camera workers)
    # to stop each inference session from trying to claim every core for itself.
    onnx_intra_op_threads: int = 0
    onnx_inter_op_threads: int = 0
    # Caps how many camera workers may run AI inference at the same instant
    # (0 = unlimited). On a single-board computer, letting N cameras all try to run
    # YOLO/InsightFace at once thrashes the CPU far worse than queuing them - each
    # one finishes faster with exclusive use of the core budget than all of them
    # crawling forward in parallel.
    max_concurrent_inference: int = 0
    # If a camera worker can't keep up with process_fps (inference takes longer than
    # the target interval), back off the target rate to whatever it can actually
    # sustain instead of continuously falling behind / maxing out the CPU.
    adaptive_frame_skip: bool = True
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


# Defaults applied on top of the hardcoded field defaults above when device_profile
# resolves to a given tier - but only for fields the user hasn't already set via
# env/.env (see _apply_device_profile). "high" intentionally has no overrides: the
# hardcoded field defaults above are already tuned for a desktop/server-class box.
_PROFILE_DEFAULTS: dict[str, dict[str, object]] = {
    "low": {
        # Dynamically-quantized (INT8 weights) export produced alongside the fp32
        # model in the Docker build - roughly half the FLOPs on a CPU with no AVX512,
        # which is exactly the situation on a Raspberry Pi / ARM SBC.
        "yolo_person_model_path": "/app/models/yolo12n-int8.onnx",
        "yolo_input_size": 320,
        "yolo_face_det_size": 320,
        "yolo_max_persons": 3,
        "insightface_det_size": 480,
        # buffalo_s is InsightFace's small model pack (lighter SCRFD detector +
        # smaller recognition backbone) - downloaded automatically the same way as
        # buffalo_l, just far cheaper to run per frame.
        "insightface_model": "buffalo_s",
        "insightface_enable_tiled_detection": False,
        "process_fps": 1.0,
        "motion_gating_min_area_ratio": 0.008,
        "motion_gating_idle_interval_seconds": 4.0,
        "onnx_intra_op_threads": 2,
        "onnx_inter_op_threads": 1,
        "max_concurrent_inference": 1,
    },
    "balanced": {
        "yolo_input_size": 480,
        "yolo_face_det_size": 480,
        "yolo_max_persons": 5,
        "insightface_det_size": 640,
        "process_fps": 1.5,
        "motion_gating_min_area_ratio": 0.006,
        "onnx_intra_op_threads": 3,
        "max_concurrent_inference": 2,
    },
    "high": {},
}


def _apply_device_profile(s: Settings) -> Settings:
    profile = (s.device_profile or "auto").strip().lower()
    if profile == "auto":
        from .vision.hw import detect_device_class

        profile = detect_device_class()

    overrides = _PROFILE_DEFAULTS.get(profile)
    if overrides is None:
        logger.warning("Unknown device_profile %r, treating as 'high' (no overrides)", profile)
        overrides = {}

    # Deliberately compare against each field's hardcoded default rather than using
    # pydantic's model_fields_set (i.e. "was this set via env/.env at all"): .env.example
    # spells out an explicit value for virtually every setting, including ones left at
    # their documented default, and docker-compose's env_file: .env injects all of them
    # as real process env vars either way - model_fields_set would treat all of those as
    # "user customized" and profile auto-tuning would never actually fire in practice.
    # A value that still matches the code default is treated as untouched and safe to
    # raise/lower for the resolved tier; a value the user deliberately changed away from
    # the default always wins.
    field_defaults = {name: field.default for name, field in Settings.model_fields.items()}
    for key, value in overrides.items():
        if getattr(s, key) == field_defaults.get(key):
            setattr(s, key, value)

    s.resolved_device_profile = profile
    logger.info(
        "Device profile resolved to %r (yolo_input_size=%s, process_fps=%s, max_concurrent_inference=%s)",
        profile,
        s.yolo_input_size,
        s.process_fps,
        s.max_concurrent_inference,
    )
    return s


@lru_cache
def get_settings() -> Settings:
    return _apply_device_profile(Settings())


settings = get_settings()
