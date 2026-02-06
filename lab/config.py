"""
Configuration for the lab environment.

Loads settings from environment variables (with .env file support).

Priority (later files override earlier ones):
  1. Repo root .env  (shared API keys, LangSmith, etc.)
  2. Lab-local .env  (any overrides specific to lab)
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env files in order of priority (later files override earlier ones):
# 1. Repo root .env (LLM API keys, LangSmith, etc.)
# 2. Lab-local .env (any overrides)
_REPO_ROOT = Path(__file__).resolve().parent.parent

for env_path in [
    _REPO_ROOT / ".env",
    Path(__file__).resolve().parent / ".env",
]:
    if env_path.exists():
        load_dotenv(env_path, override=True)


# ── LLM API Keys ─────────────────────────────────────────────

OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY")
GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY")

# ── Tinker ────────────────────────────────────────────────────

TINKER_API_KEY: str = os.environ.get("TINKER_API_KEY")

# ── LangSmith ─────────────────────────────────────────────────

LANGSMITH_TRACING: str = os.environ.get("LANGSMITH_TRACING")
LANGSMITH_ENDPOINT: str = os.environ.get("LANGSMITH_ENDPOINT")
LANGSMITH_API_KEY: str = os.environ.get("LANGSMITH_API_KEY")
LANGSMITH_PROJECT: str = os.environ.get("LANGSMITH_PROJECT")

# ── LLM Settings ─────────────────────────────────────────────

DEFAULT_LLM_MODEL: str = os.environ.get("DEFAULT_LLM_MODEL")
