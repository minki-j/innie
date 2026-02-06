# lab

Python scripts and experiments for the **innie** project: LLM fine-tuning (SFT and RLVR) for per-topic review generation, plus a FastAPI server that the Application and Orchestrator use to trigger training and run inference.

## Running the server

The lab exposes a FastAPI server for training and inference. From the **lab** directory:

```bash
uv run lab-server
```

Or with uvicorn directly:

```bash
uv run uvicorn server.main:app --host 0.0.0.0 --port 8100
```

The server listens on `0.0.0.0:8100` by default. Override with env vars:

- `LAB_SERVER_HOST` (default: `0.0.0.0`)
- `LAB_SERVER_PORT` (default: `8100`)

### Environment

The server loads env from (in order, later overrides earlier):

1. Repo root `.env`
2. `application/.env` (e.g. `POSTGRES_URL` / `POSTGRES_PRISMA_URL`)
3. `lab/.env`

Required for the server:

- **Database**: `POSTGRES_URL` or `POSTGRES_PRISMA_URL` (same Postgres as the app)
- **Tinker**: `TINKER_API_KEY` (for training and inference)
- **OpenAI** (for embeddings in RLVR): `OPENAI_API_KEY`

Optional: `MIN_REVIEWS_FOR_TRAINING` (default: 5), `DEFAULT_BASE_MODEL`, `DEFAULT_BASE_MODEL`.

### API overview

| Method | Path | Description |
|--------|------|-------------|
| POST | `/training/start` | Start a training run (userId, topicId, method: SFT \| RLVR). Called by the Application. |
| GET | `/training/{id}` | Get training run status. |
| POST | `/inference` | Generate a review (by `modelName` or `topicId` + `method`). Called by Application and Orchestrator. |
| GET | `/models` | List completed models (optional `userId`, `topicId` query params). |
| GET | `/health` | Health check. |

Training runs in the background; when it finishes, the server POSTs a webhook to the URL you pass in `webhookUrl` (e.g. the Application’s `/api/webhooks/training`).

## CLI training (local / prototype)

You can still run training from the command line with local JSONL datasets:

```bash
# SFT
uv run youtube-reviews-sft-train --jsonl-path lab/datasets/ai_dot_engineer/dataset_train.jsonl

# RLVR
uv run youtube-reviews-rlvr-train --jsonl-path lab/datasets/ai_dot_engineer/dataset_train.jsonl
```

Other entry points: `fetch-video-metadata`, `generate-synthetic-feedback`, `tinker-checkpoints-rm`.

## Project layout

- **`server/`** — FastAPI app, routes, DB access, background training task.
- **`trains/`** — SFT and RLVR training scripts (used by the server and by CLI).
- **`datasets/`** — Dataset builders and sample data (e.g. `ai_dot_engineer`).
- **`utils/`** — Helpers (fs, tokens, preview, checkpoint tools).
