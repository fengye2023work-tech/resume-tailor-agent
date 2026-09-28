from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml


class ResumeAgentSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).parents[2]
        self.skill_path = self.root / "1_docs" / "skills" / "resume-agent" / "SKILL.md"

    def _skill(self) -> tuple[dict[str, object], str]:
        text = self.skill_path.read_text(encoding="utf-8")
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, flags=re.DOTALL)
        self.assertIsNotNone(match, "skill must have YAML frontmatter")
        return yaml.safe_load(match.group(1)), match.group(2)

    def test_skill_is_discoverable_for_resume_application_work(self) -> None:
        frontmatter, _ = self._skill()

        self.assertEqual(frontmatter["name"], "resume-agent")
        description = str(frontmatter["description"])
        self.assertTrue(description.startswith("Use when"))
        self.assertIn("resume", description.lower())
        self.assertIn("job description", description.lower())

    def test_skill_defines_the_ide_state_loop_without_nested_model_sessions(self) -> None:
        _, body = self._skill()

        self.assertRegex(body, r"IDE.{0,40}primary.{0,20}(environment|entry)")
        self.assertIn("resume-agent apply", body)
        self.assertIn("resume-agent next", body)
        self.assertIn("resume-agent submit", body)
        self.assertIn("resume-agent resume", body)
        self.assertIn("resume-agent status", body)
        self.assertRegex(body, r"Do not.{0,30}(codex exec|nested model)")

    def test_skill_uses_selected_golden_record_and_approved_preferences(self) -> None:
        _, body = self._skill()

        self.assertIn("selected Golden Record", body)
        self.assertIn("approved preferences", body)
        self.assertIn("incremental", body)
        self.assertIn("established professional terminology", body)
        self.assertRegex(body, r"do not create[\s\S]{0,30}(terms|terminology)")

    def test_skill_requires_owner_approval_before_long_term_learning(self) -> None:
        _, body = self._skill()

        self.assertIn("explicit user approval", body)
        self.assertRegex(body, r"unapproved edits[\s\S]{0,30}(long-term|preferences)")

    def test_legacy_resume_tailor_is_only_a_compatibility_pointer(self) -> None:
        legacy = self.root / "1_docs" / "skills" / "resume-tailor" / "SKILL.md"
        body = legacy.read_text(encoding="utf-8")

        self.assertIn("../resume-agent/SKILL.md", body)
        self.assertNotIn("resume-agent start", body)
        self.assertNotIn("## Workflow", body)


if __name__ == "__main__":
    unittest.main()
