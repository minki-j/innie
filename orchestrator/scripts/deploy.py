"""
Deploys all Prefect flows and syncs the work pool's env vars + pip packages.

Usage: uv run deploy
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.sync_prefect import main as sync_prefect

ORCHESTRATOR_DIR = Path(__file__).resolve().parent.parent


def main() -> None:
    print("Deploying flows...")
    result = subprocess.run(
        [sys.executable, "-m", "prefect", "deploy", "--all"],
        cwd=ORCHESTRATOR_DIR,
    )
    if result.returncode != 0:
        print("Deploy failed.", file=sys.stderr)
        sys.exit(result.returncode)

    print("\nSyncing work pool...")
    sync_prefect()


if __name__ == "__main__":
    main()
