from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str | None = None
    is_active: bool = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=6)
    role: str = "Viewer"
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None


class CameraCreate(BaseModel):
    name: str
    branch: str | None = None
    location: str | None = None
    rtsp_url: str
    enabled: bool = True
    ai_enabled: bool = False
    source: Literal["manual", "onvif", "test"] = "manual"
    onvif_host: str | None = None
    onvif_profile_token: str | None = None
    attendance_role: Literal["none", "entry", "exit", "both"] = "none"


class CameraUpdate(BaseModel):
    name: str | None = None
    branch: str | None = None
    location: str | None = None
    rtsp_url: str | None = None
    enabled: bool | None = None
    ai_enabled: bool | None = None
    attendance_role: Literal["none", "entry", "exit", "both"] | None = None


class CameraDiscoverRequest(BaseModel):
    timeout_seconds: float | None = None


class CameraProbeRequest(BaseModel):
    host: str
    port: int = 80
    username: str = ""
    password: str = ""


class CameraTestStreamRequest(BaseModel):
    rtsp_url: str
    timeout_ms: int = 6000


class CameraAiModeRequest(BaseModel):
    enabled: bool


class PersonCreate(BaseModel):
    person_type: Literal["staff", "customer"]
    full_name: str
    gender: Literal["male", "female", "unknown"] = "unknown"
    branch: str | None = None
    status: Literal["active", "inactive"] = "active"
    staff_id: str | None = None
    department: str | None = None
    position: str | None = None
    customer_id: str | None = None
    customer_type: str | None = None
    vip_flag: bool = False
    email: str | None = None
    phone: str | None = None
    fp_user_id: str | None = None
    shift_start: str | None = None
    shift_end: str | None = None
    notes: str | None = None
    consent_confirmed: bool = False


class PersonUpdate(BaseModel):
    full_name: str | None = None
    gender: Literal["male", "female", "unknown"] | None = None
    branch: str | None = None
    status: Literal["active", "inactive"] | None = None
    staff_id: str | None = None
    department: str | None = None
    position: str | None = None
    customer_id: str | None = None
    customer_type: str | None = None
    vip_flag: bool | None = None
    email: str | None = None
    phone: str | None = None
    fp_user_id: str | None = None
    shift_start: str | None = None
    shift_end: str | None = None
    notes: str | None = None
    consent_confirmed: bool | None = None


class LdapLoginRequest(BaseModel):
    username: str
    password: str


class LocalAuthConfig(BaseModel):
    enabled: bool = True
    password_min_length: int = 8
    password_require_uppercase: bool = False
    password_require_lowercase: bool = False
    password_require_digit: bool = False
    password_require_special: bool = False


class OidcAuthConfig(BaseModel):
    enabled: bool = False
    issuer: str = ""
    client_id: str = ""
    # Empty means "keep the stored secret".
    client_secret: str = ""
    scopes: str = "openid profile email"
    provider_name: str = "SSO"
    default_role: str = "Viewer"
    auto_create_users: bool = True


class LdapAuthConfig(BaseModel):
    enabled: bool = False
    server_url: str = ""
    user_dn_template: str = ""
    bind_dn: str = ""
    # Empty means "keep the stored password".
    bind_password: str = ""
    search_base: str = ""
    user_filter: str = "(|(uid={username})(sAMAccountName={username})(mail={username}))"
    email_attribute: str = "mail"
    name_attribute: str = "cn"
    default_role: str = "Viewer"


class AuthConfigUpdate(BaseModel):
    local: LocalAuthConfig | None = None
    oidc: OidcAuthConfig | None = None
    ldap: LdapAuthConfig | None = None


class PersonImportRequest(BaseModel):
    persons: list[PersonCreate]
    mode: Literal["create", "upsert"] = "create"


class EmbeddingFromPathRequest(BaseModel):
    path: str


class RecognitionRequest(BaseModel):
    embedding: list[float]


