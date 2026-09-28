from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from pypdf import PdfReader


@dataclass(frozen=True)
class PdfReport:
    page_count: int
    ok: bool


@dataclass(frozen=True)
class PageLayoutReport:
    page_number: int
    overflow: bool
    fill_ratio: float
    underfilled: bool


def find_browser() -> Path:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    for name in ("msedge", "chrome", "chromium"):
        located = shutil.which(name)
        if located:
            return Path(located)
    raise FileNotFoundError("Microsoft Edge or Chrome is required for PDF rendering")


def inspect_dumped_dom(dom: str) -> list[int]:
    overflow_pages: list[int] = []
    for tag in re.findall(r"<[^>]+class=[\"'][^\"']*resume-page[^\"']*[\"'][^>]*>", dom):
        page = re.search(r"data-page=[\"'](\d+)[\"']", tag)
        overflow = re.search(r"data-overflow=[\"']true[\"']", tag)
        if page and overflow:
            overflow_pages.append(int(page.group(1)))
    return overflow_pages


def inspect_dumped_layout(dom: str) -> tuple[PageLayoutReport, ...]:
    reports: list[PageLayoutReport] = []
    for tag in re.findall(r"<[^>]+class=[\"'][^\"']*resume-page[^\"']*[\"'][^>]*>", dom):
        page = re.search(r"data-page=[\"'](\d+)[\"']", tag)
        if not page:
            continue
        fill = re.search(r"data-fill-ratio=[\"']([0-9.]+)[\"']", tag)
        reports.append(PageLayoutReport(
            page_number=int(page.group(1)),
            overflow=bool(re.search(r"data-overflow=[\"']true[\"']", tag)),
            fill_ratio=float(fill.group(1)) if fill else 1.0,
            underfilled=bool(re.search(r"data-underfilled=[\"']true[\"']", tag)),
        ))
    return tuple(reports)


@contextmanager
def _browser_profile() -> Iterator[Path]:
    profile = Path(tempfile.mkdtemp(prefix="resume-agent-edge-"))
    try:
        yield profile
    finally:
        for attempt in range(100):
            try:
                shutil.rmtree(profile)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                if attempt == 99:
                    raise
                time.sleep(0.1)


def inspect_layout(html_path: Path, browser: Path | None = None) -> tuple[PageLayoutReport, ...]:
    executable = browser or find_browser()
    with _browser_profile() as profile:
        result = subprocess.run(
            [str(executable), "--headless=new", "--disable-gpu", f"--user-data-dir={profile}", "--dump-dom", html_path.resolve().as_uri()],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    if result.returncode != 0 or "data-overflow=" not in result.stdout:
        raise RuntimeError(f"Browser overflow preflight failed: {result.stderr.strip()}")
    return inspect_dumped_layout(result.stdout)


def inspect_overflow(html_path: Path, browser: Path | None = None) -> list[int]:
    return [report.page_number for report in inspect_layout(html_path, browser) if report.overflow]


def print_pdf(html_path: Path, pdf_path: Path, browser: Path | None = None) -> Path:
    executable = browser or find_browser()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with _browser_profile() as profile:
        result = subprocess.run(
            [str(executable), "--headless=new", "--disable-gpu", f"--user-data-dir={profile}", "--no-pdf-header-footer", f"--print-to-pdf={pdf_path.resolve()}", html_path.resolve().as_uri()],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )
    if result.returncode != 0 or not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f"Browser PDF rendering failed: {result.stderr.strip()}")
    return pdf_path


def verify_pdf(pdf_path: Path) -> PdfReport:
    count = len(PdfReader(str(pdf_path)).pages)
    return PdfReport(page_count=count, ok=count == 2)
