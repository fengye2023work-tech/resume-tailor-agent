from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    repo_root: Path
    runtime_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "repo_root", self.repo_root.resolve())
        object.__setattr__(self, "runtime_root", self.runtime_root.resolve())

    @property
    def applications_root(self) -> Path:
        return self.runtime_root / "applications"

    @property
    def english_profile(self) -> Path:
        return self.runtime_root / "profiles" / "master_profile.md"

    @property
    def chinese_profile(self) -> Path:
        return self.runtime_root / "profiles" / "master_profile_ZH.md"

    @property
    def layout_spec(self) -> Path:
        return self.repo_root / "3_templates" / "layout_system" / "golden-record-v1" / "layout-spec.yaml"

    @property
    def golden_records_root(self) -> Path:
        return self.runtime_root / "golden_records"

    @property
    def golden_record_catalog(self) -> Path:
        return self.golden_records_root / "catalog.yaml"

    @classmethod
    def discover(cls, start: Path) -> "AppPaths":
        current = start.resolve()
        if current.is_file():
            current = current.parent
        for candidate in (current, *current.parents):
            if (
                (candidate / "4_code" / "pyproject.toml").is_file()
                and (candidate / "4_code" / "resume_agent").is_dir()
            ):
                return cls(candidate, candidate / ".resume-agent")
        raise FileNotFoundError(f"Resume-Agent repository not found from {start}")
