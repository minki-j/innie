# Orchestrator

Prefect pipeline that polls the database for active topics, scrapes YouTube videos, and evaluates them against topic criteria using LLMs.

## Setup

```bash
cd orchestrator
uv sync
```

## Commands

**Run the pipeline directly (no Prefect server needed):**

```bash
uv run pipeline
```

**Local Prefect server + flow (all-in-one script):**

```bash
uv run serve-local
```

This starts the Prefect server at `http://127.0.0.1:4200`, waits for it to be ready, then serves `video_pipeline` as a deployment. Both processes shut down together on Ctrl+C.

Make sure `application/.env` has these for the Next.js app to trigger it:

```
PREFECT_API_URL=http://127.0.0.1:4200/api
PREFECT_API_KEY=ignore
```

> **Note:** If your shell is logged into Prefect Cloud, always set `PREFECT_API_URL=http://127.0.0.1:4200/api` before running any `prefect` commands, otherwise the CLI will hit Prefect Cloud instead of the local server.

**Deploy flows to Prefect Cloud:**

```bash
uv run prefect deploy --all
```

**Sync dependencies and env vars to the Prefect Cloud deployment:**

```bash
uv run sync-prefect
```

Run this after deploying to push pip packages (from `pyproject.toml`) and environment variables (from `.env` files) to the managed work pool as `job_variables`.

**Regenerate Pydantic models from Prisma schema:**

```bash
uv run generate-models
```

Run this after any changes to `application/prisma/schema.prisma` to keep the Python models in sync.

**Generate flow diagram:**

```bash
uv run generate_flow_diagram --flow {flow_name}
```

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
