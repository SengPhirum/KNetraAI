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


class CameraUpdate(BaseModel):
    name: str | None = None
    branch: str | None = None
    location: str | None = None
    rtsp_url: str | None = None
    enabled: bool | None = None


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
    notes: str | None = None


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
    raw: dict[str, Any] = Field(default_factory=dict)


class SettingUpdate(BaseModel):
    value: str


class GreetingTemplateUpdate(BaseModel):
    known_template: str | None = None
    male_template: str | None = None
    female_template: str | None = None
    neutral_template: str | None = None
