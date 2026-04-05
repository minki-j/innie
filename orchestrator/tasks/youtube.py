"""
YouTube scraping tasks using yt-dlp and youtube-transcript-api.

Patterns adapted from lab/datasets/ai_dot_engineer/ scripts.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from html import unescape
from typing import Any

import httpx

from prefect import task
from prefect.states import State

from config import MAX_VIDEOS_PER_CREATOR, MAX_VIDEOS_PER_KEYWORD, YOUTUBE_API_KEY
from models.schemas import VideoData
from utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


def _should_retry_youtube(task, task_run, state: State) -> bool:
    """Retry only on transient network/download errors, not permanent failures."""
    exc = state.result(raise_on_failure=False)
    transient = (
        ConnectionError,
        TimeoutError,
        OSError,
    )
    try:
        import yt_dlp  # type: ignore

        transient = transient + (yt_dlp.utils.DownloadError,)
    except ImportError:
        pass
    return isinstance(exc, transient)


# ── yt-dlp helpers ────────────────────────────────────────────


def _get_yt_dlp():
    import yt_dlp  # type: ignore

    return yt_dlp


def _parse_upload_date(date_str: str | None) -> datetime | None:
    """Parse YYYYMMDD date string from yt-dlp into a datetime."""
    if not date_str or len(date_str) < 8:
        return None
    try:
        return datetime.strptime(date_str[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _to_rfc3339(dt: datetime | None) -> str | None:
    """Format a datetime for the YouTube Data API."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _search_videos_by_keyword_google_api(
    keyword: str,
    max_results: int,
    published_after: datetime | None = None,
    published_before: datetime | None = None,
) -> list[str]:
    """
    Search YouTube via the Google YouTube Data API.

    This path supports true server-side filtering by publication timestamp.
    """
    video_ids: list[str] = []
    seen_ids: set[str] = set()
    next_page_token: str | None = None

    with httpx.Client(timeout=30.0) as client:
        while len(video_ids) < max_results:
            get_rate_limiter("youtube").acquire()

            params = {
                "part": "snippet",
                "type": "video",
                "q": keyword,
                "maxResults": min(50, max_results - len(video_ids)),
                "order": "date",
                "key": YOUTUBE_API_KEY,
            }
            if next_page_token:
                params["pageToken"] = next_page_token
            if published_after:
                params["publishedAfter"] = _to_rfc3339(published_after)
            if published_before:
                params["publishedBefore"] = _to_rfc3339(published_before)

            response = client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

            items = payload.get("items") or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("id") or {}
                if not isinstance(item_id, dict):
                    continue
                video_id = item_id.get("videoId")
                if not video_id or video_id in seen_ids:
                    continue
                seen_ids.add(video_id)
                video_ids.append(str(video_id))
                if len(video_ids) >= max_results:
                    break

            next_page_token = payload.get("nextPageToken")
            if not next_page_token or not items:
                break

    return video_ids


def _search_videos_by_keyword_yt_dlp(
    keyword: str,
    max_results: int,
) -> list[str]:
    """
    Search YouTube via yt-dlp's keyword search.

    Note: reliable date-range filtering is not supported on this path.
    yt-dlp's keyword search returns a limited slice of YouTube search results,
    and its date-related options do not make YouTube apply an exact server-side
    published-after / published-before filter for arbitrary ranges.
    To get reliable date-range filtering, use the Google YouTube Data API instead.
    """
    get_rate_limiter("youtube").acquire()
    yt_dlp = _get_yt_dlp()
    search_url = f"ytsearch{max_results}:{keyword}"

    ydl_opts: dict[str, Any] = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_url, download=False)
    except Exception:
        logger.exception(
            "Failed to search YouTube with yt-dlp for keyword: %s", keyword
        )
        return []

    entries = info.get("entries") or [] if info else []
    video_ids: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        vid_id = entry.get("id") or entry.get("url") or ""
        if vid_id:
            video_ids.append(str(vid_id))

    logger.info("Keyword '%s': found %d videos via yt-dlp", keyword, len(video_ids))
    return video_ids


