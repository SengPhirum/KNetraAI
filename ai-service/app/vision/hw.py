from __future__ import annotations

import logging
import os
import platform

logger = logging.getLogger(__name__)

# Roughly fastest-to-slowest; the first one present in the ONNX Runtime build wins.
_GPU_PROVIDER_PRIORITY = (
    "TensorrtExecutionProvider",
    "CUDAExecutionProvider",
    "ROCMExecutionProvider",
    "CoreMLExecutionProvider",
    "DmlExecutionProvider",
)

_ARM_MACHINES = {"aarch64", "arm64", "armv7l", "armv6l", "armv8l"}


def detect_device_class() -> str:
    """Best-effort classification of the host as "low"/"balanced"/"high" power,
    used to pick sane inference defaults (model size, thread counts, target FPS)
    without requiring the user to hand-tune every setting for e.g. a Raspberry Pi.

    Deliberately conservative: an ARM board (Raspberry Pi and similar SBCs almost
    always report aarch64/armv7l/armv6l) with 4 or fewer CPUs is treated as "low"
    even if it happens to be reasonably fast, since these boards throttle hard
    under sustained multi-core load and have no GPU-style ONNX Runtime provider
    available in practice.
    """
    machine = platform.machine().lower()
    cpu_count = os.cpu_count() or 1
    is_arm = machine in _ARM_MACHINES

    mem_gb: float | None = None
    try:
        mem_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024.0**3)
    except (ValueError, AttributeError, OSError):
        pass

    if is_arm and cpu_count <= 4:
        return "low"
    # ARM alone isn't a signal of a weak device (Apple Silicon, AWS Graviton, etc. are
    # ARM and fast) - only treat it as a "balanced" hint when paired with a modest core
    # count, same as any other architecture.
    if (is_arm and cpu_count <= 8) or cpu_count <= 2 or (mem_gb is not None and mem_gb < 3):
        return "balanced"
    return "high"


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


def apply_thread_settings(session_options) -> None:
    """Clamp an ONNX Runtime session's thread pool per config.onnx_intra/inter_op_threads
    (0 = leave ONNX Runtime's own default alone). Without this, every session defaults
    to using all available cores, which is fine for one model on a desktop but causes
    severe contention once several camera workers are each running their own
    YOLO + InsightFace sessions on a 4-core Raspberry Pi at the same time.
    """
    from ..config import settings

    intra = int(settings.onnx_intra_op_threads)
    inter = int(settings.onnx_inter_op_threads)
    if intra <= 0 and inter <= 0:
        return

    import onnxruntime as ort

    if intra > 0:
        session_options.intra_op_num_threads = intra
    if inter > 0:
        session_options.inter_op_num_threads = inter
    # Sequential execution avoids the overhead of ORT's own parallel-executor
    # scheduling when we've deliberately given it a small thread budget.
    session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
