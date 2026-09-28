from __future__ import annotations

import unittest
from pathlib import Path

from resume_agent.models import ResumeBlock, ResumeBullet, ResumeContent, ResumePage
from resume_agent.profile import load_profile
from resume_agent.validation import validate_content


FIXTURES = Path(__file__).parent / "fixtures"


def content_with(bullet: ResumeBullet, *, pages: int = 2) -> ResumeContent:
    page = ResumePage(
        blocks=[ResumeBlock(kind="experience", title="Example Co", bullets=[bullet])]
    )
    return ResumeContent(
        language="en",
        template_family="general",
        headline="AI Lead",
        pages=[page for _ in range(pages)],
    )


class ContentValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_profile(FIXTURES / "profile_en.md", "en")

    def test_untraced_material_claim_fails(self) -> None:
        report = validate_content(content_with(ResumeBullet(text="Built an AI workflow.")), self.profile)

        self.assertFalse(report.ok)
        self.assertIn("claim_without_source", report.error_codes)

    def test_owner_confirmed_claim_is_allowed(self) -> None:
        claim = ResumeBullet(text="Reduced review time by 40%.", confirmed_by_user=True)

        self.assertTrue(validate_content(content_with(claim), self.profile).ok)

    def test_unknown_source_reference_fails(self) -> None:
        claim = ResumeBullet(text="Built an AI workflow.", source_refs=["profile:missing"])

        report = validate_content(content_with(claim), self.profile)

        self.assertIn("unknown_source_ref", report.error_codes)

    def test_resume_requires_exactly_two_pages(self) -> None:
        claim = ResumeBullet(text="Built an AI workflow.", confirmed_by_user=True)

        report = validate_content(content_with(claim, pages=1), self.profile)

        self.assertIn("page_count", report.error_codes)

    def test_structured_experience_requires_an_evidence_chain(self) -> None:
        claim = ResumeBullet(
            label="AI workflow",
            action="Built an AI workflow.",
            source_refs=["profile:professional-experience/example-co"],
        )

        report = validate_content(content_with(claim), self.profile)

        self.assertIn("thin_evidence", {issue.code for issue in report.issues})

    def test_bullet_count_alone_does_not_mark_a_block_dense(self) -> None:
        bullets = [
            ResumeBullet(
                label=f"Evidence {index}",
                situation="A verified operating constraint existed.",
                action="Designed and delivered a focused response.",
                result="Produced a validated operational outcome.",
                source_refs=["profile:professional-experience/example-co"],
            )
            for index in range(5)
        ]
        content = ResumeContent(
            language="en",
            template_family="general",
            headline="AI Lead",
            pages=[
                ResumePage([ResumeBlock("experience", "Example Co", bullets=bullets)]),
                ResumePage([ResumeBlock("education", "Education")]),
            ],
        )

        report = validate_content(content, self.profile)

        self.assertNotIn("dense_block", {issue.code for issue in report.issues})

    def test_complete_project_evidence_is_not_penalized_for_character_share(self) -> None:
        project = ResumeBlock(
            "project",
            "Selected systems",
            bullets=[
                ResumeBullet(
                    label="Verified system",
                    situation="A costly manual workflow constrained delivery capacity.",
                    action="Designed and shipped a deterministic tool around the verified rules.",
                    result="Reduced the documented review cycle by 40%.",
                    source_refs=["profile:professional-experience/example-co"],
                )
                for _ in range(3)
            ],
        )
        content = ResumeContent(
            language="en",
            template_family="general",
            headline="AI Lead",
            pages=[
                ResumePage([project]),
                ResumePage([ResumeBlock("education", "Education")]),
            ],
        )

        report = validate_content(content, self.profile)

        self.assertNotIn("project_weight", {issue.code for issue in report.issues})


if __name__ == "__main__":
    unittest.main()