# ── Keyword search ────────────────────────────────────────────


@task(
    name="search_videos_by_keyword_google_or_yt_dlp",
    retries=3,
    retry_delay_seconds=[10, 30, 90],
    retry_jitter_factor=0.2,
    retry_condition_fn=_should_retry_youtube,
)
def search_videos_by_keyword_google_or_yt_dlp(
    keyword: str,
    max_results: int | None = None,
    published_after: datetime | None = None,
    published_before: datetime | None = None,
) -> list[str]:
    """
    Search YouTube for videos matching a keyword.
    Returns a list of video IDs.

    Args:
        published_after: Filter videos published on or after this timestamp.
        published_before: Filter videos published on or before this timestamp.

    When a date window is provided, the Google YouTube Data API is used so
    filtering happens server-side. Otherwise, yt-dlp is used as the fast
    default path.
    """
    if max_results is None:
        max_results = MAX_VIDEOS_PER_KEYWORD

    if published_after or published_before:
        if not YOUTUBE_API_KEY:
            raise RuntimeError(
                "Date-bounded keyword search requires YOUTUBE_API_KEY "
                "(or GOOGLE_API_KEY) with YouTube Data API enabled"
            )
        try:
            video_ids = _search_videos_by_keyword_google_api(
                keyword,
                max_results,
                published_after=published_after,
                published_before=published_before,
            )
            logger.info(
                "Keyword '%s': found %d videos via YouTube Data API",
                keyword,
                len(video_ids),
            )
            return video_ids
        except httpx.HTTPStatusError as exc:
            logger.exception(
                "YouTube Data API search failed for keyword: %s",
                keyword,
            )
            raise RuntimeError(
                "Date-bounded keyword search failed. Ensure YOUTUBE_API_KEY is valid "
                "and has YouTube Data API v3 enabled."
            ) from exc
        except httpx.HTTPError as exc:
            logger.exception(
                "YouTube Data API search failed for keyword: %s",
                keyword,
            )
            raise RuntimeError(
                "Date-bounded keyword search failed due to a YouTube Data API request error."
            ) from exc

    return _search_videos_by_keyword_yt_dlp(keyword, max_results)


# ── Creator / Channel video fetch ─────────────────────────────


def _channel_videos_url(channel_url: str) -> str:
    """Ensure URL points to /videos tab."""
    url = channel_url.rstrip("/")
    if url.endswith("/videos"):
        return url
    return f"{url}/videos"


@task(
    name="fetch_creator_videos",
    retries=3,
    retry_delay_seconds=[10, 30, 90],
    retry_jitter_factor=0.2,
    retry_condition_fn=_should_retry_youtube,
)
def fetch_creator_videos(
    channel_id: str | None = None,
    channel_url: str | None = None,
    months_back: int = 1,
    max_results: int | None = None,
) -> list[str]:
    """
    Fetch recent video IDs from a YouTube channel.
    Filters to videos published within `months_back` months.
    """
    if max_results is None:
        max_results = MAX_VIDEOS_PER_CREATOR

    get_rate_limiter("youtube").acquire()
    yt_dlp = _get_yt_dlp()

    # Build the channel URL
    if channel_url:
        url = _channel_videos_url(channel_url)
    elif channel_id:
        url = f"https://www.youtube.com/channel/{channel_id}/videos"
    else:
        logger.warning("No channel_id or channel_url provided")
        return []

    ydl_opts: dict[str, Any] = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "playlistend": max_results,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        logger.exception("Failed to fetch videos from channel: %s", url)
        return []

    entries = info.get("entries") or [] if info else []
    cutoff = datetime.now(timezone.utc) - timedelta(days=months_back * 30)

    video_ids: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        vid_id = entry.get("id") or entry.get("url") or ""
        if not vid_id:
            continue
        # If upload date available, filter by cutoff
        upload_date = _parse_upload_date(entry.get("upload_date"))
        if upload_date and upload_date < cutoff:
            continue
        video_ids.append(str(vid_id))

    logger.info("Channel %s: found %d recent videos", url, len(video_ids))
    return video_ids


