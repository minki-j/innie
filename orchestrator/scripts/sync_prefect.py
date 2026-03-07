"""
Sync local dependencies and environment variables to the Prefect deployment.

Reads pip packages from pyproject.toml and orchestrator-relevant env vars
from .env files, then pushes both as job_variables to every deployment
listed in prefect.yaml.

Usage:
    uv run sync-prefect
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from dotenv import dotenv_values

_ORCH_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _ORCH_ROOT.parent

REQUIRED_ENV_VARS = [
    "POSTGRES_URL",
    "POSTGRES_PRISMA_URL",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "DEFAULT_LLM_MODEL",
    "MAX_VIDEOS_PER_KEYWORD",
    "MAX_VIDEOS_PER_CREATOR",
    "TRANSCRIPT_MAX_CHARS",
    "LAB_SERVER_URL",
    "LANGSMITH_TRACING",
    "LANGSMITH_ENDPOINT",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
]

_ENV_FILES = [
    _REPO_ROOT / ".env",
    _REPO_ROOT / "application" / ".env",
    _ORCH_ROOT / ".env",
]


def _load_pip_packages() -> list[str]:
    pyproject_path = _ORCH_ROOT / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    return list(data["project"]["dependencies"])


def _load_env_vars() -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in _ENV_FILES:
        if path.exists():
            merged.update(dotenv_values(path))

    return {k: v for k, v in merged.items() if k in REQUIRED_ENV_VARS and v}


def _get_deployment_names() -> list[tuple[str, str]]:
    """Parse prefect.yaml and return (flow_name, deployment_name) pairs.

    The flow_name is derived from the entrypoint (the function name after ':'),
    since Prefect uses @flow(name=...) — which matches the function name when
    the name kwarg equals the function name.
    """
    import yaml

    prefect_yaml = _ORCH_ROOT / "prefect.yaml"
    with open(prefect_yaml) as f:
        config = yaml.safe_load(f)

    pairs: list[tuple[str, str]] = []
    for dep in config.get("deployments", []):
        deployment_name = dep["name"]
        entrypoint: str = dep["entrypoint"]
        flow_fn_name = entrypoint.split(":")[-1]
        pairs.append((flow_fn_name, deployment_name))
    return pairs


def main() -> None:
    pip_packages = _load_pip_packages()
    env_vars = _load_env_vars()
    deployment_pairs = _get_deployment_names()

    if not deployment_pairs:
        print("No deployments found in prefect.yaml")
        sys.exit(1)

    print(f"Pip packages ({len(pip_packages)}):")
    for pkg in pip_packages:
        print(f"  - {pkg}")
    print()

    print(f"Environment variables ({len(env_vars)}):")
    for key in sorted(env_vars):
        val = env_vars[key]
        preview = val[:6] + "..." if len(val) > 6 else val
        print(f"  - {key}={preview}")
    print()

    missing = [k for k in REQUIRED_ENV_VARS if k not in env_vars]
    if missing:
        print(f"Skipped (not set): {', '.join(missing)}")
        print()

    job_variables = {
        "pip_packages": pip_packages,
        "env": env_vars,
    }

    from prefect.client.orchestration import get_client
    from prefect.client.schemas.actions import DeploymentUpdate

    with get_client(sync_client=True) as client:
        for flow_name, deployment_name in deployment_pairs:
            lookup = f"{flow_name}/{deployment_name}"
            print(f"Updating deployment '{lookup}' ...")

            try:
                deployment = client.read_deployment_by_name(lookup)
            except Exception as e:
                print(f"  Failed to read deployment: {e}")
                print("  Have you run 'uv run prefect deploy --all' first?")
                sys.exit(1)

            client.update_deployment(
                deployment_id=deployment.id,
                deployment=DeploymentUpdate(job_variables=job_variables),
            )
            print(f"  Synced job_variables to '{lookup}'")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
