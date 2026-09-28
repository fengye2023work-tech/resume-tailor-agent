from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal


Language = Literal["en", "zh"]
PreferenceStatus = Literal["proposed", "approved"]
TemplateFamily = Literal["general", "domain"]
ActionKind = Literal["model", "user", "command", "complete"]


class RunStage(str, Enum):
    INTAKE = "intake"
    RESEARCHED = "researched"
    CONTENT_READY = "content_ready"
    RENDERED = "rendered"
    FINALIZED = "finalized"


class WorkflowStep(str, Enum):
    RESEARCH = "research"
    GOLDEN_RECORD = "golden_record"
    GAP_REVIEW = "gap_review"
    QUESTIONS = "questions"
    CONTENT_PLAN = "content_plan"
    DRAFT = "draft"
    LANGUAGE_REVIEW = "language_review"
    RENDER = "render"
    OWNER_REVIEW = "owner_review"
    FINALIZE = "finalize"
    COMPLETE = "complete"


@dataclass(frozen=True)
class WorkflowAction:
    step: WorkflowStep
    kind: ActionKind
    instructions: str
    required_files: tuple[str, ...]
    output_file: str | None


@dataclass(frozen=True)
class ApplicationInput:
    company: str
    role: str
    language: Language
    jd: str
    url: str | None = None

    def __post_init__(self) -> None:
        if not self.company.strip():
            raise ValueError("Company is required")
        if not self.role.strip():
            raise ValueError("Role is required")
        if self.language not in ("en", "zh"):
            raise ValueError("Language must be 'en' or 'zh'")
        if not self.jd.strip():
            raise ValueError("JD is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApplicationInput":
        return cls(
            company=str(data["company"]),
            role=str(data["role"]),
            language=data["language"],
            jd=str(data["jd"]),
            url=data.get("url"),
        )


@dataclass(frozen=True)
class WordingPreference:
    id: str
    languages: tuple[Language, ...]
    template_families: tuple[TemplateFamily, ...]
    sections: tuple[str, ...]
    prefer: str
    avoid: str
    source: str
    status: PreferenceStatus

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WordingPreference":
        if not isinstance(data, dict):
            raise ValueError("Preference must be a mapping")
        scope = data.get("applies_to")
        if not isinstance(scope, dict):
            raise ValueError("Preference applies_to must be a mapping")
        preference_id = str(data.get("id", "")).strip()
        prefer = str(data.get("prefer", "")).strip()
        avoid = str(data.get("avoid", "")).strip()
        source = str(data.get("source", "")).strip()
        status = data.get("status")
        raw_languages = scope.get("languages")
        raw_template_families = scope.get("template_families")
        raw_sections = scope.get("sections")
        if not preference_id or not prefer or not avoid or not source:
            raise ValueError("Preference id, prefer, avoid, and source are required")
        if status not in ("proposed", "approved"):
            raise ValueError(f"Invalid preference status: {status}")
        if not isinstance(raw_languages, list):
            raise ValueError("Preference languages must be a list")
        if not isinstance(raw_template_families, list):
            raise ValueError("Preference template families must be a list")
        if not isinstance(raw_sections, list):
            raise ValueError("Preference sections must be a list")
        languages = tuple(raw_languages)
        template_families = tuple(raw_template_families)
        sections = tuple(str(value).strip() for value in raw_sections)
        if not languages or any(value not in ("en", "zh") for value in languages):
            raise ValueError(f"Invalid preference languages: {languages}")
        if not template_families or any(value not in ("general", "domain") for value in template_families):
            raise ValueError(f"Invalid preference template families: {template_families}")
        if not sections or any(not value for value in sections):
            raise ValueError("Preference sections must contain non-empty values")
        return cls(
            id=preference_id,
            languages=languages,
            template_families=template_families,
            sections=sections,
            prefer=prefer,
            avoid=avoid,
            source=source,
            status=status,
        )


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    stage: RunStage
    created_at: str
    application: ApplicationInput
    updated_at: str = ""
    current_step: WorkflowStep = WorkflowStep.RESEARCH
    selected_golden_record_id: str | None = None
    pending_questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.updated_at:
            object.__setattr__(self, "updated_at", self.created_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "stage": self.stage.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_step": self.current_step.value,
            "selected_golden_record_id": self.selected_golden_record_id,
            "pending_questions": list(self.pending_questions),
            "application": self.application.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunManifest":
        stage = RunStage(data["stage"])
        default_steps = {
            RunStage.INTAKE: WorkflowStep.RESEARCH,
            RunStage.RESEARCHED: WorkflowStep.GOLDEN_RECORD,
            RunStage.CONTENT_READY: WorkflowStep.RENDER,
            RunStage.RENDERED: WorkflowStep.OWNER_REVIEW,
            RunStage.FINALIZED: WorkflowStep.COMPLETE,
        }
        return cls(
            run_id=str(data["run_id"]),
            stage=stage,
            created_at=str(data["created_at"]),
            application=ApplicationInput.from_dict(data["application"]),
            updated_at=str(data.get("updated_at") or data["created_at"]),
            current_step=WorkflowStep(data.get("current_step", default_steps[stage].value)),
            selected_golden_record_id=data.get("selected_golden_record_id"),
            pending_questions=tuple(str(item) for item in data.get("pending_questions", [])),
        )


@dataclass
class ResumeBullet:
    text: str = ""
    label: str = ""
    situation: str = ""
    action: str = ""
    result: str = ""
    source_refs: list[str] = field(default_factory=list)
    confirmed_by_user: bool = False

    @property
    def evidence_depth(self) -> int:
        return sum(bool(value.strip()) for value in (self.situation, self.action, self.result))

    @property
    def display_label(self) -> str:
        if self.label.strip():
            return self.label.strip()
        if ":" in self.text:
            return self.text.split(":", 1)[0].strip()
        return ""

    @property
    def display_body(self) -> str:
        structured = " ".join(
            value.strip()
            for value in (self.situation, self.action, self.result)
            if value.strip()
        )
        if structured:
            return structured
        if ":" in self.text:
            return self.text.split(":", 1)[1].strip()
        return self.text.strip()

    @property
    def display_text(self) -> str:
        return " ".join(value for value in (self.display_label, self.display_body) if value)


@dataclass
class ResumeBlock:
    kind: Literal["summary", "skills", "experience", "project", "education"]
    title: str
    body: str | None = None
    bullets: list[ResumeBullet] = field(default_factory=list)


@dataclass
class ResumePage:
    blocks: list[ResumeBlock]


@dataclass
class ResumeContent:
    language: Language
    template_family: TemplateFamily
    headline: str
    pages: list[ResumePage]
    candidate_name: str = "Sample Candidate"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResumeContent":
        pages: list[ResumePage] = []
        for page_data in data.get("pages", []):
            blocks: list[ResumeBlock] = []
            for block_data in page_data.get("blocks", []):
                bullets = [ResumeBullet(
                    text=str(item.get("text", "")),
                    label=str(item.get("label", "")),
                    situation=str(item.get("situation", "")),
                    action=str(item.get("action", "")),
                    result=str(item.get("result", "")),
                    source_refs=list(item.get("source_refs", [])),
                    confirmed_by_user=bool(item.get("confirmed_by_user", False)),
                ) for item in block_data.get("bullets", [])]
                blocks.append(ResumeBlock(
                    kind=block_data.get("kind", ""),
                    title=str(block_data.get("title", "")),
                    body=block_data.get("body"),
                    bullets=bullets,
                ))
            pages.append(ResumePage(blocks))
        return cls(
            language=data.get("language", ""),
            template_family=data.get("template_family", ""),
            headline=str(data.get("headline", "")),
            pages=pages,
            candidate_name=str(data.get("candidate_name", "Sample Candidate")),
        )
