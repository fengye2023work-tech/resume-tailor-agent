from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ProfileSection:
    ref: str
    title: str
    text: str


@dataclass(frozen=True)
class ProfileDocument:
    language: str
    metadata: dict[str, object]
    sections: dict[str, ProfileSection]

    @property
    def source_refs(self) -> frozenset[str]:
        return frozenset(self.sections)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def load_profile(path: Path, language: str) -> ProfileDocument:
    if language not in ("en", "zh"):
        raise ValueError("Profile language must be 'en' or 'zh'")
    raw = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Profile frontmatter is missing: {path}")
    metadata = yaml.safe_load(match.group(1)) or {}
    body = raw[match.end() :]

    sections: dict[str, ProfileSection] = {}
    parent_slug = "root"
    current_title: str | None = None
    current_ref: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if current_ref and current_title:
            sections[current_ref] = ProfileSection(
                ref=current_ref,
                title=current_title,
                text="\n".join(buffer).strip(),
            )

    for line in body.splitlines():
        heading = re.match(r"^(#{1,2})\s+(.+?)\s*$", line)
        if not heading:
            buffer.append(line)
            continue
        flush()
        buffer = []
        level, title = len(heading.group(1)), heading.group(2)
        title_slug = _slug(title)
        if level == 1:
            parent_slug = title_slug
            current_ref = f"profile:{parent_slug}"
        else:
            current_ref = f"profile:{parent_slug}/{title_slug}"
        current_title = title
    flush()
    return ProfileDocument(language=language, metadata=metadata, sections=sections)
