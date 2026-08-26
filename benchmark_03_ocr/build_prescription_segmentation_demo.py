#!/usr/bin/env python3
"""Build a deterministic multi-line page from real RxHandBD word crops.

This is an integration fixture, not a substitute for a labeled full-page test
set.  It proves that region ordering and crop-to-recognizer wiring work before
real prescription pages and bounding-box annotations are available.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from benchmark_common import DEFAULT_DATASET_ROOT, read_csv, write_csv


PLACEMENTS = (
    ("P0001.jpg", 70, 60, 310, 118),
    ("P0003.jpg", 455, 62, 285, 118),
    ("P0005.jpg", 80, 235, 270, 112),
    ("P0011.jpg", 440, 230, 320, 120),
    ("P0013.jpg", 75, 415, 300, 118),
    ("P0018.jpg", 455, 410, 285, 118),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def ink_only_crop(path: Path, width: int, height: int) -> Image.Image:
    with Image.open(path) as source:
        gray = ImageOps.autocontrast(source.convert("L"))
    array = np.asarray(gray)
    blurred = cv2.GaussianBlur(array, (5, 5), 0)
    _, alpha = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )
    ink = Image.new("L", gray.size, 20)
    rgba = Image.merge("RGBA", (ink, ink, ink, Image.fromarray(alpha)))
    rgba.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    canvas.alpha_composite(rgba, ((width - rgba.width) // 2, (height - rgba.height) // 2))
    return canvas


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    test_root = DEFAULT_DATASET_ROOT / "RxHandBD-ML" / "Test_Set"
    labels = {
        row["Images"].strip(): row["Text"].strip()
        for row in read_csv(DEFAULT_DATASET_ROOT / "RxHandBD-ML" / "Test_Labels.csv")
    }

    page = Image.new("RGB", (850, 620), "white")
    rows: list[dict[str, object]] = []
    for index, (image_id, x, y, width, height) in enumerate(PLACEMENTS, 1):
        crop = ink_only_crop(test_root / image_id, width, height)
        page.paste(crop, (x, y), crop)
        rows.append({
            "reading_order": index,
            "line_index": (index - 1) // 2 + 1,
            "image_id": image_id,
            "ground_truth": labels.get(image_id, ""),
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        })

    page_path = args.output_dir / "synthetic_prescription_page.png"
    page.save(page_path)
    write_csv(
        args.output_dir / "synthetic_prescription_ground_truth.csv",
        rows,
        ("reading_order", "line_index", "image_id", "ground_truth", "x", "y", "width", "height"),
    )
    print(page_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
