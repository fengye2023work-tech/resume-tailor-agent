from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .models import Language, TemplateFamily


@dataclass(frozen=True)
class GoldenRecordDefinition:
    id: str
    language: Language
    template_family: TemplateFamily
    target_roles: tuple[str, ...]
    content_path: Path
    html_path: Path


def _source_path(catalog_root: Path, value: Any, *, label: str) -> Path:
    relative = Path(str(value or ""))
    if not str(value or "").strip() or relative.is_absolute():
        raise ValueError(f"Golden Record {label} path must stay inside catalog directory")
    resolved = (catalog_root / relative).resolve()
    if not resolved.is_relative_to(catalog_root):
        raise ValueError(f"Golden Record {label} path must stay inside catalog directory")
    if not resolved.is_file():
        raise ValueError(f"Golden Record {label} file not found: {relative}")
    return resolved


def load_golden_record_catalog(path: Path) -> tuple[GoldenRecordDefinition, ...]:
    catalog_path = path.resolve()
    payload = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("Golden Record catalog must use version 1")
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("Golden Record catalog records must be a list")

    catalog_root = catalog_path.parent.resolve()
    seen_ids: set[str] = set()
    records: list[GoldenRecordDefinition] = []
    for raw in raw_records:
        if not isinstance(raw, dict):
            raise ValueError("Golden Record entry must be a mapping")
        record_id = str(raw.get("id", "")).strip()
        if not record_id:
            raise ValueError("Golden Record id is required")
        if record_id in seen_ids:
            raise ValueError(f"Duplicate Golden Record id: {record_id}")
        seen_ids.add(record_id)

        language = raw.get("language")
        if language not in ("en", "zh"):
            raise ValueError(f"Invalid Golden Record language: {language}")
        template_family = raw.get("template_family")
        if template_family not in ("general", "domain"):
            raise ValueError(f"Invalid Golden Record template family: {template_family}")
        raw_roles = raw.get("target_roles")
        if not isinstance(raw_roles, list):
            raise ValueError("Golden Record target_roles must be a list")
        target_roles = tuple(str(role).strip() for role in raw_roles)
        if not target_roles or any(not role for role in target_roles):
            raise ValueError("Golden Record target_roles must contain non-empty roles")

        records.append(GoldenRecordDefinition(
            id=record_id,
            language=language,
            template_family=template_family,
            target_roles=target_roles,
            content_path=_source_path(catalog_root, raw.get("content"), label="content"),
            html_path=_source_path(catalog_root, raw.get("html"), label="HTML"),
        ))
    return tuple(records)


def get_golden_record(
    catalog: tuple[GoldenRecordDefinition, ...],
    record_id: str,
    language: Language,
) -> GoldenRecordDefinition:
    for record in catalog:
        if record.id != record_id:
            continue
        if record.language != language:
            raise ValueError(
                f"Golden Record {record_id} uses language {record.language}, not {language}"
            )
        return record
    raise ValueError(f"Unknown Golden Record: {record_id}")
