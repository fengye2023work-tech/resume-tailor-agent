from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from resume_agent.config import AppPaths
from resume_agent.models import ApplicationInput, RunStage, WorkflowStep
from resume_agent.storage import RunStore


class RunStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name).resolve()
        self.paths = AppPaths(
            repo_root=self.root,
            runtime_root=self.root / ".resume-agent",
        )
        self.store = RunStore(self.paths)
        self.application = ApplicationInput(
            company="Example Co",
            role="AI Lead",
            language="en",
            jd="Build reliable AI products.",
        )

    def test_create_run_writes_workflow_manifest_inside_private_runtime(self) -> None:
        run = self.store.create(self.application)

        run_dir = self.paths.applications_root / run.run_id
        self.assertTrue((run_dir / "run.json").is_file())
        self.assertEqual(run.stage, RunStage.INTAKE)
        self.assertEqual(run.current_step, WorkflowStep.RESEARCH)
        self.assertEqual(run.pending_questions, ())
        self.assertTrue(run_dir.is_relative_to(self.paths.runtime_root))

    def test_create_run_uses_collision_safe_slug(self) -> None:
        first = self.store.create(self.application)
        second = self.store.create(self.application)

        self.assertNotEqual(first.run_id, second.run_id)
        self.assertTrue(first.run_id.startswith("example-co-ai-lead-"))
        self.assertTrue(second.run_id.startswith("example-co-ai-lead-"))

    def test_load_round_trips_application_and_stage(self) -> None:
        created = self.store.create(self.application)

        loaded = self.store.load(created.run_id)

        self.assertEqual(loaded, created)
        self.assertEqual(loaded.application.company, "Example Co")

    def test_save_manifest_round_trips_workflow_fields(self) -> None:
        created = self.store.create(self.application)
        changed = replace(
            created,
            current_step=WorkflowStep.QUESTIONS,
            selected_golden_record_id="sample-general-zh-v1",
            pending_questions=("是否使用过 Databricks？",),
        )

        saved = self.store.save_manifest(created.run_id, changed)

        self.assertEqual(saved.current_step, WorkflowStep.QUESTIONS)
        self.assertEqual(
            saved.selected_golden_record_id,
            "sample-general-zh-v1",
        )
        self.assertEqual(saved.pending_questions, ("是否使用过 Databricks？",))
        self.assertEqual(self.store.load(created.run_id), saved)

    def test_loads_legacy_input_without_losing_application_or_stage(self) -> None:
        run_id = "legacy-company-ai-lead-20260928-000000-000001"
        run_dir = self.paths.applications_root / run_id
        run_dir.mkdir(parents=True)
        legacy = {
            "run_id": run_id,
            "stage": "researched",
            "created_at": "2026-09-28T00:00:00+00:00",
            "application": self.application.to_dict(),
        }
        (run_dir / "input.yaml").write_text(
            json.dumps(legacy, ensure_ascii=False),
            encoding="utf-8",
        )

        loaded = self.store.load(run_id)

        self.assertEqual(loaded.stage, RunStage.RESEARCHED)
        self.assertEqual(loaded.application, self.application)
        self.assertEqual(loaded.current_step, WorkflowStep.GOLDEN_RECORD)
        self.assertFalse((run_dir / "run.json").exists())

        migrated = self.store.save_manifest(run_id, loaded)

        self.assertTrue((run_dir / "run.json").is_file())
        self.assertEqual(migrated.stage, loaded.stage)
        self.assertEqual(migrated.application, loaded.application)
        self.assertGreaterEqual(migrated.updated_at, loaded.updated_at)
        self.assertTrue((run_dir / "input.yaml").is_file())

    def test_artifact_paths_cannot_escape_the_run_directory(self) -> None:
        created = self.store.create(self.application)

        with self.assertRaisesRegex(ValueError, "Artifact path escapes run"):
            self.store.artifact_path(created.run_id, "../outside.txt")

        with self.assertRaisesRegex(ValueError, "Artifact path must be relative"):
            self.store.artifact_path(created.run_id, self.root / "outside.txt")

    def test_save_artifact_round_trips_utf8_text(self) -> None:
        created = self.store.create(self.application)

        path = self.store.save_artifact(
            created.run_id,
            "analysis/gaps.md",
            "# 差距分析\n\nDatabricks 需要确认。",
        )

        self.assertEqual(
            path.read_text(encoding="utf-8"),
            "# 差距分析\n\nDatabricks 需要确认。",
        )
        self.assertEqual(
            path,
            self.paths.applications_root / created.run_id / "analysis" / "gaps.md",
        )

    def test_save_research_rejects_unknown_run(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown run"):
            self.store.save_research("missing-run", "# Research")

    def test_save_research_updates_stage_and_writes_utf8(self) -> None:
        created = self.store.create(self.application)

        research_path = self.store.save_research(created.run_id, "# Research\n\n深圳 expansion")

        self.assertEqual(research_path.read_text(encoding="utf-8"), "# Research\n\n深圳 expansion")
        self.assertEqual(self.store.load(created.run_id).stage, RunStage.RESEARCHED)


if __name__ == "__main__":
    unittest.main()