class DetectionEventCreate(BaseModel):
    camera_id: str | None = None
    person_id: str | None = None
    person_type: Literal["staff", "customer", "unknown"] = "unknown"
    confidence: float | None = None
    gender_estimate: str | None = None
    gender_confidence: float | None = None
    greeting: str
    snapshot_path: str | None = None
    # Estimated fraction of the face captured (bbox visibility x detection quality,
    # 0-1). None means the AI provider could not compute it (treated as passing).
    face_capture_score: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class DetectionClearRequest(BaseModel):
    """Admin bulk delete. With no filters set, every detection event is deleted."""

    camera_id: str | None = None
    person_type: Literal["staff", "customer", "unknown"] | None = None
    date_from: str | None = None
    date_to: str | None = None
    event_ids: list[str] | None = None


class PersonApiConfig(BaseModel):
    """Configuration for pulling people from an external HR/CRM REST API."""

    url: str = ""
    method: Literal["GET", "POST"] = "GET"
    # Header values saved as "" keep the previously stored value (secrets).
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    # Dot path to the array of records inside the response (empty = response root).
    data_path: str = ""
    default_person_type: Literal["staff", "customer"] = "staff"
    mode: Literal["create", "upsert"] = "upsert"
    # local field -> dot path in each API record, e.g. {"full_name": "profile.name"}
    mapping: dict[str, str] = Field(default_factory=dict)


class PersonApiSyncRequest(BaseModel):
    preview: bool = False
    limit: int = Field(default=0, ge=0, le=10000)  # 0 = no limit


class FpDeviceCreate(BaseModel):
    name: str
    # 'zk' = direct device polling; 'adms_push' = device pushes to /iclock;
    # 'biotime' = poll a ZKTeco BioTime server REST API with username/password.
    protocol: Literal["zk", "adms_push", "biotime"] = "zk"
    host: str = ""
    port: int = Field(default=4370, ge=1, le=65535)
    comm_key: str = "0"
    use_udp: bool = False
    api_url: str = ""
    api_username: str = ""
    api_password: str = ""
    device_serial: str | None = None
    branch: str | None = None
    location: str | None = None
    direction: Literal["in", "out", "both"] = "both"
    enabled: bool = True


class FpDeviceUpdate(BaseModel):
    name: str | None = None
    protocol: Literal["zk", "adms_push", "biotime"] | None = None
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    comm_key: str | None = None
    use_udp: bool | None = None
    api_url: str | None = None
    api_username: str | None = None
    # Empty string keeps the stored password.
    api_password: str | None = None
    device_serial: str | None = None
    branch: str | None = None
    location: str | None = None
    direction: Literal["in", "out", "both"] | None = None
    enabled: bool | None = None


class FpDiscoverRequest(BaseModel):
    """Sweep a /24 network for fingerprint devices listening on the ZK port."""

    network_base: str  # e.g. "192.168.1"
    port: int = Field(default=4370, ge=1, le=65535)


class AttendancePunchIn(BaseModel):
    device_user_id: str
    punched_at: str  # ISO datetime; naive values use the attendance timezone
    punch_type: Literal["in", "out", "unknown"] = "unknown"


class AttendancePushRequest(BaseModel):
    """Punches pushed by non-ZKTeco systems (access control middleware, etc.)."""

    records: list[AttendancePunchIn]


class AttendanceAlertsClearRequest(BaseModel):
    alert_ids: list[str] | None = None  # None/empty = clear everything


class TestVideoCameraRequest(BaseModel):
    kind: Literal["bundled", "uploaded"]
    file: str
    name: str | None = None
    autostart: bool = True


class DummyClearRequest(BaseModel):
    include_uploads: bool = False


class SettingUpdate(BaseModel):
    value: str


class GreetingTemplateUpdate(BaseModel):
    known_template: str | None = None
    male_template: str | None = None
    female_template: str | None = None
    neutral_template: str | None = None
