from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from resume_agent.privacy import scan_public_tree


class PrivacyTests(unittest.TestCase):
    def test_scanner_rejects_private_paths_and_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_profile = root / "2_knowledge" / "master_profile.md"
            private_profile.parent.mkdir()
            private_profile.write_text("candidate data", encoding="utf-8")
            source = root / "source.py"
            source.write_text(
                'api_key = "' + "fc-" + 'example-secret-value"',
                encoding="utf-8",
            )

            findings = scan_public_tree(
                root,
                ("2_knowledge/master_profile.md", "source.py"),
            )

            self.assertTrue(any("private path" in finding for finding in findings))
            self.assertTrue(any("credential" in finding for finding in findings))

    def test_current_tracked_tree_contains_no_private_material(self) -> None:
        root = Path(__file__).parents[2]
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        tracked = tuple(
            path.decode("utf-8")
            for path in result.stdout.split(b"\0")
            if path
        )

        self.assertEqual(scan_public_tree(root, tracked), [])


if __name__ == "__main__":
    unittest.main()
