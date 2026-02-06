"""
Generate synthetic reviews for all videos in a topic using an LLM persona.

Fetches every video linked to a given topic, asks an LLM to write a review
from a configurable user persona, and inserts the results into the Review table.

Usage:
    uv run python scripts/generate_synthetic_reviews.py
    uv run python scripts/generate_synthetic_reviews.py --topic <TOPIC_ID> --model gpt-4o-mini --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

import psycopg2.extras
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

# ── project imports (orchestrator root is on sys.path via uv run) ──
from config import DATABASE_URL, TRANSCRIPT_MAX_CHARS
from tasks.db import _generate_cuid, get_connection
from tasks.evaluate import _get_llm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── Default values ────────────────────────────────────────────

DEFAULT_TOPIC_ID = "cmlbif7sp0005v6ubu2tq2i0w"

DEFAULT_PERSONA = (
    "Imagine you are a GenZ software engineer who is interested in cool technology "
    "but also very politically correct. You write feedback colloquially using emojis generously."
)


# ── Structured output schema ─────────────────────────────────


class SyntheticReview(BaseModel):
    """Structured output from the LLM for a synthetic review."""

    rating: int = Field(
        description="A rating from 1 to 5, where 1 is terrible and 5 is amazing.",
        ge=1,
        le=5,
    )
    content: str = Field(
        description=(
            "A short review (2-5 sentences) of the video written in the voice "
            "of the user persona."
        ),
    )


# ── Prompt ────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are role-playing as a specific user persona to write a video review.

## Persona
{persona}

## Instructions
- Write an authentic, in-character review of the video below.
- Provide a rating from 1 (terrible) to 5 (amazing).
- Keep the review short (2-5 sentences).
- Stay in character — match the tone, vocabulary, and style described in the persona.
- Base your review on the video information provided.\
"""

HUMAN_PROMPT = """\
## Video Information

**Title:** {title}

**Channel:** {channel}

**Description:**
{description}

**Summary:**
{summary}

**Transcript (excerpt):**
{transcript}

---

Write your review of this video.\
"""

REVIEW_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", HUMAN_PROMPT),
    ]
)


# ── Core logic ────────────────────────────────────────────────


def fetch_topic_videos(topic_id: str) -> list[dict]:
    """Return all videos linked to the topic, with basic metadata."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT v.id, v.title, v.description, v."channelTitle",
                       v.transcript, v.summary
                FROM "Video" v
                JOIN "_TopicToVideo" tv ON tv."B" = v.id
                WHERE tv."A" = %s
                ORDER BY v."publishedAt" DESC
                """,
                (topic_id,),
            )
            return cur.fetchall()


def fetch_existing_review_video_ids(topic_id: str, user_id: str) -> set[str]:
    """Return video IDs that already have a review from this user in this topic."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT "videoId" FROM "Review"
                WHERE "topicId" = %s AND "userId" = %s
                """,
                (topic_id, user_id),
            )
            return {row[0] for row in cur.fetchall()}


def get_topic_user_id(topic_id: str) -> str | None:
    """Return the userId that owns the given topic."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "userId" FROM "Topic" WHERE id = %s',
                (topic_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None


def generate_review(
    video: dict,
    persona: str,
    model_name: str | None = None,
) -> SyntheticReview:
    """Use an LLM to generate a synthetic review for a single video."""
    llm, used_model = _get_llm(model_name)

    transcript_text = video.get("transcript") or "(No transcript available)"
    if len(transcript_text) > TRANSCRIPT_MAX_CHARS:
        transcript_text = (
            transcript_text[:TRANSCRIPT_MAX_CHARS]
            + "\n\n... [transcript truncated] ..."
        )

    chain = (
        REVIEW_PROMPT | llm.with_structured_output(SyntheticReview)
    ).with_config(run_name="synthetic_review_chain")

    result: SyntheticReview = chain.invoke(
        {
            "persona": persona,
            "title": video.get("title", ""),
            "channel": video.get("channelTitle", ""),
            "description": (video.get("description") or "")[:2000],
            "summary": video.get("summary") or "(No summary available)",
            "transcript": transcript_text,
        },
    )
    return result


def save_review(
    video_id: str,
    topic_id: str,
    user_id: str,
    rating: int,
    content: str,
) -> str:
    """Insert a review row and return its ID."""
    review_id = _generate_cuid()
    now = datetime.now(timezone.utc)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "Review" (id, "userId", "videoId", "topicId",
                                      rating, content, "createdAt", "updatedAt")
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ("userId", "videoId", "topicId") DO UPDATE SET
                    rating = EXCLUDED.rating,
                    content = EXCLUDED.content,
                    "updatedAt" = EXCLUDED."updatedAt"
                """,
                (review_id, user_id, video_id, topic_id, rating, content, now, now),
            )
            conn.commit()
    return review_id


# ── CLI ───────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic LLM reviews for videos in a topic.",
    )
    parser.add_argument(
        "--topic",
        default=DEFAULT_TOPIC_ID,
        help=f"Topic ID to process (default: {DEFAULT_TOPIC_ID})",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model name (default: from DEFAULT_LLM_MODEL env var)",
    )
    parser.add_argument(
        "--persona",
        default=DEFAULT_PERSONA,
        help="User persona prompt for the LLM",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate reviews but don't write to DB",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip videos that already have a review from this user (default: True)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_false",
        dest="skip_existing",
        help="Overwrite existing reviews",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    topic_id: str = args.topic
    persona: str = args.persona
    model_name: str | None = args.model
    dry_run: bool = args.dry_run

    # Resolve the user who owns the topic
    user_id = get_topic_user_id(topic_id)
    if not user_id:
        logger.error("Topic %s not found — aborting.", topic_id)
        sys.exit(1)

    logger.info("Topic:   %s", topic_id)
    logger.info("User:    %s", user_id)
    logger.info("Model:   %s", model_name or "(default)")
    logger.info("Dry run: %s", dry_run)

    # Fetch all videos in the topic
    videos = fetch_topic_videos(topic_id)
    logger.info("Found %d videos in topic.", len(videos))

    if not videos:
        logger.warning("No videos found — nothing to do.")
        return

    # Optionally skip videos that already have reviews
    if args.skip_existing:
        existing = fetch_existing_review_video_ids(topic_id, user_id)
        before = len(videos)
        videos = [v for v in videos if v["id"] not in existing]
        skipped = before - len(videos)
        if skipped:
            logger.info("Skipping %d videos that already have reviews.", skipped)

    logger.info("Generating reviews for %d videos...\n", len(videos))

    success = 0
    failed = 0

    for i, video in enumerate(videos, 1):
        vid_id = video["id"]
        title = video.get("title", "(untitled)")
        logger.info("[%d/%d] %s  —  %s", i, len(videos), vid_id, title)

        try:
            review = generate_review(video, persona, model_name)
            logger.info("  ⭐ %d/5  |  %s", review.rating, review.content[:120])

            if not dry_run:
                rid = save_review(vid_id, topic_id, user_id, review.rating, review.content)
                logger.info("  → saved review %s", rid)
            else:
                logger.info("  → dry-run, not saved")

            success += 1

        except Exception:
            logger.exception("  ✗ failed to generate review for %s", vid_id)
            failed += 1

    logger.info(
        "\nDone. %d succeeded, %d failed out of %d videos.",
        success,
        failed,
        len(videos),
    )


if __name__ == "__main__":
    main()
