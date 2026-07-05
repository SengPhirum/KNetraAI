import logging

from ..config import settings
from .opencv_mock_provider import OpenCVMvpProvider

logger = logging.getLogger(__name__)


def build_provider():
    if settings.ai_provider.lower() == "insightface":
        try:
            from .insightface_provider import InsightFaceProvider

            logger.info("Using InsightFace provider")
            return InsightFaceProvider()
        except Exception as exc:
            if not settings.allow_provider_fallback:
                raise
            logger.warning("InsightFace provider failed, falling back to OpenCV MVP provider: %s", exc)
    logger.info("Using OpenCV MVP provider")
    return OpenCVMvpProvider()
