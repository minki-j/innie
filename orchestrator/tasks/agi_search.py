"""
AGI-powered YouTube video discovery.

Uses AGI, Inc.'s REST API to intelligently search YouTube for videos
matching a topic's full context (description, criteria, gold standards,
and keywords).

API docs: https://docs.agi.tech
"""

from __future__ import annotations

import json
import logging
import re
import time

import httpx
from prefect import task

from config import AGI_API_KEY, AGI_AGENT_MODEL, MAX_VIDEOS_PER_AGI_SEARCH
from models.schemas import Topic

logger = logging.getLogger(__name__)

AGI_BASE_URL = "https://api.agi.tech/v1"
AGI_POLL_INTERVAL_SECONDS = 3
AGI_TIMEOUT_SECONDS = 900  # 15 minutes max wait


# ── Prompt builder ────────────────────────────────────────────


def _build_search_prompt(topic: Topic, max_results: int) -> str:
    """
    Build a natural-language prompt for the AGI agent that incorporates
    the topic's full context: description, keywords, criteria, and
    gold standard examples.
    """
    sections: list[str] = []

    # Header
    sections.append(
        f"Search YouTube for up to {max_results} videos about the topic: "
        f'"{topic.name}".'
    )

    # Topic description
    if topic.description:
        sections.append(f"Topic description: {topic.description}")

    # Keywords
    if topic.keywords:
        kw_list = ", ".join(kw.keyword for kw in topic.keywords)
        sections.append(f"Relevant keywords to consider when searching: {kw_list}")

    # Criteria
    if topic.criteria:
        criteria_lines = []
        for c in topic.criteria:
            kind = "INCLUDE" if c.include else "EXCLUDE"
            criteria_lines.append(f"  - [{kind} / {c.level}] {c.condition}")
        sections.append(
            "The ideal videos should meet these criteria:\n" + "\n".join(criteria_lines)
        )

    # Gold standards with enriched context
    if topic.gold_standards:
        gs_blocks = []
        for gs in topic.gold_standards:
            label = "GOOD example" if gs.is_positive else "BAD example"
            title = f" ({gs.title})" if gs.title else ""
            header = f"  - {label}: {gs.video_url}{title}"

            details = []
            if gs.note:
                details.append(f"    Note: {gs.note}")
            if gs.video_summary:
                details.append(f"    Video summary: {gs.video_summary}")
            elif gs.video_description:
                # Fall back to YouTube description if no summary exists
                desc = gs.video_description
                if len(desc) > 500:
                    desc = desc[:500] + "..."
                details.append(f"    Video description: {desc}")
            if gs.review_content:
                details.append(f"    User review: {gs.review_content}")

            gs_blocks.append(header + ("\n" + "\n".join(details) if details else ""))

        sections.append(
            "Here are examples of the kind of videos we are looking for "
            "(and not looking for). Use these examples to understand what "
            "makes a video relevant or irrelevant, and find similar ones:\n"
            + "\n".join(gs_blocks)
        )

    # Output instructions
    sections.append(
        "Search YouTube thoroughly using different search queries derived "
        "from the topic context above. Try multiple searches to get diverse results.\n\n"
        "Return ONLY a JSON array of YouTube video URLs. Example:\n"
        '["https://www.youtube.com/watch?v=abc123", "https://www.youtube.com/watch?v=def456"]\n\n'
        "Do not include any other text, only the JSON array."
    )

    return "\n\n".join(sections)


# ── AGI REST API client ──────────────────────────────────────


