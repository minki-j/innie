"""
Lightweight FastAPI server for triggering orchestrator pipelines locally.

Run with:  uv run server
"""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from pydantic import BaseModel

from config import IDEA_GRAPH_STREAM_POLL_INTERVAL_MS
from flows.idea_graph import (
    IdeaGraphGenerationFailure,
    generate_idea_graph_for_video,
)
from flows.video_pipeline import re_evaluate_videos, retry_failed_jobs, video_pipeline
from models.schemas import (
    ActiveIdeaGraphGenerationResponse,
    IdeaGraphGenerationStartResponse,
    IdeaGraphGenerationStatus,
    IdeaGraphStreamEvent,
)
from utils.idea_graph_events import get_idea_graph_event_store

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


def _submit_background(
    loop: asyncio.AbstractEventLoop,
    *,
    description: str,
    fn,
) -> asyncio.Future:
    future = loop.run_in_executor(_executor, fn)

    # Fire-and-forget jobs still need their exception observed, otherwise
    # asyncio logs "Future exception was never retrieved" after failures.
    def _log_background_result(completed_future: asyncio.Future) -> None:
        try:
            completed_future.result()
        except asyncio.CancelledError:
            logger.info("Background job cancelled: %s", description)
        except IdeaGraphGenerationFailure as exc:
            logger.warning("Background job failed: %s: %s", description, exc)
        except Exception:
            logger.exception("Background job failed: %s", description)

    future.add_done_callback(_log_background_result)
    return future


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/trigger/{funnel_id}")
async def trigger_pipeline(funnel_id: str):
    """Trigger the video pipeline for a specific funnel."""
    logger.info("Received trigger request for funnel_id=%s", funnel_id)
    try:
        loop = asyncio.get_running_loop()
        _submit_background(
            loop,
            description=f"video pipeline funnel={funnel_id}",
            fn=lambda: video_pipeline(funnel_id=funnel_id),
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
        loop = asyncio.get_running_loop()
        _submit_background(
            loop,
            description=f"re-evaluate funnel={funnel_id} video_count={len(body.video_ids)}",
            fn=lambda: re_evaluate_videos(
                funnel_id=funnel_id,
                video_ids=body.video_ids,
            ),
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
        loop = asyncio.get_running_loop()
        _submit_background(
            loop,
            description=f"retry failed queues={queue_names or 'default'}",
            fn=lambda: retry_failed_jobs(queue_names=queue_names),
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
    graph_id: str
    user_id: str
    video_id: str


def _format_sse(event: IdeaGraphStreamEvent) -> str:
    return (
        f"id: {event.event_id}\n"
        f"event: {event.type}\n"
        f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"
    )


@app.post("/idea-graphs/generate")
async def generate_idea_graph(body: GenerateIdeaGraphRequest):
    """Generate an idea graph for a user/video pair in the background."""
    logger.info(
        "Received idea-graph generation request for user_id=%s video_id=%s",
        body.user_id,
        body.video_id,
    )

    try:
        event_store = get_idea_graph_event_store()
        active_generation = event_store.get_active_generation(
            user_id=body.user_id,
            video_id=body.video_id,
        )
        if active_generation is not None:
            return IdeaGraphGenerationStartResponse(
                generation_id=active_generation.generation_id,
                graph_id=active_generation.graph_id,
                user_id=active_generation.user_id,
                video_id=active_generation.video_id,
                status=active_generation.status,
            ).model_dump(mode="json")

        generation_id = uuid4().hex
        metadata = event_store.create_generation(
            generation_id=generation_id,
            graph_id=body.graph_id,
            user_id=body.user_id,
            video_id=body.video_id,
        )

        loop = asyncio.get_running_loop()
        _submit_background(
            loop,
            description=f"idea graph generation id={generation_id} video={body.video_id}",
            fn=lambda: generate_idea_graph_for_video(
                generation_id=generation_id,
                graph_id=body.graph_id,
                user_id=body.user_id,
                video_id=body.video_id,
            ),
        )
        return IdeaGraphGenerationStartResponse(
            generation_id=generation_id,
            graph_id=metadata.graph_id,
            user_id=metadata.user_id,
            video_id=metadata.video_id,
            status=metadata.status,
        ).model_dump(mode="json")
    except Exception as e:
        logger.exception(
            "Failed to start idea graph generation for user %s video %s",
            body.user_id,
            body.video_id,
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/idea-graphs/generations/active")
async def get_active_idea_graph_generation(
    user_id: str = Query(...),
    video_id: str = Query(...),
):
    metadata = get_idea_graph_event_store().get_active_generation(
        user_id=user_id,
        video_id=video_id,
    )
    return ActiveIdeaGraphGenerationResponse(
        active=metadata is not None,
        generation=metadata,
    ).model_dump(mode="json")


@app.get("/idea-graphs/generations/{generation_id}/events")
async def stream_idea_graph_generation_events(
    generation_id: str,
    request: Request,
    after_event_id: int | None = Query(default=None, ge=0),
):
    event_store = get_idea_graph_event_store()
    metadata = event_store.get_generation(generation_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Idea graph generation not found")

    header_event_id = request.headers.get("last-event-id")
    cursor = (
        after_event_id if after_event_id is not None else int(header_event_id or "0")
    )
    poll_interval = max(0.1, IDEA_GRAPH_STREAM_POLL_INTERVAL_MS / 1000)

    async def event_stream():
        nonlocal cursor
        heartbeat_ticks = 0
        while True:
            if await request.is_disconnected():
                return

            events = event_store.list_events_after(generation_id, after_event_id=cursor)
            if events:
                heartbeat_ticks = 0
                for event in events:
                    cursor = event.event_id
                    yield _format_sse(event)
                metadata = event_store.get_generation(generation_id)
                if metadata is None:
                    return
                if (
                    metadata.status != IdeaGraphGenerationStatus.GENERATING
                    and cursor >= metadata.last_event_id
                ):
                    return
                continue

            metadata = event_store.get_generation(generation_id)
            if metadata is None:
                return
            if (
                metadata.status != IdeaGraphGenerationStatus.GENERATING
                and cursor >= metadata.last_event_id
            ):
                return

            heartbeat_ticks += 1
            if heartbeat_ticks >= int(15 / poll_interval):
                heartbeat_ticks = 0
                yield ": keep-alive\n\n"
            await asyncio.sleep(poll_interval)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        reload=True,
        port=8200,
        exclude=["**/__pycache__/**", "**/*.pyc"],
    )