# ── Video metadata extraction ─────────────────────────────────


@task(
    name="fetch_video_metadata",
    retries=3,
    retry_delay_seconds=[10, 30, 90],
    retry_jitter_factor=0.2,
    retry_condition_fn=_should_retry_youtube,
)
def fetch_video_metadata(video_id: str) -> VideoData | None:
    """
    Fetch full video metadata using yt-dlp.
    Returns a VideoData model or None on failure.
    """
    get_rate_limiter("youtube").acquire()
    yt_dlp = _get_yt_dlp()
    url = f"https://www.youtube.com/watch?v={video_id}"

    ydl_opts: dict[str, Any] = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        logger.exception("Failed to fetch metadata for video: %s", video_id)
        return None

    if not isinstance(info, dict):
        return None

    video = VideoData(
        video_id=str(info.get("id") or video_id),
        title=info.get("title") or "",
        description=info.get("description") or "",
        channel_title=info.get("channel") or info.get("uploader") or "",
        channel_id=info.get("channel_id") or "",
        published_at=_parse_upload_date(info.get("upload_date")),
        view_count=int(info.get("view_count") or 0),
        like_count=int(info.get("like_count") or 0),
        comment_count=int(info.get("comment_count") or 0),
        duration_seconds=int(info.get("duration") or 0),
        tags=info.get("tags") or [],
    )
    logger.info(
        "Fetched metadata for video %s: '%s' by %s",
        video_id,
        video.title,
        video.channel_title,
    )
    return video


# ── Transcript fetching ──────────────────────────────────────


