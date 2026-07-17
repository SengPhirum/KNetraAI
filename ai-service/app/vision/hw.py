from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Roughly fastest-to-slowest; the first one present in the ONNX Runtime build wins.
_GPU_PROVIDER_PRIORITY = (
    "TensorrtExecutionProvider",
    "CUDAExecutionProvider",
    "ROCMExecutionProvider",
    "CoreMLExecutionProvider",
    "DmlExecutionProvider",
)


def resolve_onnx_providers(preferred: str | None) -> tuple[list[str], int]:
    """Pick ONNX Runtime execution providers.

    ``preferred`` of ``None``/``""``/``"auto"`` probes the ONNX Runtime build for the
    fastest available accelerator (CUDA/TensorRT/CoreML/DirectML) and falls back to CPU.
    Any other value is treated as an explicit comma-separated provider list.

    Returns (providers, ctx_id) where ctx_id >= 0 signals hardware acceleration
    (matches InsightFace's ctx_id convention: >=0 selects a GPU device index, -1 is CPU).
    """
    if preferred and preferred.strip().lower() not in ("", "auto"):
        chosen = [item.strip() for item in preferred.split(",") if item.strip()]
        ctx_id = 0 if any(item != "CPUExecutionProvider" for item in chosen) else -1
        return chosen, ctx_id

    try:
        import onnxruntime as ort

        available = set(ort.get_available_providers())
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not probe ONNX Runtime providers, defaulting to CPU: %s", exc)
        return ["CPUExecutionProvider"], -1

    for gpu_provider in _GPU_PROVIDER_PRIORITY:
        if gpu_provider in available:
            logger.info("Auto-detected accelerator: %s", gpu_provider)
            return [gpu_provider, "CPUExecutionProvider"], 0

    logger.info("No GPU-style ONNX Runtime provider found, using CPU")
    return ["CPUExecutionProvider"], -1
