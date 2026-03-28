"""
Lightweight FastAPI server for triggering orchestrator pipelines locally.

Run with:  uv run uvicorn server:app --port 8200
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from flows.idea_graph import generate_idea_graph_for_video
from flows.video_pipeline import re_evaluate_videos, retry_failed_jobs, video_pipeline

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


@app.post("/trigger/{funnel_id}")
async def trigger_pipeline(funnel_id: str):
    """Trigger the video pipeline for a specific funnel."""
    logger.info("Received trigger request for funnel_id=%s", funnel_id)
    try:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            _executor,
            lambda: video_pipeline(funnel_id=funnel_id),
        )
        return {
            "status": "triggered",
            "funnel_id": funnel_id,
            "message": "Pipeline run started in background",
        }
    except Exception as e:
        logger.exception("Failed to trigger pipeline for funnel %s", funnel_id)
        raise HTTPException(status_code=500, detail=str(e))


class ReEvaluateRequest(BaseModel):
    video_ids: list[str]


@app.post("/re-evaluate/{funnel_id}")
async def re_evaluate(funnel_id: str, body: ReEvaluateRequest):
    """Re-evaluate selected videos against a funnel's current ClassNodes."""
    logger.info(
        "Received re-evaluate request for funnel_id=%s, %d videos",
        funnel_id,
        len(body.video_ids),
    )
    if not body.video_ids:
        raise HTTPException(status_code=400, detail="video_ids must not be empty")

    try:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            _executor,
            lambda: re_evaluate_videos(funnel_id=funnel_id, video_ids=body.video_ids),
        )
        return {
            "status": "triggered",
            "funnel_id": funnel_id,
            "video_count": len(body.video_ids),
            "message": "Re-evaluation started in background",
        }
    except Exception as e:
        logger.exception("Failed to start re-evaluation for funnel %s", funnel_id)
        raise HTTPException(status_code=500, detail=str(e))


class RetryFailedJobsRequest(BaseModel):
    queue_names: list[str] | None = None


@app.post("/retry-failed")
async def retry_failed(body: RetryFailedJobsRequest | None = None):
    """Drain dead-letter queues and re-process all failed jobs."""
    queue_names = (body.queue_names if body else None) or None
    logger.info("Received retry-failed request (queues=%s)", queue_names)
    try:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            _executor,
            lambda: retry_failed_jobs(queue_names=queue_names),
        )
        return {
            "status": "triggered",
            "queues": queue_names
            or [
                "process_video_for_funnel",
                "evaluate_class_node",
                "langgraph_classify",
            ],
            "message": "Retry run started in background",
        }
    except Exception as e:
        logger.exception("Failed to start retry-failed jobs")
        raise HTTPException(status_code=500, detail=str(e))


class GenerateIdeaGraphRequest(BaseModel):
    user_id: str
    video_id: str
    replace_existing: bool = True


@app.post("/idea-graphs/generate")
async def generate_idea_graph(body: GenerateIdeaGraphRequest):
    """Generate an idea graph for a user/video pair in the background."""
    logger.info(
        "Received idea-graph generation request for user_id=%s video_id=%s",
        body.user_id,
        body.video_id,
    )

    try:
        # `generate_idea_graph_for_video` is synchronous and can take a while,
        # so hand it off to the shared thread pool instead of blocking FastAPI's
        # async event loop. We intentionally do not await this future: the API
        # returns immediately after the background job has been scheduled.

        # TODO: This will be replaced with more async version
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            _executor,
            lambda: generate_idea_graph_for_video(
                user_id=body.user_id,
                video_id=body.video_id,
                replace_existing=body.replace_existing,
            ),
        )
        return {
            "status": "triggered",
            "user_id": body.user_id,
            "video_id": body.video_id,
            "message": "Idea graph generation started in background",
        }
    except Exception as e:
        logger.exception(
            "Failed to start idea graph generation for user %s video %s",
            body.user_id,
            body.video_id,
        )
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8200)
