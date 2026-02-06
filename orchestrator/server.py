"""
Lightweight FastAPI server for triggering orchestrator pipelines on demand.

Run with:  uv run uvicorn server:app --port 8200
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from flows.video_pipeline import re_evaluate_videos, video_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Orchestrator Trigger API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for running Prefect flows (which are synchronous)
_executor = ThreadPoolExecutor(max_workers=2)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/trigger/{topic_id}")
async def trigger_pipeline(topic_id: str):
    """Trigger the video pipeline for a specific topic."""
    logger.info("Received trigger request for topic_id=%s", topic_id)
    try:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            _executor,
            lambda: video_pipeline(topic_id=topic_id),
        )
        return {
            "status": "triggered",
            "topic_id": topic_id,
            "message": "Pipeline run started in background",
        }
    except Exception as e:
        logger.exception("Failed to trigger pipeline for topic %s", topic_id)
        raise HTTPException(status_code=500, detail=str(e))


class ReEvaluateRequest(BaseModel):
    video_ids: list[str]


@app.post("/re-evaluate/{topic_id}")
async def re_evaluate(topic_id: str, body: ReEvaluateRequest):
    """Re-evaluate selected videos against a topic's current criteria."""
    logger.info(
        "Received re-evaluate request for topic_id=%s, %d videos",
        topic_id,
        len(body.video_ids),
    )
    if not body.video_ids:
        raise HTTPException(status_code=400, detail="video_ids must not be empty")

    try:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            _executor,
            lambda: re_evaluate_videos(topic_id=topic_id, video_ids=body.video_ids),
        )
        return {
            "status": "triggered",
            "topic_id": topic_id,
            "video_count": len(body.video_ids),
            "message": "Re-evaluation started in background",
        }
    except Exception as e:
        logger.exception("Failed to start re-evaluation for topic %s", topic_id)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8200)
