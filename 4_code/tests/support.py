from __future__ import annotations

import shutil
from pathlib import Path

from resume_agent.config import AppPaths


def seed_private_runtime(paths: AppPaths) -> None:
    source = Path(__file__).parents[2] / "examples" / "private-data"
    paths.runtime_root.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = paths.runtime_root / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)
