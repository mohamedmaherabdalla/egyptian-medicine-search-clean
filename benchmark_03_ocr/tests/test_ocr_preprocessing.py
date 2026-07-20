#!/usr/bin/env python3

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from run_ocr_benchmark import preprocess_image


class OCRPreprocessingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.image_path = Path(self.temp_dir.name) / "sample.png"
        image = Image.new("L", (200, 100), 245)
        draw = ImageDraw.Draw(image)
        draw.rectangle((70, 35, 129, 64), fill=20)
        image.save(self.image_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_raw_preserves_source_geometry(self):
        self.assertEqual(preprocess_image(self.image_path, "raw").size, (200, 100))

    def test_ink_crop_square_removes_margins_and_centers_content(self):
        cropped = preprocess_image(self.image_path, "ink_crop_square_raw")
        self.assertEqual(cropped.width, cropped.height)
        self.assertLess(cropped.width, 200)
        self.assertLess(cropped.getpixel((cropped.width // 2, cropped.height // 2)), 100)

    def test_autocontrast_crop_expands_tonal_range(self):
        cropped = preprocess_image(self.image_path, "ink_crop_square_autocontrast")
        low, high = cropped.getextrema()
        self.assertEqual(low, 0)
        self.assertEqual(high, 255)

    def test_unknown_preprocessing_is_rejected(self):
        with self.assertRaises(ValueError):
            preprocess_image(self.image_path, "unknown")


if __name__ == "__main__":
    unittest.main()
