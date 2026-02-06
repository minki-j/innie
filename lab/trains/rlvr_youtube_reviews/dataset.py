from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class YouTubeReviewDatapoint:
    # identifiers
    example_id: str
    video_id: str
    video_url: str
    title: str

    # conditioning inputs
    persona_id: str
    persona_title: str
    persona_description: str
    summary: str
    transcript: str

    # RLVR target
    synthetic_user_feedback: str

    # optional metadata / cached fields
    transcript_path: str | None = None
    transcript_status: str | None = None
    feedback_embedding: list[float] | None = None
    feedback_embedding_ref: dict[str, Any] | None = None


def _resolve_path(base_dir: Path, path_str: str) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p
    return base_dir / p


def _load_f32_embedding(path: Path) -> list[float] | None:
    if not path.is_file():
        return None
    b = path.read_bytes()
    if len(b) % 4 != 0:
        return None
    n = len(b) // 4
    if n == 0:
        return None
    # NOTE: embeddings are small (e.g., 1536 floats), so unpacking is fine.
    try:
        return list(struct.unpack("<" + ("f" * n), b))
    except Exception:
        return None


def load_datapoints(
    jsonl_path: str,
    *,
    load_transcripts: bool = True,
    load_feedback_embeddings: bool = True,
) -> list[YouTubeReviewDatapoint]:
    path = Path(jsonl_path)
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    base_dir = path.resolve().parent

    out: list[YouTubeReviewDatapoint] = []
    for r in rows:
        if r.get("kind") != "datapoint":
            continue
        video = r.get("video") or {}
        persona = r.get("persona") or {}
        inp = r.get("input") or {}
        tgt = r.get("target") or {}

        video_id = str(video.get("video_id") or "")
        persona_id = str(persona.get("persona_id") or "")
        example_id = str(r.get("example_id") or f"{video_id}::{persona_id}")

        transcript_status: str | None = None
        transcript_path: str | None = None
        transcript: str = ""

        # Backward compat: older dataset stored transcript inline.
        if isinstance(inp.get("transcript"), str) and inp.get("transcript"):
            transcript = str(inp.get("transcript") or "")
            transcript_status = str(inp.get("transcript_status") or "") or None
        else:
            transcript_status = str(inp.get("transcript_status") or "") or None
            ref = inp.get("transcript_ref")
            ref_path: str | None = None
            if isinstance(ref, dict):
                p = ref.get("path")
                if isinstance(p, str) and p:
                    ref_path = p
            # Some manifests may still stash transcript_path directly.
            if ref_path is None and isinstance(inp.get("transcript_path"), str):
                ref_path = str(inp.get("transcript_path"))
            if ref_path is None:
                # Conventional location when dataset is next to `transcripts/`.
                ref_path = f"transcripts/{video_id}.txt"

            transcript_path = ref_path
            if load_transcripts:
                try:
                    transcript = _resolve_path(base_dir, ref_path).read_text(
                        encoding="utf-8"
                    )
                except Exception:
                    transcript = ""

        feedback_embedding: list[float] | None = None
        feedback_embedding_ref: dict[str, Any] | None = None

        ref = tgt.get("feedback_embedding_ref")
        if isinstance(ref, dict):
            feedback_embedding_ref = ref

        if load_feedback_embeddings and isinstance(ref, dict):
            emb_path = ref.get("embedding_path")
            if isinstance(emb_path, str) and emb_path:
                feedback_embedding = _load_f32_embedding(
                    _resolve_path(base_dir, emb_path)
                )

        synthetic_user_feedback = str(tgt.get("synthetic_user_feedback") or "")
        if not synthetic_user_feedback:
            ref = tgt.get("synthetic_user_feedback_ref")
            if isinstance(ref, dict):
                p = ref.get("path")
                if isinstance(p, str) and p:
                    try:
                        synthetic_user_feedback = _resolve_path(base_dir, p).read_text(
                            encoding="utf-8"
                        )
                    except Exception:
                        synthetic_user_feedback = ""

        out.append(
            YouTubeReviewDatapoint(
                example_id=example_id,
                video_id=video_id,
                video_url=str(video.get("video_url") or ""),
                title=str(video.get("title") or ""),
                persona_id=persona_id,
                persona_title=str(persona.get("title") or ""),
                persona_description=str(persona.get("description") or ""),
                summary=str(inp.get("summary") or ""),
                transcript=transcript,
                transcript_path=transcript_path,
                transcript_status=transcript_status,
                synthetic_user_feedback=synthetic_user_feedback,
                feedback_embedding=feedback_embedding,
                feedback_embedding_ref=feedback_embedding_ref,
            )
        )

    return out
