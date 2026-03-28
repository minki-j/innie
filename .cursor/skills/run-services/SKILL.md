---
name: run-services
description: Start all local development services for this project (Next.js app, orchestrator FastAPI server, Prefect server + flow, and LangGraph agents). Use when the user asks to run, start, or launch the app, services, orchestrator, agents, or the full dev environment.
---

# Run Services

## Agent automation vs your terminals

When this skill runs from **Cursor Chat / Agent**, it uses the **shell tool**. Those sessions are **agent-managed** (separate from terminals you open in the Terminal UI). To start services yourself, open a terminal per service and run the commands from the table below from the correct repo subdirectory.

## Services Overview

| Service | Command | URL |
|---|---|---|
| Application (Next.js) | `npm run dev` in `application/` | http://localhost:3000 |
| Orchestrator API (FastAPI) | `uv run server` in `orchestrator/` | http://127.0.0.1:8200 |
| Orchestrator Prefect | `uv run serve-local` in `orchestrator/` | http://127.0.0.1:4200 |
| Agents (LangGraph) | `uv run dev` in `agents/` | http://127.0.0.1:2024 |
| Redis | `docker start innie-redis` (or `docker run -d --name innie-redis -p 6380:6379 redis:7-alpine` on first run) | localhost:6380 |

## Startup Steps

1. Check running terminals to avoid duplicate processes before starting anything.

2. Start all five services in background (`block_until_ms: 0`).
   - For services that run inside a repo subdirectory, use the shell tool's `working_directory` parameter for that directory.
   - Do not run commands as `cd some/path && ...` unless there is no tool-supported alternative.
   - In user-facing responses, do not mention `cd` steps or narrate directory changes. Just report the service status and URLs.

3. Start the services:
   - **Redis**: `docker start innie-redis` (use `docker run -d --name innie-redis -p 6380:6379 redis:7-alpine` if the container doesn't exist yet)
   - **Application**: `npm run dev` in `application/`
   - **Orchestrator API**: `uv run server` in `orchestrator/`
   - **Orchestrator Prefect**: `uv run serve-local` in `orchestrator/` — this script starts both the Prefect server and serves the `video_pipeline` flow
   - **Agents**: `uv run dev` in `agents/`

4. Wait ~15 seconds, then read each terminal file to confirm healthy startup.

## Healthy Startup Signals

- **Redis**: `docker exec innie-redis redis-cli ping` returns `PONG`
- **Application**: `✓ Ready in` line present
- **Orchestrator API**: `Uvicorn running on http://127.0.0.1:8200`
- **Prefect**: `Your flow 'video_pipeline' is being served and polling for scheduled runs!`
- **Agents**: `Server started in` line present

## Notes

- The Prefect `serve-local` script (`orchestrator/scripts/serve_local.py`) spawns two subprocesses: `prefect server start` and `prefect flow serve`. SQLite "database is locked" warnings on startup are expected and non-fatal — the script already sets extended timeouts for this.

## Response Style

- Prefer a concise confirmation like:
  - `All five local services are up.`
  - A short flat list of URLs.
  - A short `I verified:` list of healthy signals.
  - An optional short note about expected Prefect SQLite lock warnings.
  - A brief optional offer to smoke-test or trigger the pipeline.
- Do not use a status table.
- Do not start with `Here is what was done:` or similar process narration.
- Do not dump raw command details unless the user explicitly asks for them.
