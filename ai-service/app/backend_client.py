from __future__ import annotations

from typing import Any

import httpx

from .config import settings


class BackendClient:
    def __init__(self) -> None:
        self.headers = {"x-internal-api-key": settings.internal_api_key}

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
