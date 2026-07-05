from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Vision AI System API"
    environment: str = "development"
    database_url: str = "postgresql://vision:vision@localhost:5432/vision_ai"
    jwt_secret: str = "change-this-jwt-secret"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 720
    storage_dir: str = "/data"
    ai_service_url: str = "http://localhost:8001"
    internal_api_key: str = "change-this-internal-key"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    default_admin_email: str = "admin@example.com"
    default_admin_password: str = "admin123"
    default_admin_name: str = "System Admin"
    recognition_threshold: float = 0.45
    greeting_cooldown_seconds: int = 300
    gender_min_confidence: float = 0.60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
