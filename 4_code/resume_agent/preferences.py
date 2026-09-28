from __future__ import annotations

from pathlib import Path

import yaml

from .models import Language, TemplateFamily, WordingPreference


def load_applicable_preferences(
    path: Path,
    *,
    language: Language,
    template_family: TemplateFamily,
    section: str,
    limit: int = 8,
) -> list[WordingPreference]:
    if limit < 1:
        raise ValueError("Preference limit must be positive")
    if not path.is_file():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("Preference inventory must be a version 1 mapping")
    raw_preferences = payload.get("preferences")
    if not isinstance(raw_preferences, list):
        raise ValueError("Preference inventory preferences must be a list")
    preferences = [WordingPreference.from_dict(item) for item in raw_preferences]
    ids = [item.id for item in preferences]
    if len(ids) != len(set(ids)):
        raise ValueError("Preference ids must be unique")
    matches = [
        item
        for item in preferences
        if item.status == "approved"
        and language in item.languages
        and template_family in item.template_families
        and section in item.sections
    ]
    return matches[:limit]
