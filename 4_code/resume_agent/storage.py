from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .config import AppPaths
from .models import ApplicationInput, RunManifest, RunStage, WorkflowStep


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "application"


class RunStore:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def create(self, application: ApplicationInput) -> RunManifest:
        now = datetime.now(timezone.utc)
        prefix = f"{_slug(application.company)}-{_slug(application.role)}-{now:%Y%m%d-%H%M%S-%f}"
        run_id = prefix
        counter = 2
        while (self.paths.applications_root / run_id).exists():
            run_id = f"{prefix}-{counter}"
            counter += 1

        run_dir = self._safe_run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=False)
        manifest = RunManifest(
            run_id=run_id,
            stage=RunStage.INTAKE,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            current_step=WorkflowStep.RESEARCH,
            application=application,
        )
        self._write_manifest(run_dir / "run.json", manifest)
        return manifest

    def load(self, run_id: str) -> RunManifest:
        run_dir = self._safe_run_dir(run_id)
        current_path = run_dir / "run.json"
        legacy_path = run_dir / "input.yaml"
        path = current_path if current_path.is_file() else legacy_path
        if not path.is_file():
            raise ValueError(f"Unknown run: {run_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return RunManifest.from_dict(data)

    def save_manifest(self, run_id: str, manifest: RunManifest) -> RunManifest:
        run_dir = self._safe_run_dir(run_id)
        if not run_dir.is_dir():
            raise ValueError(f"Unknown run: {run_id}")
        if manifest.run_id != run_id:
            raise ValueError("Manifest run id does not match target run")
        saved = replace(
            manifest,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._write_manifest(run_dir / "run.json", saved)
        return saved

    def artifact_path(self, run_id: str, relative_path: str | Path) -> Path:
        run_dir = self._safe_run_dir(run_id)
        if not run_dir.is_dir():
            raise ValueError(f"Unknown run: {run_id}")
        path = Path(relative_path)
        if path.is_absolute():
            raise ValueError("Artifact path must be relative")
        candidate = (run_dir / path).resolve()
        if candidate == run_dir or not candidate.is_relative_to(run_dir):
            raise ValueError(f"Artifact path escapes run: {relative_path}")
        return candidate

    def save_artifact(self, run_id: str, relative_path: str | Path, content: str) -> Path:
        path = self.artifact_path(run_id, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, content)
        return path

    def save_research(self, run_id: str, markdown: str) -> Path:
        manifest = self.load(run_id)
        path = self.save_artifact(run_id, "research.md", markdown)
        self.save_manifest(run_id, replace(manifest, stage=RunStage.RESEARCHED))
        return path

    def set_stage(self, run_id: str, stage: RunStage) -> RunManifest:
        manifest = replace(self.load(run_id), stage=stage)
        return self.save_manifest(run_id, manifest)

    def _safe_run_dir(self, run_id: str) -> Path:
        if run_id != _slug(run_id):
            raise ValueError(f"Invalid run id: {run_id}")
        applications_root = self.paths.applications_root.resolve()
        candidate = (applications_root / run_id).resolve()
        if not candidate.is_relative_to(applications_root):
            raise ValueError(f"Run path escapes private runtime: {run_id}")
        return candidate

    def _write_manifest(self, path: Path, manifest: RunManifest) -> None:
        payload = json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n"
        self._atomic_write(path, payload)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(content, encoding="utf-8")
        os.replace(temp_path, path)
