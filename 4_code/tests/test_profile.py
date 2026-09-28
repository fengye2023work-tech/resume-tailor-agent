from __future__ import annotations

import unittest
from pathlib import Path

from resume_agent.profile import load_profile


FIXTURES = Path(__file__).parent / "fixtures"


class ProfileTests(unittest.TestCase):
    def test_profile_builds_stable_heading_references(self) -> None:
        profile = load_profile(FIXTURES / "profile_en.md", "en")

        self.assertIn("profile:professional-experience/example-co", profile.source_refs)
        section = profile.sections["profile:professional-experience/example-co"]
        self.assertIn("reduced review time by 40%", section.text)

    def test_profile_rejects_language_outside_supported_pair(self) -> None:
        with self.assertRaisesRegex(ValueError, "language"):
            load_profile(FIXTURES / "profile_en.md", "fr")


if __name__ == "__main__":
    unittest.main()
