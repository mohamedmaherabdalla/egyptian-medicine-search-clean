#!/usr/bin/env python3
"""Run reproducible OCR adapters over RxHandBD and emit canonical observations."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from benchmark_common import (
    DEFAULT_ARTIFACTS_DIR,
    DEFAULT_DATA_DIR,
    compact_text,
    difficulty_for_distance,
    file_sha256,
    levenshtein,
    normalize_text,
    read_csv,
    stable_id,
    write_csv,
    write_json,
)


OBSERVATION_FIELDS = [
    "observation_id", "sample_id", "dataset_name", "dataset_version", "image_id",
    "split", "sample_level", "language", "ground_truth_raw", "ground_truth_normalized",
    "ocr_output_raw", "ocr_output_normalized", "model_name", "model_version",
    "adapter_version", "preprocessing_id", "device", "ocr_confidence", "latency_ms",
    "exact_match", "edit_distance", "normalized_edit_distance", "difficulty",
    "empty_output", "run_status", "error_message",
]


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_DATA_DIR / "dataset_manifest.csv")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument(
        "--model",
        choices=("tesseract", "trocr", "donut", "gotocr", "easyocr", "paddleocr"),
        default="tesseract",
    )
    parser.add_argument("--preprocessing", default="autocontrast_2x")
    parser.add_argument("--split", choices=("train", "test", "all"), default="all")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=max(1, min(8, os.cpu_count() or 1)))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model-id", default="")
    parser.add_argument("--model-label", default="")
    parser.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"), default="auto")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--checkpoint-every", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=8)
    return parser.parse_args()


def preprocess_image(image_path: Path, preprocessing_id: str) -> Image.Image:
    with Image.open(image_path) as source:
        image = source.convert("L")
    if preprocessing_id == "raw":
        return image
    if preprocessing_id == "autocontrast":
        return ImageOps.autocontrast(image)
    if preprocessing_id in {"ink_crop_square_raw", "ink_crop_square_autocontrast"}:
        working = ImageOps.autocontrast(image)
        histogram = working.histogram()
        total = sum(histogram)
        cumulative_count = 0
        cumulative_sum = 0
        global_sum = sum(level * count for level, count in enumerate(histogram))
        best_threshold = 127
        best_variance = -1.0
        for level, count in enumerate(histogram[:-1]):
            cumulative_count += count
            cumulative_sum += level * count
            background_count = total - cumulative_count
            if not cumulative_count or not background_count:
                continue
            mean_delta = (
                cumulative_sum / cumulative_count
                - (global_sum - cumulative_sum) / background_count
            )
            variance = cumulative_count * background_count * mean_delta * mean_delta
            if variance > best_variance:
                best_variance = variance
                best_threshold = level
        mask = working.point(lambda pixel: 255 if pixel <= best_threshold else 0)
        bbox = mask.getbbox()
        if bbox:
            left, top, right, bottom = bbox
            margin = max(8, int(max(right - left, bottom - top) * 0.08))
            bbox = (
                max(0, left - margin),
                max(0, top - margin),
                min(image.width, right + margin),
                min(image.height, bottom + margin),
            )
            crop_source = working if preprocessing_id.endswith("autocontrast") else image
            crop = crop_source.crop(bbox)
            side = max(crop.width, crop.height)
            canvas = Image.new("L", (side, side), 255)
            canvas.paste(crop, ((side - crop.width) // 2, (side - crop.height) // 2))
            return canvas
        return working if preprocessing_id.endswith("autocontrast") else image
    if preprocessing_id == "autocontrast_2x":
        image = ImageOps.autocontrast(image)
        return image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
    if preprocessing_id == "threshold_2x":
        image = ImageOps.autocontrast(image)
        image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
        return image.point(lambda pixel: 255 if pixel >= 180 else 0)
    if preprocessing_id == "sharpen_2x":
        image = ImageOps.autocontrast(image)
        image = ImageEnhance.Contrast(image).enhance(1.5)
        image = image.filter(ImageFilter.SHARPEN)
        return image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
    raise ValueError(f"unknown preprocessing: {preprocessing_id}")


def clean_ocr_text(value: str) -> str:
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    text = " ".join(lines)
    return re.sub(r"\s+", " ", text).strip()


def tesseract_version() -> str:
    completed = subprocess.run(
        ["tesseract", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.splitlines()[0].strip()


def make_tesseract_runner(preprocessing_id: str) -> tuple[Callable[[Path], OCRResult], str, str]:
    version = tesseract_version()

    def run(image_path: Path) -> OCRResult:
        image = preprocess_image(image_path, preprocessing_id)
        with tempfile.NamedTemporaryFile(suffix=".png") as temp:
            image.save(temp.name, format="PNG")
            completed = subprocess.run(
                ["tesseract", temp.name, "stdout", "-l", "eng", "--oem", "1", "--psm", "7"],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        return OCRResult(clean_ocr_text(completed.stdout))

    return run, version, "cpu"


def select_torch_device(requested: str, torch) -> str:
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def transformer_model_version(model_id: str, config) -> str:
    """Return a reproducible revision for remote or locally trained weights."""
    local_path = Path(model_id)
    local_weights = local_path / "model.safetensors"
    if local_weights.is_file():
        return f"{local_path.name}@sha256:{file_sha256(local_weights)}"
    revision = getattr(config, "_commit_hash", None) or "resolved-cache"
    return f"{model_id}@{revision}"


def make_transformers_runner(
    model_kind: str,
    model_id: str,
    requested_device: str,
    preprocessing_id: str,
) -> tuple[Callable[[Path], OCRResult], str, str]:
    try:
        import torch
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    except ImportError as exc:
        raise RuntimeError(
            "TrOCR/Donut dependencies are missing. Run the documented uv sync command first."
        ) from exc

    if model_kind == "trocr":
        resolved_model_id = model_id or "microsoft/trocr-base-handwritten"
        # Some older TrOCR checkpoints do not declare processor_class. AutoProcessor
        # then resolves to a text-only RoBERTa tokenizer and rejects image input.
        processor = TrOCRProcessor.from_pretrained(resolved_model_id)
        model = VisionEncoderDecoderModel.from_pretrained(resolved_model_id)
    else:
        from transformers import DonutProcessor
        resolved_model_id = model_id or "chinmays18/medical-prescription-ocr"
        processor = DonutProcessor.from_pretrained(resolved_model_id)
        model = VisionEncoderDecoderModel.from_pretrained(resolved_model_id)

    device = select_torch_device(requested_device, torch)
    model.to(device)
    model.eval()

    def run_batch(image_paths: list[Path]) -> list[OCRResult]:
        images = []
        for image_path in image_paths:
            images.append(preprocess_image(image_path, preprocessing_id).convert("RGB"))
        pixel_values = processor(images=images, return_tensors="pt").pixel_values.to(device)
        with torch.inference_mode():
            if model_kind == "donut":
                prompt_ids = processor.tokenizer(
                    "<s_ocr>",
                    add_special_tokens=False,
                    return_tensors="pt",
                ).input_ids.to(device)
                prompt_ids = prompt_ids.expand(len(images), -1)
                generated = model.generate(
                    pixel_values,
                    decoder_input_ids=prompt_ids,
                    max_length=512,
                    num_beams=1,
                    early_stopping=True,
                )
            else:
                generated = model.generate(pixel_values, max_new_tokens=64)
        texts = processor.batch_decode(generated, skip_special_tokens=True)
        return [OCRResult(clean_ocr_text(text)) for text in texts]

    def run(image_path: Path) -> OCRResult:
        return run_batch([image_path])[0]

    setattr(run, "run_batch", run_batch)

    version = transformer_model_version(resolved_model_id, model.config)
    return run, version, device


def make_gotocr_runner(
    model_id: str,
    requested_device: str,
    preprocessing_id: str,
) -> tuple[Callable[[Path], OCRResult], str, str]:
    """Create a plain-text GOT-OCR2 adapter with bounded word-level decoding."""
    try:
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor
    except ImportError as exc:
        raise RuntimeError("GOT-OCR2 requires the neural OCR dependencies.") from exc

    resolved_model_id = model_id or "stepfun-ai/GOT-OCR-2.0-hf"
    processor = AutoProcessor.from_pretrained(resolved_model_id, use_fast=True)
    model = AutoModelForImageTextToText.from_pretrained(resolved_model_id)
    device = select_torch_device(requested_device, torch)
    model.to(device)
    model.eval()

    def run_batch(image_paths: list[Path]) -> list[OCRResult]:
        images = [
            preprocess_image(image_path, preprocessing_id).convert("RGB")
            for image_path in image_paths
        ]
        inputs = processor(images, return_tensors="pt").to(device)
        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                do_sample=False,
                tokenizer=processor.tokenizer,
                stop_strings="<|im_end|>",
                max_new_tokens=64,
            )
        prompt_length = inputs["input_ids"].shape[1]
        texts = processor.batch_decode(
            generated[:, prompt_length:], skip_special_tokens=True
        )
        return [OCRResult(clean_ocr_text(text)) for text in texts]

    def run(image_path: Path) -> OCRResult:
        return run_batch([image_path])[0]

    setattr(run, "run_batch", run_batch)
    version = transformer_model_version(resolved_model_id, model.config)
    return run, version, device


def make_easyocr_runner(preprocessing_id: str) -> tuple[Callable[[Path], OCRResult], str, str]:
    try:
        import importlib.metadata
        import easyocr
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("EasyOCR dependencies are missing. Run the documented uv sync command first.") from exc

    reader = easyocr.Reader(["en"], gpu=False, verbose=False)

    def run(image_path: Path) -> OCRResult:
        image = preprocess_image(image_path, preprocessing_id)
        detections = reader.readtext(np.asarray(image), detail=1, paragraph=False)
        detections = sorted(detections, key=lambda item: min(point[0] for point in item[0]))
        text = " ".join(str(item[1]) for item in detections)
        confidence = (
            sum(float(item[2]) for item in detections) / len(detections)
            if detections else None
        )
        return OCRResult(clean_ocr_text(text), confidence)

    return run, f"easyocr {importlib.metadata.version('easyocr')}", "cpu"


def make_paddleocr_runner(
    preprocessing_id: str,
    model_id: str,
    batch_size: int,
) -> tuple[Callable[[Path], OCRResult], str, str]:
    """Create a recognition-only PaddleOCR adapter for the word-crop dataset."""
    try:
        import importlib.metadata
        import numpy as np
        from paddleocr import TextRecognition
    except ImportError as exc:
        raise RuntimeError(
            "PaddleOCR dependencies are missing. Install requirements-ocr.txt first."
        ) from exc

    resolved_model_id = model_id or "en_PP-OCRv3_mobile_rec"
    recognizer = TextRecognition(
        model_name=resolved_model_id,
        device="cpu",
        cpu_threads=max(1, min(4, os.cpu_count() or 1)),
    )

    def load_image(image_path: Path):
        image = preprocess_image(image_path, preprocessing_id).convert("RGB")
        # PaddleX image predictors consume OpenCV-style BGR arrays.
        return np.asarray(image)[:, :, ::-1].copy()

    def run_batch(image_paths: list[Path]) -> list[OCRResult]:
        outputs: list[OCRResult] = []
        for result in recognizer.predict(
            [load_image(image_path) for image_path in image_paths],
            batch_size=max(1, batch_size),
        ):
            text = result.get("rec_text", "")
            confidence = result.get("rec_score")
            outputs.append(
                OCRResult(
                    clean_ocr_text(str(text)),
                    None if confidence is None else float(confidence),
                )
            )
        return outputs

    def run(image_path: Path) -> OCRResult:
        return run_batch([image_path])[0]

    setattr(run, "run_batch", run_batch)
    version = (
        f"{resolved_model_id}; paddleocr {importlib.metadata.version('paddleocr')}; "
        f"paddlepaddle {importlib.metadata.version('paddlepaddle')}"
    )
    return run, version, "cpu"


def observation_for_row(
    row: dict[str, str],
    runner: Callable[[Path], OCRResult],
    model_name: str,
    model_version: str,
    preprocessing_id: str,
    device: str,
) -> dict[str, object]:
    started = time.perf_counter()
    output = OCRResult("")
    status = "ok"
    error_message = ""
    try:
        output = runner(Path(row["image_path"]))
    except Exception as exc:
        status = "error"
        error_message = repr(exc)
    latency_ms = (time.perf_counter() - started) * 1000
    return observation_from_result(
        row,
        output,
        model_name,
        model_version,
        preprocessing_id,
        device,
        latency_ms,
        status,
        error_message,
    )


def observation_from_result(
    row: dict[str, str],
    output: OCRResult,
    model_name: str,
    model_version: str,
    preprocessing_id: str,
    device: str,
    latency_ms: float,
    status: str = "ok",
    error_message: str = "",
) -> dict[str, object]:
    ground_truth_key = compact_text(row["ground_truth_raw"])
    output_key = compact_text(output.text)
    distance = levenshtein(output_key, ground_truth_key)
    normalized_distance = distance / max(len(ground_truth_key), 1)
    exact = bool(ground_truth_key) and output_key == ground_truth_key
    empty = not output_key
    return {
        "observation_id": stable_id(row["sample_id"], model_name, model_version, preprocessing_id),
        "sample_id": row["sample_id"],
        "dataset_name": row["dataset_name"],
        "dataset_version": row["dataset_version"],
        "image_id": row["image_id"],
        "split": row["split"],
        "sample_level": row["sample_level"],
        "language": row["language"],
        "ground_truth_raw": row["ground_truth_raw"],
        "ground_truth_normalized": row["ground_truth_normalized"],
        "ocr_output_raw": output.text,
        "ocr_output_normalized": normalize_text(output.text),
        "model_name": model_name,
        "model_version": model_version,
        "adapter_version": "data3-ocr-adapter-v2",
        "preprocessing_id": preprocessing_id,
        "device": device,
        "ocr_confidence": "" if output.confidence is None else round(output.confidence, 6),
        "latency_ms": round(latency_ms, 3),
        "exact_match": int(exact),
        "edit_distance": distance,
        "normalized_edit_distance": round(normalized_distance, 6),
        "difficulty": difficulty_for_distance(normalized_distance, exact=exact, empty=empty),
        "empty_output": int(empty),
        "run_status": status,
        "error_message": error_message,
    }


def observations_for_batch(
    rows: list[dict[str, str]],
    batch_runner: Callable[[list[Path]], list[OCRResult]],
    model_name: str,
    model_version: str,
    preprocessing_id: str,
    device: str,
) -> list[dict[str, object]]:
    started = time.perf_counter()
    status = "ok"
    error_message = ""
    try:
        outputs = batch_runner([Path(row["image_path"]) for row in rows])
        if len(outputs) != len(rows):
            raise RuntimeError(f"batch returned {len(outputs)} outputs for {len(rows)} rows")
    except Exception as exc:
        outputs = [OCRResult("") for _ in rows]
        status = "error"
        error_message = repr(exc)
    per_image_latency_ms = ((time.perf_counter() - started) * 1000) / max(len(rows), 1)
    return [
        observation_from_result(
            row,
            output,
            model_name,
            model_version,
            preprocessing_id,
            device,
            per_image_latency_ms,
            status,
            error_message,
        )
        for row, output in zip(rows, outputs)
    ]


def main() -> int:
    args = parse_args()
    rows = read_csv(args.manifest)
    rows = [row for row in rows if row.get("image_valid") == "1" and row.get("ground_truth_compact")]
    if args.split != "all":
        rows = [row for row in rows if row.get("split") == args.split]
    rows.sort(key=lambda row: (row.get("split", ""), row.get("image_id", "")))
    if args.limit:
        rows = rows[:args.limit]

    if args.model == "tesseract":
        runner, model_version, device = make_tesseract_runner(args.preprocessing)
        model_name = args.model_label or "tesseract_lstm"
    elif args.model == "easyocr":
        runner, model_version, device = make_easyocr_runner(args.preprocessing)
        model_name = args.model_label or "easyocr"
    elif args.model == "paddleocr":
        runner, model_version, device = make_paddleocr_runner(
            args.preprocessing,
            args.model_id,
            args.batch_size,
        )
        model_name = args.model_label or "paddleocr"
    elif args.model in {"trocr", "donut"}:
        runner, model_version, device = make_transformers_runner(
            args.model,
            args.model_id,
            args.device,
            args.preprocessing,
        )
        model_name = args.model_label or args.model
    else:
        runner, model_version, device = make_gotocr_runner(
            args.model_id,
            args.device,
            args.preprocessing,
        )
        model_name = args.model_label or "gotocr2"

    output_path = args.output or args.results_dir / (
        f"ocr_{model_name}_{args.preprocessing}_{args.split}.csv"
    )
    existing: dict[str, dict[str, str]] = {}
    if args.resume and output_path.exists():
        existing = {row["sample_id"]: row for row in read_csv(output_path)}
    pending = [row for row in rows if row["sample_id"] not in existing]

    if args.model == "tesseract" and args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            generated = list(executor.map(
                lambda row: observation_for_row(
                    row, runner, model_name, model_version, args.preprocessing, device
                ),
                pending,
            ))
    elif hasattr(runner, "run_batch"):
        generated = []
        last_checkpoint = 0
        batch_runner = getattr(runner, "run_batch")
        for start in range(0, len(pending), max(1, args.batch_size)):
            batch_rows = pending[start:start + max(1, args.batch_size)]
            generated.extend(
                observations_for_batch(
                    batch_rows,
                    batch_runner,
                    model_name,
                    model_version,
                    args.preprocessing,
                    device,
                )
            )
            checkpoint_number = len(generated) // max(args.checkpoint_every, 1)
            if args.checkpoint_every and checkpoint_number > last_checkpoint:
                last_checkpoint = checkpoint_number
                checkpoint_rows = [*existing.values(), *generated]
                checkpoint_rows.sort(
                    key=lambda item: (str(item.get("split", "")), str(item.get("image_id", "")))
                )
                write_csv(output_path, checkpoint_rows, OBSERVATION_FIELDS)
                print(f"checkpoint {len(checkpoint_rows)}/{len(rows)}", flush=True)
    else:
        generated = []
        for index, row in enumerate(pending, 1):
            generated.append(
                observation_for_row(row, runner, model_name, model_version, args.preprocessing, device)
            )
            if args.checkpoint_every and index % args.checkpoint_every == 0:
                checkpoint_rows = [*existing.values(), *generated]
                checkpoint_rows.sort(
                    key=lambda item: (str(item.get("split", "")), str(item.get("image_id", "")))
                )
                write_csv(output_path, checkpoint_rows, OBSERVATION_FIELDS)
                print(f"checkpoint {len(checkpoint_rows)}/{len(rows)}", flush=True)
    observations = [*existing.values(), *generated]
    observations.sort(key=lambda row: (str(row.get("split", "")), str(row.get("image_id", ""))))
    write_csv(output_path, observations, OBSERVATION_FIELDS)

    successful = [row for row in observations if str(row["run_status"]) == "ok"]
    exact_count = sum(int(row["exact_match"]) for row in successful)
    summary = {
        "model_name": model_name,
        "model_version": model_version,
        "preprocessing_id": args.preprocessing,
        "device": device,
        "requested_rows": len(rows),
        "completed_rows": len(observations),
        "successful_rows": len(successful),
        "error_rows": len(observations) - len(successful),
        "exact_match_count": exact_count,
        "exact_match_accuracy": exact_count / len(successful) if successful else 0.0,
        "mean_normalized_edit_distance": (
            sum(float(row["normalized_edit_distance"]) for row in successful) / len(successful)
            if successful else 0.0
        ),
        "empty_output_rate": (
            sum(int(row["empty_output"]) for row in successful) / len(successful)
            if successful else 0.0
        ),
        "mean_latency_ms": (
            sum(float(row["latency_ms"]) for row in successful) / len(successful)
            if successful else 0.0
        ),
        "output_path": str(output_path.resolve()),
    }
    write_json(output_path.with_suffix(".summary.json"), summary)
    run_manifest = {
        **summary,
        "command": sys.argv,
        "python": sys.version,
        "platform": platform.platform(),
        "manifest_sha256": file_sha256(args.manifest),
        "started_from_clean_worktree": False,
    }
    write_json(output_path.with_suffix(".run.json"), run_manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["error_rows"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
