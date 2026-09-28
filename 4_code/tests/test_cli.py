from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from resume_agent.cli import main
from resume_agent.config import AppPaths
from resume_agent.models import ApplicationInput, WorkflowStep
from resume_agent.pdf import PageLayoutReport, PdfReport
from resume_agent.storage import RunStore
from tests.support import seed_private_runtime


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.paths = AppPaths(self.root, self.root / ".resume-agent")
        seed_private_runtime(self.paths)
        self.workflow_paths = AppPaths(
            Path(__file__).parents[2],
            self.root / ".workflow-runtime",
        )
        seed_private_runtime(self.workflow_paths)

    def call(
        self,
        args: list[str],
        *,
        paths: AppPaths | None = None,
    ) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(args, paths=paths or self.paths)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_apply_ide_creates_run_and_returns_research_without_model_process(self) -> None:
        jd = self.root / "jd-zh.txt"
        jd.write_text("定义AI原生垂直领域产品。", encoding="utf-8")

        with patch("subprocess.run", side_effect=AssertionError("nested model process")):
            code, stdout, stderr = self.call([
                "apply", "--company", "Example Labs", "--role", "垂直领域产品负责人",
                "--language", "zh", "--jd-file", str(jd), "--host", "ide", "--json",
            ], paths=self.workflow_paths)

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["current_step"], "research")
        self.assertEqual(payload["action"]["step"], "research")
        self.assertEqual(payload["action"]["kind"], "model")
        self.assertEqual(payload["action"]["output_file"], "research.md")
        self.assertEqual(payload["packet"]["application"]["company"], "Example Labs")

    def test_next_json_is_stable_and_resume_returns_current_action(self) -> None:
        store = RunStore(self.workflow_paths)
        run = store.create(ApplicationInput("Example Labs", "产品负责人", "zh", "定义产品"))

        first_code, first_stdout, first_stderr = self.call(
            ["next", run.run_id, "--json"],
            paths=self.workflow_paths,
        )
        second_code, second_stdout, second_stderr = self.call(
            ["next", run.run_id, "--json"],
            paths=self.workflow_paths,
        )
        resume_code, resume_stdout, resume_stderr = self.call(
            ["resume", run.run_id, "--json"],
            paths=self.workflow_paths,
        )

        self.assertEqual((first_code, second_code, resume_code), (0, 0, 0))
        self.assertEqual(first_stderr + second_stderr + resume_stderr, "")
        self.assertEqual(first_stdout, second_stdout)
        self.assertEqual(json.loads(resume_stdout)["action"], json.loads(first_stdout)["action"])

    def test_submit_advances_only_the_expected_step_and_file(self) -> None:
        store = RunStore(self.workflow_paths)
        run = store.create(ApplicationInput("Example Labs", "产品负责人", "zh", "定义产品"))
        research = self.root / "research.md"
        research.write_text("# 招聘意图\n\n重视垂直领域产品判断。", encoding="utf-8")

        wrong_code, _, wrong_stderr = self.call([
            "submit", run.run_id, "--step", "gap_review", "--file", str(research),
        ], paths=self.workflow_paths)
        self.assertEqual(wrong_code, 2)
        self.assertIn("Expected step research", wrong_stderr)
        self.assertEqual(store.load(run.run_id).current_step, WorkflowStep.RESEARCH)

        code, stdout, stderr = self.call([
            "submit", run.run_id, "--step", "research", "--file", str(research), "--json",
        ], paths=self.workflow_paths)

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["current_step"], "golden_record")
        self.assertEqual(payload["action"]["output_file"], "golden-record-selection.yaml")
        self.assertTrue(
            (self.workflow_paths.applications_root / run.run_id / "research.md").is_file()
        )

    def test_status_json_reports_workflow_state_questions_and_artifacts(self) -> None:
        store = RunStore(self.workflow_paths)
        created = store.create(ApplicationInput("Example Labs", "产品负责人", "zh", "定义产品"))
        store.save_artifact(created.run_id, "research.md", "# Research")
        store.save_manifest(
            created.run_id,
            replace(
                created,
                current_step=WorkflowStep.QUESTIONS,
                selected_golden_record_id="sample-domain-owner-zh-v1",
                pending_questions=("是否在PoC中使用过Databricks？",),
            ),
        )

        code, stdout, stderr = self.call(
            ["status", created.run_id, "--json"],
            paths=self.workflow_paths,
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["current_step"], "questions")
        self.assertEqual(payload["selected_golden_record_id"], "sample-domain-owner-zh-v1")
        self.assertEqual(payload["pending_questions"], ["是否在PoC中使用过Databricks？"])
        self.assertEqual(payload["artifacts"], ["research.md"])

    def test_start_creates_private_run_and_prints_id(self) -> None:
        jd = self.root / "jd.txt"
        jd.write_text("Build reliable AI products", encoding="utf-8")

        code, stdout, _ = self.call([
            "start", "--company", "Example", "--role", "AI Lead",
            "--language", "en", "--jd-file", str(jd),
        ])

        self.assertEqual(code, 0)
        self.assertRegex(stdout, r"^run_id=example-ai-lead-")

    def test_status_reports_current_stage(self) -> None:
        run = RunStore(self.paths).create(ApplicationInput("Example", "AI Lead", "en", "Build AI"))

        code, stdout, _ = self.call(["status", run.run_id])

        self.assertEqual(code, 0)
        self.assertIn("stage=intake", stdout)

    def test_render_refuses_unknown_claim_source_before_browser(self) -> None:
        store = RunStore(self.paths)
        run = store.create(ApplicationInput("Example", "AI Lead", "en", "Build AI"))
        run_dir = self.paths.applications_root / run.run_id
        content = {
            "language": "en", "template_family": "general", "headline": "AI Lead",
            "pages": [
                {"blocks": [{"kind": "experience", "title": "Example", "bullets": [
                    {"text": "Built AI", "source_refs": ["profile:missing"]}
                ]}]},
                {"blocks": []},
            ],
        }
        (run_dir / "resume-content.yaml").write_text(json.dumps(content), encoding="utf-8")

        code, _, stderr = self.call(["render", run.run_id])

        self.assertEqual(code, 2)
        self.assertIn("unknown_source_ref", stderr)

    def test_render_refuses_pages_that_remain_underfilled_after_balancing(self) -> None:
        layout_source = Path(__file__).parents[2] / "3_templates" / "layout_system" / "golden-record-v1" / "layout-spec.yaml"
        layout_target = self.root / "3_templates" / "layout_system" / "golden-record-v1" / "layout-spec.yaml"
        layout_target.parent.mkdir(parents=True)
        layout_target.write_text(
            layout_source.read_text(encoding="utf-8").replace("enabled: true", "enabled: false"),
            encoding="utf-8",
        )
        store = RunStore(self.paths)
        run = store.create(ApplicationInput("Example", "AI Lead", "en", "Build AI"))
        run_dir = self.paths.applications_root / run.run_id
        content = {
            "language": "en", "template_family": "general", "headline": "AI Lead",
            "pages": [
                {"blocks": [{"kind": "experience", "title": "Example Co", "bullets": [
                    {"text": "Built an AI workflow.", "source_refs": ["profile:professional-experience/example-labs"]}
                ]}]},
                {"blocks": []},
            ],
        }
        (run_dir / "resume-content.yaml").write_text(json.dumps(content), encoding="utf-8")
        reports = (
            PageLayoutReport(1, False, 0.42, True),
            PageLayoutReport(2, False, 0.05, True),
        )

        with (
            patch("resume_agent.cli.inspect_layout", return_value=reports),
            patch("resume_agent.cli.print_pdf", return_value=run_dir / "resume.pdf"),
            patch("resume_agent.cli.verify_pdf", return_value=PdfReport(2, True)),
        ):
            code, _, stderr = self.call(["render", run.run_id])

        self.assertEqual(code, 2)
        self.assertIn("error:underfilled", stderr)


if __name__ == "__main__":
    unittest.main()
