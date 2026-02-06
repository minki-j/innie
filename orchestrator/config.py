"""
Configuration for the orchestrator pipeline.

Loads settings from environment variables (with .env file support).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env files in order of priority (later files override earlier ones):
# 1. Repo root .env (LLM API keys, etc.)
# 2. Application .env (Postgres/Neon connection vars)
# 3. Orchestrator-local .env (any overrides)
_REPO_ROOT = Path(__file__).resolve().parent.parent

for env_path in [
    _REPO_ROOT / ".env",
    _REPO_ROOT / "application" / ".env",
    Path(__file__).resolve().parent / ".env",
]:
    if env_path.exists():
        load_dotenv(env_path, override=True)


# ── Database ──────────────────────────────────────────────────

DATABASE_URL: str = os.environ.get(
    "POSTGRES_URL",
    os.environ.get("POSTGRES_PRISMA_URL", ""),
)

# ── LLM API Keys ─────────────────────────────────────────────

OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY", "")

# ── LLM Settings ─────────────────────────────────────────────

DEFAULT_LLM_MODEL: str = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")

# ── AGI, Inc. ─────────────────────────────────────────────────

AGI_API_KEY: str = os.environ.get("AGI_INC_API_KEY", "")
AGI_AGENT_MODEL: str = os.environ.get("AGI_AGENT_MODEL", "agi-0-fast")
MAX_VIDEOS_PER_AGI_SEARCH: int = int(os.environ["MAX_VIDEOS_PER_AGI_SEARCH"])

# ── YouTube Scraping ─────────────────────────────────────────

MAX_VIDEOS_PER_KEYWORD: int = int(os.environ["MAX_VIDEOS_PER_KEYWORD"])
MAX_VIDEOS_PER_CREATOR: int = int(os.environ["MAX_VIDEOS_PER_CREATOR"])

# ── Transcript ────────────────────────────────────────────────

# Max characters of transcript to send to the LLM (to stay within context window)
TRANSCRIPT_MAX_CHARS: int = int(os.environ.get("TRANSCRIPT_MAX_CHARS", "50000"))
