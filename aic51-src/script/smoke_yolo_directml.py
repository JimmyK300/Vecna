"""Smoke/throughput check for Vecna's YOLO ONNX backend.

This does not write corpus features.  It exercises YOLOFeature end-to-end:
image read -> Vecna letterbox -> ORT provider -> decode -> semantic text.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from aic51.packages.analyse.features.yolo import YOLOFeature

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def find_images(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", required=True, help="Root containing real keyframes")
    parser.add_argument("--model", required=True, help="Baked YOLOE ONNX artifact")
    parser.add_argument("--provider", choices=("dml", "cpu", "auto"), default="dml")
    parser.add_argument("--sample-size", type=int, default=1000)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--seed", type=int, default=51)
    parser.add_argument("--confidence", type=float, default=0.20)
    parser.add_argument("--max-det", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--class-names", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    images = find_images(Path(args.images))
    if not images:
        raise SystemExit(f"no images found under {args.images}")
    rng = random.Random(args.seed)
    if len(images) > args.sample_size:
        images = sorted(rng.sample(images, args.sample_size))

    extractor = YOLOFeature.from_pretrained(
        pretrained_model="yoloe-26x-seg.pt",
        backend="onnx",
        onnx_provider=args.provider,
        onnx_model_path=args.model,
        onnx_class_names_path=args.class_names,
        allow_gpu=True,
        device="cpu",  # DML belongs to ORT; torch stays CPU on this AMD host.
        confidence=args.confidence,
        max_det=args.max_det,
        imgsz=args.imgsz,
        batch_size=1,
        name="yolo",
    )
    semantics = extractor.runtime_semantics()
    if args.provider == "dml" and semantics.get("execution_provider") != "DmlExecutionProvider":
        raise RuntimeError(f"requested DML but got semantics={semantics}")

    warmup = min(max(args.warmup, 0), len(images))
    if warmup:
        extractor.get_features(images[:warmup])

    started = time.perf_counter()
    outputs = extractor.get_features(images)
    elapsed = max(time.perf_counter() - started, 1e-9)
    fps = len(images) / elapsed

    result = {
        "status": "ok",
        "frames": len(images),
        "elapsed_seconds": elapsed,
        "images_per_second": fps,
        "projected_317k_hours": 317000 / fps / 3600 if fps > 0 else None,
        "runtime_semantics": semantics,
        "semantic_outputs": [str(value.item() if hasattr(value, "item") else value) for value in outputs[:20]],
    }
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
