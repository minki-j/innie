"""
Inference task for calling the lab server's trained models.

Allows the orchestrator pipeline to generate reviews using
innie models trained for specific topics.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from prefect import task

logger = logging.getLogger(__name__)

LAB_SERVER_URL = os.environ.get("LAB_SERVER_URL")


@task(name="generate_innie_review", retries=2, retry_delay_seconds=10)
def generate_innie_review(
    *,
    transcript: str,
    topic_id: str,
    method: str = "SFT",
    video_title: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any] | None:
    """
    Generate a review using a trained innie model via the lab server.

    Can be called with either:
    - topic_id + method (uses the active model for that topic)
    - model_name (uses a specific trained model)

    Returns the inference response dict or None if the request fails.
    """
    payload: dict[str, Any] = {"transcript": transcript}

    if model_name:
        payload["modelName"] = model_name
    else:
        payload["topicId"] = topic_id
        payload["method"] = method

    if video_title:
        payload["videoTitle"] = video_title

    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{LAB_SERVER_URL}/inference", json=payload)
            resp.raise_for_status()
            result = resp.json()
            logger.info(
                "Inference succeeded model=%s topic=%s",
                result.get("modelName"),
                topic_id,
            )
            return result
    except httpx.HTTPStatusError as e:
        logger.warning(
            "Inference request failed status=%d detail=%s",
            e.response.status_code,
            e.response.text,
        )
        return None
    except Exception:
        logger.exception("Inference request failed for topic %s", topic_id)
        return None


@task(name="check_innie_model_available")
def check_innie_model_available(topic_id: str, method: str = "SFT") -> bool:
    """Check if an active innie model exists for a topic."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{LAB_SERVER_URL}/models",
                params={"topicId": topic_id},
            )
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            return any(m.get("method") == method and m.get("isActive") for m in models)
    except Exception:
        logger.exception("Failed to check model availability for topic %s", topic_id)
        return False
