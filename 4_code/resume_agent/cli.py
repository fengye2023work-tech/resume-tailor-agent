from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import yaml

from .config import AppPaths
from .context import build_action_packet
from .layout import balance_content, load_layout_spec
from .models import ApplicationInput, ResumeContent, RunManifest, RunStage, WorkflowAction, WorkflowStep
from .pdf import find_browser, inspect_layout, print_pdf, verify_pdf
from .profile import load_profile
from .render import render_html
from .storage import RunStore
from .validation import ValidationReport, validate_content
from .visual_regression import compare_layout_screenshots, render_pdf_screenshots
from .workflow import next_action, submit_action


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="resume-agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    start = sub.add_parser("start")
    apply = sub.add_parser("apply")
    for command in (start, apply):
        command.add_argument("--company", required=True)
        command.add_argument("--role", required=True)
        command.add_argument("--language", required=True, choices=("en", "zh"))
        command.add_argument("--jd-file", required=True, type=Path)
        command.add_argument("--url")
    apply.add_argument("--host", choices=("ide",), default="ide")
    apply.add_argument("--json", action="store_true")
    for name in ("status", "resume", "next"):
        command = sub.add_parser(name)
        command.add_argument("run_id")
        command.add_argument("--json", action="store_true")
    for name in ("validate", "render"):
        command = sub.add_parser(name)
        command.add_argument("run_id")
    submit = sub.add_parser("submit")
    submit.add_argument("run_id")
    submit.add_argument("--step", required=True, choices=tuple(step.value for step in WorkflowStep))
    submit.add_argument("--file", required=True, type=Path)
    submit.add_argument("--json", action="store_true")
    return parser


def _profile_path(paths: AppPaths, language: str) -> Path:
    return paths.english_profile if language == "en" else paths.chinese_profile


def _load_content(paths: AppPaths, run_id: str) -> ResumeContent:
    path = paths.applications_root / run_id / "resume-content.yaml"
    if not path.is_file():
        raise ValueError(f"Missing resume content: {path}")
    return ResumeContent.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def _report_errors(report: ValidationReport) -> None:
    for issue in report.issues:
        stream = sys.stderr if issue.severity == "error" else sys.stdout
        print(f"{issue.severity}:{issue.code}:{issue.message}", file=stream)


def _action_dict(action: WorkflowAction) -> dict[str, object]:
    return {
        "step": action.step.value,
        "kind": action.kind,
        "instructions": action.instructions,
        "required_files": list(action.required_files),
        "output_file": action.output_file,
    }


def _artifact_names(paths: AppPaths, run_id: str) -> list[str]:
    run_dir = paths.applications_root / run_id
    ignored = {"run.json", "input.yaml"}
    return sorted(
        path.relative_to(run_dir).as_posix()
        for path in run_dir.rglob("*")
        if path.is_file() and path.name not in ignored
    )


def _status_dict(paths: AppPaths, manifest: RunManifest) -> dict[str, object]:
    return {
        "run_id": manifest.run_id,
        "stage": manifest.stage.value,
        "current_step": manifest.current_step.value,
        "selected_golden_record_id": manifest.selected_golden_record_id,
        "pending_questions": list(manifest.pending_questions),
        "artifacts": _artifact_names(paths, manifest.run_id),
    }


def _workflow_dict(paths: AppPaths, manifest: RunManifest) -> dict[str, object]:
    action = next_action(paths, manifest)
    payload = _status_dict(paths, manifest)
    payload["action"] = _action_dict(action)
    payload["packet"] = build_action_packet(paths, manifest, action)
    return payload


def _print_workflow(payload: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"run_id={payload['run_id']}")
    print(f"current_step={payload['current_step']}")
    action = payload.get("action")
    if isinstance(action, dict):
        print(f"action_kind={action['kind']}")
        print(f"output_file={action['output_file'] or ''}")
        print(f"instructions={action['instructions']}")


