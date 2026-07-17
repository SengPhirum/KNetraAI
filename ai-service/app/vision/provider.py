import logging

from ..config import settings
from .opencv_mock_provider import OpenCVMvpProvider

logger = logging.getLogger(__name__)


def build_provider():
    provider_name = settings.ai_provider.lower()

    if provider_name == "yolo_cascade":
        try:
            from .yolo_cascade_provider import YoloCascadeProvider

            logger.info("Using YOLO person cascade + InsightFace provider")
            return YoloCascadeProvider()
        except Exception as exc:
            logger.warning(
                "YOLO cascade provider failed, falling back to plain InsightFace provider: %s", exc
            )
            provider_name = "insightface"

    if provider_name == "insightface":
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
