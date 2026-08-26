#!/usr/bin/env python3
"""Detect ordered handwritten text regions on a prescription page.

The RxHandBD benchmark contains pre-cropped words.  This module is the separate
page-level front end needed when the input is an uncropped prescription image.
It intentionally does not perform OCR so region detection can be tested and
measured independently from recognition.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True)
class TextRegion:
    region_id: str
    line_index: int
    reading_order: int
    bbox: BoundingBox
    ink_ratio: float

    def to_dict(self) -> dict[str, object]:
        return {
            "region_id": self.region_id,
            "line_index": self.line_index,
            "reading_order": self.reading_order,
            **asdict(self.bbox),
            "ink_ratio": round(self.ink_ratio, 6),
        }


@dataclass(frozen=True)
class SegmentationResult:
    rectified_image: Image.Image
    ink_mask: np.ndarray
    regions: tuple[TextRegion, ...]
    deskew_angle_degrees: float


def _odd_at_least(value: int, minimum: int = 15) -> int:
    value = max(minimum, value)
    return value if value % 2 else value + 1


def build_ink_mask(image: Image.Image) -> np.ndarray:
    """Return a cleaned binary mask where handwriting/text pixels are white."""

    gray = np.asarray(image.convert("L"))
    page_scale = max(gray.shape)
    block_size = _odd_at_least(round(page_scale * 0.025), 21)
    mask = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        block_size,
        13,
    )

    # Remove isolated scan noise while preserving thin pen strokes.
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    cleaned = np.zeros_like(mask)
    minimum_area = max(3, round(gray.size * 0.000002))
    for label in range(1, component_count):
        x, y, width, height, area = stats[label]
        if area < minimum_area:
            continue
        if width <= 1 and height <= 2:
            continue
        cleaned[labels == label] = 255
    return cleaned


def estimate_skew_angle(mask: np.ndarray) -> float:
    """Estimate a conservative page angle from foreground pixels."""

    y_values, x_values = np.where(mask > 0)
    if len(x_values) < 20:
        return 0.0
    points = np.column_stack((x_values, y_values)).astype(np.float32)
    angle = float(cv2.minAreaRect(points)[-1])
    if angle > 45.0:
        angle -= 90.0
    # A large angle is usually a sparse-stroke failure, not page rotation.
    return angle if abs(angle) <= 12.0 else 0.0


def rotate_page(image: Image.Image, angle: float) -> Image.Image:
    if abs(angle) < 0.05:
        return image.convert("RGB")
    return image.convert("RGB").rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor="white",
    )


def _median_component_height(mask: np.ndarray) -> float:
    component_count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    heights = [
        int(stats[label, cv2.CC_STAT_HEIGHT])
        for label in range(1, component_count)
        if int(stats[label, cv2.CC_STAT_AREA]) >= 5
        and int(stats[label, cv2.CC_STAT_HEIGHT]) >= 2
    ]
    return float(np.median(heights)) if heights else max(8.0, mask.shape[0] * 0.02)


def _boxes_from_mask(mask: np.ndarray, level: str) -> list[BoundingBox]:
    median_height = _median_component_height(mask)
    if level == "word":
        kernel_width = max(5, round(median_height * 0.75))
        kernel_height = max(3, round(median_height * 0.18))
    elif level == "line":
        # Prescription lines often contain a drug name, strength, and form with
        # gaps several character-heights wide.  Connect horizontally without
        # increasing vertical reach, which keeps adjacent rows separate.
        kernel_width = max(21, round(median_height * 6.0), round(mask.shape[1] * 0.42))
        kernel_height = max(3, round(median_height * 0.25))
    else:
        raise ValueError("segmentation level must be 'word' or 'line'")

    connector = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (kernel_width, kernel_height),
    )
    connected = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, connector)
    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    page_height, page_width = mask.shape
    minimum_area = max(12, round(page_height * page_width * 0.00001))
    boxes: list[BoundingBox] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        foreground_area = cv2.countNonZero(mask[y:y + height, x:x + width])
        if foreground_area < minimum_area:
            continue
        if width < 3 or height < 3:
            continue
        margin_x = max(3, round(height * 0.15))
        margin_y = max(3, round(height * 0.12))
        left = max(0, x - margin_x)
        top = max(0, y - margin_y)
        right = min(page_width, x + width + margin_x)
        bottom = min(page_height, y + height + margin_y)
        boxes.append(BoundingBox(left, top, right - left, bottom - top))
    return _merge_satellite_boxes(boxes)


def _union_box(left: BoundingBox, right: BoundingBox) -> BoundingBox:
    x = min(left.x, right.x)
    y = min(left.y, right.y)
    far_right = max(left.right, right.right)
    bottom = max(left.bottom, right.bottom)
    return BoundingBox(x, y, far_right - x, bottom - y)


def _box_gap(left: BoundingBox, right: BoundingBox) -> tuple[int, int]:
    horizontal = max(0, max(left.x, right.x) - min(left.right, right.right))
    vertical = max(0, max(left.y, right.y) - min(left.bottom, right.bottom))
    return horizontal, vertical


def _merge_satellite_boxes(boxes: list[BoundingBox]) -> list[BoundingBox]:
    """Attach detached dots, crosses, and flourishes to nearby text regions."""

    if len(boxes) < 2:
        return boxes
    median_area = float(np.median([box.width * box.height for box in boxes]))
    median_height = float(np.median([box.height for box in boxes]))
    working = list(boxes)

    while len(working) > 1:
        tiny_indexes = [
            index for index, box in enumerate(working)
            if box.width * box.height < median_area * 0.22
            or box.height < median_height * 0.38
        ]
        best_merge: tuple[float, int, int] | None = None
        for tiny_index in tiny_indexes:
            tiny = working[tiny_index]
            for target_index, target in enumerate(working):
                if target_index == tiny_index:
                    continue
                if target.width * target.height <= tiny.width * tiny.height:
                    continue
                horizontal_gap, vertical_gap = _box_gap(tiny, target)
                distance = float(np.hypot(horizontal_gap, vertical_gap))
                if distance > max(10.0, median_height * 0.85):
                    continue
                # A detached mark should overlap the target in one axis or be
                # very close in both axes. This avoids stealing a short word.
                if horizontal_gap and vertical_gap and distance > median_height * 0.55:
                    continue
                candidate = (distance, tiny_index, target_index)
                if best_merge is None or candidate < best_merge:
                    best_merge = candidate
        if best_merge is None:
            break
        _, tiny_index, target_index = best_merge
        merged = _union_box(working[tiny_index], working[target_index])
        for index in sorted((tiny_index, target_index), reverse=True):
            working.pop(index)
        working.append(merged)
    return working


def _vertical_overlap(left: BoundingBox, right: BoundingBox) -> float:
    overlap = max(0, min(left.bottom, right.bottom) - max(left.y, right.y))
    return overlap / max(1, min(left.height, right.height))


def order_regions(boxes: Iterable[BoundingBox]) -> list[tuple[int, BoundingBox]]:
    """Assign line numbers and left-to-right reading order."""

    lines: list[list[BoundingBox]] = []
    for box in sorted(boxes, key=lambda item: (item.y + item.height / 2, item.x)):
        best_line = -1
        best_score = -1.0
        center = box.y + box.height / 2
        for index, line in enumerate(lines):
            line_top = min(item.y for item in line)
            line_bottom = max(item.bottom for item in line)
            line_height = max(1, line_bottom - line_top)
            line_center = (line_top + line_bottom) / 2
            overlap = max(
                _vertical_overlap(box, existing)
                for existing in line
            )
            center_score = 1.0 - abs(center - line_center) / max(box.height, line_height)
            score = max(overlap, center_score)
            if score >= 0.45 and score > best_score:
                best_line = index
                best_score = score
        if best_line < 0:
            lines.append([box])
        else:
            lines[best_line].append(box)

    lines.sort(key=lambda line: min(item.y for item in line))
    ordered: list[tuple[int, BoundingBox]] = []
    for line_index, line in enumerate(lines, 1):
        for box in sorted(line, key=lambda item: item.x):
            ordered.append((line_index, box))
    return ordered


def segment_prescription(
    image: Image.Image,
    *,
    level: str = "line",
    deskew: bool = True,
) -> SegmentationResult:
    initial_mask = build_ink_mask(image)
    angle = estimate_skew_angle(initial_mask) if deskew else 0.0
    rectified = rotate_page(image, angle)
    mask = build_ink_mask(rectified)
    ordered_boxes = order_regions(_boxes_from_mask(mask, level))

    regions: list[TextRegion] = []
    for reading_order, (line_index, box) in enumerate(ordered_boxes, 1):
        crop_mask = mask[box.y:box.bottom, box.x:box.right]
        ink_ratio = cv2.countNonZero(crop_mask) / max(crop_mask.size, 1)
        regions.append(TextRegion(
            region_id=f"region_{reading_order:04d}",
            line_index=line_index,
            reading_order=reading_order,
            bbox=box,
            ink_ratio=ink_ratio,
        ))
    return SegmentationResult(rectified, mask, tuple(regions), angle)


def crop_region(image: Image.Image, region: TextRegion) -> Image.Image:
    box = region.bbox
    return image.crop((box.x, box.y, box.right, box.bottom))


def annotate_regions(image: Image.Image, regions: Iterable[TextRegion]) -> Image.Image:
    annotated = image.convert("RGB").copy()
    draw = ImageDraw.Draw(annotated)
    font = ImageFont.load_default()
    for region in regions:
        box = region.bbox
        color = (28, 103, 177)
        draw.rectangle((box.x, box.y, box.right, box.bottom), outline=color, width=2)
        label = f"{region.reading_order} / L{region.line_index}"
        label_box = draw.textbbox((box.x, box.y), label, font=font)
        label_height = label_box[3] - label_box[1] + 4
        label_top = max(0, box.y - label_height)
        draw.rectangle(
            (box.x, label_top, box.x + label_box[2] - label_box[0] + 6, box.y),
            fill=color,
        )
        draw.text((box.x + 3, label_top + 2), label, fill="white", font=font)
    return annotated


def segment_file(
    image_path: Path,
    *,
    level: str = "line",
    deskew: bool = True,
) -> SegmentationResult:
    with Image.open(image_path) as image:
        return segment_prescription(image.convert("RGB"), level=level, deskew=deskew)
