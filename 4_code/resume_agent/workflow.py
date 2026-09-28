from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from .config import AppPaths
from .golden_records import get_golden_record, load_golden_record_catalog
from .models import ResumeContent, RunManifest, RunStage, WorkflowAction, WorkflowStep
from .storage import RunStore


def next_action(paths: AppPaths, manifest: RunManifest) -> WorkflowAction:
    step = manifest.current_step
    if step == WorkflowStep.RESEARCH:
        return WorkflowAction(
            step=step,
            kind="model",
            instructions="研究公司、产品、岗位背景和招聘意图；区分事实、来源与合理推断。",
            required_files=(),
            output_file="research.md",
        )
    if step == WorkflowStep.GOLDEN_RECORD:
        return WorkflowAction(
            step=step,
            kind="model",
            instructions="从已批准的Golden Record中选择最接近岗位的一份，并说明选择依据。",
            required_files=("research.md",),
            output_file="golden-record-selection.yaml",
        )
    if step == WorkflowStep.GAP_REVIEW:
        return WorkflowAction(
            step=step,
            kind="model",
            instructions="对照JD、Master Profile与所选Golden Record分析强调、弱化和必要提问。",
            required_files=("research.md", "golden-record-selection.yaml"),
            output_file="questions.yaml",
        )
    if step == WorkflowStep.QUESTIONS:
        questions = "\n".join(f"- {question}" for question in manifest.pending_questions)
        return WorkflowAction(
            step=step,
            kind="user",
            instructions=f"请回答以下会明显影响真实性或竞争力的问题：\n{questions}",
            required_files=("questions.yaml",),
            output_file="answers.yaml",
        )
    if step == WorkflowStep.CONTENT_PLAN:
        required = ["research.md", "golden-record-selection.yaml", "questions.yaml"]
        if (paths.applications_root / manifest.run_id / "answers.yaml").is_file():
            required.append("answers.yaml")
        return WorkflowAction(
            step=step,
            kind="model",
            instructions="基于所选Golden Record制定增量修改方案，明确保留、移动、压缩、展开或改写的内容。",
            required_files=tuple(required),
            output_file="content-plan.yaml",
        )
    if step == WorkflowStep.DRAFT:
        return WorkflowAction(
            step=step,
            kind="model",
            instructions="按已批准事实和修改方案生成两页结构化内容，不从零重写。",
            required_files=("content-plan.yaml",),
            output_file="resume-content-draft.yaml",
        )
    if step == WorkflowStep.LANGUAGE_REVIEW:
        return WorkflowAction(
            step=step,
            kind="model",
            instructions="检查事实、责任边界、技术含义和术语，再自然化语言；不要创造新事实或新名词。",
            required_files=("resume-content-draft.yaml",),
            output_file="resume-content.yaml",
        )
    if step == WorkflowStep.RENDER:
        return WorkflowAction(
            step=step,
            kind="command",
            instructions="运行确定性校验、两页内容平衡、HTML渲染、PDF生成和视觉回归。",
            required_files=("resume-content.yaml",),
            output_file="agent-draft.html",
        )
    if step == WorkflowStep.OWNER_REVIEW:
        return WorkflowAction(
            step=step,
            kind="user",
            instructions="请在可编辑HTML中检查并修改内容，确认后再进入finalize学习流程。",
            required_files=("agent-draft.html", "resume.pdf"),
            output_file=None,
        )
    if step in (WorkflowStep.FINALIZE, WorkflowStep.COMPLETE):
        return WorkflowAction(
            step=step,
            kind="complete" if step == WorkflowStep.COMPLETE else "user",
            instructions="当前阶段由finalize学习流程处理。" if step == WorkflowStep.FINALIZE else "申请流程已完成。",
            required_files=(),
            output_file=None,
        )
    raise ValueError(f"Unsupported workflow step: {step}")


def _mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a YAML mapping in {path.name}")
    return payload


def _text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _text_list(payload: dict[str, Any], key: str) -> list[str]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        raise ValueError(f"{key} must be a list")
    values = [str(item).strip() for item in raw]
    if any(not value for value in values):
        raise ValueError(f"{key} must contain non-empty text")
    return values


def _validate_research(path: Path) -> None:
    if not path.read_text(encoding="utf-8").strip():
        raise ValueError("research.md must not be empty")


def _validate_selection(paths: AppPaths, manifest: RunManifest, path: Path) -> str:
    payload = _mapping(path)
    record_id = _text(payload, "golden_record_id")
    _text(payload, "reason")
    catalog = load_golden_record_catalog(paths.golden_record_catalog)
    get_golden_record(catalog, record_id, manifest.application.language)
    return record_id


def _validate_gap_review(path: Path) -> tuple[str, ...]:
    payload = _mapping(path)
    _text(payload, "summary")
    _text_list(payload, "emphasis")
    _text_list(payload, "deemphasis")
    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list):
        raise ValueError("questions must be a list")
    ids: set[str] = set()
    questions: list[str] = []
    for raw in raw_questions:
        if not isinstance(raw, dict):
            raise ValueError("Each question must be a mapping")
        question_id = _text(raw, "id")
        question = _text(raw, "question")
        _text(raw, "reason")
        if question_id in ids:
            raise ValueError(f"Duplicate question id: {question_id}")
        ids.add(question_id)
        questions.append(question)
    return tuple(questions)


