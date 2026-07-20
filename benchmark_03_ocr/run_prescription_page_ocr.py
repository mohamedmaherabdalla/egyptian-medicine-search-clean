#!/usr/bin/env python3
"""Segment full prescription pages and optionally OCR every ordered region."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from benchmark_common import normalize_text, stable_id, write_csv, write_json
from prescription_segmentation import annotate_regions, crop_region, segment_file
from run_ocr_benchmark import (
    OCRResult,
    make_easyocr_runner,
    make_gotocr_runner,
    make_paddleocr_runner,
    make_tesseract_runner,
    make_transformers_runner,
)


REGION_FIELDS = [
    "page_id", "source_path", "region_id", "segmentation_level", "line_index",
    "reading_order", "x", "y", "width", "height", "ink_ratio", "crop_path",
    "ocr_output_raw", "ocr_output_normalized", "ocr_confidence", "ocr_latency_ms",
    "run_status", "error_message",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split prescription pages into ordered crops, then OCR each crop.",
    )
    parser.add_argument("--input", type=Path, required=True, help="Image file or directory")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--level", choices=("line", "word"), default="line")
    parser.add_argument(
        "--model",
        choices=("none", "tesseract", "trocr", "easyocr", "paddleocr", "gotocr"),
        default="none",
    )
    parser.add_argument("--model-id", default="")
    parser.add_argument("--model-label", default="")
    parser.add_argument("--preprocessing", default="autocontrast")
    parser.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"), default="auto")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--no-deskew", action="store_true")
    return parser.parse_args()


def discover_images(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if not input_path.is_dir():
        raise FileNotFoundError(input_path)
    extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
    return sorted(
        path for path in input_path.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    )


def build_runner(args: argparse.Namespace):
    if args.model == "none":
        return None, "segmentation_only", "", ""
    if args.model == "tesseract":
        runner, version, device = make_tesseract_runner(args.preprocessing)
    elif args.model == "trocr":
        runner, version, device = make_transformers_runner(
            "trocr", args.model_id, args.device, args.preprocessing,
        )
    elif args.model == "easyocr":
        runner, version, device = make_easyocr_runner(args.preprocessing)
    elif args.model == "paddleocr":
        runner, version, device = make_paddleocr_runner(
            args.preprocessing, args.model_id, args.batch_size,
        )
    else:
        runner, version, device = make_gotocr_runner(
            args.model_id, args.device, args.preprocessing,
        )
    return runner, args.model_label or args.model, version, device


def recognize_crops(runner, crop_paths: list[Path]) -> list[tuple[OCRResult, float, str, str]]:
    if runner is None:
        return [(OCRResult(""), 0.0, "not_requested", "") for _ in crop_paths]

    if hasattr(runner, "run_batch"):
        started = time.perf_counter()
        try:
            outputs = getattr(runner, "run_batch")(crop_paths)
            if len(outputs) != len(crop_paths):
                raise RuntimeError(f"OCR returned {len(outputs)} outputs for {len(crop_paths)} crops")
            per_crop_ms = (time.perf_counter() - started) * 1000 / max(len(crop_paths), 1)
            return [(output, per_crop_ms, "ok", "") for output in outputs]
        except Exception as exc:
            message = repr(exc)
            return [(OCRResult(""), 0.0, "error", message) for _ in crop_paths]

    results: list[tuple[OCRResult, float, str, str]] = []
    for crop_path in crop_paths:
        started = time.perf_counter()
        try:
            output = runner(crop_path)
            results.append((output, (time.perf_counter() - started) * 1000, "ok", ""))
        except Exception as exc:
            results.append((OCRResult(""), 0.0, "error", repr(exc)))
    return results


def reconstruct_lines(rows: list[dict[str, object]]) -> list[str]:
    lines: dict[int, list[str]] = {}
    for row in rows:
        text = str(row["ocr_output_raw"]).strip()
        if text:
            lines.setdefault(int(row["line_index"]), []).append(text)
    return [" ".join(lines[index]) for index in sorted(lines)]


def main() -> int:
    args = parse_args()
    image_paths = discover_images(args.input)
    if not image_paths:
        raise RuntimeError(f"no supported images found under {args.input}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    runner, model_name, model_version, device = build_runner(args)
    all_rows: list[dict[str, object]] = []
    page_summaries: list[dict[str, object]] = []

    for image_path in image_paths:
        page_id = stable_id(image_path.resolve(), length=12)
        page_dir = args.output_dir / f"{image_path.stem}_{page_id}"
        crop_dir = page_dir / "crops"
        crop_dir.mkdir(parents=True, exist_ok=True)

        segmented = segment_file(
            image_path,
            level=args.level,
            deskew=not args.no_deskew,
        )
        rectified_path = page_dir / "rectified.png"
        annotated_path = page_dir / "annotated.png"
        segmented.rectified_image.save(rectified_path)
        annotate_regions(segmented.rectified_image, segmented.regions).save(annotated_path)

        crop_paths: list[Path] = []
        for region in segmented.regions:
            crop_path = crop_dir / f"{region.reading_order:04d}.png"
            crop_region(segmented.rectified_image, region).save(crop_path)
            crop_paths.append(crop_path)

        recognized = recognize_crops(runner, crop_paths)
        page_rows: list[dict[str, object]] = []
        for region, crop_path, (output, latency_ms, status, error) in zip(
            segmented.regions, crop_paths, recognized,
        ):
            box = region.bbox
            row = {
                "page_id": page_id,
                "source_path": str(image_path.resolve()),
                "region_id": region.region_id,
                "segmentation_level": args.level,
                "line_index": region.line_index,
                "reading_order": region.reading_order,
                "x": box.x,
                "y": box.y,
                "width": box.width,
                "height": box.height,
                "ink_ratio": round(region.ink_ratio, 6),
                "crop_path": str(crop_path.resolve()),
                "ocr_output_raw": output.text,
                "ocr_output_normalized": normalize_text(output.text),
                "ocr_confidence": "" if output.confidence is None else round(output.confidence, 6),
                "ocr_latency_ms": round(latency_ms, 3),
                "run_status": status,
                "error_message": error,
            }
            page_rows.append(row)
            all_rows.append(row)

        lines = reconstruct_lines(page_rows)
        page_payload = {
            "page_id": page_id,
            "source_path": str(image_path.resolve()),
            "rectified_path": str(rectified_path.resolve()),
            "annotated_path": str(annotated_path.resolve()),
            "segmentation_level": args.level,
            "deskew_angle_degrees": round(segmented.deskew_angle_degrees, 4),
            "region_count": len(page_rows),
            "line_count": len({row["line_index"] for row in page_rows}),
            "ocr_model": model_name,
            "ocr_model_version": model_version,
            "device": device,
            "reconstructed_lines": lines,
            "reconstructed_text": "\n".join(lines),
            "regions": page_rows,
        }
        write_json(page_dir / "page.json", page_payload)
        page_summaries.append({key: value for key, value in page_payload.items() if key != "regions"})

    write_csv(args.output_dir / "regions.csv", all_rows, REGION_FIELDS)
    manifest = {
        "input": str(args.input.resolve()),
        "pages": len(image_paths),
        "regions": len(all_rows),
        "segmentation_level": args.level,
        "ocr_model": model_name,
        "ocr_model_version": model_version,
        "device": device,
        "page_summaries": page_summaries,
        "command": sys.argv,
    }
    write_json(args.output_dir / "run_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if all(row["run_status"] != "error" for row in all_rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