def _normalize_whitespace(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _is_plausible_transcript(text: str) -> bool:
    """Check if text looks like an actual transcript (not HTML/JS)."""
    text = text.strip()
    if not text or len(text) < 200:
        return False
    suspicious = ["window.ytcfg", "<!doctype html", "<html", "<script"]
    lower = text[:5000].lower()
    if any(m in lower for m in suspicious):
        return False
    letters = sum(1 for ch in text if ch.isalpha())
    spaces = sum(1 for ch in text if ch.isspace())
    ratio = (letters + spaces) / max(1, len(text))
    return ratio > 0.65


def _strip_vtt(vtt: str) -> str:
    """Strip VTT formatting to plain text."""
    if not vtt.lstrip().startswith("WEBVTT"):
        return ""
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = unescape(line)
        lines.append(line)
    return _normalize_whitespace(" ".join(lines))


def _select_transcript_yta(video_id: str):
    # We select the best youtube-transcript-api transcript once so both callers can
    # reuse the same language/fallback logic. One caller flattens it to plain text
    # for stored transcripts, while the idea-graph pipeline needs the original
    # timestamped parts to preserve start/end offsets for evidence grounding.
    """Select the best transcript candidate via youtube-transcript-api."""
    get_rate_limiter("youtube").acquire()
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
        from youtube_transcript_api._errors import (  # type: ignore
            NoTranscriptFound,
            TranscriptsDisabled,
            VideoUnavailable,
        )
    except ImportError:
        return None, "yta:import_error"

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        chosen = None
        status = "yta:none"

        for t in transcript_list:
            if getattr(t, "language_code", "").startswith("en") and not getattr(
                t, "is_generated", False
            ):
                chosen, status = t, "yta:en:manual"
                break

        if chosen is None:
            for t in transcript_list:
                if getattr(t, "language_code", "").startswith("en"):
                    chosen, status = t, "yta:en:generated"
                    break

        if chosen is None:
            for t in transcript_list:
                try:
                    chosen = t.translate("en")
                    status = f"yta:{getattr(t, 'language_code', '?')}:translated_en"
                    break
                except Exception:
                    continue

        if chosen is None:
            for t in transcript_list:
                chosen = t
                status = f"yta:{getattr(t, 'language_code', '?')}:fallback"
                break

        if chosen is None:
            return None, status

        return chosen, status
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as e:
        return None, f"yta:{type(e).__name__}"
    except Exception as e:
        return None, f"yta:error:{type(e).__name__}"


def _fetch_transcript_yta(video_id: str) -> tuple[str | None, str]:
    """Fetch transcript via youtube-transcript-api."""
    chosen, status = _select_transcript_yta(video_id)
    if chosen is None:
        return None, status

    try:
        parts = chosen.fetch()
        text = " ".join(p.get("text", "") for p in parts if p.get("text"))
        text = _normalize_whitespace(text)

        if text and _is_plausible_transcript(text):
            return text, status
        return None, f"{status}:invalid"
    except Exception as e:
        return None, f"{status}:error:{type(e).__name__}"


def fetch_transcript_segments(video_id: str) -> tuple[list[dict[str, Any]] | None, str]:
    """Fetch transcript segments with timestamps for idea-graph grounding."""
    chosen, status = _select_transcript_yta(video_id)
    if chosen is None:
        return None, status

    try:
        parts = chosen.fetch()
        segments = []
        for part in parts:
            text = _normalize_whitespace(part.get("text", ""))
            if not text:
                continue
            start = float(part.get("start", 0))
            duration = float(part.get("duration", 0))
            segments.append(
                {
                    "text": text,
                    "start_sec": start,
                    "end_sec": start + max(duration, 0),
                }
            )
        if not segments:
            return None, f"{status}:no_segments"
        return segments, status
    except Exception as e:
        return None, f"{status}:error:{type(e).__name__}"


def _fetch_transcript_ytdlp(video_id: str) -> tuple[str | None, str]:
    """Fallback: fetch transcript via yt-dlp subtitle extraction."""
    get_rate_limiter("youtube").acquire()
    yt_dlp = _get_yt_dlp()
    import urllib.request

    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts: dict[str, Any] = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitlesformat": "vtt",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return None, f"ytdlp:error:{type(e).__name__}"

    # Try manual subs first, then auto
    for subs_key in ("subtitles", "automatic_captions"):
        subs = info.get(subs_key) or {}
        for lang in ("en", "en-US", "en-GB"):
            fmts = subs.get(lang)
            if not isinstance(fmts, list):
                continue
            for fmt in fmts:
                if fmt.get("ext") == "vtt" and fmt.get("url"):
                    try:
                        req = urllib.request.Request(
                            fmt["url"],
                            headers={"User-Agent": "Mozilla/5.0"},
                        )
                        with urllib.request.urlopen(req, timeout=20) as resp:
                            raw = resp.read().decode("utf-8", errors="replace")
                        text = _strip_vtt(raw)
                        if text and _is_plausible_transcript(text):
                            return text, f"ytdlp:{lang}:vtt"
                    except Exception:
                        continue

    return None, "ytdlp:no_subtitles"


@task(
    name="fetch_transcript",
    retries=3,
    retry_delay_seconds=[10, 30, 90],
    retry_jitter_factor=0.2,
    retry_condition_fn=_should_retry_youtube,
)
def fetch_transcript(video_id: str) -> tuple[str | None, str]:
    """
    Fetch the best available transcript for a video.
    Tries youtube-transcript-api first, then falls back to yt-dlp.
    """
    text, status = _fetch_transcript_yta(video_id)
    if text is not None:
        logger.info("Transcript for %s: %s (%d chars)", video_id, status, len(text))
        return text, status

    text, status = _fetch_transcript_ytdlp(video_id)
    if text is not None:
        logger.info("Transcript for %s: %s (%d chars)", video_id, status, len(text))
    else:
        logger.warning("No transcript found for %s: %s", video_id, status)
    return text, status