def _agi_run_task(prompt: str, agent_model: str, api_key: str) -> str:
    """
    Execute a task via AGI, Inc.'s REST API:
      1. Create a session
      2. Send a message (the task prompt)
      3. Poll until status is 'finished'
      4. Retrieve the DONE message
      5. Delete the session

    Returns the agent's final response text.
    """
    headers = {"Authorization": f"Bearer {api_key}"}

    with httpx.Client(base_url=AGI_BASE_URL, timeout=60) as client:
        # 1. Create session
        resp = client.post(
            "/sessions",
            headers=headers,
            json={"agent_name": agent_model},
        )
        resp.raise_for_status()
        session_id = resp.json()["session_id"]
        logger.info("AGI session created: %s", session_id)

        try:
            # 2. Send task message
            resp = client.post(
                f"/sessions/{session_id}/message",
                headers=headers,
                json={"message": prompt},
            )
            resp.raise_for_status()

            # 3. Poll for completion
            elapsed = 0.0
            while elapsed < AGI_TIMEOUT_SECONDS:
                time.sleep(AGI_POLL_INTERVAL_SECONDS)
                elapsed += AGI_POLL_INTERVAL_SECONDS

                resp = client.get(
                    f"/sessions/{session_id}/status",
                    headers=headers,
                )
                resp.raise_for_status()
                status = resp.json().get("status", "")
                logger.debug(
                    "AGI session %s status: %s (%.0fs)", session_id, status, elapsed
                )

                if status == "finished":
                    break
            else:
                logger.warning(
                    "AGI session %s timed out after %ds",
                    session_id,
                    AGI_TIMEOUT_SECONDS,
                )
                return ""

            # 4. Get result messages
            resp = client.get(
                f"/sessions/{session_id}/messages",
                headers=headers,
            )
            resp.raise_for_status()
            messages = resp.json().get("messages", [])

            # Find the DONE message with the final result
            for msg in messages:
                if msg.get("type") == "DONE":
                    return msg.get("content", "") or msg.get("text", "")

            # Fallback: return the last message content
            if messages:
                last = messages[-1]
                return last.get("content", "") or last.get("text", "")

            return ""

        finally:
            # 5. Always clean up the session
            try:
                client.delete(f"/sessions/{session_id}", headers=headers)
                logger.info("AGI session deleted: %s", session_id)
            except Exception:
                logger.warning("Failed to delete AGI session: %s", session_id)


# ── Video ID extraction ──────────────────────────────────────


_YT_VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)"
    r"([a-zA-Z0-9_-]{11})"
)

_BARE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")


def _extract_video_ids(raw_response: str) -> list[str]:
    """
    Parse the AGI agent's response to extract YouTube video IDs.
    Handles JSON arrays of URLs, plain lists of URLs, or bare video IDs.
    """
    video_ids: list[str] = []
    seen: set[str] = set()

    # Try parsing as JSON first
    try:
        parsed = json.loads(raw_response.strip())
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict) and "urls" in parsed:
            items = parsed["urls"]
        else:
            items = []
    except (json.JSONDecodeError, ValueError):
        # Fall back to line-by-line parsing
        items = raw_response.strip().splitlines()

    for item in items:
        text = str(item).strip().strip('"').strip("'").strip(",")
        if not text:
            continue

        # Try extracting video ID from URL
        match = _YT_VIDEO_ID_RE.search(text)
        if match:
            vid_id = match.group(1)
            if vid_id not in seen:
                seen.add(vid_id)
                video_ids.append(vid_id)
            continue

        # Check if it's a bare video ID
        if _BARE_ID_RE.match(text) and text not in seen:
            seen.add(text)
            video_ids.append(text)

    return video_ids


# ── Prefect task ──────────────────────────────────────────────


@task(name="search_videos_with_agi", retries=1, retry_delay_seconds=30)
def search_videos_with_agi(
    topic: Topic,
    max_results: int | None = None,
) -> list[str]:
    """
    Use AGI, Inc.'s web-browsing agent to intelligently search YouTube
    for videos matching a topic's full context.

    Returns a list of video IDs discovered by the agent.
    Returns an empty list if AGI_API_KEY is not configured or on failure.
    """
    if not AGI_API_KEY:
        logger.info("AGI_API_KEY not configured, skipping AGI search")
        return []

    if max_results is None:
        max_results = MAX_VIDEOS_PER_AGI_SEARCH

    prompt = _build_search_prompt(topic, max_results)
    logger.info(
        "Starting AGI search for topic '%s' (max %d videos)",
        topic.name,
        max_results,
    )

    try:
        result = _agi_run_task(prompt, AGI_AGENT_MODEL, AGI_API_KEY)
        logger.debug("AGI raw response for topic '%s': %s", topic.name, result)

        video_ids = _extract_video_ids(result)
        logger.info(
            "AGI search for topic '%s': found %d videos",
            topic.name,
            len(video_ids),
        )
        return video_ids

    except Exception:
        logger.exception("AGI search failed for topic '%s'", topic.name)
        return []
