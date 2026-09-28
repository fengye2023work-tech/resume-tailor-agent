from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from PIL import Image

from .layout import LayoutSpec


@dataclass(frozen=True)
class PageVisualReport:
    page_number: int
    bbox_delta: float
    profile_distance: float
    ink_density_delta: float
    ok: bool


@dataclass(frozen=True)
class VisualRegressionReport:
    pages: tuple[PageVisualReport, ...]

    @property
    def ok(self) -> bool:
        return bool(self.pages) and all(page.ok for page in self.pages)


def find_pdftoppm() -> Path:
    located = shutil.which("pdftoppm")
    if located:
        return Path(located)
    candidates = [
        Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "native" / "poppler" / "Library" / "bin" / "pdftoppm.exe",
        Path(r"C:\Program Files\poppler\Library\bin\pdftoppm.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("pdftoppm is required for visual regression")


def render_pdf_screenshots(
    pdf_path: Path,
    output_dir: Path,
    *,
    renderer: Path | None = None,
    dpi: int = 150,
) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / "page"
    result = subprocess.run(
        [str(renderer or find_pdftoppm()), "-png", "-r", str(dpi), str(pdf_path), str(prefix)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
    )
    pages = tuple(sorted(output_dir.glob("page-*.png"), key=lambda path: int(path.stem.rsplit("-", 1)[1])))
    if result.returncode != 0 or not pages:
        raise RuntimeError(f"PDF screenshot rendering failed: {result.stderr.strip()}")
    return pages


def _mask(path: Path, size: tuple[int, int] | None = None) -> Image.Image:
    image = Image.open(path).convert("L")
    if size and image.size != size:
        image = image.resize(size, Image.Resampling.BILINEAR)
    return image.point(lambda value: 255 if value < 238 else 0, mode="1")


def _signature(mask: Image.Image) -> tuple[tuple[float, float, float, float], float, tuple[float, ...]]:
    width, height = mask.size
    bbox = mask.getbbox() or (0, 0, 0, 0)
    normalized_bbox = (
        bbox[0] / width,
        bbox[1] / height,
        bbox[2] / width,
        bbox[3] / height,
    )
    ink_density = mask.histogram()[255] / (width * height)
    rows = [
        sum(bool(mask.getpixel((x, y))) for x in range(width)) / width
        for y in range(height)
    ]
    columns = [
        sum(bool(mask.getpixel((x, y))) for y in range(height)) / height
        for x in range(width)
    ]

    def downsample(values: list[float], bins: int = 32) -> tuple[float, ...]:
        result: list[float] = []
        for index in range(bins):
            start = index * len(values) // bins
            end = max(start + 1, (index + 1) * len(values) // bins)
            result.append(sum(values[start:end]) / (end - start))
        return tuple(result)

    return normalized_bbox, ink_density, downsample(rows) + downsample(columns)


def compare_layout_screenshots(
    candidates: list[Path] | tuple[Path, ...],
    baselines: list[Path] | tuple[Path, ...],
    spec: LayoutSpec,
) -> VisualRegressionReport:
    if len(candidates) != len(baselines):
        raise ValueError("Candidate and baseline screenshot counts must match")
    reports: list[PageVisualReport] = []
    for page_number, (candidate_path, baseline_path) in enumerate(zip(candidates, baselines), start=1):
        if not candidate_path.is_file() or not baseline_path.is_file():
            raise FileNotFoundError(candidate_path if not candidate_path.is_file() else baseline_path)
        baseline_mask = _mask(baseline_path)
        candidate_mask = _mask(candidate_path, baseline_mask.size)
        baseline_bbox, baseline_density, baseline_profile = _signature(baseline_mask)
        candidate_bbox, candidate_density, candidate_profile = _signature(candidate_mask)
        bbox_delta = sum(abs(left - right) for left, right in zip(candidate_bbox, baseline_bbox)) / 4
        profile_distance = sum(abs(left - right) for left, right in zip(candidate_profile, baseline_profile)) / len(baseline_profile)
        ink_density_delta = abs(candidate_density - baseline_density)
        ok = (
            bbox_delta <= spec.visual.max_bbox_delta
            and profile_distance <= spec.visual.max_profile_distance
            and ink_density_delta <= spec.visual.max_ink_density_delta
        )
        reports.append(PageVisualReport(page_number, bbox_delta, profile_distance, ink_density_delta, ok))
    return VisualRegressionReport(tuple(reports))
