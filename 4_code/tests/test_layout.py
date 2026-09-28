from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from resume_agent.layout import balance_content, load_layout_spec
from resume_agent.models import ResumeBlock, ResumeBullet, ResumeContent, ResumePage
from resume_agent.pdf import PageLayoutReport
from resume_agent.render import render_html
from resume_agent.models import ApplicationInput


SPEC = """
id: test-layout
page:
  width_mm: 210
  height_mm: 297
  page_1_padding_mm: [8, 20, 3, 20]
  page_2_padding_mm: [12, 20, 3, 20]
palette:
  paper: '#ffffff'
  text_main: '#111827'
  text_muted: '#4b5563'
  accent: '#2563eb'
  border: '#e5e7eb'
spacing:
  section_gap_mm: 5
  item_gap_mm: 3.8
typography:
  identity_pt: 28
  headline_pt: 10.5
  section_pt: 11
  summary_pt: 9
  body_pt: 8.55
occupancy:
  minimum_fill_ratio: [0.60, 0.60]
  target_fill_ratio: [0.70, 0.70]
balance:
  max_iterations: 6
visual_regression:
  enabled: true
  baseline_pages: [baseline/page-1.png, baseline/page-2.png]
  max_bbox_delta: 0.05
  max_profile_distance: 0.08
  max_ink_density_delta: 0.04
"""


class LayoutSpecTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.spec_path = self.root / "layout-spec.yaml"
        self.spec_path.write_text(SPEC, encoding="utf-8")
        self.spec = load_layout_spec(self.spec_path)

    def test_renderer_uses_external_layout_spec(self) -> None:
        content = ResumeContent(
            language="en",
            template_family="general",
            headline="AI Lead",
            pages=[ResumePage([]), ResumePage([])],
        )
        output = self.root / "resume.html"

        html = render_html(
            content,
            ApplicationInput("Example", "AI Lead", "en", "Build AI"),
            output,
            layout_spec=self.spec,
        ).read_text(encoding="utf-8")

        self.assertIn("width:210.0mm", html)
        self.assertIn("padding:8.0mm 20.0mm 3.0mm 20.0mm", html)
        self.assertIn("const minimum=p.dataset.page==='1'?0.600:0.600", html)

    def test_balancer_moves_content_to_an_underfilled_first_page(self) -> None:
        first = ResumeBlock("experience", "First", bullets=[ResumeBullet(text="A")])
        second = ResumeBlock(
            "experience",
            "Second",
            bullets=[ResumeBullet(text=value) for value in ("B", "C", "D", "E", "F")],
        )
        content = ResumeContent(
            language="en",
            template_family="general",
            headline="AI Lead",
            pages=[ResumePage([first]), ResumePage([second])],
        )

        def measure(candidate: ResumeContent) -> tuple[PageLayoutReport, ...]:
            counts = [sum(len(block.bullets) for block in page.blocks) for page in candidate.pages]
            fills = [0.30 + count * 0.10 for count in counts]
            return tuple(
                PageLayoutReport(
                    page_number=index + 1,
                    overflow=fill > 0.95,
                    fill_ratio=fill,
                    underfilled=fill < 0.60,
                )
                for index, fill in enumerate(fills)
            )

        result = balance_content(content, self.spec, measure)

        self.assertTrue(result.changed)
        self.assertEqual([bullet.text for bullet in result.content.pages[0].blocks[-1].bullets], ["B", "C"])
        self.assertEqual([bullet.text for bullet in result.content.pages[1].blocks[0].bullets], ["D", "E", "F"])
        for report in result.reports:
            self.assertAlmostEqual(report.fill_ratio, 0.60)

    def test_balancer_keeps_already_balanced_pages_unchanged(self) -> None:
        content = ResumeContent(
            language="en",
            template_family="general",
            headline="AI Lead",
            pages=[
                ResumePage([ResumeBlock("experience", "First", bullets=[ResumeBullet(text="A")])]),
                ResumePage([ResumeBlock("experience", "Second", bullets=[ResumeBullet(text="B")])]),
            ],
        )
        reports = (
            PageLayoutReport(1, False, 0.70, False),
            PageLayoutReport(2, False, 0.70, False),
        )

        result = balance_content(content, self.spec, lambda _: reports)

        self.assertFalse(result.changed)
        self.assertIs(result.content, content)
        self.assertEqual(result.iterations, 0)


if __name__ == "__main__":
    unittest.main()
