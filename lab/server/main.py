"""
FastAPI application for the lab training/inference server.
"""

from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.config import SERVER_HOST, SERVER_PORT

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Innie Lab Server",
    description="Training and inference server for innie models",
    version="0.1.0",
)

# CORS — allow Application and Orchestrator to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routes ──────────────────────────────────────────

from server.routes.training import router as training_router  # noqa: E402
from server.routes.inference import router as inference_router  # noqa: E402
from server.routes.models import router as models_router  # noqa: E402

app.include_router(training_router)
app.include_router(inference_router)
app.include_router(models_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    """Entry point for the lab-server script."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("Starting Innie Lab Server on %s:%d", SERVER_HOST, SERVER_PORT)
    uvicorn.run(
        "server.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
