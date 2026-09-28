from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from pypdf import PdfWriter

from resume_agent.cli import main
from resume_agent.config import AppPaths
from resume_agent.models import ApplicationInput, RunStage, WorkflowStep
from resume_agent.pdf import PageLayoutReport, verify_pdf
from resume_agent.storage import RunStore
from tests.support import seed_private_runtime


class EndToEndTests(unittest.TestCase):
    @staticmethod
    def call(args: list[str], paths: AppPaths) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(args, paths=paths)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_ide_workflow_reaches_owner_review_without_nested_model_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = Path(__file__).parents[2]
            layout_source = source_root / "3_templates" / "layout_system" / "golden-record-v1" / "layout-spec.yaml"
            layout_target = root / "3_templates" / "layout_system" / "golden-record-v1" / "layout-spec.yaml"
            layout_target.parent.mkdir(parents=True)
            layout_target.write_text(
                layout_source.read_text(encoding="utf-8").replace("enabled: true", "enabled: false"),
                encoding="utf-8",
            )
            paths = AppPaths(root, root / ".resume-agent")
            seed_private_runtime(paths)
            jd = root / "jd.txt"
            jd.write_text("负责垂直领域AI产品，熟悉Databricks。", encoding="utf-8")

            reports = (
                PageLayoutReport(1, False, 0.91, False),
                PageLayoutReport(2, False, 0.89, False),
            )

            def fake_print_pdf(_html_path: Path, pdf_path: Path) -> Path:
                writer = PdfWriter()
                writer.add_blank_page(width=595, height=842)
                writer.add_blank_page(width=595, height=842)
                with pdf_path.open("wb") as stream:
                    writer.write(stream)
                return pdf_path

            def submit(run_id: str, step: str, source: Path) -> dict[str, object]:
                code, stdout, stderr = self.call([
                    "submit", run_id, "--step", step, "--file", str(source), "--json",
                ], paths)
                self.assertEqual(code, 0, stderr)
                return json.loads(stdout)

            with (
                patch("subprocess.run", side_effect=AssertionError("nested model process")),
                patch("resume_agent.cli.inspect_layout", return_value=reports),
                patch("resume_agent.cli.print_pdf", side_effect=fake_print_pdf),
            ):
                code, stdout, stderr = self.call([
                    "apply", "--company", "Example Labs", "--role", "垂直领域产品负责人",
                    "--language", "zh", "--jd-file", str(jd), "--host", "ide", "--json",
                ], paths)
                self.assertEqual(code, 0, stderr)
                payload = json.loads(stdout)
                run_id = str(payload["run_id"])
                transitions = [str(payload["current_step"])]
                inputs = root / "inputs"
                inputs.mkdir()

                research = inputs / "research.md"
                research.write_text("# 招聘意图\n\n重视垂直领域产品判断与亲手搭建能力。", encoding="utf-8")
                payload = submit(run_id, "research", research)
                transitions.append(str(payload["current_step"]))

                selection = inputs / "golden-record-selection.yaml"
                selection.write_text(yaml.safe_dump({
                    "golden_record_id": "sample-domain-owner-zh-v1",
                    "reason": "岗位与垂直领域产品负责人模板最接近。",
                }, allow_unicode=True), encoding="utf-8")
                payload = submit(run_id, "golden_record", selection)
                transitions.append(str(payload["current_step"]))

                questions = inputs / "questions.yaml"
                questions.write_text(yaml.safe_dump({
                    "summary": "核心经历匹配，需要确认明确技能。",
                    "emphasis": ["垂直领域判断", "Agent产品实践"],
                    "deemphasis": ["早期通用自动化"],
                    "questions": [{
                        "id": "databricks",
                        "question": "是否在PoC中使用过Databricks？",
                        "reason": "JD明确要求，但Master Profile没有记录。",
                    }],
                }, allow_unicode=True), encoding="utf-8")
                payload = submit(run_id, "gap_review", questions)
                transitions.append(str(payload["current_step"]))

                answers = inputs / "answers.yaml"
                answers.write_text(yaml.safe_dump({
                    "answers": [{"question_id": "databricks", "answer": "在PoC中使用过，熟悉基本工作流。"}],
                }, allow_unicode=True), encoding="utf-8")
                payload = submit(run_id, "questions", answers)
                transitions.append(str(payload["current_step"]))

                plan = inputs / "content-plan.yaml"
                plan.write_text(yaml.safe_dump({
                    "golden_record_id": "sample-domain-owner-zh-v1",
                    "changes": [{
                        "section": "技术能力", "action": "adapt", "reason": "回应JD且保留事实边界。",
                    }],
                }, allow_unicode=True), encoding="utf-8")
                payload = submit(run_id, "content_plan", plan)
                transitions.append(str(payload["current_step"]))

                content = {
                    "language": "zh",
                    "template_family": "domain",
                    "headline": "垂直领域AI产品负责人",
                    "pages": [
                        {"blocks": [{"kind": "summary", "title": "简介", "body": "从领域问题出发搭建可验证的AI产品。", "bullets": []}]},
                        {"blocks": [{"kind": "summary", "title": "能力", "body": "兼顾业务判断、Agent架构与端到端原型。", "bullets": []}]},
                    ],
                }
                draft = inputs / "resume-content-draft.yaml"
                draft.write_text(yaml.safe_dump(content, allow_unicode=True), encoding="utf-8")
                payload = submit(run_id, "draft", draft)
                transitions.append(str(payload["current_step"]))

                reviewed = inputs / "resume-content.yaml"
                reviewed.write_text(yaml.safe_dump(content, allow_unicode=True), encoding="utf-8")
                payload = submit(run_id, "language_review", reviewed)
                transitions.append(str(payload["current_step"]))

                render_code, _, render_stderr = self.call(["render", run_id], paths)
                self.assertEqual(render_code, 0, render_stderr)
                run_dir = paths.applications_root / run_id
                payload = submit(run_id, "render", run_dir / "agent-draft.html")
                transitions.append(str(payload["current_step"]))

            self.assertEqual(transitions, [
                "research", "golden_record", "gap_review", "questions", "content_plan",
                "draft", "language_review", "render", "owner_review",
            ])
            self.assertEqual(RunStore(paths).load(run_id).current_step, WorkflowStep.OWNER_REVIEW)
            self.assertTrue((run_dir / "agent-draft.html").is_file())
            self.assertTrue(verify_pdf(run_dir / "resume.pdf").ok)
            pdf_packet = payload["packet"]["artifacts"]["resume.pdf"]
            self.assertEqual(Path(pdf_packet["path"]), run_dir / "resume.pdf")
            self.assertGreater(pdf_packet["size_bytes"], 0)

    def test_valid_application_renders_exactly_two_page_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layout_source = Path(__file__).parents[2] / "3_templates" / "layout_system" / "golden-record-v1" / "layout-spec.yaml"
            layout_target = root / "3_templates" / "layout_system" / "golden-record-v1" / "layout-spec.yaml"
            layout_target.parent.mkdir(parents=True)
            layout_target.write_text(
                layout_source.read_text(encoding="utf-8")
                .replace("enabled: true", "enabled: false")
                .replace("minimum_fill_ratio: [0.86, 0.80]", "minimum_fill_ratio: [0.01, 0.01]")
                .replace("target_fill_ratio: [0.92, 0.90]", "target_fill_ratio: [0.10, 0.10]"),
                encoding="utf-8",
            )
            paths = AppPaths(root, root / ".resume-agent")
            seed_private_runtime(paths)
            store = RunStore(paths)
            run = store.create(ApplicationInput("Example Co", "AI Lead", "en", "Build AI"))
            run_dir = paths.applications_root / run.run_id
            content = {
                "language": "en", "template_family": "general", "headline": "AI Lead",
                "pages": [
                    {"blocks": [{"kind": "experience", "title": "Example Co", "bullets": [
                        {"text": "Built reliable AI products.", "source_refs": ["profile:professional-experience/example-labs"]}
                    ]}]},
                    {"blocks": [{"kind": "education", "title": "Education", "bullets": [
                        {"text": "MSc, Example University", "source_refs": ["profile:education-certifications"]}
                    ]}]},
                ],
            }
            (run_dir / "resume-content.yaml").write_text(json.dumps(content), encoding="utf-8")

            code = main(["render", run.run_id], paths=paths)

            self.assertEqual(code, 0)
            self.assertEqual(store.load(run.run_id).stage, RunStage.RENDERED)
            self.assertTrue((run_dir / "agent-draft.html").is_file())
            self.assertTrue(verify_pdf(run_dir / "resume.pdf").ok)


if __name__ == "__main__":
    unittest.main()
