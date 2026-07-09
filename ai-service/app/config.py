from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "KNetraAI Inference Service"
    backend_url: str = "http://localhost:8000"
    internal_api_key: str = "change-this-internal-key"
    storage_dir: str = "/data"
    ai_provider: str = "insightface"
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
    insightface_providers: str = "CPUExecutionProvider"
    insightface_ctx_id: int = -1
    insightface_enable_tiled_detection: bool = True
    insightface_tile_min_width: int = 1100
    insightface_tile_overlap: float = 0.18
    insightface_insecure_model_download: bool = False
    allow_provider_fallback: bool = False
    stream_jpeg_quality: int = 80
    stream_max_width: int = 960
    onvif_discovery_timeout: float = 4.0
    onvif_probe_timeout: float = 8.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
