from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from resume_agent.models import ApplicationInput, ResumeBlock, ResumeBullet, ResumeContent, ResumePage
from resume_agent.render import render_html


class RenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.output = Path(self.temp_dir.name) / "resume.html"
        self.application = ApplicationInput("Example Co", "AI Lead", "en", "Build AI")
        self.content = ResumeContent(
            language="en",
            template_family="general",
            headline="AI Lead",
            pages=[
                ResumePage([ResumeBlock("summary", "Profile", "Practical AI builder")]),
                ResumePage([ResumeBlock("education", "Education", "MSc")]),
            ],
        )

    def test_renderer_emits_two_explicit_a4_pages(self) -> None:
        html = render_html(self.content, self.application, self.output).read_text(encoding="utf-8")

        self.assertEqual(html.count('class="resume-page"'), 2)
        self.assertIn('data-page="1"', html)
        self.assertIn('data-page="2"', html)
        self.assertIn("@page", html)
        self.assertIn("Sample Candidate", html)

    def test_renderer_escapes_untrusted_text(self) -> None:
        self.content.headline = '<script>alert("x")</script>'

        html = render_html(self.content, self.application, self.output).read_text(encoding="utf-8")

        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    def test_renderer_preserves_legacy_resume_design_system(self) -> None:
        self.content.pages[0].blocks = [
            ResumeBlock("summary", "Contact", "Helsinki · person@example.com"),
            ResumeBlock("summary", "Professional Profile", "Practical AI builder"),
            ResumeBlock("skills", "Core Expertise", bullets=[
                ResumeBullet("AI delivery: Discovery and production rollout."),
                ResumeBullet("Agentic systems: Reliable orchestration."),
            ]),
            ResumeBlock("experience", "Example Co | AI Lead | 2024-Present", bullets=[
                ResumeBullet("Production platform: Delivered measurable value.")
            ]),
        ]

        html = render_html(self.content, self.application, self.output).read_text(encoding="utf-8")

        self.assertIn("family=Manrope", html)
        self.assertIn("family=Outfit", html)
        self.assertIn("grid-template-columns:1.25fr .75fr", html)
        self.assertIn('class="header-right"', html)
        self.assertIn('class="skills-container"', html)
        self.assertIn('class="exp-title">AI Lead', html)
        self.assertIn('class="exp-company">Example Co', html)
        self.assertIn('class="achievement-label">Production platform', html)
        self.assertNotIn("<h2>Contact</h2>", html)

    def test_renderer_expands_structured_evidence_chain(self) -> None:
        self.content.pages[0].blocks = [
            ResumeBlock(
                "experience",
                "Example Co | AI Lead | 2024-Present",
                bullets=[
                    ResumeBullet(
                        label="Production platform",
                        situation="Records were fragmented across systems.",
                        action="I designed and shipped a governed retrieval workflow.",
                        result="Review time fell by 40%.",
                    )
                ],
            )
        ]

        html = render_html(self.content, self.application, self.output).read_text(encoding="utf-8")

        self.assertIn('class="achievement-label">Production platform', html)
        self.assertIn(
            "Records were fragmented across systems. I designed and shipped a governed retrieval workflow. Review time fell by 40%.",
            html,
        )

    def test_renderer_localizes_fixed_section_labels_for_chinese_resume(self) -> None:
        application = ApplicationInput("示例公司", "AI产品经理", "zh", "建设AI场景")
        content = ResumeContent(
            language="zh",
            template_family="domain",
            headline="AI场景产品经理",
            pages=[
                ResumePage([
                    ResumeBlock("skills", "Core Expertise", bullets=[
                        ResumeBullet("场景规划: 业务调研与产品路线图。"),
                        ResumeBullet("产品交付: 原型与功能验收。"),
                        ResumeBullet("AI应用: Agent工作流。"),
                        ResumeBullet("建筑科技: BIM与参数化设计。"),
                    ]),
                    ResumeBlock("experience", "示例公司 | AI产品经理 | 2026–至今"),
                ]),
                ResumePage([ResumeBlock("education", "教育", "建筑学硕士")]),
            ],
        )

        html = render_html(content, application, self.output).read_text(encoding="utf-8")

        self.assertIn("产品策略与交付", html)
        self.assertIn("技术基础与行业能力", html)
        self.assertIn("专业经历与产品成果", html)
        self.assertIn("Microsoft YaHei", html)
        self.assertNotIn("PRODUCT STRATEGY &amp; DELIVERY", html)

    def test_renderer_rejects_content_without_two_pages(self) -> None:
        self.content.pages.pop()

        with self.assertRaisesRegex(ValueError, "two pages"):
            render_html(self.content, self.application, self.output)


if __name__ == "__main__":
    unittest.main()
