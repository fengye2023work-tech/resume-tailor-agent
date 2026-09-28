from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw
from pypdf import PdfWriter

from resume_agent.layout import load_layout_spec
from resume_agent.visual_regression import compare_layout_screenshots, render_pdf_screenshots

from test_layout import SPEC


class VisualRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        spec_path = self.root / "layout-spec.yaml"
        spec_path.write_text(SPEC, encoding="utf-8")
        self.spec = load_layout_spec(spec_path)

    def image(self, name: str, *, left: int = 10) -> Path:
        path = self.root / name
        image = Image.new("RGB", (100, 140), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((left, 10, left + 70, 125), fill="black")
        image.save(path)
        return path

    def test_identical_screenshots_pass(self) -> None:
        baseline = self.image("baseline.png")
        candidate = self.image("candidate.png")

        report = compare_layout_screenshots([candidate], [baseline], self.spec)

        self.assertTrue(report.ok)
        self.assertEqual(report.pages[0].bbox_delta, 0.0)
        self.assertEqual(report.pages[0].profile_distance, 0.0)

    def test_shifted_layout_fails(self) -> None:
        baseline = self.image("baseline.png")
        candidate = self.image("candidate.png", left=25)

        report = compare_layout_screenshots([candidate], [baseline], self.spec)

        self.assertFalse(report.ok)
        self.assertGreater(report.pages[0].bbox_delta, self.spec.visual.max_bbox_delta)

    def test_pdf_renderer_produces_one_screenshot_per_page(self) -> None:
        pdf_path = self.root / "two-pages.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        writer.add_blank_page(width=595, height=842)
        with pdf_path.open("wb") as stream:
            writer.write(stream)

        pages = render_pdf_screenshots(pdf_path, self.root / "rendered")

        self.assertEqual(len(pages), 2)
        self.assertTrue(all(page.is_file() and page.stat().st_size > 0 for page in pages))


if __name__ == "__main__":
    unittest.main()
