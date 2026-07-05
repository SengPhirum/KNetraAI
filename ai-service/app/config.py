from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "Vision AI Inference Service"
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
