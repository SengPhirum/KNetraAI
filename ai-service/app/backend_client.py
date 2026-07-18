from __future__ import annotations

import logging
from time import monotonic
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger(__name__)

_RUNTIME_SETTINGS_TTL_SECONDS = 30.0


class BackendClient:
    def __init__(self) -> None:
        self.headers = {"x-internal-api-key": settings.internal_api_key}
        # Env-derived fallbacks used until the first successful fetch (and if the
        # backend is unreachable). Refreshed from the backend settings table so
        # changes in the Settings UI apply live, without an ai-service restart.
        self._runtime_settings: dict[str, Any] = {
            "greeting_cooldown_seconds": float(settings.greeting_cooldown_seconds),
            "presence_absence_seconds": 30.0,
            "gender_min_confidence": float(settings.gender_min_confidence),
            "min_face_capture": 0.75,
            "require_gender_or_person": True,
        }
        self._runtime_settings_fetched_at = 0.0

    async def recognize(self, embedding: list[float]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{settings.backend_url}/internal/recognize",
                json={"embedding": embedding},
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def create_detection_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{settings.backend_url}/internal/detection-events",
                json=payload,
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def runtime_settings(self) -> dict[str, Any]:
        """Backend-managed live tunables, cached for a short interval."""
        now = monotonic()
        if now - self._runtime_settings_fetched_at >= _RUNTIME_SETTINGS_TTL_SECONDS:
            self._runtime_settings_fetched_at = now  # even on failure, avoid hammering
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.get(
                        f"{settings.backend_url}/internal/runtime-settings",
                        headers=self.headers,
                    )
                response.raise_for_status()
                self._runtime_settings.update(response.json())
            except httpx.HTTPError as exc:
                logger.debug("Runtime settings fetch failed, keeping last known values: %s", exc)
        return self._runtime_settings

    @property
    def cached_runtime_settings(self) -> dict[str, Any]:
        return self._runtime_settings
