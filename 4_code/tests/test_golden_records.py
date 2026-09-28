from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from resume_agent.config import AppPaths
from resume_agent.golden_records import get_golden_record, load_golden_record_catalog
from tests.support import seed_private_runtime


class GoldenRecordCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo_root = Path(__file__).parents[2]
        self.paths = AppPaths(self.repo_root, Path(self.temp_dir.name) / ".resume-agent")
        seed_private_runtime(self.paths)

    def test_sample_catalog_exposes_two_fictional_chinese_records(self) -> None:
        records = load_golden_record_catalog(self.paths.golden_record_catalog)

        self.assertEqual(
            [record.id for record in records],
            [
                "sample-general-zh-v1",
                "sample-domain-owner-zh-v1",
            ],
        )
        self.assertEqual([record.language for record in records], ["zh", "zh"])
        self.assertEqual(
            [record.template_family for record in records],
            ["general", "domain"],
        )
        for record in records:
            self.assertTrue(record.content_path.is_file())
            self.assertTrue(record.html_path.is_file())
            self.assertTrue(record.content_path.is_relative_to(self.paths.golden_records_root))
            self.assertTrue(record.html_path.is_relative_to(self.paths.golden_records_root))
            self.assertTrue(record.target_roles)

    def test_duplicate_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "content.yaml").write_text("language: zh\n", encoding="utf-8")
            (root / "resume.html").write_text("<html></html>", encoding="utf-8")
            catalog = root / "catalog.yaml"
            catalog.write_text(
                """\
version: 1
records:
  - id: duplicate
    language: zh
    template_family: general
    target_roles: [AI产品经理]
    content: content.yaml
    html: resume.html
  - id: duplicate
    language: zh
    template_family: domain
    target_roles: [垂直领域产品负责人]
    content: content.yaml
    html: resume.html
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Duplicate Golden Record id"):
                load_golden_record_catalog(catalog)

    def test_missing_source_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "resume.html").write_text("<html></html>", encoding="utf-8")
            catalog = root / "catalog.yaml"
            catalog.write_text(
                """\
version: 1
records:
  - id: missing-content
    language: zh
    template_family: general
    target_roles: [AI产品经理]
    content: missing.yaml
    html: resume.html
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Golden Record content file not found"):
                load_golden_record_catalog(catalog)

    def test_source_path_cannot_escape_catalog_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root.parent / "outside.yaml"
            outside.write_text("language: zh\n", encoding="utf-8")
            self.addCleanup(outside.unlink, missing_ok=True)
            (root / "resume.html").write_text("<html></html>", encoding="utf-8")
            catalog = root / "catalog.yaml"
            catalog.write_text(
                """\
version: 1
records:
  - id: escaped-content
    language: zh
    template_family: general
    target_roles: [AI产品经理]
    content: ../outside.yaml
    html: resume.html
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "must stay inside"):
                load_golden_record_catalog(catalog)

    def test_selecting_record_with_wrong_language_is_rejected(self) -> None:
        records = load_golden_record_catalog(self.paths.golden_record_catalog)

        with self.assertRaisesRegex(ValueError, "language zh, not en"):
            get_golden_record(
                records,
                "sample-general-zh-v1",
                "en",
            )

    def test_unknown_record_id_is_rejected(self) -> None:
        records = load_golden_record_catalog(self.paths.golden_record_catalog)

        with self.assertRaisesRegex(ValueError, "Unknown Golden Record"):
            get_golden_record(records, "missing", "zh")


if __name__ == "__main__":
    unittest.main()
