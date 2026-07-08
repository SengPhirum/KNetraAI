from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "KNetraAI Inference Service"
    backend_url: str = "http://localhost:8000"
    internal_api_key: str = "change-this-internal-key"
    storage_dir: str = "/data"
    ai_provider: str = "opencv_mock"
    process_fps: float = 2.0
    greeting_cooldown_seconds: int = 300
    gender_min_confidence: float = 0.60
    snapshot_jpeg_quality: int = 85
    insightface_model: str = "buffalo_l"
    allow_provider_fallback: bool = True
    stream_jpeg_quality: int = 80
    stream_max_width: int = 960
    onvif_discovery_timeout: float = 4.0
    onvif_probe_timeout: float = 8.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
