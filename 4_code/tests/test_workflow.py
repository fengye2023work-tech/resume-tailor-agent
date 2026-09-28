from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import yaml

from resume_agent.config import AppPaths
from resume_agent.models import ApplicationInput, WorkflowStep
from resume_agent.storage import RunStore
from resume_agent.workflow import next_action, submit_action
from tests.support import seed_private_runtime


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo_root = Path(__file__).parents[2]
        self.paths = AppPaths(self.repo_root, Path(self.temp_dir.name) / ".resume-agent")
        seed_private_runtime(self.paths)
        self.store = RunStore(self.paths)
        self.manifest = self.store.create(ApplicationInput(
            company="Example Co",
            role="垂直领域AI产品负责人",
            language="zh",
            jd="负责垂直领域产品；熟悉 Databricks 者优先。",
        ))
        self.submissions = Path(self.temp_dir.name) / "submissions"
        self.submissions.mkdir()

    def _write(self, name: str, content: str) -> Path:
        path = self.submissions / name
        path.write_text(content, encoding="utf-8")
        return path

    def _write_yaml(self, name: str, payload: object) -> Path:
        return self._write(name, yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))

    def _submit_research_and_selection(self) -> None:
        manifest = submit_action(
            self.store,
            self.manifest.run_id,
            WorkflowStep.RESEARCH,
            self._write("research.md", "# 招聘意图\n\n重视垂直领域产品判断。"),
        )
        self.assertEqual(manifest.current_step, WorkflowStep.GOLDEN_RECORD)
        manifest = submit_action(
            self.store,
            self.manifest.run_id,
            WorkflowStep.GOLDEN_RECORD,
            self._write_yaml(
                "golden-record-selection.yaml",
                {
                    "golden_record_id": "sample-domain-owner-zh-v1",
                    "reason": "岗位强调垂直领域产品判断。",
                },
            ),
        )
        self.assertEqual(manifest.current_step, WorkflowStep.GAP_REVIEW)
        self.assertEqual(manifest.selected_golden_record_id, "sample-domain-owner-zh-v1")

    def test_ordered_workflow_skips_questions_when_none_are_needed(self) -> None:
        self.assertEqual(next_action(self.paths, self.manifest).step, WorkflowStep.RESEARCH)
        self._submit_research_and_selection()

        manifest = submit_action(
            self.store,
            self.manifest.run_id,
            WorkflowStep.GAP_REVIEW,
            self._write_yaml(
                "questions.yaml",
                {
                    "summary": "现有证据足以完成定制。",
                    "emphasis": ["垂直领域产品判断"],
                    "deemphasis": ["早期通用经历"],
                    "questions": [],
                },
            ),
        )
        self.assertEqual(manifest.current_step, WorkflowStep.CONTENT_PLAN)
        self.assertEqual(manifest.pending_questions, ())

        manifest = submit_action(
            self.store,
            self.manifest.run_id,
            WorkflowStep.CONTENT_PLAN,
            self._write_yaml(
                "content-plan.yaml",
                {
                    "golden_record_id": "sample-domain-owner-zh-v1",
                    "changes": [
                        {"section": "summary", "action": "adapt", "reason": "回应岗位意图"}
                    ],
                },
            ),
        )
        self.assertEqual(manifest.current_step, WorkflowStep.DRAFT)

        draft = {
            "language": "zh",
            "template_family": "domain",
            "headline": "垂直领域AI产品负责人",
            "pages": [{"blocks": []}, {"blocks": []}],
        }
        manifest = submit_action(
            self.store,
            self.manifest.run_id,
            WorkflowStep.DRAFT,
            self._write_yaml("resume-content-draft.yaml", draft),
        )
        self.assertEqual(manifest.current_step, WorkflowStep.LANGUAGE_REVIEW)

        manifest = submit_action(
            self.store,
            self.manifest.run_id,
            WorkflowStep.LANGUAGE_REVIEW,
            self._write_yaml("resume-content.yaml", draft),
        )
        self.assertEqual(manifest.current_step, WorkflowStep.RENDER)
        render_action = next_action(self.paths, manifest)
        self.assertEqual(render_action.kind, "command")
        self.assertEqual(render_action.output_file, "agent-draft.html")

        run_dir = self.paths.applications_root / self.manifest.run_id
        html = run_dir / "agent-draft.html"
        html.write_text("<!doctype html><main class='resume-page'>简历</main>", encoding="utf-8")
        (run_dir / "resume.pdf").write_bytes(b"%PDF-1.4\n")
        manifest = submit_action(
            self.store,
            self.manifest.run_id,
            WorkflowStep.RENDER,
            html,
        )

        self.assertEqual(manifest.current_step, WorkflowStep.OWNER_REVIEW)
        owner_action = next_action(self.paths, manifest)
        self.assertEqual(owner_action.kind, "user")
        self.assertIsNone(owner_action.output_file)

    def test_material_missing_skill_becomes_one_focused_user_question(self) -> None:
        self._submit_research_and_selection()

        manifest = submit_action(
            self.store,
            self.manifest.run_id,
            WorkflowStep.GAP_REVIEW,
            self._write_yaml(
                "questions.yaml",
                {
                    "summary": "Databricks 是岗位中的重要技能，但现有资料没有证据。",
                    "emphasis": ["真实垂直领域经验"],
                    "deemphasis": [],
                    "questions": [
                        {
                            "id": "databricks-experience",
                            "question": "你是否在项目或PoC中使用过Databricks？",
                            "reason": "回答会明显影响技术能力的写法。",
                        }
                    ],
                },
            ),
        )

        self.assertEqual(manifest.current_step, WorkflowStep.QUESTIONS)
        self.assertEqual(manifest.pending_questions, ("你是否在项目或PoC中使用过Databricks？",))
        action = next_action(self.paths, manifest)
        self.assertEqual(action.kind, "user")
        self.assertIn("你是否在项目或PoC中使用过Databricks？", action.instructions)
        self.assertNotIn("回答会明显影响", action.instructions)

        manifest = submit_action(
            self.store,
            self.manifest.run_id,
            WorkflowStep.QUESTIONS,
            self._write_yaml(
                "answers.yaml",
                {
                    "answers": [
                        {
                            "question_id": "databricks-experience",
                            "answer": "在PoC中使用过，熟悉基本工作流。",
                        }
                    ]
                },
            ),
        )
        self.assertEqual(manifest.current_step, WorkflowStep.CONTENT_PLAN)
        self.assertEqual(manifest.pending_questions, ())

    def test_malformed_submission_keeps_current_step_and_valid_artifacts(self) -> None:
        accepted = submit_action(
            self.store,
            self.manifest.run_id,
            WorkflowStep.RESEARCH,
            self._write("research.md", "# 有效研究\n\n招聘意图明确。"),
        )
        stored_research = self.store.artifact_path(self.manifest.run_id, "research.md")
        self.assertEqual(accepted.current_step, WorkflowStep.GOLDEN_RECORD)

        with self.assertRaisesRegex(ValueError, "golden_record_id"):
            submit_action(
                self.store,
                self.manifest.run_id,
                WorkflowStep.GOLDEN_RECORD,
                self._write_yaml("golden-record-selection.yaml", {"reason": "缺少ID"}),
            )

        unchanged = self.store.load(self.manifest.run_id)
        self.assertEqual(unchanged.current_step, WorkflowStep.GOLDEN_RECORD)
        self.assertEqual(stored_research.read_text(encoding="utf-8"), "# 有效研究\n\n招聘意图明确。")
        self.assertFalse(
            self.store.artifact_path(
                self.manifest.run_id,
                "golden-record-selection.yaml",
            ).exists()
        )

    def test_submission_for_wrong_step_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Expected step research"):
            submit_action(
                self.store,
                self.manifest.run_id,
                WorkflowStep.GAP_REVIEW,
                self._write_yaml("questions.yaml", {"questions": []}),
            )

        self.assertEqual(
            self.store.load(self.manifest.run_id).current_step,
            WorkflowStep.RESEARCH,
        )


if __name__ == "__main__":
    unittest.main()
