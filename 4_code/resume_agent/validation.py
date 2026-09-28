from __future__ import annotations

from dataclasses import dataclass

from .models import ResumeContent
from .profile import ProfileDocument


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def error_codes(self) -> set[str]:
        return {issue.code for issue in self.issues if issue.severity == "error"}


def validate_content(content: ResumeContent, profile: ProfileDocument) -> ValidationReport:
    issues: list[ValidationIssue] = []
    if content.language != profile.language:
        issues.append(ValidationIssue("language_mismatch", "Resume and profile languages differ"))
    if len(content.pages) != 2:
        issues.append(ValidationIssue("page_count", "Resume content must define exactly two pages"))
    if content.template_family not in ("general", "domain"):
        issues.append(ValidationIssue("unsupported_template", "Unsupported template family"))

    supported_blocks = {"summary", "skills", "experience", "project", "education"}
    for page_number, page in enumerate(content.pages, start=1):
        for block in page.blocks:
            if block.kind not in supported_blocks:
                issues.append(ValidationIssue("unknown_block_type", f"Unknown block type: {block.kind}"))
            for bullet_number, bullet in enumerate(block.bullets, start=1):
                location = f"page {page_number}, {block.title}, bullet {bullet_number}"
                if not bullet.display_text:
                    issues.append(ValidationIssue("empty_bullet", f"Empty bullet at {location}"))
                if len(bullet.display_text) > 320:
                    issues.append(ValidationIssue("long_bullet", f"Long bullet at {location}", "warning"))
                has_structured_evidence = any(
                    value.strip()
                    for value in (bullet.label, bullet.situation, bullet.action, bullet.result)
                )
                if block.kind in {"experience", "project"} and has_structured_evidence and bullet.evidence_depth < 2:
                    issues.append(ValidationIssue(
                        "thin_evidence",
                        f"Structured evidence at {location} needs at least two of situation, action, and result",
                        "warning",
                    ))
                if not bullet.source_refs and not bullet.confirmed_by_user:
                    issues.append(ValidationIssue("claim_without_source", f"Untraced claim at {location}"))
                for source_ref in bullet.source_refs:
                    if source_ref not in profile.source_refs:
                        issues.append(ValidationIssue("unknown_source_ref", f"Unknown source {source_ref} at {location}"))
    return ValidationReport(tuple(issues))
