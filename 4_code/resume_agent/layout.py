from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

from .models import ResumeBlock, ResumeContent
from .pdf import PageLayoutReport


@dataclass(frozen=True)
class PageSpec:
    width_mm: float
    height_mm: float
    page_1_padding_mm: tuple[float, float, float, float]
    page_2_padding_mm: tuple[float, float, float, float]


@dataclass(frozen=True)
class PaletteSpec:
    paper: str
    text_main: str
    text_muted: str
    accent: str
    border: str


@dataclass(frozen=True)
class SpacingSpec:
    section_gap_mm: float
    item_gap_mm: float


@dataclass(frozen=True)
class TypographySpec:
    identity_pt: float
    headline_pt: float
    section_pt: float
    summary_pt: float
    body_pt: float


@dataclass(frozen=True)
class OccupancySpec:
    minimum_fill_ratio: tuple[float, float]
    target_fill_ratio: tuple[float, float]


@dataclass(frozen=True)
class BalanceSpec:
    max_iterations: int


@dataclass(frozen=True)
class VisualSpec:
    enabled: bool
    baseline_pages: tuple[str, ...]
    max_bbox_delta: float
    max_profile_distance: float
    max_ink_density_delta: float


@dataclass(frozen=True)
class LayoutSpec:
    id: str
    source_path: Path
    page: PageSpec
    palette: PaletteSpec
    spacing: SpacingSpec
    typography: TypographySpec
    occupancy: OccupancySpec
    balance: BalanceSpec
    visual: VisualSpec

    def minimum_fill(self, page_number: int) -> float:
        return self.occupancy.minimum_fill_ratio[page_number - 1]

    def target_fill(self, page_number: int) -> float:
        return self.occupancy.target_fill_ratio[page_number - 1]

    @property
    def baseline_paths(self) -> tuple[Path, ...]:
        return tuple((self.source_path.parent / relative).resolve() for relative in self.visual.baseline_pages)


@dataclass(frozen=True)
class BalanceResult:
    content: ResumeContent
    reports: tuple[PageLayoutReport, ...]
    changed: bool
    iterations: int


MeasureLayout = Callable[[ResumeContent], tuple[PageLayoutReport, ...]]


def default_layout_spec_path() -> Path:
    return Path(__file__).resolve().parents[2] / "3_templates" / "layout_system" / "golden-record-v1" / "layout-spec.yaml"


def _pair(values: object, name: str) -> tuple[float, float]:
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError(f"{name} must contain exactly two values")
    return float(values[0]), float(values[1])


def _padding(values: object, name: str) -> tuple[float, float, float, float]:
    if not isinstance(values, list) or len(values) != 4:
        raise ValueError(f"{name} must contain top, right, bottom, and left")
    return tuple(float(value) for value in values)  # type: ignore[return-value]