def _validate_answers(store: RunStore, manifest: RunManifest, path: Path) -> None:
    questions = _mapping(store.artifact_path(manifest.run_id, "questions.yaml"))["questions"]
    expected_ids = {str(item["id"]).strip() for item in questions}
    payload = _mapping(path)
    raw_answers = payload.get("answers")
    if not isinstance(raw_answers, list):
        raise ValueError("answers must be a list")
    received_ids: set[str] = set()
    for raw in raw_answers:
        if not isinstance(raw, dict):
            raise ValueError("Each answer must be a mapping")
        question_id = _text(raw, "question_id")
        _text(raw, "answer")
        if question_id in received_ids:
            raise ValueError(f"Duplicate answer question_id: {question_id}")
        received_ids.add(question_id)
    if received_ids != expected_ids:
        raise ValueError("Answers must match all pending question ids")


def _validate_content_plan(manifest: RunManifest, path: Path) -> None:
    payload = _mapping(path)
    if _text(payload, "golden_record_id") != manifest.selected_golden_record_id:
        raise ValueError("content plan must use the selected Golden Record")
    raw_changes = payload.get("changes")
    if not isinstance(raw_changes, list) or not raw_changes:
        raise ValueError("changes must be a non-empty list")
    for raw in raw_changes:
        if not isinstance(raw, dict):
            raise ValueError("Each content change must be a mapping")
        _text(raw, "section")
        if raw.get("action") not in ("keep", "move", "compress", "expand", "adapt", "remove"):
            raise ValueError("Unsupported content change action")
        _text(raw, "reason")


def _validate_resume_content(paths: AppPaths, manifest: RunManifest, path: Path) -> None:
    payload = _mapping(path)
    content = ResumeContent.from_dict(payload)
    if content.language != manifest.application.language:
        raise ValueError("Resume content language does not match application")
    if len(content.pages) != 2:
        raise ValueError("Resume content must define exactly two pages")
    if not manifest.selected_golden_record_id:
        raise ValueError("A Golden Record must be selected before drafting")
    record = get_golden_record(
        load_golden_record_catalog(paths.golden_record_catalog),
        manifest.selected_golden_record_id,
        manifest.application.language,
    )
    if content.template_family != record.template_family:
        raise ValueError("Resume content template family does not match selected Golden Record")


def _validate_render(path: Path) -> None:
    if "resume-page" not in path.read_text(encoding="utf-8"):
        raise ValueError("Rendered HTML does not contain resume pages")
    pdf_path = path.with_name("resume.pdf")
    if not pdf_path.is_file() or not pdf_path.read_bytes().startswith(b"%PDF"):
        raise ValueError("Rendered resume.pdf is missing or invalid")


def submit_action(
    store: RunStore,
    run_id: str,
    step: WorkflowStep,
    artifact_path: Path,
) -> RunManifest:
    manifest = store.load(run_id)
    if step != manifest.current_step:
        raise ValueError(
            f"Expected step {manifest.current_step.value}, received {step.value}"
        )
    action = next_action(store.paths, manifest)
    if action.output_file is None:
        raise ValueError(f"Step {step.value} does not accept an artifact")
    source = artifact_path.resolve()
    if not source.is_file():
        raise ValueError(f"Submitted artifact not found: {artifact_path}")
    if source.name != Path(action.output_file).name:
        raise ValueError(f"Step {step.value} expects {action.output_file}")

    selected_id = manifest.selected_golden_record_id
    pending_questions = manifest.pending_questions
    next_step: WorkflowStep
    stage = manifest.stage
    if step == WorkflowStep.RESEARCH:
        _validate_research(source)
        next_step = WorkflowStep.GOLDEN_RECORD
        stage = RunStage.RESEARCHED
    elif step == WorkflowStep.GOLDEN_RECORD:
        selected_id = _validate_selection(store.paths, manifest, source)
        next_step = WorkflowStep.GAP_REVIEW
    elif step == WorkflowStep.GAP_REVIEW:
        pending_questions = _validate_gap_review(source)
        next_step = WorkflowStep.QUESTIONS if pending_questions else WorkflowStep.CONTENT_PLAN
    elif step == WorkflowStep.QUESTIONS:
        _validate_answers(store, manifest, source)
        pending_questions = ()
        next_step = WorkflowStep.CONTENT_PLAN
    elif step == WorkflowStep.CONTENT_PLAN:
        _validate_content_plan(manifest, source)
        next_step = WorkflowStep.DRAFT
    elif step == WorkflowStep.DRAFT:
        _validate_resume_content(store.paths, manifest, source)
        next_step = WorkflowStep.LANGUAGE_REVIEW
    elif step == WorkflowStep.LANGUAGE_REVIEW:
        _validate_resume_content(store.paths, manifest, source)
        next_step = WorkflowStep.RENDER
        stage = RunStage.CONTENT_READY
    elif step == WorkflowStep.RENDER:
        _validate_render(source)
        next_step = WorkflowStep.OWNER_REVIEW
        stage = RunStage.RENDERED
    else:
        raise ValueError(f"Unsupported submitted workflow step: {step.value}")

    target = store.artifact_path(run_id, action.output_file)
    if source != target:
        store.save_artifact(run_id, action.output_file, source.read_text(encoding="utf-8"))
    saved = replace(
        manifest,
        stage=stage,
        current_step=next_step,
        selected_golden_record_id=selected_id,
        pending_questions=pending_questions,
    )
    return store.save_manifest(run_id, saved)
