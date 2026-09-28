from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable


_PRIVATE_PREFIXES = (
    ".resume-agent/",
    "2_knowledge/",
    "output/",
    "3_templates/design_references/",
    "3_templates/design_templates/",
    "3_templates/generic_materials/",
    "3_templates/golden_record/",
    "docs/research/",
)

_PRIVATE_PATHS = {
    "CONTEXT.md",
    "MANIFEST.md",
    "1_docs/first-creation-review.md",
    "1_docs/prd_extracted.txt",
}

_BINARY_SUFFIXES = {".pdf", ".doc", ".docx"}

_CREDENTIAL_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"fc-[A-Za-z0-9]{12,}"),
    re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    re.compile(
        r"(?i)(?:api[_-]?key|token|secret|password)\s*[=:]\s*[\"'][^\"']{8,}[\"']"
    ),
)

_EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_SAFE_EMAIL_DOMAINS = {"example.com", "example.org", "example.net"}


def _private_terms(root: Path) -> tuple[str, ...]:
    denylist = root / ".resume-agent" / "privacy-denylist.txt"
    if not denylist.is_file():
        return ()
    return tuple(
        line.strip()
        for line in denylist.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def scan_public_tree(root: Path, tracked_paths: Iterable[str]) -> list[str]:
    root = root.resolve()
    findings: list[str] = []
    private_terms = tuple(term.casefold() for term in _private_terms(root))
    for raw_path in tracked_paths:
        relative = raw_path.replace("\\", "/")
        if relative in _PRIVATE_PATHS or relative.startswith(_PRIVATE_PREFIXES):
            findings.append(f"private path: {relative}")
            continue
        path = root / relative
        if path.suffix.lower() in _BINARY_SUFFIXES:
            findings.append(f"private binary type: {relative}")
            continue
        if not path.is_file():
            findings.append(f"missing tracked file: {relative}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(f"unreviewed binary file: {relative}")
            continue
        if any(pattern.search(text) for pattern in _CREDENTIAL_PATTERNS):
            findings.append(f"credential pattern: {relative}")
        unsafe_emails = {
            match.group(0)
            for match in _EMAIL_PATTERN.finditer(text)
            if match.group(0).rsplit("@", 1)[1].casefold() not in _SAFE_EMAIL_DOMAINS
        }
        if unsafe_emails:
            findings.append(f"non-example email: {relative}")
        folded = text.casefold()
        if any(term in folded for term in private_terms):
            findings.append(f"private denylist term: {relative}")
    return sorted(set(findings))


def _tracked_paths(root: Path) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return tuple(
        value.decode("utf-8")
        for value in result.stdout.split(b"\0")
        if value
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    root = Path(args[0] if args else ".").resolve()
    findings = scan_public_tree(root, _tracked_paths(root))
    if findings:
        for finding in findings:
            print(f"privacy_error:{finding}", file=sys.stderr)
        return 1
    print("privacy_scan=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
