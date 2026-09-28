from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import yaml

from resume_agent.config import AppPaths
from resume_agent.context import build_action_packet
from resume_agent.models import ApplicationInput, WorkflowStep
from resume_agent.storage import RunStore
from resume_agent.workflow import next_action
from tests.support import seed_private_runtime


class ActionContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo_root = Path(__file__).parents[2]
        self.paths = AppPaths(self.repo_root, Path(self.temp_dir.name) / ".resume-agent")
        seed_private_runtime(self.paths)
        self.store = RunStore(self.paths)
        created = self.store.create(ApplicationInput(
            company="Example Labs",
            role="垂直领域产品负责人",
            language="zh",
            jd="定义AI原生垂直领域产品。",
        ))
        self.manifest = self.store.save_manifest(
            created.run_id,
            replace(
                created,
                current_step=WorkflowStep.DRAFT,
                selected_golden_record_id="sample-domain-owner-zh-v1",
            ),
        )
        self.store.save_artifact(
            created.run_id,
            "content-plan.yaml",
            yaml.safe_dump(
                {
                    "golden_record_id": "sample-domain-owner-zh-v1",
                    "changes": [
                        {"section": "summary", "action": "adapt", "reason": "岗位匹配"}
                    ],
                },
                allow_unicode=True,
            ),
        )
        self.store.save_artifact(created.run_id, "research.md", "不应进入当前步骤")
        self.store.save_artifact(created.run_id, "owner-final.html", "不应加载的终稿HTML")
        self.store.save_artifact(created.run_id, "owner-edit-diff.json", "不应加载的历史差异")
        self._write_preferences()

    def _write_preferences(self) -> None:
        preferences: list[dict[str, object]] = []
        for section in ("summary", "project"):
            for index in range(10):
                preferences.append({
                    "id": f"{section}-{index}",
                    "applies_to": {
                        "languages": ["zh"],
                        "template_families": ["domain"],
                        "sections": [section],
                    },
                    "prefer": f"{section}规则{index}",
                    "avoid": f"避免{index}",
                    "source": "owner-approved-test",
                    "status": "approved",
                })
        preferences.append({
            "id": "english-only",
            "applies_to": {
                "languages": ["en"],
                "template_families": ["domain"],
                "sections": ["summary"],
            },
            "prefer": "English preference",
            "avoid": "Generic prose",
            "source": "owner-approved-test",
            "status": "approved",
        })
        path = self.paths.runtime_root / "preferences" / "wording.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(
            yaml.safe_dump({"version": 1, "preferences": preferences}, allow_unicode=True),
            encoding="utf-8",
        )

    def test_draft_packet_contains_only_scoped_sources(self) -> None:
        action = next_action(self.paths, self.manifest)

        packet = build_action_packet(self.paths, self.manifest, action)
        encoded = json.dumps(packet, ensure_ascii=False)

        self.assertEqual(packet["step"], "draft")
        self.assertEqual(packet["profile"]["source"], "master_profile_ZH.md")
        self.assertEqual(packet["profile"]["language"], "zh")
        self.assertNotIn("master_profile.md", encoded)
        self.assertEqual(packet["golden_record"]["id"], "sample-domain-owner-zh-v1")
        self.assertEqual(packet["golden_record"]["content"]["template_family"], "domain")
        self.assertNotIn("sample-general-zh-v1", encoded)
        self.assertEqual(set(packet["artifacts"]), {"content-plan.yaml"})
        self.assertNotIn("不应加载的终稿HTML", encoded)
        self.assertNotIn("不应加载的历史差异", encoded)
        self.assertNotIn("不应进入当前步骤", encoded)

    def test_preferences_are_limited_to_eight_per_relevant_section(self) -> None:
        packet = build_action_packet(
            self.paths,
            self.manifest,
            next_action(self.paths, self.manifest),
        )

        self.assertEqual(len(packet["preferences"]["summary"]), 8)
        self.assertEqual(len(packet["preferences"]["project"]), 8)
        self.assertEqual(packet["preferences"]["experience"], [])
        self.assertEqual(packet["preferences"]["skills"], [])
        self.assertNotIn("English preference", json.dumps(packet, ensure_ascii=False))

    def test_packet_is_json_serializable_and_carries_direct_guardrails(self) -> None:
        packet = build_action_packet(
            self.paths,
            self.manifest,
            next_action(self.paths, self.manifest),
        )

        json.dumps(packet, ensure_ascii=False)
        instructions = packet["instructions"]
        self.assertIn("所选Golden Record", instructions)
        self.assertIn("有岗位理由", instructions)
        self.assertIn("有竞争力", instructions)
        self.assertIn("通行的专业术语", instructions)
        self.assertIn("不要创造", instructions)

    def test_research_packet_does_not_load_profile_or_resume_content(self) -> None:
        research_manifest = self.store.save_manifest(
            self.manifest.run_id,
            replace(
                self.manifest,
                current_step=WorkflowStep.RESEARCH,
                selected_golden_record_id=None,
            ),
        )

        packet = build_action_packet(
            self.paths,
            research_manifest,
            next_action(self.paths, research_manifest),
        )

        self.assertNotIn("profile", packet)
        self.assertNotIn("golden_record", packet)
        self.assertEqual(packet["artifacts"], {})
        self.assertIn("招聘意图", packet["instructions"])


if __name__ == "__main__":
    unittest.main()