def _render_run(paths: AppPaths, store: RunStore, manifest: RunManifest) -> int:
    content = _load_content(paths, manifest.run_id)
    profile = load_profile(_profile_path(paths, content.language), content.language)
    report = validate_content(content, profile)
    _report_errors(report)
    if not report.ok:
        return 2
    run_dir = paths.applications_root / manifest.run_id
    layout_spec = load_layout_spec(paths.layout_spec)
    html_path = run_dir / "agent-draft.html"

    def measure(candidate: ResumeContent):
        render_html(candidate, manifest.application, html_path, layout_spec=layout_spec)
        return inspect_layout(html_path)

    balance = balance_content(content, layout_spec, measure)
    content = balance.content
    render_html(content, manifest.application, html_path, layout_spec=layout_spec)
    layout_reports = inspect_layout(html_path)
    print(f"balance:changed={str(balance.changed).lower()} iterations={balance.iterations}")
    for page in layout_reports:
        print(f"layout:page={page.page_number} fill_ratio={page.fill_ratio:.3f}")
    overflow = [item.page_number for item in layout_reports if item.overflow]
    if overflow:
        print(f"error:overflow:pages={','.join(map(str, overflow))}", file=sys.stderr)
        return 2
    underfilled = [item for item in layout_reports if item.underfilled]
    for page in underfilled:
        print(
            f"warning:underfilled:page={page.page_number} fill_ratio={page.fill_ratio:.3f}",
            file=sys.stdout,
        )
    if underfilled:
        pages = ",".join(str(item.page_number) for item in underfilled)
        print(f"error:underfilled:pages={pages} after automatic balancing", file=sys.stderr)
        return 2
    pdf_path = print_pdf(html_path, run_dir / "resume.pdf")
    pdf_report = verify_pdf(pdf_path)
    if not pdf_report.ok:
        print(f"error:pdf_page_count:expected=2 actual={pdf_report.page_count}", file=sys.stderr)
        return 2
    if layout_spec.visual.enabled:
        with tempfile.TemporaryDirectory(prefix="resume-agent-visual-") as directory:
            screenshots = render_pdf_screenshots(pdf_path, Path(directory))
            visual_report = compare_layout_screenshots(screenshots, layout_spec.baseline_paths, layout_spec)
        for page in visual_report.pages:
            print(
                "visual:"
                f"page={page.page_number} bbox_delta={page.bbox_delta:.4f} "
                f"profile_distance={page.profile_distance:.4f} "
                f"ink_density_delta={page.ink_density_delta:.4f}",
            )
        if not visual_report.ok:
            print("error:visual_regression:layout differs from Golden Record baseline", file=sys.stderr)
            return 2
    store.set_stage(manifest.run_id, RunStage.RENDERED)
    print(f"html={html_path}")
    print(f"pdf={pdf_path}")
    return 0


def main(argv: list[str] | None = None, *, paths: AppPaths | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = paths or AppPaths.discover(Path.cwd())
    store = RunStore(paths)
    try:
        if args.command == "doctor":
            browser = find_browser()
            for profile in (paths.english_profile, paths.chinese_profile):
                if not profile.is_file():
                    raise FileNotFoundError(profile)
            layout_spec = load_layout_spec(paths.layout_spec)
            if layout_spec.visual.enabled:
                for baseline in layout_spec.baseline_paths:
                    if not baseline.is_file():
                        raise FileNotFoundError(baseline)
            print(f"browser={browser}")
            print("profiles=ok")
            print(f"layout={layout_spec.id}")
            return 0
        if args.command in ("start", "apply"):
            jd = args.jd_file.read_text(encoding="utf-8")
            run = store.create(ApplicationInput(args.company, args.role, args.language, jd, args.url))
            if args.command == "apply":
                _print_workflow(_workflow_dict(paths, run), as_json=args.json)
            else:
                print(f"run_id={run.run_id}")
                print(f"run_dir={paths.applications_root / run.run_id}")
            return 0
        manifest = store.load(args.run_id)
        if args.command == "status":
            payload = _status_dict(paths, manifest)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"run_id={manifest.run_id}")
                print(f"stage={manifest.stage.value}")
                print(f"current_step={manifest.current_step.value}")
                print(f"selected_golden_record_id={manifest.selected_golden_record_id or ''}")
                for question in manifest.pending_questions:
                    print(f"pending_question={question}")
                for artifact in payload["artifacts"]:
                    print(f"artifact={artifact}")
            return 0
        if args.command in ("resume", "next"):
            _print_workflow(_workflow_dict(paths, manifest), as_json=args.json)
            return 0
        if args.command == "submit":
            saved = submit_action(
                store,
                args.run_id,
                WorkflowStep(args.step),
                args.file,
            )
            _print_workflow(_workflow_dict(paths, saved), as_json=args.json)
            return 0
        if args.command == "render":
            return _render_run(paths, store, manifest)
        content = _load_content(paths, args.run_id)
        profile = load_profile(_profile_path(paths, content.language), content.language)
        report = validate_content(content, profile)
        _report_errors(report)
        if not report.ok:
            return 2
        if args.command == "validate":
            store.set_stage(args.run_id, RunStage.CONTENT_READY)
            print("validation=ok")
            return 0
        raise ValueError(f"Unsupported command: {args.command}")
    except (FileNotFoundError, OSError, RuntimeError) as exc:
        print(f"environment_error:{exc}", file=sys.stderr)
        return 3
    except (ValueError, yaml.YAMLError) as exc:
        print(f"validation_error:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
