"""
Configuration for the orchestrator pipeline.

Loads settings from environment variables (with .env file support).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


# ── Database ──────────────────────────────────────────────────

DATABASE_URL: str = os.environ.get("POSTGRES_URL")

# ── LLM API Keys ─────────────────────────────────────────────

OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY")
GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY")

# ── LLM Settings ─────────────────────────────────────────────

DEFAULT_LLM_MODEL: str = os.environ.get("DEFAULT_LLM_MODEL")

# ── LangGraph (classify_items agent) ─────────────────────────

LANGGRAPH_API_URL: str = os.environ.get("LANGGRAPH_API_URL")
LANGGRAPH_API_KEY: str | None = os.environ.get("LANGGRAPH_API_KEY")

# Models used for multi-model voting in classify_items_graph.
# Comma-separated list of model values from agents/llm_factory.py AIModel enum.
# e.g. "gpt-4o,claude-3-5-sonnet-latest"
CLASSIFY_MODELS: list[str] = [
    m.strip() for m in os.environ.get("CLASSIFY_MODELS").split(",") if m.strip()
]
CLASSIFY_TOTAL_INVOCATIONS: int = int(os.environ.get("CLASSIFY_TOTAL_INVOCATIONS"))
CLASSIFY_MAJORITY_THRESHOLD: float = float(
    os.environ.get("CLASSIFY_MAJORITY_THRESHOLD")
)

# ── YouTube Scraping ─────────────────────────────────────────

MAX_VIDEOS_PER_KEYWORD: int = int(os.environ["MAX_VIDEOS_PER_KEYWORD"])
MAX_VIDEOS_PER_CREATOR: int = int(os.environ["MAX_VIDEOS_PER_CREATOR"])

# ── Transcript ────────────────────────────────────────────────

# Max characters of transcript to send to the LLM (to stay within context window)
TRANSCRIPT_MAX_CHARS: int = int(os.environ.get("TRANSCRIPT_MAX_CHARS"))

# ── Redis ─────────────────────────────────────────────────────

REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6380/0")
IDEA_GRAPH_STREAM_TTL_SECONDS: int = int(
    os.environ.get("IDEA_GRAPH_STREAM_TTL_SECONDS", "3600")
)
IDEA_GRAPH_STREAM_POLL_INTERVAL_MS: int = int(
    os.environ.get("IDEA_GRAPH_STREAM_POLL_INTERVAL_MS", "500")
)

# ── Rate Limits (calls per window_seconds) ───────────────────

YOUTUBE_RATE_LIMIT_CALLS: int = int(os.environ.get("YOUTUBE_RATE_LIMIT_CALLS", "5"))
YOUTUBE_RATE_LIMIT_WINDOW: int = int(os.environ.get("YOUTUBE_RATE_LIMIT_WINDOW", "60"))

OPENAI_RATE_LIMIT_CALLS: int = int(os.environ.get("OPENAI_RATE_LIMIT_CALLS", "60"))
OPENAI_RATE_LIMIT_WINDOW: int = int(os.environ.get("OPENAI_RATE_LIMIT_WINDOW", "60"))

ANTHROPIC_RATE_LIMIT_CALLS: int = int(os.environ.get("ANTHROPIC_RATE_LIMIT_CALLS", "50"))
ANTHROPIC_RATE_LIMIT_WINDOW: int = int(os.environ.get("ANTHROPIC_RATE_LIMIT_WINDOW", "60"))

GOOGLE_RATE_LIMIT_CALLS: int = int(os.environ.get("GOOGLE_RATE_LIMIT_CALLS", "60"))
GOOGLE_RATE_LIMIT_WINDOW: int = int(os.environ.get("GOOGLE_RATE_LIMIT_WINDOW", "60"))

LANGGRAPH_RATE_LIMIT_CALLS: int = int(os.environ.get("LANGGRAPH_RATE_LIMIT_CALLS", "10"))
LANGGRAPH_RATE_LIMIT_WINDOW: int = int(os.environ.get("LANGGRAPH_RATE_LIMIT_WINDOW", "60"))
