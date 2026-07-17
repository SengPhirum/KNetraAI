"""One-time export of the official Ultralytics YOLO12n weights to ONNX.

The ai-service runtime only depends on onnxruntime, never on torch/ultralytics,
to keep the production image slim. Those heavier packages are only needed for
this export step, which the Docker build already runs automatically in its
"model-export" stage.

Run this manually when developing ai-service outside Docker, or to regenerate
the ONNX file with a different input size / model variant:

    pip install "ultralytics>=8.3,<9"
    python scripts/export_yolo_person_model.py [--model yolo12n.pt] [--imgsz 640] [--out ../models/yolo12n.onnx]

Only Ultralytics' own official, GitHub-released COCO checkpoints are used
(downloaded by the `ultralytics` package itself) - class 0 of that checkpoint
is "person", which is all the cascade provider uses. Any Ultralytics YOLO
detect-task checkpoint works here (yolov8n.pt, yolo11n.pt, yolo12n.pt, ...) -
they all export to the same (1, 4+num_classes, num_boxes) ONNX output shape
that app/vision/yolo_onnx.py parses, so swapping --model is a safe way to
try a different size/accuracy tradeoff without touching any Python code.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="yolo12n.pt", help="Ultralytics checkpoint name (default: yolo12n.pt)")
    parser.add_argument("--imgsz", type=int, default=640, help="Export input size (must match YOLO_INPUT_SIZE)")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent.parent / "models" / "yolo12n.onnx"),
        help="Destination path for the exported ONNX file",
    )
    args = parser.parse_args()

    from ultralytics import YOLO

    model = YOLO(args.model)
    exported = model.export(format="onnx", imgsz=args.imgsz, opset=12, simplify=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(exported), str(out_path))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
