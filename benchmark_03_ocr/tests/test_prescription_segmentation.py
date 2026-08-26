from __future__ import annotations

import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


BENCHMARK_DIR = Path(__file__).resolve().parents[1]
if str(BENCHMARK_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_DIR))

from prescription_segmentation import (  # noqa: E402
    BoundingBox,
    build_ink_mask,
    crop_region,
    estimate_skew_angle,
    order_regions,
    segment_prescription,
)


class PrescriptionSegmentationTests(unittest.TestCase):
    def make_page(self) -> Image.Image:
        page = Image.new("RGB", (760, 420), "white")
        draw = ImageDraw.Draw(page)
        # Four disconnected handwritten-like regions on two lines.
        for x, y, width in ((45, 60, 210), (410, 62, 230), (50, 245, 190), (390, 242, 250)):
            points = []
            for offset in range(0, width, 12):
                points.extend([
                    (x + offset, y + 34),
                    (x + offset + 5, y + 5 + (offset % 17)),
                    (x + offset + 11, y + 32),
                ])
            draw.line(points, fill="black", width=5, joint="curve")
        return page

    def test_orders_regions_by_line_then_x(self) -> None:
        boxes = [
            BoundingBox(320, 210, 90, 35),
            BoundingBox(30, 45, 100, 38),
            BoundingBox(300, 48, 90, 35),
            BoundingBox(35, 205, 110, 40),
        ]
        ordered = order_regions(boxes)
        self.assertEqual([(line, box.x) for line, box in ordered], [
            (1, 30), (1, 300), (2, 35), (2, 320),
        ])

    def test_word_mode_finds_four_ordered_regions(self) -> None:
        result = segment_prescription(self.make_page(), level="word", deskew=False)
        self.assertEqual(len(result.regions), 4)
        self.assertEqual([region.line_index for region in result.regions], [1, 1, 2, 2])
        self.assertEqual([region.reading_order for region in result.regions], [1, 2, 3, 4])
        for region in result.regions:
            crop = crop_region(result.rectified_image, region)
            self.assertGreater(crop.width, 100)
            self.assertGreater(crop.height, 20)

    def test_line_mode_merges_each_row(self) -> None:
        result = segment_prescription(self.make_page(), level="line", deskew=False)
        self.assertEqual(len(result.regions), 2)
        self.assertEqual([region.line_index for region in result.regions], [1, 2])

    def test_deskew_preserves_regions_and_removes_small_rotation(self) -> None:
        rotated = self.make_page().rotate(7, expand=True, fillcolor="white")
        result = segment_prescription(rotated, level="word", deskew=True)
        residual = estimate_skew_angle(build_ink_mask(result.rectified_image))
        self.assertEqual(len(result.regions), 4)
        self.assertLess(abs(residual), 1.0)


if __name__ == "__main__":
    unittest.main()
