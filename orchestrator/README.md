# Orchestrator

Prefect pipeline that polls the database for active topics, scrapes YouTube videos, and evaluates them against topic criteria using LLMs.

## Setup

```bash
cd orchestrator
uv sync
```

## Commands

**Run the pipeline:**

```bash
uv run pipeline
```

**Deploy flows to Prefect:**
```bash
uv run prefect deploy --all
```

**Sync dependencies and env vars to the Prefect deployment:**
```bash
uv run sync-prefect
```

Run this after deploying to push pip packages (from `pyproject.toml`) and environment variables (from `.env` files) to the managed work pool as `job_variables`.

**Generate flow diagram**
```bash
uv run generate_flow_diagram --flow {flow_name}
```

**Regenerate Pydantic models from Prisma schema:**

```bash
uv run generate-models
```

Run this after any changes to `application/prisma/schema.prisma` to keep the Python models in sync.

## Environment Variables

The pipeline loads env vars from (in order, later overrides earlier):

1. `../.env` — LLM API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.)
2. `../application/.env` — Postgres connection (`POSTGRES_URL`)
3. `.env` (local) — any overrides

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_URL` | — | Postgres connection string |
| `OPENAI_API_KEY` | — | OpenAI API key (required for default gpt-4o) |
| `ANTHROPIC_API_KEY` | — | Anthropic API key (for Claude models) |
| `GOOGLE_API_KEY` | — | Google API key (for Gemini models) |
| `DEFAULT_LLM_MODEL` | `gpt-4o` | LLM model for criterion evaluation |
| `MAX_VIDEOS_PER_KEYWORD` | `20` | Max videos fetched per keyword search |
| `MAX_VIDEOS_PER_CREATOR` | `30` | Max videos fetched per creator channel |
| `TRANSCRIPT_MAX_CHARS` | `50000` | Transcript truncation limit for LLM context |
