from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pypdf import PdfWriter

from resume_agent.pdf import inspect_dumped_dom, inspect_dumped_layout, inspect_overflow, print_pdf, verify_pdf


class PdfTests(unittest.TestCase):
    def test_dumped_dom_reports_overflow_page_numbers(self) -> None:
        dom = '<main class="resume-page" data-page="1" data-overflow="false"></main><main class="resume-page" data-page="2" data-overflow="true"></main>'
        self.assertEqual(inspect_dumped_dom(dom), [2])

    def test_dumped_dom_reports_page_fill_and_underfill(self) -> None:
        dom = (
            '<main class="resume-page" data-page="1" data-overflow="false" '
            'data-fill-ratio="0.797" data-underfilled="true"></main>'
            '<main class="resume-page" data-page="2" data-overflow="false" '
            'data-fill-ratio="0.891" data-underfilled="false"></main>'
        )

        reports = inspect_dumped_layout(dom)

        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[0].page_number, 1)
        self.assertAlmostEqual(reports[0].fill_ratio, 0.797)
        self.assertTrue(reports[0].underfilled)
        self.assertFalse(reports[1].underfilled)

    def test_pdf_requires_exactly_two_pages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "one.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=595, height=842)
            with path.open("wb") as stream:
                writer.write(stream)

            report = verify_pdf(path)

        self.assertFalse(report.ok)
        self.assertEqual(report.page_count, 1)

    def test_two_page_pdf_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "two.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=595, height=842)
            writer.add_blank_page(width=595, height=842)
            with path.open("wb") as stream:
                writer.write(stream)

            report = verify_pdf(path)

        self.assertTrue(report.ok)

    def test_pdf_renderer_decodes_browser_output_as_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            html_path = root / "resume.html"
            pdf_path = root / "resume.pdf"
            html_path.write_text("<html></html>", encoding="utf-8")
            pdf_path.write_bytes(b"pdf")
            with patch("resume_agent.pdf.subprocess.run", return_value=SimpleNamespace(returncode=0, stderr="")) as run:
                print_pdf(html_path, pdf_path, browser=Path("edge.exe"))

        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["errors"], "replace")

    def test_overflow_preflight_tolerates_transient_profile_lock(self) -> None:
        browser_result = SimpleNamespace(
            returncode=0,
            stdout='<main class="resume-page" data-page="1" data-overflow="false"></main>',
            stderr="",
        )
        with tempfile.TemporaryDirectory() as directory:
            html_path = Path(directory) / "resume.html"
            html_path.write_text("<html></html>", encoding="utf-8")
            with (
                patch("resume_agent.pdf.subprocess.run", return_value=browser_result),
                patch("resume_agent.pdf.shutil.rmtree", side_effect=[PermissionError(32, "profile locked"), None]),
            ):
                try:
                    overflow = inspect_overflow(html_path, browser=Path("edge.exe"))
                except PermissionError as exc:
                    self.fail(f"transient browser profile lock escaped cleanup: {exc}")

        self.assertEqual(overflow, [])


if __name__ == "__main__":
    unittest.main()
