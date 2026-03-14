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

DATABASE_URL: str = os.environ.get("POSTGRES_URL")

# ── LLM API Keys ─────────────────────────────────────────────

OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY")
GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY")

# ── LLM Settings ─────────────────────────────────────────────

DEFAULT_LLM_MODEL: str = os.environ.get("DEFAULT_LLM_MODEL")

# ── LangGraph (classify_items agent) ─────────────────────────

LANGGRAPH_API_URL: str = os.environ.get("LANGGRAPH_API_URL", "http://localhost:2024")
LANGGRAPH_API_KEY: str | None = os.environ.get("LANGGRAPH_API_KEY")

# Models used for multi-model voting in classify_items_graph.
# Comma-separated list of model values from agents/llm_factory.py AIModel enum.
# e.g. "gpt-4o,claude-3-5-sonnet-latest"
CLASSIFY_MODELS: list[str] = [
    m.strip()
    for m in os.environ.get("CLASSIFY_MODELS", "gpt-4o").split(",")
    if m.strip()
]
CLASSIFY_TOTAL_INVOCATIONS: int = int(os.environ.get("CLASSIFY_TOTAL_INVOCATIONS", "3"))
CLASSIFY_MAJORITY_THRESHOLD: float = float(
    os.environ.get("CLASSIFY_MAJORITY_THRESHOLD", "0.5")
)

# ── YouTube Scraping ─────────────────────────────────────────

MAX_VIDEOS_PER_KEYWORD: int = int(os.environ["MAX_VIDEOS_PER_KEYWORD"])
MAX_VIDEOS_PER_CREATOR: int = int(os.environ["MAX_VIDEOS_PER_CREATOR"])

# ── Transcript ────────────────────────────────────────────────

# Max characters of transcript to send to the LLM (to stay within context window)
TRANSCRIPT_MAX_CHARS: int = int(os.environ.get("TRANSCRIPT_MAX_CHARS"))
