from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "KNetraAI API"
    environment: str = "development"
    database_url: str = "postgresql://vision:vision@localhost:5432/vision_ai"
    jwt_secret: str = "change-this-jwt-secret"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 720
    storage_dir: str = "/data"
    ai_service_url: str = "http://localhost:8001"
    internal_api_key: str = "change-this-internal-key"
    cors_origins: str = "http://localhost:3010,http://127.0.0.1:3010"
    default_admin_email: str = "admin@example.com"
    default_admin_password: str = "admin123"
    default_admin_name: str = "System Admin"
    recognition_threshold: float = 0.45
    greeting_cooldown_seconds: int = 300
    gender_min_confidence: float = 0.60

    # Public URLs used to build OIDC redirects.
    frontend_base_url: str = "http://localhost:3010"
    api_base_url: str = "http://localhost:8010"

    # OIDC single sign-on (Keycloak, Authentik, or any OpenID Connect provider).
    oidc_enabled: bool = False
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_scopes: str = "openid profile email"
    oidc_provider_name: str = "SSO"
    oidc_default_role: str = "Viewer"
    oidc_auto_create_users: bool = True

    # LDAP / Active Directory authentication.
    ldap_enabled: bool = False
    ldap_server_url: str = ""
    ldap_user_dn_template: str = ""
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    ldap_search_base: str = ""
    ldap_user_filter: str = "(|(uid={username})(sAMAccountName={username})(mail={username}))"
    ldap_email_attribute: str = "mail"
    ldap_name_attribute: str = "cn"
    ldap_default_role: str = "Viewer"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
