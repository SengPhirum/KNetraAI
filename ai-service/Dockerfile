# --- model-export stage --------------------------------------------------
# Exports the official Ultralytics YOLO12n (COCO) checkpoint to ONNX for the
# person-detection cascade. torch/ultralytics only ever live in this stage -
# the runtime image below stays slim and depends on onnxruntime only.
FROM python:3.11-slim AS model-export

WORKDIR /export
RUN pip install --no-cache-dir "ultralytics>=8.3,<9" onnx onnxruntime sympy \
    # ultralytics pulls in the GUI opencv-python variant, which needs X11 libs
    # (libxcb.so.1 etc.) this slim, headless builder doesn't have. Swap it for
    # opencv-python-headless, same as the runtime image uses - no display needed
    # to export a model.
    && pip uninstall -y opencv-python \
    && pip install --no-cache-dir opencv-python-headless
RUN python -c "\
from ultralytics import YOLO; \
m = YOLO('yolo12n.pt'); \
m.export(format='onnx', imgsz=640, opset=12, simplify=True, dynamic=True)"
# dynamic=True keeps height/width as symbolic dims in the export instead of baking in a
# fixed 640x640 input, so YOLO_INPUT_SIZE (e.g. 320 on the "low" device profile) actually
# takes effect at inference time instead of onnxruntime rejecting the mismatched shape.
#
# Dynamically-quantized (INT8 weights) copy, used automatically by the "low" device
# profile (see app/config.py) - roughly a third the size and noticeably faster on CPUs
# without AVX512/VNNI, which covers essentially every ARM SBC (Raspberry Pi included).
# quant_pre_process (shape inference + node fusion) is run first since ONNX Runtime's
# own docs recommend it for materially better quantized-model quality/compatibility;
# skip_symbolic_shape=True because full symbolic shape inference doesn't complete on a
# model with dynamic H/W dims (basic ONNX shape inference + node fusion still run).
RUN python -c "\
from onnxruntime.quantization.shape_inference import quant_pre_process; \
from onnxruntime.quantization import quantize_dynamic, QuantType; \
quant_pre_process('yolo12n.onnx', 'yolo12n-preprocessed.onnx', skip_symbolic_shape=True); \
quantize_dynamic('yolo12n-preprocessed.onnx', 'yolo12n-int8.onnx', weight_type=QuantType.QUInt8)"

# --- runtime stage ---------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates libglib2.0-0 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Set to "gpu" (see docker-compose.gpu.yml) to swap in onnxruntime-gpu so the
# CUDAExecutionProvider auto-detected by app/vision/hw.py is actually available.
# Requires an NVIDIA driver + the NVIDIA Container Toolkit on the host.
ARG ONNXRUNTIME_VARIANT=cpu
RUN if [ "$ONNXRUNTIME_VARIANT" = "gpu" ]; then \
        pip install --no-cache-dir --force-reinstall "onnxruntime-gpu>=1.18"; \
    fi

COPY app ./app
COPY --from=model-export /export/yolo12n.onnx ./models/yolo12n.onnx
COPY --from=model-export /export/yolo12n-int8.onnx ./models/yolo12n-int8.onnx

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
