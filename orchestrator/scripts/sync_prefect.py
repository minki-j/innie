"""
Syncs pip packages and env vars to the work pool's base_job_template in Prefect Cloud.

Reads dependencies from pyproject.toml and env vars from orchestrator/.env, then
updates the work pool's default values so all deployments on the pool inherit them.

Usage: uv run sync-prefect
"""

from __future__ import annotations

import asyncio
import sys
import tomllib
from pathlib import Path

import httpx
from dotenv import dotenv_values

ORCHESTRATOR_DIR = Path(__file__).resolve().parent.parent
WORK_POOL_NAME = "main"

# These are connection meta-vars for reaching Prefect Cloud itself — the
# remote worker doesn't need them as runtime env vars.
SKIP_ENV_KEYS = {"PREFECT_API_KEY", "PREFECT_API_URL"}


def load_env() -> dict[str, str]:
    """Load env vars from orchestrator/.env only."""
    path = ORCHESTRATOR_DIR / ".env"
    return {k: v for k, v in dotenv_values(path).items() if v is not None}


def get_pip_packages() -> list[str]:
    """Read the project's dependencies from pyproject.toml."""
    with open(ORCHESTRATOR_DIR / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    return data["project"]["dependencies"]


async def _main() -> None:
    env = load_env()

    api_url = env.get("PREFECT_API_URL", "").rstrip("/")
    api_key = env.get("PREFECT_API_KEY", "")

    if not api_url or "127.0.0.1" in api_url or "localhost" in api_url:
        print(
            "Error: PREFECT_API_URL must point to Prefect Cloud.\n"
            "Uncomment and set PREFECT_API_URL in orchestrator/.env, e.g.:\n"
            "  PREFECT_API_URL=https://api.prefect.cloud/api/accounts/<id>/workspaces/<id>",
            file=sys.stderr,
        )
        sys.exit(1)

    if not api_key:
        print("Error: PREFECT_API_KEY is not set in orchestrator/.env", file=sys.stderr)
        sys.exit(1)

    pip_packages = get_pip_packages()
    sync_env = {k: v for k, v in env.items() if k not in SKIP_ENV_KEYS}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        resp = await client.get(f"{api_url}/work_pools/{WORK_POOL_NAME}")
        resp.raise_for_status()
        work_pool = resp.json()

        template = work_pool.get("base_job_template", {})
        props = template.setdefault("variables", {}).setdefault("properties", {})
        props.setdefault("pip_packages", {})["default"] = pip_packages
        props.setdefault("env", {})["default"] = sync_env

        resp = await client.patch(
            f"{api_url}/work_pools/{WORK_POOL_NAME}",
            json={"base_job_template": template},
        )
        resp.raise_for_status()

    print(f"Done — {len(pip_packages)} pip packages, {len(sync_env)} env vars pushed to work pool '{WORK_POOL_NAME}'.")


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
