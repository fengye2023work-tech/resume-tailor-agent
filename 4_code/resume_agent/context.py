from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from .config import AppPaths
from .golden_records import get_golden_record, load_golden_record_catalog
from .models import RunManifest, WorkflowAction, WorkflowStep
from .preferences import load_applicable_preferences
from .storage import RunStore


_PROMPTS = {
    WorkflowStep.RESEARCH: "research.md",
    WorkflowStep.GOLDEN_RECORD: "golden-record-selection.md",
    WorkflowStep.GAP_REVIEW: "gap-review.md",
    WorkflowStep.CONTENT_PLAN: "content-plan.md",
    WorkflowStep.DRAFT: "draft.md",
    WorkflowStep.LANGUAGE_REVIEW: "language-review.md",
}

_PROFILE_STEPS = {
    WorkflowStep.GAP_REVIEW,
    WorkflowStep.CONTENT_PLAN,
    WorkflowStep.DRAFT,
    WorkflowStep.LANGUAGE_REVIEW,
}

_PREFERENCE_SECTIONS = {
    WorkflowStep.GAP_REVIEW: ("summary", "experience", "project", "skills"),
    WorkflowStep.CONTENT_PLAN: ("summary", "experience", "project", "skills"),
    WorkflowStep.DRAFT: ("summary", "experience", "project", "skills"),
    WorkflowStep.LANGUAGE_REVIEW: ("summary", "experience", "project", "skills"),
}


def _load_artifact(path: Path) -> object:
    if path.suffix.lower() == ".pdf":
        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
        }
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        return yaml.safe_load(text)
    return text


def _prompt_for(action: WorkflowAction) -> str:
    prompt_name = _PROMPTS.get(action.step)
    if prompt_name is None:
        return action.instructions
    prompt_path = Path(__file__).with_name("prompts") / prompt_name
    return prompt_path.read_text(encoding="utf-8").strip()


def _preference_dict(preference: object) -> dict[str, object]:
    raw = asdict(preference)
    return {
        "id": raw["id"],
        "prefer": raw["prefer"],
        "avoid": raw["avoid"],
        "source": raw["source"],
    }


def build_action_packet(
    paths: AppPaths,
    manifest: RunManifest,
    action: WorkflowAction,
) -> dict[str, object]:
    if action.step != manifest.current_step:
        raise ValueError(
            f"Action step {action.step.value} does not match run step {manifest.current_step.value}"
        )
    store = RunStore(paths)
    artifacts: dict[str, object] = {}
    for relative_path in action.required_files:
        path = store.artifact_path(manifest.run_id, relative_path)
        if not path.is_file():
            raise ValueError(f"Required artifact is missing: {relative_path}")
        artifacts[relative_path] = _load_artifact(path)

    packet: dict[str, object] = {
        "step": action.step.value,
        "kind": action.kind,
        "instructions": _prompt_for(action),
        "application": manifest.application.to_dict(),
        "artifacts": artifacts,
        "preferences": {},
    }

    catalog = load_golden_record_catalog(paths.golden_record_catalog)
    if action.step == WorkflowStep.GOLDEN_RECORD:
        packet["golden_record_candidates"] = [
            {
                "id": record.id,
                "language": record.language,
                "template_family": record.template_family,
                "target_roles": list(record.target_roles),
            }
            for record in catalog
            if record.language == manifest.application.language
        ]

    selected_record = None
    if manifest.selected_golden_record_id:
        selected_record = get_golden_record(
            catalog,
            manifest.selected_golden_record_id,
            manifest.application.language,
        )
        if action.step in _PROFILE_STEPS:
            content = yaml.safe_load(selected_record.content_path.read_text(encoding="utf-8"))
            packet["golden_record"] = {
                "id": selected_record.id,
                "language": selected_record.language,
                "template_family": selected_record.template_family,
                "target_roles": list(selected_record.target_roles),
                "content": content,
            }

    if action.step in _PROFILE_STEPS:
        profile_path = (
            paths.chinese_profile
            if manifest.application.language == "zh"
            else paths.english_profile
        )
        packet["profile"] = {
            "source": profile_path.name,
            "language": manifest.application.language,
            "content": profile_path.read_text(encoding="utf-8"),
        }

    sections = _PREFERENCE_SECTIONS.get(action.step, ())
    if selected_record and sections:
        inventory = paths.runtime_root / "preferences" / "wording.yaml"
        packet["preferences"] = {
            section: [
                _preference_dict(preference)
                for preference in load_applicable_preferences(
                    inventory,
                    language=manifest.application.language,
                    template_family=selected_record.template_family,
                    section=section,
                    limit=8,
                )
            ]
            for section in sections
        }
    return packet
