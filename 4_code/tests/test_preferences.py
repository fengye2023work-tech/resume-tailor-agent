from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from resume_agent.preferences import load_applicable_preferences


VALID_YAML = """\
version: 1
preferences:
  - id: zh-summary-view
    applies_to:
      languages: [zh]
      template_families: [general]
      sections: [summary]
    prefer: 先表达有证据支撑的个人观点。
    avoid: 从职位名称和通用职责起笔。
    source: owner-final-2026-09-13
    status: approved
  - id: zh-summary-builder
    applies_to:
      languages: [zh]
      template_families: [general]
      sections: [summary, experience]
    prefer: 用亲自搭建的原型证明 Builder 特征。
    avoid: 只写协调和推进。
    source: owner-final-2026-09-13
    status: approved
  - id: pending-rule
    applies_to:
      languages: [zh]
      template_families: [general]
      sections: [summary]
    prefer: 不应生效。
    avoid: 不应生效。
    source: owner-final-2026-09-13
    status: proposed
"""


class PreferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "wording.yaml"
        self.path.write_text(VALID_YAML, encoding="utf-8")

    def test_loads_only_approved_exact_scope_matches_in_file_order(self) -> None:
        rules = load_applicable_preferences(
            self.path,
            language="zh",
            template_family="general",
            section="summary",
            limit=8,
        )

        self.assertEqual([rule.id for rule in rules], ["zh-summary-view", "zh-summary-builder"])

    def test_applies_positive_limit_after_filtering(self) -> None:
        rules = load_applicable_preferences(
            self.path,
            language="zh",
            template_family="general",
            section="summary",
            limit=1,
        )

        self.assertEqual([rule.id for rule in rules], ["zh-summary-view"])

    def test_nonmatching_scope_returns_empty_list(self) -> None:
        rules = load_applicable_preferences(
            self.path,
            language="en",
            template_family="general",
            section="summary",
        )

        self.assertEqual(rules, [])

    def test_missing_file_is_an_empty_optional_inventory(self) -> None:
        self.assertEqual(
            load_applicable_preferences(
                self.path.with_name("missing.yaml"),
                language="zh",
                template_family="general",
                section="summary",
            ),
            [],
        )

    def test_rejects_nonpositive_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "limit must be positive"):
            load_applicable_preferences(
                self.path,
                language="zh",
                template_family="general",
                section="summary",
                limit=0,
            )

    def test_rejects_duplicate_ids(self) -> None:
        self.path.write_text(VALID_YAML.replace("pending-rule", "zh-summary-view"), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "ids must be unique"):
            load_applicable_preferences(
                self.path,
                language="zh",
                template_family="general",
                section="summary",
            )


    def test_rejects_wrong_schema_version(self) -> None:
        self.path.write_text(VALID_YAML.replace("version: 1", "version: 2"), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "version 1"):
            load_applicable_preferences(
                self.path,
                language="zh",
                template_family="general",
                section="summary",
            )


    def test_rejects_preferences_that_are_not_a_list(self) -> None:
        self.path.write_text("version: 1\npreferences: {}\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "preferences must be a list"):
            load_applicable_preferences(
                self.path,
                language="zh",
                template_family="general",
                section="summary",
            )

    def test_rejects_preference_missing_required_text(self) -> None:
        self.path.write_text(VALID_YAML.replace("    prefer: 先表达有证据支撑的个人观点。\n", "", 1), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "id, prefer, avoid, and source are required"):
            load_applicable_preferences(
                self.path,
                language="zh",
                template_family="general",
                section="summary",
            )

    def test_rejects_invalid_scope_and_status_values(self) -> None:
        invalid_values = (
            ("status", None, "active", "Invalid preference status"),
            ("scope", "languages", ["fr"], "Invalid preference languages"),
            ("scope", "template_families", ["creative"], "Invalid preference template families"),
            ("scope", "sections", [""], "sections must contain non-empty values"),
        )
        for target, key, value, message in invalid_values:
            with self.subTest(target=target, key=key):
                payload = yaml.safe_load(VALID_YAML)
                if target == "status":
                    payload["preferences"][0]["status"] = value
                else:
                    payload["preferences"][0]["applies_to"][key] = value
                self.path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")

                with self.assertRaisesRegex(ValueError, message):
                    load_applicable_preferences(
                        self.path,
                        language="zh",
                        template_family="general",
                        section="summary",
                    )

    def test_rejects_non_mapping_records_and_scalar_scope_lists(self) -> None:
        invalid_payloads = (
            ({"version": 1, "preferences": ["not-a-mapping"]}, "Preference must be a mapping"),
            (
                {
                    "version": 1,
                    "preferences": [
                        {
                            "id": "scalar-sections",
                            "applies_to": {
                                "languages": ["zh"],
                                "template_families": ["general"],
                                "sections": "summary",
                            },
                            "prefer": "保留个人观点。",
                            "avoid": "通用表述。",
                            "source": "owner-final-2026-09-13",
                            "status": "approved",
                        }
                    ],
                },
                "Preference sections must be a list",
            ),
        )
        for payload, message in invalid_payloads:
            with self.subTest(message=message):
                self.path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")

                with self.assertRaisesRegex(ValueError, message):
                    load_applicable_preferences(
                        self.path,
                        language="zh",
                        template_family="general",
                        section="summary",
                    )

    def test_rejects_malformed_yaml(self) -> None:
        self.path.write_text("version: [", encoding="utf-8")

        with self.assertRaises(yaml.YAMLError):
            load_applicable_preferences(
                self.path,
                language="zh",
                template_family="general",
                section="summary",
            )


class SeedInventoryTests(unittest.TestCase):
    def test_seed_inventory_is_valid_and_scoped_to_chinese_general_resume(self) -> None:
        root = Path(__file__).parents[2]
        inventory = root / ".resume-agent" / "preferences" / "wording.yaml"

        summary_rules = load_applicable_preferences(
            inventory,
            language="zh",
            template_family="general",
            section="summary",
        )
        project_rules = load_applicable_preferences(
            inventory,
            language="zh",
            template_family="general",
            section="project",
        )

        self.assertEqual(len(summary_rules), 4)
        self.assertEqual(len(project_rules), 7)
        self.assertEqual(
            load_applicable_preferences(
                inventory,
                language="en",
                template_family="general",
                section="summary",
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
