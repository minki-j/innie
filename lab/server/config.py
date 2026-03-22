"""
Configuration for the lab FastAPI server.

Loads settings from environment variables (with .env file support).

Priority (later files override earlier ones):
  1. Repo root .env  (shared API keys, etc.)
  2. Application .env (Postgres/Neon connection vars)
  3. Lab-local .env   (any overrides specific to lab)
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


# ── Database ──────────────────────────────────────────────────

DATABASE_URL: str = os.environ.get(
    "POSTGRES_URL",
    os.environ.get("POSTGRES_PRISMA_URL", ""),
)

# ── LLM API Keys ─────────────────────────────────────────────

OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY", "")

# ── Tinker ────────────────────────────────────────────────────

TINKER_API_KEY: str = os.environ.get("TINKER_API_KEY", "")

# ── Server ────────────────────────────────────────────────────

SERVER_HOST: str = os.environ.get("LAB_SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.environ.get("LAB_SERVER_PORT", "8100"))

# ── Training defaults ────────────────────────────────────────

DEFAULT_BASE_MODEL: str = os.environ.get(
    "DEFAULT_BASE_MODEL", "meta-llama/Llama-3.1-8B-Instruct"
)
MIN_REVIEWS_FOR_TRAINING: int = int(os.environ.get("MIN_REVIEWS_FOR_TRAINING", "5"))
