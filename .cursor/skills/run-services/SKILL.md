---
name: run-services
description: Start all local development services for this project (Next.js app, orchestrator FastAPI server, Prefect server + flow, and LangGraph agents). Use when the user asks to run, start, or launch the app, services, orchestrator, agents, or the full dev environment.
---

# Run Services

## Services Overview

| Service | Command | URL |
|---|---|---|
| Application (Next.js) | `npm run dev` in `application/` | http://localhost:3000 |
| Orchestrator API (FastAPI) | `uv run uvicorn server:app --port 8200 --reload` in `orchestrator/` | http://127.0.0.1:8200 |
| Orchestrator Prefect | `uv run serve-local` in `orchestrator/` | http://127.0.0.1:4200 |
| Agents (LangGraph) | `uv run langgraph dev --no-browser` in `agents/` | http://127.0.0.1:2024 |

## Startup Steps

1. Check running terminals to avoid duplicate processes before starting anything.

2. Start all four services in background (block_until_ms: 0):
   - **Application**: `npm run dev` in `application/`
   - **Orchestrator API**: `uv run uvicorn server:app --port 8200 --reload` in `orchestrator/`
   - **Orchestrator Prefect**: `uv run serve-local` in `orchestrator/` — this script starts both the Prefect server and serves the `video_pipeline` flow
   - **Agents**: `uv run langgraph dev --no-browser` in `agents/`

3. Wait ~15 seconds, then read each terminal file to confirm healthy startup.

## Healthy Startup Signals

- **Application**: `✓ Ready in` line present
- **Orchestrator API**: `Uvicorn running on http://127.0.0.1:8200`
- **Prefect**: `Your flow 'video_pipeline' is being served and polling for scheduled runs!`
- **Agents**: `Server started in` line present

## Notes

- The Prefect `serve-local` script (`orchestrator/scripts/serve_local.py`) spawns two subprocesses: `prefect server start` and `prefect flow serve`. SQLite "database is locked" warnings on startup are expected and non-fatal — the script already sets extended timeouts for this.
- LangGraph Studio UI is available at https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
- Trigger the Prefect pipeline manually: `prefect deployment run 'video_pipeline/video-pipeline'`
