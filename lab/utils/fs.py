from __future__ import annotations

import os
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    """
    Find the monorepo root by walking up until we see a `.git` directory.

    Falls back to `start` if no git root is found.
    """
    start = start.resolve()
    for p in (start, *start.parents):
        if (p / ".git").is_dir():
            return p
    return start


def load_dotenv(path: Path) -> bool:
    """
    Minimal `.env` loader (no external deps).

    - Supports lines like KEY=VALUE and optional `export KEY=VALUE`
    - Ignores blank lines and comments (# ...)
    - Does not override already-set environment variables
    """
    if not path.is_file():
        return False

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        # Strip simple surrounding quotes.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)
    return True