def load_layout_spec(path: Path | None = None) -> LayoutSpec:
    source = (path or default_layout_spec_path()).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Layout spec not found: {source}")
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    try:
        page = data["page"]
        palette = data["palette"]
        spacing = data["spacing"]
        typography = data["typography"]
        occupancy = data["occupancy"]
        balance = data["balance"]
        visual = data["visual_regression"]
        spec = LayoutSpec(
            id=str(data["id"]),
            source_path=source,
            page=PageSpec(
                width_mm=float(page["width_mm"]),
                height_mm=float(page["height_mm"]),
                page_1_padding_mm=_padding(page["page_1_padding_mm"], "page.page_1_padding_mm"),
                page_2_padding_mm=_padding(page["page_2_padding_mm"], "page.page_2_padding_mm"),
            ),
            palette=PaletteSpec(**{key: str(palette[key]) for key in ("paper", "text_main", "text_muted", "accent", "border")}),
            spacing=SpacingSpec(
                section_gap_mm=float(spacing["section_gap_mm"]),
                item_gap_mm=float(spacing["item_gap_mm"]),
            ),
            typography=TypographySpec(
                identity_pt=float(typography["identity_pt"]),
                headline_pt=float(typography["headline_pt"]),
                section_pt=float(typography["section_pt"]),
                summary_pt=float(typography["summary_pt"]),
                body_pt=float(typography["body_pt"]),
            ),
            occupancy=OccupancySpec(
                minimum_fill_ratio=_pair(occupancy["minimum_fill_ratio"], "occupancy.minimum_fill_ratio"),
                target_fill_ratio=_pair(occupancy["target_fill_ratio"], "occupancy.target_fill_ratio"),
            ),
            balance=BalanceSpec(max_iterations=int(balance["max_iterations"])),
            visual=VisualSpec(
                enabled=bool(visual.get("enabled", True)),
                baseline_pages=tuple(str(value) for value in visual["baseline_pages"]),
                max_bbox_delta=float(visual["max_bbox_delta"]),
                max_profile_distance=float(visual["max_profile_distance"]),
                max_ink_density_delta=float(visual["max_ink_density_delta"]),
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid layout spec {source}: {exc}") from exc
    for value in (*spec.occupancy.minimum_fill_ratio, *spec.occupancy.target_fill_ratio):
        if not 0 < value <= 1:
            raise ValueError(f"Layout occupancy ratios must be in (0, 1]: {value}")
    return spec


def _penalty(reports: tuple[PageLayoutReport, ...], spec: LayoutSpec) -> float:
    overflow = sum(100.0 for report in reports if report.overflow)
    underfill = sum(
        max(0.0, spec.minimum_fill(report.page_number) - report.fill_ratio) * 10
        for report in reports
    )
    target_distance = sum(
        abs(spec.target_fill(report.page_number) - report.fill_ratio)
        for report in reports
    )
    return overflow + underfill + target_distance


def _merge_or_add_block(target: list[ResumeBlock], block: ResumeBlock, *, at_start: bool) -> None:
    adjacent = target[0] if at_start and target else target[-1] if target else None
    if adjacent and adjacent.kind == block.kind and adjacent.title == block.title:
        if at_start:
            adjacent.bullets[:0] = block.bullets
        else:
            adjacent.bullets.extend(block.bullets)
        if block.body and not adjacent.body:
            adjacent.body = block.body
        return
    if at_start:
        target.insert(0, block)
    else:
        target.append(block)


def _move_one(content: ResumeContent, source_page: int, target_page: int) -> ResumeContent | None:
    candidate = copy.deepcopy(content)
    source = candidate.pages[source_page].blocks
    target = candidate.pages[target_page].blocks
    if not source:
        return None
    from_start = source_page > target_page
    block_index = 0 if from_start else len(source) - 1
    block = source[block_index]
    if not block.bullets:
        moved = source.pop(block_index)
        _merge_or_add_block(target, moved, at_start=not from_start)
        return candidate

    bullet_index = 0 if from_start else len(block.bullets) - 1
    bullet = block.bullets.pop(bullet_index)
    moved = ResumeBlock(
        kind=block.kind,
        title=block.title,
        body=block.body if from_start else None,
        bullets=[bullet],
    )
    if from_start:
        block.body = None
    if not block.bullets:
        source.pop(block_index)
    _merge_or_add_block(target, moved, at_start=not from_start)
    return candidate


def balance_content(content: ResumeContent, spec: LayoutSpec, measure: MeasureLayout) -> BalanceResult:
    reports = measure(content)
    if len(reports) != 2:
        raise ValueError("Layout balancing requires exactly two measured pages")
    if not any(report.overflow or report.underfilled for report in reports):
        return BalanceResult(content, reports, False, 0)

    current = content
    current_penalty = _penalty(reports, spec)
    seen: set[tuple[tuple[tuple[str, int], ...], ...]] = set()
    iterations = 0
    for _ in range(spec.balance.max_iterations):
        fingerprint = tuple(
            tuple((block.title, len(block.bullets)) for block in page.blocks)
            for page in current.pages
        )
        if fingerprint in seen:
            break
        seen.add(fingerprint)
        options: list[tuple[float, ResumeContent, tuple[PageLayoutReport, ...]]] = []
        for source_page, target_page in ((1, 0), (0, 1)):
            candidate = _move_one(current, source_page, target_page)
            if candidate is None:
                continue
            candidate_reports = measure(candidate)
            options.append((_penalty(candidate_reports, spec), candidate, candidate_reports))
        if not options:
            break
        best_penalty, best_content, best_reports = min(options, key=lambda item: item[0])
        if best_penalty >= current_penalty - 1e-9:
            break
        current = best_content
        reports = best_reports
        current_penalty = best_penalty
        iterations += 1
        if not any(report.overflow or report.underfilled for report in reports):
            break
    return BalanceResult(current, reports, current is not content, iterations)
